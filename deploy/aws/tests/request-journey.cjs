/* One guarded, real Chromium journey. No raw answers, credentials or traces on disk. */
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const assert = require("node:assert/strict");
const { chromium, expect } = require(require.resolve("@playwright/test", {
  paths: [path.resolve(__dirname, "../../../frontend")],
}));
const policy = require("./request-reliability-policy.json");
const origin = "https://rag-demo.3-109-17-151.sslip.io";
const output = process.argv[2];
const bootstrap = JSON.parse(fs.readFileSync(path.join(output, "bootstrap.json")));
const cid = bootstrap.conversation_id;
const chatPath = "/chat?conversation=" + cid;
const historyPath = "/api/v2/conversations/" + cid;
const filePath = "/api/v2/documents/" + policy.document.id + "/file";
const hash = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");
const report = { run_id: policy.run_id, conversation: cid, turns: [], submitted: 0 };
const ordinaryReadback = process.argv[4] === "--readback";
const save = (name, data) => fs.writeFileSync(path.join(output, name), JSON.stringify(data, null, 2),
  { flag: "wx", mode: 0o600 });
let step = "login";

async function login(context, email, password) {
  const page = await context.newPage();
  await page.goto("/login");
  assert.equal(new URL(page.url()).origin, origin);
  await page.getByLabel("Email", {exact:true}).fill(email);
  await page.getByLabel("Password", {exact:true}).fill(password);
  await page.getByRole("button", {name:"Sign in",exact:true}).click();
  await page.waitForURL(origin + "/dashboard", {timeout:30_000});
  return page;
}

async function logout(page) {
  await page.evaluate(async () => {
    const csrf = document.cookie.split("; ").find((x) => x.startsWith("rag_csrf="))?.slice(9);
    if (csrf) await fetch("/api/v2/auth/logout", {method:"POST",headers:{"X-CSRF-Token":decodeURIComponent(csrf)}});
  });
}

async function guardedHistory(page) {
  const response = await page.request.get(historyPath);
  assert.equal(response.status(), 200);
  assert.equal(response.headers()["x-rag-browser-run-id"], policy.run_id);
  return {messages:(await response.json()).messages, headers:response.headers()};
}

function score(item, answer) {
  const citations = answer.citations ?? [];
  const text = answer.answer || "";
  const fromDocument = citations.length > 0 && citations.every((c) =>
    c.document_id === policy.document.id && Number.isInteger(c.chunk_id) && c.page > 0 && c.page <= 2);
  const fieldChecks = item.required.map((requirement) => new RegExp(requirement, "i").test(text));
  const inventedTeam = item.id === "two-fields" &&
    /\b(?:team(?: size)?\s*(?:is|was|of|:)?\s*\d+|\d+\s+(?:people|team members|engineers))\b/i.test(text);
  const derivation = !["months", "challenge"].includes(item.id) ||
    (answer.calculation?.total_months === 45 && answer.calculation.start === "2022-02" &&
     answer.calculation.end === "2025-11" && citations.some((c) =>
       c.chunk_id === answer.calculation.source_chunk_id && c.page === answer.calculation.source_page &&
       c.ref === answer.calculation.source_ref && c.document_id === answer.calculation.source_document));
  return {
    id:item.id, turn_id:answer.turn_id, answer_sha256:hash(text), status:answer.answer_status,
    evidence_pages:item.pages.every((p) => citations.some((c) => c.page === p && c.document_id === policy.document.id)),
    task_fulfilled:fieldChecks.every(Boolean) && !inventedTeam,
    grounding:fromDocument && derivation && citations.every((c) => text.includes("["+c.ref+"]")),
    status_correct:answer.answer_status === item.status,
    pages:citations.map((c) => c.page),
  };
}

