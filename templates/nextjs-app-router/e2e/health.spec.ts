import { expect, test } from "@playwright/test";

test("GET /api/health returns { ok: true }", async ({ request }) => {
  const res = await request.get("/api/health");
  expect(res.ok()).toBeTruthy();
  const body = await res.json();
  expect(body).toMatchObject({ ok: true });
});

test("home page renders the scaffolded heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});
