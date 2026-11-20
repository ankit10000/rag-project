import { test, expect } from "@playwright/test";
import path from "node:path";
import { writeFile } from "node:fs/promises";
test.use({ channel: "chromium" });

/** Explicitly enabled synthetic functional integration, never formal evaluation.
 * Requires the separately instrumented scratch-only API + two worker harness,
 * a fresh run identity and a shared 12-call provider cap before this file runs.
 * Do not rerun the same harness identity after a provider result or interruption.
 */
test("live core: image-only OCR, real workers/RAG, citations, memory, tenant denial and deletion", async ({
  page,
}, info) => {
  test.skip(
    process.env.RAG_V2_LIVE_BROWSER !== "1",
    "Requires explicitly enabled bounded live synthetic harness.",
  );
  test.setTimeout(240_000);
  const run = process.env.RAG_V2_BROWSER_RUN_ID;
  expect(run, "A fresh instrumented harness identity is mandatory").toMatch(
    /^v2-browser-aster-/,
  );
  const owner = `${run}@example.test`,
    other = `${run}-other@example.test`;
  const password = "Synthetic-browser-password-263!";
  const evidence: Record<string, unknown> = {
    run_id: run,
    scope: "SYNTHETIC_FUNCTIONAL_BROWSER_ONLY",
    answers: [],
  };
  const identity = await page.request.get("/api/v2/health");
  expect(
    identity.headers()["x-rag-browser-run-id"],
    "Gateway must target the instrumented bounded scratch harness",
  ).toBe(run);
  async function register(email: string) {
    await page.goto("/register");
    await page.getByLabel("Name", { exact: true }).fill("Aster Browser Tester");
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page
      .getByRole("button", { name: "Create account", exact: true })
      .click();
    await expect(page.getByRole("status")).toContainText("account is ready");
  }
  async function login(email: string) {
    await page.goto("/login");
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Hello, Aster Browser Tester." }),
    ).toBeVisible();
  }
  async function logout() {
    if (test.info().project.name.startsWith("mobile"))
      await page.getByRole("button", { name: "Toggle navigation" }).click();
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login$/);
  }
  async function question(text: string) {
    await page.getByLabel("Your message").fill(text);
    const promise = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/v2/chat") &&
        response.request().method() === "POST",
      { timeout: 120_000 },
    );
    await page.getByRole("button", { name: "Send", exact: true }).click();
    const response = await promise;
    expect(response.status()).toBe(200);
    const answer = await response.json();
    (evidence.answers as unknown[]).push({ query: text, response: answer });
    return answer;
  }
  try {
    await register(owner);
    await login(owner);
    await page.goto("/documents");
    const filename = `${run}.pdf`;
    const uploaded = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/v2/documents") &&
        response.request().method() === "POST",
    );
    await page.getByLabel("Choose PDF", { exact: true }).setInputFiles({
      name: filename,
      mimeType: "application/pdf",
      buffer: await (
        await import("node:fs/promises")
      ).readFile(path.join(process.cwd(), "tests/fixtures/aster-scan.pdf")),
    });
    const upload = await (await uploaded).json();
    evidence.upload = upload;
    const did: string = upload.document_id;
    expect(did).toBeTruthy();
    await expect
      .poll(
        async () => {
          let response;
          try {
            response = await page.request.get(`/api/v2/documents/${did}`);
          } catch (error) {
            // GET is idempotent. A bounded polling window may tolerate an
            // observed transient transport reset, never duplicate a chat POST.
            if (
              error instanceof Error &&
              /ECONNRESET|ECONNREFUSED|socket hang up/.test(error.message)
            )
              return "transport_retry";
            throw error;
          }
          expect(response.status()).toBe(200);
          return (await response.json()).status;
        },
        { timeout: 100_000, intervals: [1000, 2000, 4000] },
      )
      .toBe("ready");
    const detail = await (
      await page.request.get(`/api/v2/documents/${did}`)
    ).json();
    evidence.document = detail;
    expect(detail.pages).toBe(1);
    expect(detail.chunks).toBe(1);
    expect(detail.page_metadata[0].method).toBe("pymupdf-tesseract-fast-4.1.0");
    await page.goto(`/documents/${did}`);
    await expect(
      page.getByRole("heading", { name: filename, exact: true }),
    ).toBeVisible();
    expect(
      (await page.request.get(`/api/v2/documents/${did}/file`)).status(),
    ).toBe(200);
    await page.goto("/chat");
    const first = await question(
      "I prefer chamomile tea. According to the Aster Harbor visitor policy, how many credits does a day pass cost and for how many days is it valid?",
    );
    expect(first.answer).toMatch(/83/);
    expect(first.answer).toMatch(/17/);
    expect(first.answer_status ?? first.status).toBe("answered");
    expect(first.retrieval_status).toBe("ok");
    expect(first.citations.length).toBeGreaterThan(0);
    for (const citation of first.citations) {
      expect(citation.document_id).toBe(did);
      expect(citation.page).toBe(1);
    }
    const cid: string = first.conversation_id;
    evidence.conversation_id = cid;
    const chip = page.getByRole("link", { name: /Open citation S1/ }).first();
    await expect(chip).toHaveAttribute(
      "href",
      `/api/v2/documents/${did}/file#page=1`,
    );
    const sourceNavigation = page.context().waitForEvent("request", {
      predicate: (request) =>
        request.url().endsWith(`/api/v2/documents/${did}/file`),
    });
    const popupPromise = page.waitForEvent("popup");
    await chip.click();
    const popup = await popupPromise;
    expect((await sourceNavigation).url()).toContain(
      `/api/v2/documents/${did}/file`,
    );
    await popup.close();
    const second = await question(
      "For my Aster Harbor visit, remind me how many days the day pass lasts. My preferred drink is chamomile tea.",
    );
    expect(second.answer).toMatch(/17/);
    // The canonical committed response can arrive before post-answer memory
    // work. Verify the actual provenance below rather than a transient counter.
    const memories = await (
      await page.request.get(`/api/v2/memories?conversation_id=${cid}`)
    ).json();
    evidence.memories = memories;
    const memory = memories
      .flatMap(
        (entry: {
          memories: {
            memory_id: number;
            memory: string;
            source_message_ids: number[];
          }[];
        }) => entry.memories,
      )
      .find((entry: { memory: string }) => /chamomile/i.test(entry.memory));
    expect(memory).toBeTruthy();
    expect(memory.source_message_ids.length).toBeGreaterThan(0);
    const sourcePath = `/api/v2/conversations/${cid}/memories/${memory.memory_id}/sources`;
    const sources = await page.request.get(sourcePath);
    expect(sources.status()).toBe(200);
    evidence.memory_sources = await sources.json();
    expect(
      (evidence.memory_sources as { role: string }[]).some(
        (source) => source.role === "user",
      ),
    ).toBe(true);
    const third = await question("What drink do I prefer?");
    expect(third.answer).toMatch(/chamomile/i);
    await page.goto(`/chat?conversation=${cid}`);
    await expect(page.getByRole("log")).toContainText("83");
    await expect(
      page.getByRole("log").getByText("answered", { exact: true }).first(),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: /Open citation S1/ }).first(),
    ).toHaveAttribute("href", `/api/v2/documents/${did}/file#page=1`);
    await page.reload();
    await expect(
      page.getByRole("link", { name: /Open citation S1/ }).first(),
    ).toBeVisible();
    await page.screenshot({
      path: info.outputPath("live-grounded-chat.png"),
      fullPage: true,
    });
    await logout();
    await register(other);
    await login(other);
    for (const resource of [
      `/api/v2/documents/${did}`,
      `/api/v2/documents/${did}/file`,
      `/api/v2/conversations/${cid}`,
      sourcePath,
      `/api/v2/jobs/${upload.job_id}`,
    ])
      expect((await page.request.get(resource)).status(), resource).toBe(404);
    await logout();
    await login(owner);
    await page.goto("/documents");
    await page
      .getByRole("button", { name: `Actions for ${filename}`, exact: true })
      .click();
    await page
      .getByRole("menuitem", { name: `Delete ${filename}`, exact: true })
      .click();
    const documentDeleted = page.waitForResponse(
      (response) =>
        response.request().method() === "DELETE" &&
        response.url().endsWith(`/api/v2/documents/${did}`),
    );
    await page
      .getByRole("alertdialog", { name: "Delete document?" })
      .getByRole("button", { name: "Delete document", exact: true })
      .click();
    expect((await documentDeleted).status()).toBe(200);
    await expect(
      page.getByRole("link", { name: filename, exact: true }),
    ).toHaveCount(0);
    await page.goto("/conversations");
    await page
      .getByRole("button", { name: /Delete I prefer chamomile tea/ })
      .click();
    await page
      .getByRole("alertdialog", { name: "Delete conversation?" })
      .getByRole("button", { name: "Delete conversation", exact: true })
      .click();
    await expect
      .poll(async () =>
        (await page.request.get(`/api/v2/conversations/${cid}`)).status(),
      )
      .toBe(404);
    await new Promise((resolve) => setTimeout(resolve, 1500));
    expect((await page.request.get(`/api/v2/documents/${did}`)).status()).toBe(
      404,
    );
    expect((await page.request.get(sourcePath)).status()).toBe(404);
    evidence.status = "PASS";
    await logout();
  } catch (error) {
    evidence.status = "FAIL";
    // Playwright's transport call log can include session cookies. Keep only
    // the first error line in publishable evidence; raw traces stay private.
    const safeMessage =
      error instanceof Error ? error.message.split("\n")[0] : "Unknown failure";
    evidence.failure = safeMessage;
    throw new Error(safeMessage);
  } finally {
    const evidencePath = info.outputPath("live-browser-evidence.json");
    await writeFile(evidencePath, JSON.stringify(evidence, null, 2), {
      flag: "wx",
      mode: 0o600,
    });
    await info.attach("synthetic-live-browser-evidence", {
      path: evidencePath,
      contentType: "application/json",
    });
  }
});
