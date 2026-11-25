import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import type { ChatResponse, Message } from "../../lib/api-types";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fixtureDocument, installUIFixture } from "./ui-contract-fixture";

type Requirement = {
  id: string;
  question: string;
  status: string;
  required_facts: string[];
  document?: string;
  page?: number;
  required_gap?: string;
};
type Policy = { run_id?: string; maximum_sdk_calls: number; questions: Requirement[] };
type Citation = { ref: string; document_id: string; page: number };
type SavedTurn = {
  id: string;
  conversation_id: string;
  turn_id: string;
  message: string;
  answer: string;
  answer_status: string;
  citations: Citation[];
};
type State = {
  run_id: string;
  base_url: string;
  owner: string;
  other: string;
  owner_id: string;
  other_id: string;
  password: string;
  documents: Record<string, { id: string; job_id: string }>;
  turns: SavedTurn[];
  memory: { conversation_id: string; memory_id: number };
};
const staticPolicy = JSON.parse(
  fs.readFileSync(path.resolve("../deploy/aws/tests/acceptance-policy.json"), "utf8"),
) as Policy;

function privateJson(file: string, value: unknown) {
  fs.writeFileSync(file, JSON.stringify(value, null, 2) + "\n", {
    mode: 0o600,
    flag: "wx",
  });
}
async function savedAnswerUI(page: Page, turn: SavedTurn, turns: SavedTurn[]) {
  // The API preserves exact Markdown bytes. The UI renders its semantic text;
  // list/emphasis delimiters are not literal DOM text.
  const requirement = staticPolicy.questions.find((item) => item.id === turn.id)!;
  expect(requirement).toBeTruthy();
  const conversationTurns = turns.filter((item) => item.conversation_id === turn.conversation_id);
  const index = conversationTurns.findIndex((item) => item.turn_id === turn.turn_id);
  expect(index).toBeGreaterThanOrEqual(0);
  const answers = page.getByRole("log").locator("article").filter({ has: page.getByRole("heading", { name: "RAG", exact: true }) });
  await expect(answers).toHaveCount(conversationTurns.length);
  const answer = answers.nth(index);
  await expect(answer.getByText(turn.answer_status, { exact: true })).toBeVisible();
  for (const fact of requirement.required_facts) await expect(answer).toContainText(fact);
  if (requirement.required_gap) await expect(answer).toContainText(new RegExp(requirement.required_gap, "i"));
  for (const citation of turn.citations) await expect(answer.getByRole("link", {
    name: new RegExp(`Open citation ${citation.ref}.*p\\. ${citation.page}`),
  }).first()).toHaveAttribute("href", `/api/v2/documents/${citation.document_id}/file#page=${citation.page}`);
}
async function mutation(page: Page, route: string, method: string, body?: unknown) {
  return page.evaluate(async ({ route, method, body }) => {
    const csrf = decodeURIComponent(document.cookie.split("; ").find((s) => s.startsWith("rag_csrf="))?.slice(9) ?? "");
    const response = await fetch(route, {
      method,
      headers: { "X-CSRF-Token": csrf, ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
    return { status: response.status, body: await response.json() };
  }, { route, method, body });
}
async function register(page: Page, email: string, password: string) {
  await page.goto("/register");
  await page.getByLabel("Name", { exact: true }).fill("AWS Synthetic Tester");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("account is ready");
}
async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}
async function logout(page: Page) {
  const response = await mutation(page, "/api/v2/auth/logout", "POST");
  expect(response.status).toBe(200);
  await page.goto("/login");
}

// These assertions verify UI contracts only; they make no OCR/Gemini claim.
for (const requirement of staticPolicy.questions) {
  test(`AWS acceptance fixture UI: ${requirement.id} (no provider)`, async ({ page }) => {
    const fixture = await installUIFixture(page);
    await page.route("**/api/v2/chat", async (route) => {
      const input = route.request().postDataJSON();
      const response: ChatResponse = {
        kind: "answer", conversation_id: input.conversation_id, turn_id: input.turn_id,
        answer: requirement.required_facts.join("; ") + (requirement.page ? " [S1]." : ".") +
          (requirement.required_gap ? " The document does not list a telephone number." : ""),
        status: requirement.status, answer_status: requirement.status,
        citations: requirement.page ? [{ ref: "S1", document_id: fixtureDocument.id,
          document: requirement.document!, page: requirement.page, chunk_id: 12 }] : [],
      };
      const messages: Message[] = [
        { id: 1, role: "user", content: input.message, turn_id: input.turn_id },
        { id: 2, role: "assistant", content: response.answer, turn_id: input.turn_id, answer_metadata: response },
      ];
      fixture.histories.set(input.conversation_id, messages);
      fixture.committed.set(input.turn_id, response);
      await route.fulfill({ json: response });
    });
    await page.goto("/chat");
    await page.getByLabel("Your message", { exact: true }).fill(requirement.question);
    await page.getByRole("button", { name: "Send", exact: true }).click();
    const log = page.getByRole("log");
    await expect(log.getByText(requirement.status, { exact: true })).toBeVisible();
    for (const fact of requirement.required_facts) await expect(log).toContainText(fact);
    if (requirement.page) await expect(log.getByRole("link", { name: /Open citation S1/ })).toHaveAttribute(
      "href", `/api/v2/documents/${fixtureDocument.id}/file#page=${requirement.page}`,
    );
    await page.reload();
    await expect(log.getByText(requirement.status, { exact: true })).toBeVisible();
    await expect(log.locator("article")).toHaveCount(2);
  });
}

test("AWS real deployment: synthetic OCR/Gemini, retained regressions, isolation and history", async ({ page, baseURL }, info) => {
  test.skip(process.env.RAG_AWS_E2E_PHASE !== "journey", "Explicit fresh bounded deployment experiment only");
  test.skip(info.project.name !== "desktop-chromium", "One provider family, no duplicate mobile generations");
  test.setTimeout(540_000);
  const fixtureDir = process.env.RAG_AWS_FIXTURES_DIR!;
  const output = process.env.RAG_AWS_EVIDENCE_DIR!;
  const policy = JSON.parse(fs.readFileSync(path.join(fixtureDir, "acceptance-policy.json"), "utf8")) as Policy;
  expect(policy.run_id).toMatch(/^aws-demo-\d{8}-live-\d{2}$/);
  expect(policy.maximum_sdk_calls).toBe(18);
  const url = new URL(baseURL!);
  if (url.protocol !== "https:") {
    expect(process.env.RAG_AWS_ALLOW_LOCAL_HTTP).toBe("1");
    expect(["127.0.0.1", "localhost"]).toContain(url.hostname);
  }
  fs.mkdirSync(output, { mode: 0o700, recursive: true });
  expect(fs.existsSync(path.join(output, "journey-result.json"))).toBe(false);
  const identity = policy.run_id!;
  let state: State = {
    run_id: identity, base_url: baseURL!, owner: `${identity}-a@example.test`,
    other: `${identity}-b@example.test`, owner_id: "", other_id: "", password: crypto.randomBytes(24).toString("base64url"),
    documents: {}, turns: [], memory: { conversation_id: "", memory_id: 0 },
  };
  const result: Record<string, unknown> = { run_id: identity, status: "RUNNING", policy: "aws-demo-development-acceptance/1", formal_acceptance: false };
  const continuation = process.env.RAG_AWS_CONTINUE_FROM;
  if (continuation) {
    state = JSON.parse(fs.readFileSync(path.join(continuation, "failed-state.json"), "utf8")) as State;
    expect(state.run_id).toBe(identity); expect(state.base_url).toBe(baseURL);
    expect(state.turns.map((turn) => turn.id)).toEqual(["ocr-facts"]);
    expect(JSON.parse(fs.readFileSync(path.join(continuation, "journey-result.json"), "utf8")).status).toBe("FAIL");
    result.execution = "CONTINUATION"; result.original_result = "FAIL (preserved harness wait race)";
    result.continued_from = continuation;
  }
  async function upload(filename: string, expectedPages: number, ocrPage: number) {
    await page.goto("/documents");
    const sent = page.waitForResponse((response) => response.url().endsWith("/api/v2/documents") && response.request().method() === "POST");
    await page.getByLabel("Choose PDF", { exact: true }).setInputFiles({
      name: filename, mimeType: "application/pdf", buffer: fs.readFileSync(path.join(fixtureDir, filename)),
    });
    const response = await sent; expect(response.status()).toBe(202);
    const uploaded = await response.json();
    state.documents[filename] = { id: uploaded.document_id, job_id: uploaded.job_id };
    await expect.poll(async () => {
      const response = await page.request.get(`/api/v2/documents/${uploaded.document_id}`);
      expect(response.status()).toBe(200); return (await response.json()).status;
    }, { timeout: 180_000, intervals: [500, 1000, 2000] }).toBe("ready");
    const document = await (await page.request.get(`/api/v2/documents/${uploaded.document_id}`)).json();
    expect(document.pages).toBe(expectedPages); expect(document.chunks).toBeGreaterThan(0);
    expect(document.page_metadata.find((p: { page_number: number }) => p.page_number === ocrPage).method).toBe("pymupdf-tesseract-fast-4.1.0");
    const job = await (await page.request.get(`/api/v2/jobs/${uploaded.job_id}`)).json();
    expect(job.status).toBe("succeeded");
    await page.goto(`/documents/${uploaded.document_id}?page=${ocrPage}`);
    await expect(page.locator(`canvas[data-rendered-page="${ocrPage}"]`)).toHaveAttribute("data-render-state", "ready", { timeout: 30_000 });
    const pixels = await page.locator("canvas").evaluate((node) => {
      const canvas = node as HTMLCanvasElement; const context = canvas.getContext("2d")!;
      const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
      let low = 255, high = 0;
      for (let index = 0; index < data.length; index += 4) { low = Math.min(low, data[index]); high = Math.max(high, data[index]); }
      return { low, high, width: canvas.width, height: canvas.height };
    });
    expect(pixels.high - pixels.low).toBeGreaterThan(150);
    result[filename] = { id: uploaded.document_id, job_id: uploaded.job_id, pages: document.pages, chunks: document.chunks, page_metadata: document.page_metadata, rendered_pixels: pixels };
  }
  async function question(requirement: Requirement, conversation?: string) {
    await page.goto(conversation ? `/chat?conversation=${conversation}` : "/chat");
    let posted = 0, submittedTurn = "", cid = conversation ?? "";
    const isDisconnect = requirement.id === "partial-project-phone";
    let releaseRecovery: () => void = () => {};
    const recoveryGate = new Promise<void>((resolve) => { releaseRecovery = resolve; });
    const recordPost = (request: { method(): string; url(): string; postDataJSON(): { turn_id: string; conversation_id: string } }) => {
      if (request.method() === "POST" && request.url().endsWith("/api/v2/chat")) {
        posted++; const body = request.postDataJSON(); submittedTurn = body.turn_id; cid = body.conversation_id;
      }
    };
    page.on("request", recordPost);
    if (isDisconnect) {
      await page.route("**/api/v2/conversations/*/turns/*", async (route) => { await recoveryGate; await route.continue(); });
      await page.route("**/api/v2/chat", async (route) => {
        const upstream = await route.fetch({ timeout: 120_000, maxRedirects: 0 });
        expect(upstream.status()).toBe(200);
        await route.fulfill({ status: 504, json: { error: { code: "request_timeout" } } });
        releaseRecovery();
      });
    }
    const existingAnswers = page.getByRole("log").locator("article").filter({ has: page.getByRole("heading", { name: "RAG", exact: true }) });
    const priorAnswerCount = conversation ? state.turns.filter((turn) => turn.conversation_id === conversation).length : 0;
    await expect(existingAnswers).toHaveCount(priorAnswerCount);
    const postResponse = page.waitForResponse((response) => response.request().method() === "POST" && response.url().endsWith("/api/v2/chat"), { timeout: 125_000 }).catch(() => null);
    try {
      await page.getByLabel("Your message", { exact: true }).fill(requirement.question);
      await page.getByRole("button", { name: "Send", exact: true }).click();
      const answerArticles = page.getByRole("log").locator("article").filter({ has: page.getByRole("heading", { name: "RAG", exact: true }) });
      await expect(answerArticles).toHaveCount(priorAnswerCount + 1, { timeout: 120_000 });
      const answerArticle = answerArticles.last();
      await expect(answerArticle.getByText(requirement.status, { exact: true })).toBeVisible({ timeout: 120_000 });
      for (const fact of requirement.required_facts) await expect(answerArticle).toContainText(fact);
      if (requirement.required_gap) {
        await expect(answerArticle).toContainText(new RegExp(requirement.required_gap));
        await expect(answerArticle).toContainText(/not (?:list|provide|contain|available|specified)|no (?:telephone|phone)|couldn.t find|does not|isn.t (?:listed|provided|available)/i);
      }
      const deliveredPost = await postResponse;
      expect(deliveredPost).not.toBeNull();
      expect(deliveredPost!.status()).toBe(isDisconnect ? 504 : 200);
      const history = await (await page.request.get(`/api/v2/conversations/${cid}`)).json();
      const message = history.messages.findLast((item: { role: string }) => item.role === "assistant");
      const answer = message.answer_metadata;
      expect(answer.answer_status).toBe(requirement.status);
      expect(message.turn_id).toBe(submittedTurn);
      const declaredRefs = new Set(answer.citations.map((citation: Citation) => citation.ref));
      for (const match of String(message.content).matchAll(/\[(S\d+)\]/g)) expect(declaredRefs.has(match[1])).toBe(true);
      if (requirement.required_gap) expect(message.content).not.toMatch(/(?:telephone|phone)(?:\s+number)?\s*(?:(?:is|:)\s*)?\+?\d(?:[\s().-]*\d){6,}/i);
      if (requirement.page) {
        const did = state.documents[requirement.document!].id;
        expect(answer.citations.some((citation: Citation) => citation.document_id === did && citation.page === requirement.page)).toBe(true);
        for (const citation of answer.citations) {
          expect(citation.document_id).toBe(did);
          expect(citation.page).toBeGreaterThan(0); expect(citation.page).toBeLessThanOrEqual(requirement.document!.startsWith("Browser") ? 2 : 1);
        }
        const chip = answerArticle.getByRole("link", { name: new RegExp(`Open citation.*p\\. ${requirement.page}`) }).first();
        await expect(chip).toHaveAttribute("href", `/api/v2/documents/${did}/file#page=${requirement.page}`);
        expect((await page.request.get(`/api/v2/documents/${did}/file`)).status()).toBe(200);
      }
      const saved: SavedTurn = { id: requirement.id, conversation_id: cid, turn_id: submittedTurn, message: requirement.question, answer: message.content, answer_status: answer.answer_status, citations: answer.citations };
      state.turns.push(saved);
      await page.reload();
      await expect(page.getByRole("log").getByText(requirement.status, { exact: true }).last()).toBeVisible();
      expect(posted).toBe(1);
      if (isDisconnect) {
        await page.unroute("**/api/v2/chat");
        await page.unroute("**/api/v2/conversations/*/turns/*");
        const retry = await mutation(page, "/api/v2/chat", "POST", { conversation_id: cid, turn_id: submittedTurn, message: requirement.question });
        expect(retry.status).toBe(200); expect(retry.body.answer).toBe(message.content);
        const retriedHistory = await (await page.request.get(`/api/v2/conversations/${cid}`)).json();
        expect(retriedHistory.messages).toHaveLength(2);
        await expect(page.locator("main").getByRole("alert")).toHaveCount(0);
        result.timeout_reconciliation = { mode: "real committed server response, browser transport changed to HTTP504", original_upstream_status: 200, browser_post_status: 504, recovery_status: 200, original_turn_id: submittedTurn, retry_status: retry.status, duplicate_messages: 0 };
      }
      return saved;
    } finally {
      releaseRecovery(); page.off("request", recordPost);
      if (isDisconnect) { await page.unroute("**/api/v2/chat"); await page.unroute("**/api/v2/conversations/*/turns/*"); }
    }
  }
  try {
    const health = await page.request.get("/api/v2/health");
    expect(health.status()).toBe(200); expect(health.headers()["x-rag-browser-run-id"]).toBe(identity);
    let first: SavedTurn;
    if (continuation) {
      await login(page, state.owner, state.password);
      expect((await (await page.request.get("/api/v2/auth/me")).json()).id).toBe(state.owner_id);
      const submitted = JSON.parse(fs.readFileSync(path.join(continuation, "submitted-turns.json"), "utf8"));
      expect(submitted).toHaveLength(2);
      const pending = submitted[1];
      expect(pending.message_sha256).toBe(crypto.createHash("sha256").update(policy.questions[1].question).digest("hex"));
      await expect.poll(async () => (await page.request.get(`/api/v2/conversations/${pending.conversation_id}/turns/${pending.turn_id}`)).status(),
        { timeout: 30_000, intervals: [500, 1000] }).toBe(200);
      const recovered = await (await page.request.get(`/api/v2/conversations/${pending.conversation_id}/turns/${pending.turn_id}`)).json();
      const history = await (await page.request.get(`/api/v2/conversations/${pending.conversation_id}`)).json();
      expect(history.messages).toHaveLength(4);
      const user = history.messages.find((message: { role: string; turn_id: string }) => message.role === "user" && message.turn_id === pending.turn_id);
      const assistant = history.messages.find((message: { role: string; turn_id: string }) => message.role === "assistant" && message.turn_id === pending.turn_id);
      expect(user.content).toBe(policy.questions[1].question);
      expect(assistant.content).toBe(recovered.answer); expect(recovered.answer_status).toBe("answered");
      expect(recovered.answer).toMatch(/concise/i);
      first = state.turns[0];
      state.turns.push({ id: policy.questions[1].id, conversation_id: pending.conversation_id, turn_id: pending.turn_id,
        message: user.content, answer: assistant.content, answer_status: recovered.answer_status, citations: recovered.citations });
      await page.goto(`/chat?conversation=${first.conversation_id}`);
      const answers = page.getByRole("log").locator("article").filter({ has: page.getByRole("heading", { name: "RAG", exact: true }) });
      await expect(answers).toHaveCount(2); await expect(answers.last()).toContainText(/concise/i);
      await expect(answers.last().getByText("answered", { exact: true })).toBeVisible();
      result.recovered_followup = { turn_id: pending.turn_id, status: recovered.answer_status, concise_fact: true,
        canonical_messages: history.messages.length, chat_POSTs: 0 };
    } else {
      await register(page, state.owner, state.password); await login(page, state.owner, state.password);
      state.owner_id = (await (await page.request.get("/api/v2/auth/me")).json()).id;
      await upload("Aster_Harbor_Policy.pdf", 1, 1);
      await upload("Browser_Check_Morgan_Vale.pdf", 2, 2);
      first = await question(policy.questions[0]);
      await question(policy.questions[1], first.conversation_id);
    }
    const memories = await (await page.request.get(`/api/v2/memories?conversation_id=${first.conversation_id}`)).json();
    const preference = memories.flatMap((group: { memories: { memory: string; memory_id: number; provenance: string; source_message_ids: number[] }[] }) => group.memories).find((item: { memory: string }) => /concise/i.test(item.memory));
    expect(preference).toBeTruthy(); expect(preference.provenance).toBe("USER_SUPPORTED"); expect(preference.source_message_ids.length).toBeGreaterThan(0);
    state.memory = { conversation_id: first.conversation_id, memory_id: preference.memory_id };
    const sources = await (await page.request.get(`/api/v2/conversations/${first.conversation_id}/memories/${preference.memory_id}/sources`)).json();
    expect(sources.some((source: { role: string; message_id: number }) => source.role === "user" && preference.source_message_ids.includes(source.message_id))).toBe(true);
    result.memory = { provenance: preference.provenance, source_message_ids: preference.source_message_ids, sources };
    for (const requirement of policy.questions.slice(2)) await question(requirement);
    result.turns = state.turns;
    await page.screenshot({ path: path.join(output, "partial-chat.png"), fullPage: true });
    await logout(page); await register(page, state.other, state.password); await login(page, state.other, state.password);
    state.other_id = (await (await page.request.get("/api/v2/auth/me")).json()).id;
    const denied: Record<string, number> = {};
    for (const document of Object.values(state.documents)) for (const route of [
      `/api/v2/documents/${document.id}`, `/api/v2/documents/${document.id}/file`, `/api/v2/jobs/${document.job_id}`,
    ]) { denied[route] = (await page.request.get(route)).status(); expect(denied[route]).toBe(404); }
    for (const turn of state.turns) for (const route of [
      `/api/v2/conversations/${turn.conversation_id}`, `/api/v2/conversations/${turn.conversation_id}/turns/${turn.turn_id}`,
      `/api/v2/memories?conversation_id=${turn.conversation_id}`,
    ]) { denied[route] = (await page.request.get(route)).status(); expect(denied[route]).toBe(404); }
    const memoryPath = `/api/v2/conversations/${state.memory.conversation_id}/memories/${state.memory.memory_id}/sources`;
    expect((await page.request.get(memoryPath)).status()).toBe(404);
    const documents = await (await page.request.get("/api/v2/documents")).json(); expect(documents).toEqual([]);
    expect(await (await page.request.get("/api/v2/conversations")).json()).toEqual([]);
    expect(await (await page.request.get("/api/v2/memories")).json()).toEqual([]);
    expect((await mutation(page, "/api/v2/chat", "POST", { conversation_id: first.conversation_id, turn_id: crypto.randomUUID(), message: "Unauthorized cross-owner query" })).status).toBe(404);
    result.isolation = { status: "PASS", denied, chunks: "No public raw-chunk route exists; authenticated tenant retrieval tested by lead DB/RLS suite" };
    await logout(page);
    result.status = continuation ? "CONTINUATION_JOURNEY_PASS_RESTART_PENDING" : "JOURNEY_PASS_RESTART_PENDING";
    privateJson(path.join(output, "retained-state.json"), state);
    privateJson(path.join(output, "tenant-state.json"), {
      run_id: state.run_id, owner: state.owner, other: state.other,
      owner_id: state.owner_id, other_id: state.other_id,
      documents: state.documents, memory: state.memory,
      turns: state.turns.map(({ conversation_id, turn_id }) => ({ conversation_id, turn_id })),
    });
  } catch (error) {
    result.status = "FAIL"; result.failure_type = error instanceof Error ? error.name : "Unknown";
    privateJson(path.join(output, "failed-state.json"), state);
    throw error;
  } finally { privateJson(path.join(output, "journey-result.json"), result); }
});

test("AWS restart persistence and deletion (no provider)", async ({ page, baseURL }, info) => {
  test.skip(process.env.RAG_AWS_E2E_PHASE !== "persistence", "Requires the retained successful journey and an actual service restart");
  test.skip(info.project.name !== "desktop-chromium", "One retained deployment owner");
  test.setTimeout(180_000);
  const output = process.env.RAG_AWS_EVIDENCE_DIR!;
  const state = JSON.parse(fs.readFileSync(path.join(output, "retained-state.json"), "utf8")) as State;
  expect(baseURL).toBe(state.base_url);
  const restart = JSON.parse(fs.readFileSync(process.env.RAG_AWS_RESTART_RECEIPT!, "utf8"));
  expect(restart.restarted_services).toEqual(expect.arrayContaining(["api", "worker"]));
  const result: Record<string, unknown> = { run_id: state.run_id, status: "RUNNING", restarted_services: restart.restarted_services, provider_calls: 0 };
  let chatPosts = 0;
  page.on("request", (request) => { if (request.method() === "POST" && request.url().endsWith("/api/v2/chat")) chatPosts++; });
  try {
    await login(page, state.owner, state.password);
    for (const turn of state.turns) {
      const canonical = await page.request.get(`/api/v2/conversations/${turn.conversation_id}/turns/${turn.turn_id}`);
      expect(canonical.status()).toBe(200);
      const committed = await canonical.json();
      expect(committed.answer).toBe(turn.answer); expect(committed.answer_status).toBe(turn.answer_status);
      expect(committed.citations).toEqual(turn.citations);
      await page.goto(`/chat?conversation=${turn.conversation_id}`);
      await savedAnswerUI(page, turn, state.turns);
      await expect(page.getByRole("log").getByText(turn.answer_status, { exact: true }).last()).toBeVisible();
      for (const citation of turn.citations) {
        await expect(page.getByRole("log").getByRole("link", { name: new RegExp(`Open citation ${citation.ref}.*p\\. ${citation.page}`) }).first()).toHaveAttribute("href", `/api/v2/documents/${citation.document_id}/file#page=${citation.page}`);
        expect((await page.request.get(`/api/v2/documents/${citation.document_id}/file`)).status()).toBe(200);
      }
      await page.reload(); await savedAnswerUI(page, turn, state.turns);
    }
    // A fresh eight-page image-only fixture leaves a measurable cancellation
    // window. Observe a real live lease before deletion; do not call a mock worker.
    await page.goto("/documents");
    const uploadSent = page.waitForResponse((response) => response.request().method() === "POST" && response.url().endsWith("/api/v2/documents"));
    await page.getByLabel("Choose PDF", { exact: true }).setInputFiles({
      name: "Deletion_Fence_Scan.pdf", mimeType: "application/pdf",
      buffer: fs.readFileSync(path.join(process.env.RAG_AWS_FIXTURES_DIR!, "Deletion_Fence_Scan.pdf")),
    });
    const raceUpload = await uploadSent; expect(raceUpload.status()).toBe(202);
    const raced = await raceUpload.json();
    await expect.poll(async () => (await (await page.request.get(`/api/v2/jobs/${raced.job_id}`)).json()).status,
      { timeout: 30_000, intervals: [50, 50, 100] }).toBe("running");
    expect((await mutation(page, `/api/v2/documents/${raced.document_id}`, "DELETE")).status).toBe(200);
    const cancelledJob = await (await page.request.get(`/api/v2/jobs/${raced.job_id}`)).json();
    expect(cancelledJob.status).toBe("cancelled");
    await expect.poll(async () => (await page.request.get(`/api/v2/documents/${raced.document_id}/file`)).status()).toBe(404);
    privateJson(path.join(output, "deletion-fence-result.json"), {
      status: "RUNNING_LEASE_CANCELLED", document_id: raced.document_id, job_id: raced.job_id,
      observed_before_delete: "running", observed_after_delete: cancelledJob.status,
      verification: "Live worker cancellation observed; lead readonly chunk probe follows the worker's cancellation check",
    });
    result.deletion_fence = { document_id: raced.document_id, job_id: raced.job_id, observed_before_delete: "running", observed_after_delete: cancelledJob.status };
    const provenance = `/api/v2/conversations/${state.memory.conversation_id}/memories/${state.memory.memory_id}/sources`;
    expect((await page.request.get(provenance)).status()).toBe(200);
    for (const document of Object.values(state.documents)) {
      expect((await mutation(page, `/api/v2/documents/${document.id}`, "DELETE")).status).toBe(200);
      expect((await page.request.get(`/api/v2/documents/${document.id}`)).status()).toBe(404);
      expect((await page.request.get(`/api/v2/documents/${document.id}/file`)).status()).toBe(404);
      expect((await mutation(page, `/api/v2/jobs/${document.job_id}/retry`, "POST")).status).toBe(404);
    }
    for (const cid of new Set(state.turns.map((turn) => turn.conversation_id))) {
      expect((await mutation(page, `/api/v2/conversations/${cid}`, "DELETE")).status).toBe(200);
      expect((await page.request.get(`/api/v2/conversations/${cid}`)).status()).toBe(404);
    }
    // Restarted durable workers have an opportunity to observe the tombstones;
    // the worker publication-fence suite independently exercises an old lease.
    await page.waitForTimeout(5000);
    expect((await page.request.get(`/api/v2/documents/${raced.document_id}`)).status()).toBe(404);
    expect((await (await page.request.get(`/api/v2/jobs/${raced.job_id}`)).json()).status).toBe("cancelled");
    for (const document of Object.values(state.documents)) expect((await page.request.get(`/api/v2/documents/${document.id}`)).status()).toBe(404);
    expect((await page.request.get(provenance)).status()).toBe(404);
    expect(chatPosts).toBe(0); result.chat_POSTs = chatPosts;
    result.status = "PASS"; result.persistence = "PASS"; result.deletion = "PASS";
    result.stale_worker = "A live running lease was cancelled by document deletion; job remained cancelled and the document stayed unavailable after five seconds. Lead readonly DB probe verifies no chunks were recreated.";
    await logout(page);
  } catch (error) { result.status = "FAIL"; result.failure_type = error instanceof Error ? error.name : "Unknown"; throw error; }
  finally { privateJson(path.join(output, "persistence-result.json"), result); }
});

test("AWS local Linux capacity: real OCR, sessions and ownership without a provider", async ({ browser, baseURL }, info) => {
  test.skip(process.env.RAG_AWS_LOCAL !== "1", "Explicit isolated Linux-stack check only");
  test.skip(info.project.name !== "desktop-chromium", "One bounded local fixture");
  test.setTimeout(240_000);
  const url = new URL(baseURL!);
  expect(url.protocol).toBe("https:"); expect(["127.0.0.1", "localhost"]).toContain(url.hostname);
  const output = process.env.RAG_AWS_EVIDENCE_DIR!;
  fs.mkdirSync(output, { recursive: true, mode: 0o700 });
  const local = await browser.newContext({ baseURL, ignoreHTTPSErrors: true });
  const page = await local.newPage();
  const marker = `aws-local-${Date.now()}`;
  const owner = `${marker}-a@example.test`, other = `${marker}-b@example.test`;
  const password = crypto.randomBytes(24).toString("base64url");
  const result: Record<string, unknown> = { run_id: marker, status: "RUNNING", provider_calls: 0, local_internal_CA: true };
  let chatPosts = 0;
  page.on("request", (request) => { if (request.method() === "POST" && request.url().endsWith("/api/v2/chat")) chatPosts++; });
  try {
    await register(page, owner, password); await login(page, owner, password);
    await page.goto("/documents");
    const sent = page.waitForResponse((response) => response.request().method() === "POST" && response.url().endsWith("/api/v2/documents"));
    await page.getByLabel("Choose PDF", { exact: true }).setInputFiles({
      name: `${marker}.pdf`, mimeType: "application/pdf",
      buffer: fs.readFileSync(path.join(process.env.RAG_AWS_FIXTURES_DIR!, "Browser_Check_Morgan_Vale.pdf")),
    });
    const response = await sent; expect(response.status()).toBe(202);
    const upload = await response.json(), did = upload.document_id;
    await expect.poll(async () => (await (await page.request.get(`/api/v2/documents/${did}`)).json()).status,
      { timeout: 180_000, intervals: [500, 1000, 2000] }).toBe("ready");
    const document = await (await page.request.get(`/api/v2/documents/${did}`)).json();
    expect(document.pages).toBe(2); expect(document.chunks).toBeGreaterThanOrEqual(2);
    expect(document.page_metadata.find((item: { page_number: number }) => item.page_number === 2).method).toBe("pymupdf-tesseract-fast-4.1.0");
    await page.goto(`/documents/${did}?page=2`);
    await expect(page.locator('canvas[data-rendered-page="2"]')).toHaveAttribute("data-render-state", "ready", { timeout: 30_000 });
    const created = await mutation(page, "/api/v2/conversations", "POST", { title: marker });
    expect(created.status).toBe(201); const cid = created.body.conversation_id;
    await logout(page); await register(page, other, password); await login(page, other, password);
    for (const route of [`/api/v2/documents/${did}`, `/api/v2/documents/${did}/file`, `/api/v2/jobs/${upload.job_id}`, `/api/v2/conversations/${cid}`, `/api/v2/memories?conversation_id=${cid}`]) {
      expect((await page.request.get(route)).status(), route).toBe(404);
    }
    expect(await (await page.request.get("/api/v2/documents")).json()).toEqual([]);
    await logout(page); await login(page, owner, password);
    expect((await mutation(page, `/api/v2/documents/${did}`, "DELETE")).status).toBe(200);
    expect((await mutation(page, `/api/v2/conversations/${cid}`, "DELETE")).status).toBe(200);
    expect((await page.request.get(`/api/v2/documents/${did}/file`)).status()).toBe(404);
    expect((await page.request.get(`/api/v2/conversations/${cid}`)).status()).toBe(404);
    expect(chatPosts).toBe(0);
    result.status = "PASS"; result.ocr = document.page_metadata; result.tenant_isolation = "PASS"; result.deletion = "PASS"; result.chat_POSTs = chatPosts;
    await logout(page);
  } catch (error) { result.status = "FAIL"; result.failure_type = error instanceof Error ? error.name : "Unknown"; throw error; }
  finally { privateJson(path.join(output, `${marker}-result.json`), result); await local.close(); }
});

test("AWS zero-provider isolation continuation after completed answer checks", async ({ page, baseURL }, info) => {
  test.skip(process.env.RAG_AWS_E2E_PHASE !== "isolation", "Explicit recovery of retained completed turns; no generation");
  test.skip(info.project.name !== "desktop-chromium", "One retained deployment identity");
  test.setTimeout(150_000);
  const output = process.env.RAG_AWS_EVIDENCE_DIR!;
  const source = process.env.RAG_AWS_FAILED_FROM!;
  const state = JSON.parse(fs.readFileSync(path.join(source, "failed-state.json"), "utf8")) as State;
  expect(state.base_url).toBe(baseURL);
  expect(state.turns.map((turn) => turn.id)).toEqual(staticPolicy.questions.map((question) => question.id));
  expect(state.turns.map((turn) => turn.answer_status)).toEqual(["answered", "answered", "answered", "answered", "partial"]);
  expect(state.owner_id).not.toBe(state.other_id); expect(state.other_id).toMatch(/^[a-f0-9-]{36}$/);
  fs.mkdirSync(output, { recursive: true, mode: 0o700 });
  const result: Record<string, unknown> = { run_id: state.run_id, execution: "ZERO_PROVIDER_CONTINUATION", original_failed_results_preserved: true, status: "RUNNING", provider_calls: 0 };
  let chatPosts = 0;
  page.on("request", (request) => { if (request.method() === "POST" && request.url().endsWith("/api/v2/chat")) chatPosts++; });
  try {
    await login(page, state.other, state.password);
    const denied: Record<string, number> = {};
    for (const document of Object.values(state.documents)) for (const route of [
      `/api/v2/documents/${document.id}`, `/api/v2/documents/${document.id}/file`, `/api/v2/jobs/${document.job_id}`,
    ]) { denied[route] = (await page.request.get(route)).status(); expect(denied[route], route).toBe(404); }
    for (const turn of state.turns) for (const route of [
      `/api/v2/conversations/${turn.conversation_id}`, `/api/v2/conversations/${turn.conversation_id}/turns/${turn.turn_id}`,
      `/api/v2/memories?conversation_id=${turn.conversation_id}`,
    ]) { denied[route] = (await page.request.get(route)).status(); expect(denied[route], route).toBe(404); }
    const provenance = `/api/v2/conversations/${state.memory.conversation_id}/memories/${state.memory.memory_id}/sources`;
    expect((await page.request.get(provenance)).status()).toBe(404);
    for (const route of ["documents", "conversations", "memories", "jobs"]) expect(await (await page.request.get(`/api/v2/${route}`)).json()).toEqual([]);
    expect((await mutation(page, "/api/v2/chat", "POST", { conversation_id: state.turns[0].conversation_id, turn_id: crypto.randomUUID(), message: "Unauthorized cross-owner query" })).status).toBe(404);
    expect(chatPosts).toBe(1); // Ownership rejects it before the generation path.
    await logout(page); await login(page, state.owner, state.password);
    for (const turn of state.turns) {
      const response = await page.request.get(`/api/v2/conversations/${turn.conversation_id}/turns/${turn.turn_id}`);
      expect(response.status()).toBe(200);
      const committed = await response.json(); expect(committed.answer).toBe(turn.answer); expect(committed.answer_status).toBe(turn.answer_status);
      expect(committed.citations).toEqual(turn.citations);
      await page.goto(`/chat?conversation=${turn.conversation_id}`);
      await savedAnswerUI(page, turn, state.turns);
      for (const citation of turn.citations) await expect(page.getByRole("log").getByRole("link", {
        name: new RegExp(`Open citation ${citation.ref}.*p\\. ${citation.page}`),
      }).first()).toHaveAttribute("href", `/api/v2/documents/${citation.document_id}/file#page=${citation.page}`);
      await page.reload(); await savedAnswerUI(page, turn, state.turns);
    }
    expect((await page.request.get(provenance)).status()).toBe(200);
    expect(chatPosts).toBe(1);
    await logout(page);
    result.status = "ISOLATION_HISTORY_PASS_RESTART_PENDING"; result.denied = denied;
    result.unauthorized_chat_POSTs = chatPosts; result.authorized_chat_POSTs = 0;
    privateJson(path.join(output, "retained-state.json"), state);
    privateJson(path.join(output, "tenant-state.json"), {
      run_id: state.run_id, owner: state.owner, other: state.other, owner_id: state.owner_id, other_id: state.other_id,
      documents: state.documents, memory: state.memory,
      turns: state.turns.map(({ conversation_id, turn_id }) => ({ conversation_id, turn_id })),
    });
  } catch (error) { result.status = "FAIL"; result.failure_type = error instanceof Error ? error.name : "Unknown"; throw error; }
  finally { privateJson(path.join(output, "isolation-result.json"), result); }
});
