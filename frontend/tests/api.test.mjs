import test from "node:test";
import assert from "node:assert/strict";
import { ApiError, request, csrfToken, fileUrl, api } from "../lib/api.ts";
test("public errors never disclose a backend message", () => {
  assert.equal(
    new ApiError(403, "denied").message,
    "You do not have permission to do that.",
  );
  assert.equal(
    new ApiError(404, "secret").message,
    "This item is unavailable or you do not have access.",
  );
});
test("mutations use readable CSRF cookie and same-origin credentials", async () => {
  const oldFetch = globalThis.fetch;
  const oldDocument = globalThis.document;
  globalThis.document = { cookie: "other=x; rag_csrf=bounded-token; misc=z" };
  try {
    globalThis.fetch = async (url, options) => {
      assert.equal(url, "/api/v2/conversations");
      assert.equal(options.headers.get("X-CSRF-Token"), "bounded-token");
      assert.equal(options.credentials, "same-origin");
      assert.equal(options.headers.has("Authorization"), false);
      return Response.json({ conversation_id: "safe" });
    };
    assert.equal(csrfToken(), "bounded-token");
    const result = await api.createConversation("Hi");
    assert.equal(result.conversation_id, "safe");
  } finally {
    globalThis.fetch = oldFetch;
    globalThis.document = oldDocument;
  }
});
test("provider details in errors are discarded", async () => {
  const old = globalThis.fetch;
  try {
    globalThis.fetch = async () =>
      Response.json(
        { error: { code: "internal", message: "SECRET provider key" } },
        { status: 500 },
      );
    await assert.rejects(
      () => request("documents"),
      (e) => !e.message.includes("SECRET") && e.status === 500,
    );
  } finally {
    globalThis.fetch = old;
  }
});
test("memory deletion uses owner-scoped conversation route", async () => {
  const old = globalThis.fetch;
  try {
    globalThis.fetch = async (url, options) => {
      assert.equal(url, "/api/v2/conversations/cid/memories/41");
      assert.equal(options.method, "DELETE");
      return Response.json({ deleted: true });
    };
    await api.deleteMemory("cid", 41);
  } finally {
    globalThis.fetch = old;
  }
});
test("PDF links stay same-origin and bound page number", () => {
  assert.equal(
    fileUrl("unsafe/name", -5),
    "/api/v2/documents/unsafe%2Fname/file#page=1",
  );
});
test("document replacement uses the actual multipart PUT contract", async () => {
  const old = globalThis.fetch;
  try {
    globalThis.fetch = async (url, options) => {
      assert.equal(url, "/api/v2/documents/did");
      assert.equal(options.method, "PUT");
      assert.ok(options.body instanceof FormData);
      assert.equal(options.body.get("file").name, "replacement.pdf");
      return Response.json({
        document_id: "did",
        job_id: "jid",
        status: "queued",
      });
    };
    const result = await api.replaceDocument(
      "did",
      new File(["%PDF"], "replacement.pdf", { type: "application/pdf" }),
    );
    assert.equal(result.status, "queued");
  } finally {
    globalThis.fetch = old;
  }
});
