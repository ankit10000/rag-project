import { test, expect } from "@playwright/test";
import type { ChatResponse, Message } from "../../lib/api-types";
import { fixtureDocument, installUIFixture } from "./ui-contract-fixture";

const cid = "a0000000-0000-4000-8000-000000000001";
function answer(status: string, content: string, page?: number): ChatResponse {
  return {
    kind: "answer",
    conversation_id: cid,
    status,
    answer_status: status,
    answer: content,
    citations: page
      ? [
          {
            ref: "S1",
            document_id: fixtureDocument.id,
            document: fixtureDocument.filename,
            page,
            chunk_id: 12,
          },
        ]
      : [],
  };
}

test.describe("Preserved browser reliability contracts — mocked transport only", () => {
  test("answered, partial, abstained and failed retain authoritative metadata on refresh", async ({
    page,
  }) => {
    await installUIFixture(page);
    const cases = [
      answer("answered", "The academic degree is in the source [S1].", 2),
      answer(
        "partial",
        "The project changed from 40 to 12 minutes [S1]. The document does not provide a telephone number.",
        1,
      ),
      answer(
        "abstained",
        "I couldn't find sufficient information in the provided documents.",
      ),
      answer("unverified", "A supported answer could not be verified."),
    ];
    const messages: Message[] = cases.flatMap((response, index) => [
      { id: index * 2 + 1, role: "user", content: `Saved question ${index}` },
      {
        id: index * 2 + 2,
        role: "assistant",
        content: response.answer,
        answer_metadata: response,
      },
    ]);
    await page.route(`**/api/v2/conversations/${cid}`, (route) =>
      route.fulfill({ json: { conversation_id: cid, messages } }),
    );
    await page.goto(`/chat?conversation=${cid}`);
    for (const status of ["answered", "partial", "abstained", "failed"])
      await expect(
        page.getByRole("log").getByText(status, { exact: true }),
      ).toHaveCount(1);
    const chips = page
      .getByRole("log")
      .getByRole("link", { name: /Open citation S1/ });
    await expect(chips).toHaveCount(2);
    await expect(chips.nth(0)).toHaveAttribute(
      "href",
      `/api/v2/documents/${fixtureDocument.id}/file#page=2`,
    );
    await expect(chips.nth(1)).toHaveAttribute(
      "href",
      `/api/v2/documents/${fixtureDocument.id}/file#page=1`,
    );
    await page.reload();
    for (const status of ["answered", "partial", "abstained", "failed"])
      await expect(
        page.getByRole("log").getByText(status, { exact: true }),
      ).toHaveCount(1);
    await expect(chips).toHaveCount(2);
    await expect(page.getByRole("log").locator("article")).toHaveCount(8);
  });
  test("failed POST reconciles its committed result without a second submitted turn", async ({
    page,
  }) => {
    await installUIFixture(page);
    const created = "a0000000-0000-4000-8000-000000000003";
    const messages: Message[] = [];
    let committed: ChatResponse | null = null;
    let posts = 0;
    let stableTurn = "";
    const recoveryIds: string[] = [];
    await page.route("**/api/v2/chat", async (route) => {
      const input = route.request().postDataJSON();
      posts++;
      stableTurn = input.turn_id;
      committed = {
        ...answer(
          "partial",
          "The Atlas project reduced report preparation time from 40 to 12 minutes [S1]. The provided documents do not contain a telephone number listed for Morgan.",
          1,
        ),
        conversation_id: created,
        turn_id: stableTurn,
      };
      messages.push(
        { id: 201, role: "user", content: input.message, turn_id: stableTurn },
        {
          id: 202,
          role: "assistant",
          content: committed.answer,
          turn_id: stableTurn,
          answer_metadata: committed,
        },
      );
      await route.fulfill({
        status: 504,
        json: { error: { code: "request_timeout" } },
      });
    });
    await page.route(`**/api/v2/conversations/${created}`, (route) =>
      route.fulfill({ json: { conversation_id: created, messages } }),
    );
    await page.route(`**/api/v2/conversations/${created}/turns/*`, (route) => {
      recoveryIds.push(route.request().url().split("/").at(-1)!);
      return route.fulfill({
        status: committed ? 200 : 202,
        json: committed ?? { state: "pending" },
      });
    });
    await page.goto("/chat");
    await page
      .getByLabel("Your message")
      .fill(
        "According to Morgan Vale’s resume, how did the Atlas project change report preparation time? Also, what telephone number is listed for Morgan?",
      );
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(
      page.getByRole("log").getByText("partial", { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("log")).toContainText("40 to 12");
    await expect(page.getByRole("log").locator("article")).toHaveCount(2);
    await expect(page.locator("main").getByRole("alert")).toHaveCount(0);
    expect(posts).toBe(1);
    expect(stableTurn).toMatch(/^[0-9a-f-]{36}$/);
    expect(recoveryIds.length).toBeGreaterThan(0);
    expect([...new Set(recoveryIds)]).toEqual([stableTurn]);
    await page.reload();
    await expect(
      page.getByRole("log").getByText("partial", { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("log").locator("article")).toHaveCount(2);
    expect(posts).toBe(1);
    await expect(
      page.getByRole("log").getByRole("link", { name: /Open citation S1/ }),
    ).toHaveAttribute(
      "href",
      `/api/v2/documents/${fixtureDocument.id}/file#page=1`,
    );
  });
});
