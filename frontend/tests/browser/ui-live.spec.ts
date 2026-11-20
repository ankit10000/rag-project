import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
test.use({ channel: "chromium" });

test("grey workspace real scratch journey: OCR, Gemini, source/history, two-user isolation and deletion", async ({
  page,
}, info) => {
  test.skip(
    process.env.RAG_GREY_UI_LIVE !== "1",
    "Explicit fresh bounded scratch/provider journey only",
  );
  test.setTimeout(240_000);
  const run = process.env.RAG_GREY_UI_RUN_ID!;
  expect(run).toMatch(/^rag-grey-ui-\d{8}-live-\d{2}$/);
  const output = path.resolve("../v2_evidence/ui-grey-20261120", run);
  const screenshots = path.resolve("evidence", run);
  fs.mkdirSync(screenshots, { recursive: true, mode: 0o700 });
  const evidence: Record<string, unknown> = {
    run,
    scope: "synthetic UI functional integration, not formal acceptance",
    status: "RUNNING",
    screenshots: [],
  };
  const owner = `${run}@example.test`,
    other = `${run}-other@example.test`;
  const password = "Grey-ui-synthetic-password-274!";
  const header = await page.request.get("/api/v2/health");
  expect(header.headers()["x-rag-browser-run-id"]).toBe(run);
  async function register(email: string, name: string) {
    await page.goto("/register");
    await page.getByLabel("Name", { exact: true }).fill(name);
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
    await expect(page).toHaveURL(/\/dashboard$/);
  }
  async function logout() {
    if (info.project.name.startsWith("mobile"))
      await page.getByRole("button", { name: "Toggle navigation" }).click();
    await page.getByRole("button", { name: "Sign out", exact: true }).click();
    await expect(page).toHaveURL(/\/login$/);
  }
  async function screenshot(name: string) {
    await page.screenshot({
      path: path.join(screenshots, name + ".png"),
      fullPage: true,
    });
    (evidence.screenshots as string[]).push(
      `frontend/evidence/${run}/${name}.png`,
    );
  }
  try {
    await register(owner, "Avery Reed");
    await login(owner);
    await page.goto("/documents");
    const filename = `${run}.pdf`;
    const uploadResponse = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/v2/documents") &&
        r.request().method() === "POST",
    );
    await page.getByLabel("Choose PDF", { exact: true }).setInputFiles({
      name: filename,
      mimeType: "application/pdf",
      buffer: fs.readFileSync("tests/fixtures/aster-scan.pdf"),
    });
    const uploaded = await uploadResponse;
    expect(uploaded.status()).toBe(202);
    const upload = await uploaded.json();
    evidence.upload = upload;
    const did: string = upload.document_id;
    await expect
      .poll(
        async () => {
          const response = await page.request.get(`/api/v2/documents/${did}`);
          expect(response.status()).toBe(200);
          return (await response.json()).status;
        },
        { timeout: 100_000, intervals: [500, 1000, 2000] },
      )
      .toBe("ready");
    const document = await (
      await page.request.get(`/api/v2/documents/${did}`)
    ).json();
    evidence.document = document;
    expect(document.pages).toBe(1);
    expect(document.chunks).toBeGreaterThan(0);
    expect(document.page_metadata[0].method).toBe(
      "pymupdf-tesseract-fast-4.1.0",
    );
    await page.reload();
    await screenshot("documents-desktop");
    await page.goto(`/documents/${did}?page=1`);
    await expect(
      page.getByRole("heading", { name: filename, exact: true }),
    ).toBeVisible();
    await expect(
      page.locator('canvas[data-rendered-page="1"]'),
    ).toHaveAttribute("data-render-state", "ready", { timeout: 30_000 });
    const file = await page.request.get(`/api/v2/documents/${did}/file`);
    expect(file.status()).toBe(200);
    expect(file.headers()["content-type"]).toContain("application/pdf");
    await screenshot("pdf-preview-desktop");
    await page.goto("/chat");
    const question =
      "According to the Aster Harbor visitor policy, how many credits does a day pass cost, and for how many days is it valid?";
    await page.getByLabel("Your message", { exact: true }).fill(question);
    await page.getByRole("button", { name: "Send", exact: true }).click();
    const assistant = page
      .getByRole("log")
      .locator("article")
      .filter({ has: page.getByRole("heading", { name: "RAG", exact: true }) });
    await expect(assistant).toContainText("83", { timeout: 90_000 });
    await expect(assistant).toContainText("17");
    await expect(assistant).toContainText("answered");
    const cid = new URL(page.url()).searchParams.get("conversation")!;
    expect(cid).toBeTruthy();
    evidence.conversation_id = cid;
    const history = await (
      await page.request.get(`/api/v2/conversations/${cid}`)
    ).json();
    evidence.history = history;
    expect(history.messages).toHaveLength(2);
    const answer = history.messages[1].answer_metadata;
    expect(answer.answer_status).toBe("answered");
    expect(answer.citations.length).toBeGreaterThan(0);
    for (const citation of answer.citations) {
      expect(citation.document_id).toBe(did);
      expect(citation.page).toBe(1);
    }
    const chip = assistant
      .getByRole("link", { name: /Open citation S1/ })
      .first();
    await expect(chip).toHaveAttribute(
      "href",
      `/api/v2/documents/${did}/file#page=1`,
    );
    const navigation = page.context().waitForEvent("request", {
      predicate: (r) => r.url().endsWith(`/api/v2/documents/${did}/file`),
    });
    const opened = page.waitForEvent("popup");
    await chip.click();
    const popup = await opened;
    expect((await navigation).url()).toContain(`/api/v2/documents/${did}/file`);
    await popup.close();
    await page.reload();
    await expect(assistant).toContainText("answered");
    await expect(chip).toBeVisible();
    await screenshot("chat-desktop");
    await page.goto("/conversations");
    await page
      .locator("main")
      .getByRole("link", { name: question.slice(0, 100), exact: true })
      .click();
    await expect(assistant).toContainText("83");
    await expect(chip).toBeVisible();
    await page.setViewportSize({ width: 768, height: 1024 });
    await screenshot("chat-tablet");
    await page.setViewportSize({ width: 390, height: 844 });
    await screenshot("chat-mobile");
    const fits = await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    );
    expect(fits).toBe(true);
    await page.getByRole("button", { name: "Toggle navigation" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await screenshot("mobile-sidebar");
    await page.keyboard.press("Escape");
    await page.setViewportSize({ width: 1440, height: 1000 });
    await logout();
    await register(other, "Morgan Chen");
    await login(other);
    for (const route of [
      `/api/v2/documents/${did}`,
      `/api/v2/documents/${did}/file`,
      `/api/v2/conversations/${cid}`,
      `/api/v2/jobs/${upload.job_id}`,
    ])
      expect((await page.request.get(route)).status(), route).toBe(404);
    const othersDocs = await (
      await page.request.get("/api/v2/documents")
    ).json();
    expect(othersDocs.some((d: { id: string }) => d.id === did)).toBe(false);
    await page.goto(`/documents/${did}`);
    await expect(page.locator("main").getByRole("alert")).toContainText(
      "unavailable or you do not have access",
    );
    await screenshot("isolated-source-denied");
    await logout();
    await login(owner);
    await page.goto("/documents");
    await page
      .getByRole("button", { name: `Actions for ${filename}`, exact: true })
      .click();
    await page
      .getByRole("menuitem", { name: `Delete ${filename}`, exact: true })
      .click();
    await page
      .getByRole("alertdialog")
      .getByRole("button", { name: "Delete document", exact: true })
      .click();
    await expect
      .poll(async () =>
        (await page.request.get(`/api/v2/documents/${did}`)).status(),
      )
      .toBe(404);
    await page.goto("/conversations");
    await page
      .locator("main")
      .getByRole("button", {
        name: `Delete ${question.slice(0, 100)}`,
        exact: true,
      })
      .click();
    await page
      .getByRole("alertdialog")
      .getByRole("button", { name: "Delete conversation", exact: true })
      .click();
    await expect
      .poll(async () =>
        (await page.request.get(`/api/v2/conversations/${cid}`)).status(),
      )
      .toBe(404);
    expect(
      (await page.request.get(`/api/v2/documents/${did}/file`)).status(),
    ).toBe(404);
    evidence.status = "PASS";
    evidence.isolation = "PASS";
    evidence.deletion = "PASS";
    evidence.preview_sizes = ["desktop1440", "tablet768", "mobile390"];
    await logout();
  } catch (error) {
    evidence.status = "FAIL";
    evidence.failure =
      error instanceof Error ? error.message.split("\n")[0] : "Unknown failure";
    throw error;
  } finally {
    fs.writeFileSync(
      path.join(output, "browser-result.json"),
      JSON.stringify(evidence, null, 2),
      { flag: "wx", mode: 0o600 },
    );
  }
});