async function rendered(page, index, item, answer) {
  const article = page.getByRole("log").locator("article").filter({
    has:page.getByRole("heading", {name:"RAG",exact:true}),
  }).nth(index);
  await expect(article).toBeVisible({timeout:125_000});
  await expect(article.getByText(answer.answer_status, {exact:true})).toBeVisible();
  for (const c of answer.citations) {
    const chip = article.getByRole("link", {name:new RegExp("Open citation " + c.ref + ".*p\\. " + c.page + "$")});
    await expect(chip).toHaveAttribute("href", filePath + "#page=" + c.page);
  }
  const visible = await article.innerText();
  return item.required.every((r) => new RegExp(r, "i").test(visible));
}

async function readOnlyIsolation(browser, statePath) {
  const state = JSON.parse(fs.readFileSync(statePath));
  assert.ok(state.other.endsWith("@example.test") && state.password);
  const second = await browser.newContext({baseURL:origin});
  try {
    const page = await login(second, state.other, state.password);
    try {
      for (const [route, hidden] of [["documents",policy.document.id],["conversations",cid]]) {
        const response = await page.request.get("/api/v2/" + route);
        assert.equal(response.status(), 200);
        const items = await response.json();
        assert.ok(Array.isArray(items) && items.every((item) => (item.id ?? item.conversation_id) !== hidden));
      }
      report.second_owner_collections_isolated = true;
    } finally { await logout(page); }
  } finally { await second.close(); }
}

async function readback(page) {
  const prior = JSON.parse(fs.readFileSync(path.join(output, "browser-result.json")));
  assert.equal(prior.passed, true);
  let attempted = 0;
  await page.route("**/api/v2/chat", async (route) => { attempted++; await route.abort(); });
  await page.goto(chatPath);
  const history = await page.request.get(historyPath);
  assert.equal(history.status(), 200);
  assert.equal(history.headers()["x-rag-browser-run-id"], undefined);
  const {messages} = await history.json();
  assert.equal(messages.length, policy.questions.length*2);
  for (let i=0;i<policy.questions.length;i++) {
    const item = policy.questions[i];
    const [user, assistant] = messages.slice(2*i,2*i+2);
    assert.equal(user.content,item.question);
    const answer = assistant.answer_metadata;
    assert.equal(answer.turn_id, prior.turns[i].turn_id);
    assert.equal(hash(assistant.content), prior.turns[i].answer_sha256);
    assert.equal(answer.answer, assistant.content);
    const row = score(item, answer);
    assert.ok(row.task_fulfilled && row.evidence_pages && row.status_correct && row.grounding);
    row.ui = await rendered(page, i, item, answer);
    assert.ok(row.ui);
    report.turns.push(row);
    if (item.id === "two-fields") {
      // The body is identified by the earlier synthetic pass, never general account content.
      console.log("Synthetic final turn:",answer.answer);
    }
  }
  assert.equal(attempted,0);
  report.normal_service_without_guard_header = true;
  report.passed = true;
}

