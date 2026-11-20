import test from "node:test";
import assert from "node:assert/strict";
import { reconcileChat } from "../lib/chat-reconciliation.ts";
test("committed turn is recovered despite a failed POST", async () => {
  let polls = 0,
    sends = 0;
  const result = await reconcileChat(
    async () => {
      sends++;
      throw new Error("504");
    },
    async () =>
      ++polls === 1
        ? { state: "pending" }
        : { answer: "committed", turn_id: "stable" },
    1000,
    async () => {},
  );
  assert.equal(result.answer, "committed");
  assert.equal(sends, 1);
  assert.equal(polls, 2);
});
test("committed turn wins while post-answer memory work is still running", async () => {
  const result = await reconcileChat(
    () => new Promise(() => {}),
    async () => ({ answer: "saved" }),
  );
  assert.equal(result.answer, "saved");
});
test("reopening only reconciles; never resubmits", async () => {
  assert.equal(
    (await reconcileChat(null, async () => ({ answer: "saved" }))).answer,
    "saved",
  );
});
test("owner denial is not swallowed", async () => {
  await assert.rejects(
    () =>
      reconcileChat(null, async () => {
        throw Object.assign(new Error("denied"), { status: 404 });
      }),
    /denied/,
  );
});
