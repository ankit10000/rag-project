import type { Page } from "@playwright/test";
import type { ChatResponse, Conversation, Message } from "../../lib/api-types";

export const fixtureUser = {
  id: "10000000-0000-4000-8000-000000000001",
  email: "one@example.test",
  display_name: "Avery",
  role: "user",
  status: "active",
};
export const fixtureDocument = {
  id: "d0000000-0000-4000-8000-000000000001",
  filename: "observatory.pdf",
  status: "ready",
  pages: 2,
  chunks: 3,
  created_at: "2026-11-20T00:00:00Z",
  page_metadata: [
    { page_number: 1, method: "native", characters: 200 },
    { page_number: 2, method: "pymupdf-tesseract-fast-4.1.0", characters: 250 },
  ],
};

/** Stateful API-shaped fixture. No database, OCR or model correctness claim. */
export async function installUIFixture(page: Page) {
  const conversations: Conversation[] = [
    {
      conversation_id: "a0000000-0000-4000-8000-000000000001",
      title: "Orbital research",
      message_count: 0,
    },
    {
      conversation_id: "a0000000-0000-4000-8000-000000000002",
      title: "Meeting notes",
      message_count: 0,
    },
  ];
  const histories = new Map<string, Message[]>();
  const committed = new Map<string, ChatResponse>();
  let nextConversation = 3;
  let nextMessage = 1;
  await page.route("**/api/v2/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/v2/", "");
    const method = request.method();
    let result: unknown = [];
    let status = 200;
    if (["auth/me", "auth/login"].includes(path)) result = fixtureUser;
    else if (path === "auth/logout") result = { ok: true };
    else if (path === "health") result = { status: "ok" };
    else if (path === "documents") result = [fixtureDocument];
    else if (path === `documents/${fixtureDocument.id}`)
      result = fixtureDocument;
    else if (path === "jobs") result = [];
    else if (path === "conversations" && method === "GET")
      result = conversations;
    else if (path === "conversations" && method === "POST") {
      const input = request.postDataJSON();
      const conversation = {
        conversation_id: `a0000000-0000-4000-8000-${String(nextConversation++).padStart(12, "0")}`,
        title: input.title,
        message_count: 0,
      };
      conversations.unshift(conversation);
      histories.set(conversation.conversation_id, []);
      result = conversation;
      status = 201;
    } else if (/^conversations\/[^/]+\/turns\//.test(path)) {
      const turn = path.split("/").at(-1)!;
      result = committed.get(turn) ?? { state: "pending", turn_id: turn };
      status = committed.has(turn) ? 200 : 202;
    } else if (/^conversations\/[^/]+$/.test(path)) {
      const id = path.split("/")[1];
      const existing = conversations.find(
        (item) => item.conversation_id === id,
      );
      if (method === "PATCH") {
        if (existing) existing.title = request.postDataJSON().title;
        result = { conversation_id: id, title: existing?.title };
      } else if (method === "DELETE") {
        const index = conversations.findIndex(
          (item) => item.conversation_id === id,
        );
        if (index >= 0) conversations.splice(index, 1);
        histories.delete(id);
        result = { deleted: true };
      } else
        result = { conversation_id: id, messages: histories.get(id) ?? [] };
    } else if (path === "chat") {
      const body = request.postDataJSON();
      const existing = committed.get(body.turn_id);
      if (existing) result = existing;
      else {
        const answer: ChatResponse = {
          conversation_id: body.conversation_id,
          turn_id: body.turn_id,
          kind: "answer",
          answer: "The permit costs 71 tokens [S1].",
          status: "answered",
          answer_status: "answered",
          citations: [
            {
              ref: "S1",
              document: fixtureDocument.filename,
              document_id: fixtureDocument.id,
              page: 2,
              chunk_id: 12,
            },
          ],
        };
        const messages = histories.get(body.conversation_id) ?? [];
        messages.push(
          {
            id: nextMessage++,
            role: "user",
            content: body.message,
            turn_id: body.turn_id,
          },
          {
            id: nextMessage++,
            role: "assistant",
            content: answer.answer,
            turn_id: body.turn_id,
            answer_metadata: answer,
          },
        );
        histories.set(body.conversation_id, messages);
        const conversation = conversations.find(
          (item) => item.conversation_id === body.conversation_id,
        );
        if (conversation) conversation.message_count = messages.length;
        committed.set(body.turn_id, answer);
        result = answer;
      }
    }
    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(result),
    });
  });
  return { conversations, histories, committed };
}
