import { test, expect } from "@playwright/test";
function pdf() {
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  const text =
    "BT /F1 16 Tf 50 700 Td (Synthetic browser upload fixture.) Tj ET";
  objects.push(`<< /Length ${text.length} >>\nstream\n${text}\nendstream`);
  let body = "%PDF-1.4\n";
  const offsets = [0];
  for (let index = 0; index < objects.length; index++) {
    offsets.push(Buffer.byteLength(body));
    body += `${index + 1} 0 obj\n${objects[index]}\nendobj\n`;
  }
  const xref = Buffer.byteLength(body);
  body += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets.slice(1))
    body += `${String(offset).padStart(10, "0")} 00000 n \n`;
  body += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return Buffer.from(body);
}
test("real API: register, session, upload/download, tenant denial, history and deletion (no provider)", async ({
  page,
}) => {
  test.skip(
    process.env.RAG_E2E_REAL !== "1",
    "Requires the configured scratch-only v2 API; no provider calls.",
  );
  const suffix = `${Date.now()}-${test.info().project.name}`;
  const owner = `browser-owner-${suffix}@example.test`,
    other = `browser-other-${suffix}@example.test`;
  const password = "Browser-only-password-738!";
  async function setup(email: string) {
    await page.goto("/register");
    await page.getByLabel("Name", { exact: true }).fill("Browser Tester");
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page
      .getByRole("button", { name: "Create account", exact: true })
      .click();
    await expect(page.getByRole("status")).toContainText("account is ready");
  }
  async function login(email: string) {
    await page.goto("/login");
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Hello, Browser Tester." }),
    ).toBeVisible();
  }
  async function logout() {
    if (test.info().project.name.startsWith("mobile"))
      await page.getByRole("button", { name: "Toggle navigation" }).click();
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login$/);
  }
  await setup(owner);
  await login(owner);
  await page.goto("/documents");
  const filename = `browser-${suffix}.pdf`;
  await page.getByLabel("Choose PDF", { exact: true }).setInputFiles({
    name: filename,
    mimeType: "application/pdf",
    buffer: pdf(),
  });
  await expect(
    page.getByRole("status").filter({ hasText: "Upload received" }),
  ).toBeVisible();
  await page.getByRole("link", { name: filename, exact: true }).click();
  await expect(
    page.getByRole("heading", { name: filename, exact: true }),
  ).toBeVisible();
  const docUrl = page.url();
  const did = docUrl.split("/").pop()!;
  const download = await page.request.get(`/api/v2/documents/${did}/file`);
  expect(download.status()).toBe(200);
  expect(download.headers()["content-type"]).toContain("application/pdf");
  // No chat endpoint is called: create a conversation via the real authenticated API,
  // then exercise its visible history/rename/delete controls without a provider.
  const conversation = await page.evaluate(async () => {
    const csrf =
      document.cookie
        .split("; ")
        .find((x) => x.startsWith("rag_csrf="))
        ?.split("=")[1] ?? "";
    const response = await fetch("/api/v2/conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify({ title: "Browser history fixture" }),
    });
    if (!response.ok) throw new Error("Conversation creation failed");
    return response.json();
  });
  await logout();
  await setup(other);
  await login(other);
  await page.goto(docUrl);
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "unavailable or you do not have access",
  );
  expect(
    (await page.request.get(`/api/v2/documents/${did}/file`)).status(),
  ).toBe(404);
  expect(
    (
      await page.request.get(
        `/api/v2/conversations/${conversation.conversation_id}`,
      )
    ).status(),
  ).toBe(404);
  await logout();
  await login(owner);
  await page.goto("/conversations");
  await page
    .getByRole("button", { name: "Rename Browser history fixture" })
    .click();
  const rename = page.getByRole("dialog", { name: "Rename conversation" });
  await rename.getByLabel("Conversation title").fill("Renamed browser fixture");
  await rename.getByRole("button", { name: "Save title" }).click();
  await expect(
    page
      .locator("main")
      .getByRole("link", { name: "Renamed browser fixture", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Delete Renamed browser fixture" })
    .click();
  const conversationDeleted = page.waitForResponse(
    (response) =>
      response.request().method() === "DELETE" &&
      response
        .url()
        .endsWith(`/api/v2/conversations/${conversation.conversation_id}`),
  );
  await page
    .getByRole("alertdialog", { name: "Delete conversation?" })
    .getByRole("button", { name: "Delete conversation", exact: true })
    .click();
  expect((await conversationDeleted).status()).toBe(200);
  await expect(
    page
      .locator("main")
      .getByRole("link", { name: "Renamed browser fixture", exact: true }),
  ).toHaveCount(0);
  await page.goto("/documents");
  await page
    .getByRole("button", { name: `Actions for ${filename}`, exact: true })
    .click();
  await page
    .getByRole("menuitem", { name: `Delete ${filename}`, exact: true })
    .click();
  const documentDeleted = page.waitForResponse(
    (response) =>
      response.request().method() === "DELETE" &&
      response.url().endsWith(`/api/v2/documents/${did}`),
  );
  await page
    .getByRole("alertdialog", { name: "Delete document?" })
    .getByRole("button", { name: "Delete document", exact: true })
    .click();
  expect((await documentDeleted).status()).toBe(200);
  await expect(
    page.getByRole("link", { name: filename, exact: true }),
  ).toHaveCount(0);
  expect(
    (await page.request.get(`/api/v2/documents/${did}/file`)).status(),
  ).toBe(404);
  await logout();
});
