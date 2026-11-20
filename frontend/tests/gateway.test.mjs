import test from "node:test";
import assert from "node:assert/strict";
import { POST, GET } from "../app/api/v2/[...path]/route.ts";
function req(method, origin = "http://localhost:3000") {
  const request = new Request("http://localhost:3000/api/v2/auth/login", {
    method,
    headers: {
      origin,
      cookie: "rag_session=abc; rag_csrf=csrf; unrelated=private",
      ...(method === "POST" ? { "content-type": "application/json" } : {}),
    },
    ...(method === "POST" ? { body: "{}" } : {}),
  });
  Object.defineProperty(request, "nextUrl", { value: new URL(request.url) });
  return request;
}
const context = (path) => ({ params: Promise.resolve({ path }) });
test("gateway rejects cross-origin authenticated mutation before upstream", async () => {
  const old = globalThis.fetch;
  try {
    globalThis.fetch = () => {
      throw new Error("must not call upstream");
    };
    assert.equal(
      (
        await POST(
          req("POST", "https://attacker.example"),
          context(["auth", "login"]),
        )
      ).status,
      403,
    );
  } finally {
    globalThis.fetch = old;
  }
});
test("gateway does not forward arbitrary cookies or browser bearer credentials", async () => {
  const old = globalThis.fetch;
  try {
    globalThis.fetch = async (url, options) => {
      assert.equal(url.pathname, "/api/v2/auth/login");
      assert.equal(
        options.headers.get("cookie"),
        "rag_session=abc; rag_csrf=csrf",
      );
      assert.equal(options.headers.get("authorization"), null);
      assert.equal(options.headers.get("content-length"), "2");
      return Response.json(
        { id: "u" },
        { headers: { "set-cookie": "rag_session=new; HttpOnly; Path=/" } },
      );
    };
    const response = await POST(req("POST"), context(["auth", "login"]));
    assert.equal(response.status, 200);
    assert.match(response.headers.get("set-cookie"), /HttpOnly/);
  } finally {
    globalThis.fetch = old;
  }
});
test("gateway rejects decoded path traversal", async () => {
  assert.equal(
    (await GET(req("GET"), context(["documents", "..", "admin"]))).status,
    400,
  );
});
test("gateway hides internal failure response", async () => {
  const old = globalThis.fetch;
  try {
    globalThis.fetch = async () =>
      Response.json({ detail: "provider secret" }, { status: 500 });
    const response = await GET(req("GET"), context(["documents"]));
    assert.equal(response.status, 500);
    assert.doesNotMatch(await response.text(), /provider secret/);
  } finally {
    globalThis.fetch = old;
  }
});
test("real loopback Host survives Next internal localhost normalization", async () => {
  const old = globalThis.fetch;
  try {
    globalThis.fetch = async () => Response.json({ ok: true });
    const request = new Request("http://127.0.0.1:3000/api/v2/auth/login", {
      method: "POST",
      headers: {
        host: "127.0.0.1:3000",
        origin: "http://127.0.0.1:3000",
        "x-forwarded-host": "attacker.example",
      },
      body: "{}",
    });
    Object.defineProperty(request, "nextUrl", {
      value: new URL("http://localhost:3000/api/v2/auth/login"),
    });
    assert.equal((await POST(request, context(["auth", "login"]))).status, 200);
  } finally {
    globalThis.fetch = old;
  }
});
test("gateway aborts stalled body before any upstream mutation", async () => {
  const old = globalThis.fetch;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20);
  const body = new ReadableStream({
    pull() {
      return new Promise(() => {});
    },
  });
  const request = new Request("http://localhost:3000/api/v2/documents", {
    method: "POST",
    headers: { origin: "http://localhost:3000", host: "localhost:3000" },
    body,
    duplex: "half",
    signal: controller.signal,
  });
  Object.defineProperty(request, "nextUrl", { value: new URL(request.url) });
  try {
    globalThis.fetch = () => {
      throw new Error("Upstream must not be called");
    };
    const response = await POST(request, context(["documents"]));
    assert.equal(response.status, 408);
    assert.equal((await response.json()).error.code, "request_timeout");
  } finally {
    clearTimeout(timer);
    globalThis.fetch = old;
  }
});
