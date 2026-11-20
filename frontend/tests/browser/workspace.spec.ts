import { test, expect } from "@playwright/test";
import {
  fixtureUser,
  fixtureDocument,
  installUIFixture,
} from "./ui-contract-fixture";

test.describe("Browser UI contract fixtures (not database integration)", () => {
  test.beforeEach(async ({ page }) => {
    await installUIFixture(page);
  });
  test("login, tenant dashboard, navigation and logout", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email", { exact: true }).fill(fixtureUser.email);
    await page
      .getByLabel("Password", { exact: true })
      .fill("testing-password-123");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Hello, Avery." }),
    ).toBeVisible();
    if (test.info().project.name.startsWith("mobile"))
      await page.getByRole("button", { name: "Toggle navigation" }).click();
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login$/);
  });
  test("canonical answer status and citation metadata survive reopen and refresh", async ({
    page,
  }) => {
    await page.goto("/chat");
    await page.getByLabel("Your message").fill("What does a permit cost?");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.getByText("answered", { exact: true })).toBeVisible();
    const chip = page.getByRole("link", { name: /Open citation S1/ });
    await expect(chip).toHaveAttribute(
      "href",
      `/api/v2/documents/${fixtureDocument.id}/file#page=2`,
    );
    await expect(
      page.getByText("The permit costs 71 tokens [S1].", { exact: true }),
    ).toBeVisible();
    for (let turn = 0; turn < 2; turn++) {
      await page.getByLabel("Your message").fill(`Follow-up ${turn}`);
      await page.getByRole("button", { name: "Send", exact: true }).click();
      await expect(page.getByRole("log").locator("article")).toHaveCount(
        (turn + 2) * 2,
      );
    }
    await expect
      .poll(async () => {
        const answer = await page
          .getByRole("log")
          .locator("article")
          .last()
          .boundingBox();
        const composer = await page.locator("form").boundingBox();
        return Boolean(
          answer && composer && answer.y + answer.height <= composer.y + 1,
        );
      })
      .toBe(true);
    await page.reload();
    await expect(page.getByRole("log").locator("article")).toHaveCount(6);
    await expect(chip).toHaveCount(3);
    await expect(page.getByText("answered", { exact: true })).toHaveCount(3);
    await page.screenshot({
      path: test.info().outputPath("chat-layout.png"),
      fullPage: true,
    });
  });
  test("permission errors do not render private response details", async ({
    page,
  }) => {
    await page.route("**/api/v2/documents/private", (route) =>
      route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({
          error: { code: "not_found", message: "SECRET another tenant's PDF" },
        }),
      }),
    );
    await page.goto("/documents/private");
    await expect(page.locator("main").getByRole("alert")).toContainText(
      "unavailable or you do not have access",
    );
    await expect(page.locator("body")).not.toContainText("SECRET");
  });
  test("responsive shell supports keyboard skip link and no horizontal overflow", async ({
    page,
  }) => {
    await page.goto("/dashboard");
    await expect(
      page.getByRole("heading", { name: "Hello, Avery." }),
    ).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(
      page.getByRole("link", { name: "Skip to content" }),
    ).toBeFocused();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });
  test("mobile drawer traps focus and Escape restores its trigger", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/chat");
    const trigger = page.getByRole("button", { name: "Toggle navigation" });
    await trigger.click();
    const drawer = page.getByRole("dialog", { name: "Workspace navigation" });
    await expect(drawer).toBeVisible();
    for (let count = 0; count < 14; count++) {
      await page.keyboard.press("Tab");
      expect(
        await page.evaluate(
          () => !!document.activeElement?.closest('[role="dialog"]'),
        ),
      ).toBe(true);
    }
    await page.keyboard.press("Escape");
    await expect(drawer).not.toBeVisible();
    await expect(trigger).toBeFocused();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });
  test("desktop sidebar collapse and coherent light appearance persist", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/chat");
    await page.getByRole("button", { name: "Use light mode" }).click();
    await expect(page.locator("html")).not.toHaveClass(/dark/);
    await page.getByRole("button", { name: "Collapse sidebar" }).click();
    await expect(
      page.getByRole("button", { name: "Expand sidebar" }),
    ).toBeVisible();
    await page.reload();
    await expect(page.locator("html")).not.toHaveClass(/dark/);
    await expect(
      page.getByRole("button", { name: "Expand sidebar" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Expand sidebar" }).click();
    await expect(
      page.getByRole("region", { name: "Recent chats" }),
    ).toBeVisible();
  });
  test("conversation search, rename and delete use real contract-shaped state", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/chat");
    await page
      .getByRole("button", { name: "Search conversations", exact: true })
      .click();
    const search = page.getByRole("dialog", { name: "Search conversations" });
    await search.getByLabel("Search conversations").fill("Orbital");
    await expect(
      search.getByRole("listitem").filter({ hasText: "Orbital research" }),
    ).toBeVisible();
    await expect(
      search.getByRole("listitem").filter({ hasText: "Meeting notes" }),
    ).toHaveCount(0);
    await page.keyboard.press("Escape");
    const recent = page.getByRole("region", { name: "Recent chats" });
    await recent
      .getByRole("link", { name: "Orbital research", exact: true })
      .hover();
    await recent
      .getByRole("button", { name: "Actions for Orbital research" })
      .click();
    await page.getByRole("menuitem", { name: "Rename", exact: true }).click();
    const rename = page.getByRole("dialog", { name: "Rename conversation" });
    await rename.getByLabel("Conversation title").fill("Renamed orbital notes");
    await rename.getByRole("button", { name: "Save title" }).click();
    await expect(
      recent.getByRole("link", { name: "Renamed orbital notes", exact: true }),
    ).toBeVisible();
    await recent
      .getByRole("link", { name: "Renamed orbital notes", exact: true })
      .hover();
    await recent
      .getByRole("button", { name: "Actions for Renamed orbital notes" })
      .click();
    await page.getByRole("menuitem", { name: "Delete", exact: true }).click();
    const remove = page.getByRole("alertdialog", {
      name: "Delete conversation?",
    });
    await remove.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(
      recent.getByRole("link", { name: "Renamed orbital notes", exact: true }),
    ).toBeVisible();
    await recent
      .getByRole("button", { name: "Actions for Renamed orbital notes" })
      .click();
    await page.getByRole("menuitem", { name: "Delete", exact: true }).click();
    await remove
      .getByRole("button", { name: "Delete conversation", exact: true })
      .click();
    await expect(
      recent.getByRole("link", { name: "Renamed orbital notes", exact: true }),
    ).toHaveCount(0);
  });
  test("tablet and phone screens retain readable composer without page overflow", async ({
    page,
  }) => {
    for (const width of [1024, 768, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/chat");
      await expect(page.getByLabel("Your message")).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      const composer = await page.locator("form").boundingBox();
      expect(composer && composer.y + composer.height <= 900).toBeTruthy();
    }
  });
});