async function run() {
  const lines = [];
  for await (const part of process.stdin) lines.push(part);
  const credentials = JSON.parse(Buffer.concat(lines).toString("utf8"));
  const browser = await chromium.launch();
  let page;
  try {
    const ctx = await browser.newContext({baseURL:origin,viewport:{width:1280,height:880}});
    page = await login(ctx, credentials.email, credentials.password);
    if (ordinaryReadback) {
      step = "ordinary-service readback";
      await readback(page);
      return;
    }
    step = "guarded preflight and source verification";
    assert.deepEqual((await guardedHistory(page)).messages, []);
    const pdf = await page.request.get(filePath);
    assert.equal(pdf.status(), 200);
    assert.equal(hash(await pdf.body()), policy.document.sha256);
    report.source_pdf_verified = true;
    await page.goto(chatPath);
    const answers = [];
    let next = null;
    await page.route("**/api/v2/chat", async (route) => {
      const request = route.request();
      const body = request.postDataJSON();
      if (request.method() !== "POST" || !next || body.conversation_id !== cid ||
          body.message !== next.question || typeof body.turn_id !== "string") {
        await route.abort();
        return;
      }
      // Retain the real UI's idempotency identity before it can reach the server.
      save("browser-turn-"+next.id+".json",{turn_id:body.turn_id,utc:new Date().toISOString()});
      next = null;
      report.submitted++;
      await route.continue();
    });
    for (let i=0; i<policy.questions.length; i++) {
      const item = policy.questions[i];
      step = item.id;
      if (item.id === "two-fields" && report.turns.some((r) =>
          !(r.evidence_pages && r.task_fulfilled && r.grounding && r.status_correct && r.ui))) {
        report.stopped = "earlier turn failed; independent generation not submitted";
        break;
      }
      const before = await guardedHistory(page);
      assert.equal(before.messages.length, 2*i);
      if (Number(before.headers["x-rag-provider-remaining"] ?? 1) <= 0) {
        report.stopped = "provider guard exhausted"; break;
      }
      await page.getByLabel("Your message").fill(item.question);
      // An exclusive claim survives an interrupted browser. No automatic resend.
      save("browser-claim-" + item.id + ".json", {id:item.id,utc:new Date().toISOString()});
      next = item;
      const start = performance.now();
      const [response] = await Promise.all([
        page.waitForResponse((r) => new URL(r.url()).pathname === "/api/v2/chat" &&
          r.request().method() === "POST", {timeout:130_000}),
        page.getByRole("button",{name:"Send",exact:true}).click(),
      ]);
      assert.equal(response.headers()["x-rag-browser-run-id"], policy.run_id);
      assert.equal(response.status(), 200);
      const answer = await response.json();
      assert.equal(answer.turn_id, response.request().postDataJSON().turn_id);
      assert.equal(answer.conversation_id, cid);
      answers.push(answer);
      const row = score(item, answer);
      report.turns.push(row);
      row.ui = await rendered(page,i,item,answer);
      row.latency_ms = Math.round(performance.now()-start);
      save("browser-result-" + item.id + ".json", row);
    }
    step = "reopen, refresh and source navigation";
    await page.goto("/conversations");
    await page.goto(chatPath);
    await page.reload();
    const {messages} = await guardedHistory(page);
    assert.equal(messages.length, answers.length*2);
    for (let i=0;i<answers.length;i++) {
      const [u,a] = messages.slice(2*i,2*i+2);
      const answer = answers[i];
      assert.equal(u.content,policy.questions[i].question);
      assert.equal(a.content,answer.answer);
      assert.equal(a.turn_id,answer.turn_id);
      assert.deepEqual(a.answer_metadata.citations,answer.citations);
      assert.equal(a.answer_metadata.answer_status,answer.answer_status);
      report.turns[i].reopened = await rendered(page,i,policy.questions[i],answer);
    }
    const firstCitation = page.getByRole("log").getByRole("link",{name:/^Open citation /}).first();
    const [opened] = await Promise.all([
      ctx.waitForEvent("response", {
        predicate:(r) => new URL(r.url()).pathname === filePath && [200,206].includes(r.status()),
        timeout:30_000,
      }),
      firstCitation.click(),
    ]);
    assert.ok((opened.headers()["content-type"] || "").includes("application/pdf"));
    report.citation_opened = true;
    for (const p of new Set(answers.flatMap((a)=>a.citations.map((c)=>c.page)))) {
      await page.goto("/documents/"+policy.document.id+"?page="+p);
      await expect(page.locator("canvas[data-rendered-page='"+p+"']")).toHaveAttribute("data-render-state","ready",{timeout:30_000});
    }
    report.pdf_rendered = true;
    step = "two-owner visibility";
    await readOnlyIsolation(browser, process.argv[3]);
    report.passed = answers.length === policy.questions.length && report.turns.every((r) =>
      r.evidence_pages && r.task_fulfilled && r.grounding && r.status_correct && r.ui && r.reopened);
  } finally {
    if (page) await logout(page).catch(() => {});
    await browser.close();
  }
}

run().catch((error) => {
  // Exception messages and Playwright assertion values may contain private page text.
  report.interruption = {step, type:error.name, location:error.stack?.match(/request-journey\.cjs:(\d+):/)?.[1]};
  report.passed = false;
}).finally(() => {
  save(ordinaryReadback ? "browser-ordinary-readback.json" : "browser-result.json",report);
  console.log(JSON.stringify(report));
  if (!report.passed) process.exitCode=1;
});
