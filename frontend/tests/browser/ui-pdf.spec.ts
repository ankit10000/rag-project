import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
test("authenticated PDF renderer paints original pages on desktop and mobile", async ({
  page,
  context,
}) => {
  test.skip(
    process.env.RAG_UI_RETAINED !== "1",
    "Explicit read-only retained scratch fixture",
  );
  test.setTimeout(60_000);
  const auth = JSON.parse(
    fs.readFileSync("/private/tmp/rag-ui-retained-session.json", "utf8"),
  );
  await context.addCookies([
    {
      name: "rag_session",
      value: auth.token,
      url: "http://127.0.0.1:3000",
      httpOnly: true,
      sameSite: "Strict",
    },
    {
      name: "rag_csrf",
      value: auth.csrf,
      url: "http://127.0.0.1:3000",
      sameSite: "Strict",
    },
  ]);
  const did = "567ee27b-074a-4d09-9af5-5dd796b8667e";
  const root = path.resolve("evidence/rag-grey-ui-20261120-live-01");
  const measurements: unknown[] = [];
  const remote: string[] = [];
  page.on("request", (r) => {
    const url = new URL(r.url());
    if (
      ["http:", "https:"].includes(url.protocol) &&
      url.origin !== "http://127.0.0.1:3000"
    )
      remote.push(url.origin);
  });
  async function painted(originalPage: number) {
    const canvas = page.locator("canvas[data-rendered-page]");
    await expect(canvas).toHaveAttribute("data-render-state", "ready", {
      timeout: 30_000,
    });
    await expect(canvas).toHaveAttribute(
      "data-rendered-page",
      String(originalPage),
    );
    const stats = await canvas.evaluate((element) => {
      const c = element as HTMLCanvasElement;
      const pixels = c
        .getContext("2d")!
        .getImageData(0, 0, c.width, c.height).data;
      let min = 255,
        max = 0;
      for (let p = 0; p < pixels.length; p += 64) {
        min = Math.min(min, pixels[p]);
        max = Math.max(max, pixels[p]);
      }
      return { width: c.width, height: c.height, min, max };
    });
    expect(stats.width).toBeGreaterThan(100);
    expect(stats.height).toBeGreaterThan(100);
    expect(stats.min).toBeLessThan(100);
    expect(stats.max).toBeGreaterThan(230);
    measurements.push({ originalPage, ...stats });
    return canvas;
  }
  await page.goto(`/documents/${did}?page=2`);
  await painted(2);
  await expect(
    page.getByRole("link", { name: "Open PDF", exact: true }),
  ).toHaveAttribute("href", `/api/v2/documents/${did}/file#page=2`);
  await page.screenshot({
    path: path.join(root, "pdf-rendered-page2-desktop-verified.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Previous page", exact: true })
    .click();
  await painted(1);
  await page.getByRole("button", { name: "Next page", exact: true }).click();
  await painted(2);
  await page.setViewportSize({ width: 390, height: 844 });
  // Wait for ResizeObserver and the canvas repaint, not merely the old ready flag.
  await expect
    .poll(async () =>
      page
        .locator("canvas")
        .evaluate((element) => (element as HTMLCanvasElement).width),
    )
    .toBeLessThan(780);
  await painted(2);
  const aspect = await page.locator("canvas").evaluate((element) => {
    const c = element as HTMLCanvasElement;
    const rect = c.getBoundingClientRect();
    return Math.abs(rect.height / rect.width - c.height / c.width);
  });
  expect(aspect).toBeLessThan(0.02);
  await expect
    .poll(async () =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBe(true);
  await page.screenshot({
    path: path.join(root, "pdf-rendered-page2-mobile-verified.png"),
    fullPage: true,
  });
  await page.getByRole("link", { name: "Documents", exact: true }).click();
  expect(remote).toEqual([]);
  fs.writeFileSync(
    path.resolve(
      "../v2_evidence/ui-grey-20261120/pdf-render-result-verified.json",
    ),
    JSON.stringify(
      {
        status: "PASS",
        measurements,
        remote_requests: remote,
        source_document_id: did,
        original_pages: [2, 1, 2, 2],
        provider_calls: 0,
      },
      null,
      2,
    ),
    { flag: "wx", mode: 0o600 },
  );
});
