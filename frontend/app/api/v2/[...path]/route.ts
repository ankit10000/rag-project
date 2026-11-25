import type { NextRequest } from "next/server";
import {
  BodyReadFailure,
  readBoundedBody,
} from "../../../../lib/body-budget.ts";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const MAX_BODY = 32 * 1024 * 1024;
async function gateway(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const deadline = AbortSignal.any([
    request.signal,
    AbortSignal.timeout(120_000),
  ]);
  const { path } = await params;
  if (
    path.some((p) => !p || p === "." || p === ".." || /[\\/\x00-\x1f]/.test(p))
  )
    return Response.json({ error: { code: "invalid_path" } }, { status: 400 });
  const isWrite = !["GET", "HEAD"].includes(request.method);
  // Verify the browser's own origin before forwarding session-authenticated writes.
  // Next normalizes loopback URLs internally; use the actual request Host, never
  // client-supplied forwarded-host/proto headers, to retain the browser origin.
  const host = request.headers.get("host");
  let browserOrigin = host
    ? `${request.nextUrl.protocol}//${host}`
    : request.nextUrl.origin;
  // A TLS-terminating deployment explicitly declares its public origin. Never
  // derive this trust boundary from client-controlled forwarded headers.
  const publicOrigin = process.env.RAG_PUBLIC_ORIGIN;
  if (publicOrigin !== undefined) {
    try {
      const configured = new URL(publicOrigin);
      if (
        configured.protocol !== "https:" ||
        configured.username || configured.password ||
        configured.pathname !== "/" || configured.search || configured.hash
      ) throw new Error("invalid public origin");
      if (host?.toLowerCase() !== configured.host)
        return Response.json(
          { error: { code: "origin_rejected" } }, { status: 403 },
        );
      browserOrigin = configured.origin;
    } catch {
      return Response.json(
        { error: { code: "gateway_configuration" } }, { status: 503 },
      );
    }
  }
  if (isWrite && request.headers.get("origin") !== browserOrigin)
    return Response.json(
      { error: { code: "origin_rejected" } },
      { status: 403 },
    );
  const backend = new URL(
    process.env.RAG_BACKEND_ORIGIN ?? "http://127.0.0.1:8000",
  );
  if (
    !["http:", "https:"].includes(backend.protocol) ||
    backend.username ||
    backend.password ||
    backend.pathname !== "/" ||
    backend.search ||
    backend.hash
  )
    return Response.json(
      { error: { code: "gateway_configuration" } },
      { status: 503 },
    );
  const target = new URL(
    `/api/v2/${path.map(encodeURIComponent).join("/")}`,
    backend,
  );
  target.search = request.nextUrl.search;
  const headers = new Headers();
  for (const key of ["content-type", "x-csrf-token", "origin", "range"]) {
    const value = request.headers.get(key);
    if (value) headers.set(key, value);
  }
  const cookie = request.headers
    .get("cookie")
    ?.split(";")
    .map((x) => x.trim())
    .filter((x) => /^rag_(session|csrf)=/.test(x))
    .join("; ");
  if (cookie) headers.set("cookie", cookie);
  let body: Uint8Array | undefined;
  if (isWrite) {
    const length = request.headers.get("content-length");
    if (length && (!/^\d+$/.test(length) || Number(length) > MAX_BODY))
      return Response.json(
        { error: { code: "payload_too_large" } },
        { status: 413 },
      );
    try {
      body = await readBoundedBody(request.body, deadline, MAX_BODY);
    } catch (error) {
      if (error instanceof BodyReadFailure)
        return Response.json(
          { error: { code: error.code } },
          { status: error.status },
        );
      return Response.json(
        { error: { code: "invalid_body" } },
        { status: 400 },
      );
    }
    headers.set("content-length", String(body.byteLength));
  }
  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body: body as BodyInit | undefined,
      cache: "no-store",
      redirect: "manual",
      signal: deadline,
    });
    const out = new Headers({
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    });
    for (const key of [
      "content-type",
      "content-disposition",
      "content-range",
      "accept-ranges",
      "x-request-id",
      "x-rag-browser-run-id",
    ]) {
      const value = upstream.headers.get(key);
      if (value) out.set(key, value);
    }
    for (const value of upstream.headers.getSetCookie())
      if (/^rag_(session|csrf)=/.test(value)) out.append("set-cookie", value);
    if (upstream.status >= 500)
      return Response.json(
        {
          error: {
            code:
              upstream.status === 504
                ? "request_timeout"
                : "service_unavailable",
          },
        },
        { status: upstream.status, headers: out },
      );
    if (upstream.status >= 300 && upstream.status < 400)
      return Response.json(
        { error: { code: "unexpected_redirect" } },
        { status: 502 },
      );
    return new Response(upstream.body, {
      status: upstream.status,
      headers: out,
    });
  } catch {
    if (deadline.aborted)
      return Response.json(
        { error: { code: "request_timeout" } },
        { status: 504 },
      );
    return Response.json(
      { error: { code: "service_unavailable" } },
      { status: 503 },
    );
  }
}
export {
  gateway as GET,
  gateway as HEAD,
  gateway as POST,
  gateway as PATCH,
  gateway as PUT,
  gateway as DELETE,
};
