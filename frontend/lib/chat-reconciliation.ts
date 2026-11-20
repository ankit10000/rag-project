/** A transport failure does not establish that a turn failed to commit. */
export async function reconcileChat<T>(
  send: (() => Promise<T>) | null,
  recover: () => Promise<T | { state: "pending" }>,
  milliseconds = 180_000,
  pause = (ms: number) =>
    new Promise<void>((resolve) => setTimeout(resolve, ms)),
): Promise<T> {
  let stopped = false;
  const until = Date.now() + milliseconds;
  const polling = async (): Promise<T> => {
    while (!stopped && Date.now() < until) {
      const result = await recover().catch((error) => {
        if ([401, 403, 404, 410].includes(error.status)) throw error;
        return { state: "pending" as const };
      });
      if (!("state" in (result as object))) return result as T;
      await pause(1000);
    }
    throw new Error(
      "The result is still unconfirmed. Retry this question to check the same turn safely.",
    );
  };
  try {
    // A failed POST leaves polling active. A committed GET wins even if
    // synchronous post-answer memory work delays the original response.
    return await Promise.race([
      polling(),
      ...(send
        ? [
            send().catch((error) => {
              if (
                error.status >= 400 &&
                error.status < 500 &&
                ![408, 429].includes(error.status)
              )
                throw error;
              return new Promise<T>(() => {});
            }),
          ]
        : []),
    ]);
  } finally {
    stopped = true;
  }
}
