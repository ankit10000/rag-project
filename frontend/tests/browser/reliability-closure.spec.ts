import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
test("retained education and partial failures, disconnected commit, retry and refreshed metadata", async ({
  page,
  context,
}) => {
  test.skip(
    process.env.RAG_BROWSER_CLOSURE !== "1",
    "Explicit scratch/provider test only",
  );
  test.setTimeout(240_000);
  const secret = JSON.parse(
    fs.readFileSync("/private/tmp/rag-browser-closure-session.json", "utf8"),
  );
  await context.addCookies([
    {
      name: "rag_session",
      value: secret.token,
      url: "http://127.0.0.1:3000",
      httpOnly: true,
      sameSite: "Strict",
    },
    {
      name: "rag_csrf",
      value: secret.csrf,
      url: "http://127.0.0.1:3000",
      sameSite: "Strict",
    },
  ]);
  const output = path.resolve("../v2_evidence/browser-final-20261120/live-01");
  const results: unknown[] = [];
  const questions = [
    "What is the qualifications of Morgan Vale?",
    "In Browser_Check_Morgan_Vale.pdf, what is listed under EDUCATION? Please give the degree, institute and study dates.",
    "According to Morgan Vale’s resume, how did the Atlas project change report preparation time? Also, what telephone number is listed for Morgan?",
  ];
  for (let i = 0; i < 3; i++) {
    let disconnect: {
      transport: string;
      disconnected_before_POST_response: boolean;
    } | null = null;
    if (i < 2) {
      const historical = JSON.parse(
        fs.readFileSync(
          path.resolve(
            "../v2_evidence/browser-confirmation-20261120/live-01/verified-browser-results.json",
          ),
          "utf8",
        ),
      );
      if (i === 1) {
        disconnect = historical[1].disconnect;
        expect(disconnect?.transport).toBe("AbortError");
        expect(disconnect?.disconnected_before_POST_response).toBe(true);
      }
      await page.goto(`/chat?conversation=${historical[i].conversation_id}`);
    } else {
      await page.goto("/chat");
      await page.getByLabel("Your message", { exact: true }).fill(questions[i]);
      await page.getByRole("button", { name: "Send", exact: true }).click();
    }
    const assistant = page
      .getByRole("log")
      .locator("article")
      .filter({ has: page.getByRole("heading", { name: "RAG", exact: true }) });
    await expect(assistant).toHaveCount(1, { timeout: 100_000 });
    await expect(assistant).toContainText(i === 2 ? "partial" : "answered");
    if (i < 2) {
      for (const fact of [
        "Bachelor of Engineering",
        "Computer Engineering",
        "Sample Institute of Technology",
        "2016",
        "2020",
      ])
        await expect(assistant).toContainText(fact);
      await expect(
        assistant.getByRole("link", { name: /Open citation.*p\. 2/ }),
      ).toBeVisible();
    } else {
      await expect(assistant).toContainText("40");
      await expect(assistant).toContainText("12");
      await expect(assistant).toContainText(/telephone|phone/);
    }
    const cid = new URL(page.url()).searchParams.get("conversation")!;
    const answer = await assistant.innerText();
    const history = await page.evaluate(
      async (id) => await (await fetch(`/api/v2/conversations/${id}`)).json(),
      cid,
    );
    const turn = history.messages[1].turn_id;
    await page.reload();
    await expect(assistant).toHaveCount(1);
    await expect(assistant).toContainText(i === 2 ? "partial" : "answered");
    const link = assistant.getByRole("link", { name: /Open citation/ }).first();
    await expect(link).toBeVisible();
    const href = await link.getAttribute("href");
    expect(href).toContain(
      "/documents/567ee27b-074a-4d09-9af5-5dd796b8667e/file#page=",
    );
    if (i < 2) expect(href).toContain("#page=2");
    const file = await page.request.get(href!.split("#")[0]);
    expect(file.status()).toBe(200);
    expect(file.headers()["content-type"]).toContain("application/pdf");
    const navigated = context.waitForEvent("request", {
      predicate: (r) => r.url().endsWith(href!.split("#")[0]),
    });
    const opened = page.waitForEvent("popup");
    await link.click();
    const popup = await opened;
    expect((await navigated).url()).toBe(
      "http://127.0.0.1:3000" + href!.split("#")[0],
    );
    await popup.close();
    const retry = await page.evaluate(
      async ({ cid, turn, message }) => {
        const csrf = decodeURIComponent(
          document.cookie
            .split("; ")
            .find((x) => x.startsWith("rag_csrf="))!
            .split("=")
            .slice(1)
            .join("="),
        );
        const r = await fetch("/api/v2/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          body: JSON.stringify({
            conversation_id: cid,
            turn_id: turn,
            message,
          }),
        });
        return {
          status: r.status,
          answer: (await r.json()).answer,
          history: await (await fetch(`/api/v2/conversations/${cid}`)).json(),
        };
      },
      { cid, turn, message: questions[i] },
    );
    expect(retry.status).toBe(200);
    expect(retry.history.messages).toHaveLength(2);
    expect(retry.answer).toBe(history.messages[1].content);
    await page.screenshot({
      path: path.join(output, `verified-browser-${i + 1}.png`),
    });
    results.push({
      question: questions[i],
      conversation_id: cid,
      turn_id: turn,
      answer,
      history: retry.history,
      disconnect,
      pdf_http_status: file.status(),
      verified_navigation_target: href,
      retry_status: retry.status,
      retry_message_count: retry.history.messages.length,
      generation_run:
        i < 2
          ? "browser-confirmation-20261120/live-01"
          : "browser-final-20261120/live-01",
    });
    fs.writeFileSync(
      path.join(output, "verified-browser-results.json"),
      JSON.stringify(results, null, 2),
      { mode: 0o600 },
    );
  }
});

