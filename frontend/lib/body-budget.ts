/** One bounded reader shared by gateway body and upstream request deadlines. */
export class BodyReadFailure extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string) {
    super(code);
    this.status = status;
    this.code = code;
  }
}

export async function readBoundedBody(
  body: ReadableStream<Uint8Array> | null,
  signal: AbortSignal,
  maximum: number,
): Promise<Uint8Array> {
  if (signal.aborted) throw new BodyReadFailure(408, "request_timeout");
  if (!body) return new Uint8Array(0);
  const reader = body.getReader();
  const chunks: Uint8Array[] = [];
  let length = 0;
  try {
    while (true) {
      const part = await new Promise<ReadableStreamReadResult<Uint8Array>>(
        (resolve, reject) => {
          const aborted = () => {
            reject(new BodyReadFailure(408, "request_timeout"));
            // A hostile stream may also stall cancellation. Deadline handling
            // cannot await that promise, and never starts upstream work.
            void reader.cancel().catch(() => {});
          };
          if (signal.aborted) return aborted();
          signal.addEventListener("abort", aborted, { once: true });
          reader.read().then(
            (value) => {
              signal.removeEventListener("abort", aborted);
              resolve(value);
            },
            (error) => {
              signal.removeEventListener("abort", aborted);
              reject(error);
            },
          );
        },
      );
      if (part.done) break;
      length += part.value.byteLength;
      if (length > maximum) {
        void reader.cancel().catch(() => {});
        throw new BodyReadFailure(413, "payload_too_large");
      }
      chunks.push(part.value);
    }
    if (signal.aborted) throw new BodyReadFailure(408, "request_timeout");
    const bytes = new Uint8Array(length);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.byteLength;
    }
    return bytes;
  } finally {
    reader.releaseLock();
  }
}
