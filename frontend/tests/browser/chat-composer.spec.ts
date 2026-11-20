import { test, expect, type Page } from "@playwright/test";

type Turn = { turn_id: string; message: string };
const conversation = "a0000000-0000-4000-8000-000000000001";
const documentId = "d0000000-0000-4000-8000-000000000001";
const sourceDocument = {
  id: documentId,
  filename: "research.pdf",
  status: "ready",
  pages: 2,
  chunks: 2,
  page_metadata: [],
  created_at: "2026-11-20T00:00:00Z",
};
const response = {
  conversation_id: conversation,
  kind: "answer",
  status: "partial",
  answer_status: "partial",
  answer:
    "**Supported finding:** the result is 42 [S1].\n\n```ts\nconst result = 42;\n```\n\nThe document does not provide a telephone number.",
  citations: [
    {
      ref: "S1",
      document: sourceDocument.filename,
      document_id: documentId,
      chunk_id: 42,
      page: 2,
    },
  ],
};

async function fixture(page: Page) {
  const submitted: Turn[] = [];
  const messages: {
    id: number;
    role: string;
    content: string;
    turn_id?: string;
    answer_metadata?: typeof response;
  }[] = [];
  let uploadCount = 0;
  await page.route("**/api/v2/**", async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    let result: unknown = [];
    let status = 200;
    if (pathname.endsWith("/auth/me"))
      result = {
        id: "user",
        display_name: "Avery",
        email: "avery@example.test",
        role: "user",
        status: "active",
      };
    else if (pathname.endsWith("/documents") && request.method() === "POST") {
      uploadCount++;
      result = {
        id: documentId,
        document_id: documentId,
        filename: sourceDocument.filename,
        status: "queued",
        job_id: "job",
      };
      status = 202;
    } else if (pathname.endsWith("/documents")) result = [sourceDocument];
    else if (pathname.endsWith(`/documents/${documentId}`))
      result = sourceDocument;
    else if (
      pathname.endsWith("/conversations") &&
      request.method() === "POST"
    ) {
      result = {
        conversation_id: conversation,
        title: "Fixture chat",
        message_count: 0,
      };
      status = 201;
    } else if (pathname.endsWith("/conversations")) result = [];
    else if (pathname.endsWith(`/conversations/${conversation}`))
      result = { conversation_id: conversation, messages };
    else if (pathname.endsWith("/chat")) {
      const body = request.postDataJSON() as Turn;
      submitted.push(body);
      const id = messages.length + 1;
      messages.push(
        { id, role: "user", content: body.message, turn_id: body.turn_id },
        {
          id: id + 1,
          role: "assistant",
          content: response.answer,
          turn_id: body.turn_id,
          answer_metadata: response,
        },
      );
      result = response;
    } else if (pathname.includes("/turns/")) {
      result = messages.length ? response : { state: "pending" };
      status = messages.length ? 200 : 202;
    }
    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(result),
    });
  });
  return { submitted, uploads: () => uploadCount };
}

test.describe("Chat composer UI fixtures — no DB or provider", () => {
  test("Enter sends once, Shift+Enter keeps a newline and completed history remains authoritative", async ({
    page,
  }) => {
    const state = await fixture(page);
    await page.goto("/chat");
    const input = page.getByLabel("Your message", { exact: true });
    await input.fill("First line");
    await input.press("Shift+Enter");
    await input.press("End");
    await input.type("Second line");
    expect(state.submitted).toHaveLength(0);
    await input.press("Enter");
    await expect(page.getByText("partial", { exact: true })).toBeVisible();
    expect(state.submitted).toHaveLength(1);
    expect(state.submitted[0].message).toBe("First line\nSecond line");
    await expect(page.getByRole("log").locator("article")).toHaveCount(2);
    await page.reload();
    await expect(page.getByText("partial", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("link", { name: /Open citation S1/ }),
    ).toHaveAttribute("href", `/api/v2/documents/${documentId}/file#page=2`);
    expect(state.submitted).toHaveLength(1);
  });

  test("Markdown/code copy and source citations fit the mobile and desktop composer", async ({
    page,
    context,
  }) => {
    await fixture(page);
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.goto("/chat");
    await page
      .getByLabel("Your message", { exact: true })
      .fill("Show a supported finding");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(
      page.locator("strong").filter({ hasText: "Supported finding:" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Copy code", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Copy code", exact: true }).click();
    await expect
      .poll(() => page.evaluate(() => navigator.clipboard.readText()))
      .toBe("const result = 42;");
    await expect(
      page.getByRole("button", { name: "Copy response", exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    const log = page.getByRole("log");
    // Copying code focuses a button midway through the response and may scroll
    // that button into view. A tall article can extend beyond the viewport's
    // bounds while correctly clipped by the message scroll container.
    const layout = await log.evaluate((element) => ({
      overflowY: getComputedStyle(element).overflowY,
      top: element.getBoundingClientRect().top,
      bottom: element.getBoundingClientRect().bottom,
      clientHeight: element.clientHeight,
      scrollHeight: element.scrollHeight,
      scrollTop: element.scrollTop,
      documentHeight: element.ownerDocument.documentElement.scrollHeight,
      viewportHeight: element.ownerDocument.defaultView?.innerHeight ?? 0,
    }));
    const composer = await page.locator("form").boundingBox();
    expect(["auto", "scroll"]).toContain(layout.overflowY);
    expect(layout.clientHeight).toBeGreaterThan(0);
    expect(layout.documentHeight).toBeLessThanOrEqual(
      layout.viewportHeight + 1,
    );
    expect(composer).not.toBeNull();
    expect(layout.bottom).toBeLessThanOrEqual(composer!.y + 1);
    await test.info().attach("chat-layout-after-code-focus", {
      body: JSON.stringify({ ...layout, composer }, null, 2),
      contentType: "application/json",
    });
    // The final answer must also be fully reachable above the composer once
    // the user scrolls to the end of the conversation.
    await log.evaluate((element) => {
      element.scrollTo({ top: element.scrollHeight, behavior: "instant" });
    });
    await expect
      .poll(async () => {
        const answer = await log.locator("article").last().boundingBox();
        const composer = await page.locator("form").boundingBox();
        return Boolean(
          answer && composer && answer.y + answer.height <= composer.y + 1,
        );
      })
      .toBe(true);
  });

  test("Source menu inserts an honest filename request; uploads show actual processing until ready", async ({
    page,
  }) => {
    const state = await fixture(page);
    await page.goto("/chat");
    await page.getByRole("button", { name: "Browse document sources" }).click();
    await page
      .getByRole("menuitem", { name: "Ask about research.pdf", exact: true })
      .click();
    await expect(page.getByLabel("Your message", { exact: true })).toHaveValue(
      "In research.pdf, ",
    );
    expect(state.submitted).toHaveLength(0);
    await page.getByLabel("Choose chat PDF", { exact: true }).setInputFiles({
      name: "bad.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("not a PDF"),
    });
    await expect(page.locator("main").getByRole("alert")).toContainText(
      "non-empty PDF of 25 MB or less",
    );
    expect(state.uploads()).toBe(0);
    await page.getByLabel("Choose chat PDF", { exact: true }).setInputFiles({
      name: "research.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.7\nFixture only"),
    });
    await expect(page.getByText("Processing", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Send", exact: true }),
    ).toBeDisabled();
    await expect(page.getByText("Ready", { exact: true })).toBeVisible({
      timeout: 8000,
    });
    await expect(
      page.getByRole("button", { name: "Send", exact: true }),
    ).toBeEnabled();
    expect(state.uploads()).toBe(1);
  });
});