test("ordinary two-worker preview reopens all three verified turns without generation", async ({
  page,
  context,
}) => {
  test.skip(
    process.env.RAG_BROWSER_READONLY !== "1",
    "Explicit scratch-only read verification",
  );
  const fixture = JSON.parse(
    fs.readFileSync("/private/tmp/rag-browser-closure-session.json", "utf8"),
  );
  await context.addCookies([
    {
      name: "rag_session",
      value: fixture.token,
      url: "http://127.0.0.1:3000",
      httpOnly: true,
      sameSite: "Strict",
    },
    {
      name: "rag_csrf",
      value: fixture.csrf,
      url: "http://127.0.0.1:3000",
      sameSite: "Strict",
    },
  ]);
  const output = path.resolve("../v2_evidence/browser-final-20261120/live-01");
  const saved = JSON.parse(
    fs.readFileSync(path.join(output, "verified-browser-results.json"), "utf8"),
  );
  let posts = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/api/v2/chat") && request.method() === "POST")
      posts++;
  });
  for (let i = 0; i < saved.length; i++) {
    await page.goto(`/chat?conversation=${saved[i].conversation_id}`);
    const log = page.getByRole("log");
    await expect(log).toContainText(i === 2 ? "partial" : "answered");
    await expect(log).toContainText(i === 2 ? "40" : "Bachelor of Engineering");
    await expect(
      log.getByRole("link", { name: /Open citation/ }).first(),
    ).toHaveAttribute("href", saved[i].verified_navigation_target);
    await page.reload();
    await expect(log).toContainText(i === 2 ? "partial" : "answered");
    const file = await page.request.get(
      saved[i].verified_navigation_target.split("#")[0],
    );
    expect(file.status()).toBe(200);
  }
  expect(posts).toBe(0);
  fs.writeFileSync(
    path.join(output, "ordinary-preview.json"),
    JSON.stringify(
      {
        status: "PASS",
        cases: 3,
        chat_POSTs: posts,
        mode: "ordinary API, no harness patches",
        statuses: ["answered", "answered", "partial"],
        original_pages: [2, 2, 1],
      },
      null,
      2,
    ),
    { mode: 0o600 },
  );
});
