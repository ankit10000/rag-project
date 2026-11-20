import test from "node:test";
import assert from "node:assert/strict";
import { BodyReadFailure, readBoundedBody } from "../lib/body-budget.ts";

test("stalled body and stalled cancel obey the original short signal deadline", async () => {
  let cancelled = false;
  const stream = new ReadableStream({
    pull() {
      return new Promise(() => {});
    },
    cancel() {
      cancelled = true;
      return new Promise(() => {});
    },
  });
  const controller = new AbortController();
  const started = performance.now();
  const timer = setTimeout(() => controller.abort(), 20);
  try {
    await assert.rejects(
      readBoundedBody(stream, controller.signal, 32),
      (error) =>
        error instanceof BodyReadFailure &&
        error.status === 408 &&
        error.code === "request_timeout",
    );
    assert.equal(cancelled, true);
    assert.ok(performance.now() - started < 500);
  } finally {
    clearTimeout(timer);
  }
});

test("actual bytes are bounded even without Content-Length", async () => {
  let cancelled = false;
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new Uint8Array(5));
    },
    cancel() {
      cancelled = true;
    },
  });
  await assert.rejects(
    readBoundedBody(stream, new AbortController().signal, 4),
    (error) => error.status === 413,
  );
  assert.equal(cancelled, true);
});

test("ordinary multipart bytes pass unchanged under the same signal", async () => {
  const expected = new TextEncoder().encode("bounded-upload");
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(expected.subarray(0, 4));
      controller.enqueue(expected.subarray(4));
      controller.close();
    },
  });
  assert.deepEqual(
    await readBoundedBody(stream, new AbortController().signal, 32),
    expected,
  );
});
