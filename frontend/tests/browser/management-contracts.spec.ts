import { test, expect } from "@playwright/test";
import { fixtureUser, installUIFixture } from "./ui-contract-fixture";

test.describe("Management UI contracts (mocked API, no database or providers)", () => {
  test.beforeEach(async ({ page }) => {
    await installUIFixture(page);
  });
  test("PDF validation prevents invalid uploads and shows real processing metadata", async ({
    page,
  }) => {
    let uploads = 0;
    page.on("request", (request) => {
      if (
        request.url().endsWith("/api/v2/documents") &&
        request.method() === "POST"
      )
        uploads++;
    });
    await page.goto("/documents");
    await expect(
      page.getByRole("link", { name: "observatory.pdf", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("1 native · 1 OCR page", { exact: true }),
    ).toBeVisible();
    await page.getByLabel("Choose PDF", { exact: true }).setInputFiles({
      name: "unsafe.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("not PDF"),
    });
    await expect(page.locator("main").getByRole("alert")).toContainText(
      "Choose a PDF file",
    );
    await page.getByLabel("Choose PDF", { exact: true }).setInputFiles({
      name: "empty.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.alloc(0),
    });
    await expect(page.locator("main").getByRole("alert")).toContainText(
      "This PDF is empty",
    );
    expect(uploads).toBe(0);
  });
  test("saved memory search, provenance and forget confirmation reflect the API", async ({
    page,
  }) => {
    const cid = "a0000000-0000-4000-8000-000000000001";
    let removed = false;
    await page.route("**/api/v2/memories?**", (route) =>
      route.fulfill({
        json: [
          {
            conversation_id: cid,
            memories: removed
              ? []
              : [
                  {
                    memory_id: 33,
                    memory: "Prefers concise source-supported answers.",
                    category: "preference",
                    provenance: "USER_SUPPORTED",
                    source_message_ids: [17],
                  },
                ],
            unverified_hidden: 0,
          },
        ],
      }),
    );
    await page.route(
      `**/api/v2/conversations/${cid}/memories/33/sources`,
      (route) =>
        route.fulfill({
          json: [{ message_id: 17, role: "user", link_kind: "USER_SOURCE" }],
        }),
    );
    await page.route(`**/api/v2/conversations/${cid}/memories/33`, (route) => {
      removed = true;
      return route.fulfill({ json: { deleted: true } });
    });
    await page.goto("/memories");
    await page.getByLabel("Conversation", { exact: true }).selectOption(cid);
    await expect(
      page.getByText("Prefers concise source-supported answers.", {
        exact: true,
      }),
    ).toBeVisible();
    await page.getByLabel("Search saved memories").fill("absent");
    await expect(
      page.getByText("No saved memories match your search."),
    ).toBeVisible();
    await page.getByLabel("Search saved memories").fill("concise");
    await page
      .getByRole("button", { name: "View sources for memory 33" })
      .click();
    const source = page.getByRole("dialog", { name: "Memory sources" });
    await expect(source.getByText("Message 17", { exact: true })).toBeVisible();
    await expect(
      source.getByText("user source", { exact: true }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Delete memory 33" }).click();
    const confirmation = page.getByRole("alertdialog", {
      name: "Delete and forget this memory?",
    });
    await confirmation
      .getByRole("button", { name: "Cancel", exact: true })
      .click();
    expect(removed).toBe(false);
    await page.getByRole("button", { name: "Delete memory 33" }).click();
    await confirmation
      .getByRole("button", { name: "Delete and forget", exact: true })
      .click();
    await expect(
      page.getByText("No saved memories match your search."),
    ).toBeVisible();
    expect(removed).toBe(true);
  });
  test("appearance settings persist and provider controls do not imply unsupported edits", async ({
    page,
  }) => {
    await page.goto("/settings");
    await expect(
      page.getByRole("heading", { name: "Model & provider" }),
    ).toBeVisible();
    await expect(
      page.getByText(/configuration is managed by your workspace/),
    ).toBeVisible();
    await page.getByRole("tab", { name: "Appearance", exact: true }).click();
    const light = page.getByRole("button", {
      name: "Light Soft, clear neutrals",
    });
    await light.click();
    await expect(light).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("html")).not.toHaveClass(/dark/);
    await page.reload();
    await expect(page.locator("html")).not.toHaveClass(/dark/);
    await page.getByRole("tab", { name: "Appearance", exact: true }).click();
    await expect(light).toHaveAttribute("aria-pressed", "true");
    await page
      .getByRole("button", { name: "Dark Charcoal and neutral grey" })
      .click();
    await expect(page.locator("html")).toHaveClass(/dark/);
  });
  test("ordinary users cannot see account-administration controls", async ({
    page,
  }) => {
    let adminFetches = 0;
    page.on("request", (request) => {
      if (request.url().includes("/api/v2/admin/")) adminFetches++;
    });
    await page.goto("/admin");
    await expect(page.locator("main").getByRole("alert")).toContainText(
      "administrators",
    );
    await expect(page.getByRole("button", { name: /Manage .*@/ })).toHaveCount(
      0,
    );
    expect(adminFetches).toBe(0);
  });
  test("administrator account changes require confirmation and refresh returned state", async ({
    page,
  }) => {
    const admin = { ...fixtureUser, role: "admin" };
    const other = {
      ...fixtureUser,
      id: "10000000-0000-4000-8000-000000000002",
      email: "other@example.test",
      display_name: "Other",
    };
    let changed = 0;
    await page.route("**/api/v2/auth/me", (route) =>
      route.fulfill({ json: admin }),
    );
    await page.route("**/api/v2/admin/users", (route) =>
      route.fulfill({ json: [admin, other] }),
    );
    await page.route(`**/api/v2/admin/users/${other.id}`, (route) => {
      Object.assign(other, route.request().postDataJSON());
      changed++;
      return route.fulfill({ json: other });
    });
    await page.goto("/admin");
    await page
      .getByRole("button", { name: "Manage other@example.test" })
      .click();
    await page
      .getByRole("menuitem", { name: "Disable account", exact: true })
      .click();
    const confirmation = page.getByRole("alertdialog", {
      name: "Disable account?",
    });
    await confirmation
      .getByRole("button", { name: "Cancel", exact: true })
      .click();
    expect(changed).toBe(0);
    await page
      .getByRole("button", { name: "Manage other@example.test" })
      .click();
    await page
      .getByRole("menuitem", { name: "Disable account", exact: true })
      .click();
    await confirmation
      .getByRole("button", { name: "Confirm change", exact: true })
      .click();
    await expect(
      page.getByRole("row").filter({ hasText: "other@example.test" }),
    ).toContainText("disabled");
    expect(changed).toBe(1);
  });
});
