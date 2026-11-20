import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
test("redesigned UI reopens retained real education and partial results with original pages", async ({
  page,
  context,
}) => {
  test.skip(
    process.env.RAG_UI_RETAINED !== "1",
    "Explicit read-only scratch regression fixture",
  );
  const auth = JSON.parse(
    fs.readFileSync("/private/tmp/rag-ui-retained-session.json", "utf8"),
  );
  await context.addCookies([
    {
      name: "rag_session",
      value: auth.token,
      url: "http://127.0.0.1:3000",
      httpOnly: true,
      sameSite: "Strict",
    },
    {
      name: "rag_csrf",
      value: auth.csrf,
      url: "http://127.0.0.1:3000",
      sameSite: "Strict",
    },
  ]);
  const cases = JSON.parse(
    fs.readFileSync(
      path.resolve(
        "../v2_evidence/browser-final-20261120/live-01/verified-browser-results.json",
      ),
      "utf8",
    ),
  );
  let posts = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/api/v2/chat"))
      posts++;
  });
  for (let i = 0; i < cases.length; i++) {
    const item = cases[i];
    await page.goto(`/chat?conversation=${item.conversation_id}`);
    const log = page.getByRole("log");
    await expect(log).toContainText(i === 2 ? "partial" : "answered");
    await expect(log).toContainText(i === 2 ? "40" : "Bachelor of Engineering");
    const citation = log.getByRole("link", { name: /Open citation/ }).first();
    await expect(citation).toHaveAttribute(
      "href",
      item.verified_navigation_target,
    );
    await page.reload();
    await expect(log).toContainText(i === 2 ? "partial" : "answered");
    await expect(citation).toBeVisible();
    const recovered = await page.request.get(
      `/api/v2/conversations/${item.conversation_id}/turns/${item.turn_id}`,
    );
    expect(recovered.status()).toBe(200);
    const result = await recovered.json();
    expect(result.answer_status).toBe(i === 2 ? "partial" : "answered");
    expect(result.citations[0].page).toBe(i === 2 ? 1 : 2);
    expect(result.citations[0].document_id).toBe(
      "567ee27b-074a-4d09-9af5-5dd796b8667e",
    );
  }
  expect(posts).toBe(0);
  fs.writeFileSync(
    path.resolve(
      "../v2_evidence/ui-grey-20261120/retained-browser-result.json",
    ),
    JSON.stringify(
      {
        status: "PASS",
        cases: 3,
        statuses: ["answered", "answered", "partial"],
        original_pages: [2, 2, 1],
        new_chat_POSTs: posts,
        original_model_results: "preserved; not regenerated",
      },
      null,
      2,
    ),
    { flag: "wx", mode: 0o600 },
  );
});
