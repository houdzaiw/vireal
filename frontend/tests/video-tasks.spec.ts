import { expect, type Page, test } from "@playwright/test"

const taskId = "00000000-0000-4000-8000-000000000001"
const userId = "00000000-0000-4000-8000-000000000002"

async function mockAdmin(page: Page, superuser = true) {
  await page.addInitScript(() =>
    localStorage.setItem("access_token", "qa-admin-token"),
  )
  await page.route("**/api/v1/**", (route) =>
    route.fulfill({ status: 404, json: { detail: "Mocked API only" } }),
  )
  await page.route("**/api/v1/users/me", (route) =>
    route.fulfill({
      json: {
        id: userId,
        email: "admin@example.com",
        is_active: true,
        is_superuser: superuser,
      },
    }),
  )
  await page.route("**/api/v1/admin/app/video-tasks?**", (route) =>
    route.fulfill({ json: { data: [task()], count: 1 } }),
  )
  await page.route(`**/api/v1/admin/app/video-tasks/${taskId}`, (route) =>
    route.fulfill({ json: task() }),
  )
}

function task(overrides: Record<string, unknown> = {}) {
  return {
    id: taskId,
    app_user_id: userId,
    effect_id: null,
    template_id: "dance-1",
    model: "wan-video/wan-2.7-r2v",
    provider: "replicate",
    provider_task_id: null,
    status: "submission_unknown",
    duration: 5,
    coin_cost_snapshot: 12,
    coin_refunded_at: null,
    provider_last_checked_at: null,
    provider_next_check_at: null,
    submission_attempted_at: new Date().toISOString(),
    real_submission_counted_at: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    completed_at: null,
    expires_at: new Date(Date.now() + 86400000).toISOString(),
    error: null,
    needs_review: true,
    ledger: [
      {
        id: "test-ledger",
        delta: -12,
        balance_after: 88,
        entry_type: "generation_debit",
        reason: "Mocked generation",
      },
    ],
    ...overrides,
  }
}

test("unknown task shows its ledger and prevents unchecked manual settlement", async ({
  page,
}) => {
  await mockAdmin(page)
  let requests = 0
  await page.route(
    `**/api/v1/admin/app/video-tasks/${taskId}/resolve`,
    async (route) => {
      const body = route.request().postDataJSON()
      expect(body).toMatchObject({
        resolution: "not_submitted",
        provider_confirmed: true,
      })
      expect(body.idempotency_key).toBeTruthy()
      expect(body).not.toHaveProperty("delta")
      expect(route.request().headers().authorization).toBe(
        "Bearer qa-admin-token",
      )
      requests++
      await route.fulfill({
        json: task({
          status: "failed",
          coin_refunded_at: new Date().toISOString(),
        }),
      })
    },
  )
  await page.goto("/video-tasks")
  await expect(
    page.getByText("共 1 条；显示最近 100 条，每分钟更新。", { exact: true }),
  ).toBeVisible()
  await page.getByRole("button", { name: /dance-1/ }).click()
  await expect(
    page.getByRole("button", { name: "核对供应商状态" }),
  ).toBeDisabled()
  const settle = page.getByRole("button", { name: "按原扣币记录结案" })
  await expect(settle).toBeDisabled()
  await page
    .getByLabel("操作原因（至少 5 字）")
    .fill("Supplier support confirmed original request was not accepted")
  await page
    .getByLabel("证据说明/供应商工单号（至少 10 字，勿填密钥或私人图片地址）")
    .fill("Supplier support ticket MOCK-001 confirms no accepted prediction")
  await expect(settle).toBeDisabled()
  await page.getByRole("checkbox").check()
  await settle.click()
  await expect.poll(() => requests).toBe(1)
  await expect(
    page.getByText("已审计结案，金币补偿仅按原扣币快照执行一次", {
      exact: true,
    }),
  ).toBeVisible()
})

test("reconciliation retries reuse the idempotency key and never create a generation", async ({
  page,
}) => {
  await mockAdmin(page)
  await page.route(`**/api/v1/admin/app/video-tasks/${taskId}`, (route) =>
    route.fulfill({
      json: task({ provider_task_id: "qa-existing-prediction" }),
    }),
  )
  const keys: string[] = []
  await page.route(
    `**/api/v1/admin/app/video-tasks/${taskId}/reconcile`,
    async (route) => {
      keys.push(route.request().postDataJSON().idempotency_key)
      await route.fulfill(
        keys.length === 1
          ? { status: 502, json: { detail: "Mock transient failure" } }
          : {
              json: task({
                status: "running",
                provider_task_id: "qa-existing-prediction",
              }),
            },
      )
    },
  )
  let generationCalls = 0
  await page.route("**/api/v1/app/video-tasks", async (route) => {
    generationCalls++
    await route.abort()
  })
  await page.goto("/video-tasks")
  await page.getByRole("button", { name: /dance-1/ }).click()
  await page
    .getByLabel("操作原因（至少 5 字）")
    .fill("Check existing supplier prediction after delayed callback")
  const reconcile = page.getByRole("button", { name: "核对供应商状态" })
  await reconcile.click()
  await expect.poll(() => keys.length).toBe(1)
  await expect(reconcile).toBeEnabled()
  await reconcile.click()
  await expect.poll(() => keys.length).toBe(2)
  expect(keys[0]).toBe(keys[1])
  expect(generationCalls).toBe(0)
})

test("non-superuser cannot open task operations", async ({ page }) => {
  await mockAdmin(page, false)
  await page.goto("/video-tasks")
  await expect(page).toHaveURL(/\/$/)
  await expect(
    page.getByRole("button", { name: "按原扣币记录结案" }),
  ).toHaveCount(0)
})
