import { expect, type Page, test } from "@playwright/test"

const first = "00000000-0000-4000-8000-000000000001"
const second = "00000000-0000-4000-8000-000000000002"

function user(id = first, account_type = "clerk") {
  return {
    id,
    email: `${id}@example.com`,
    nickname: id === first ? "Clerk wallet user" : "Other wallet user",
    account_type,
    auth_providers: [],
    email_verified: true,
    status: "active",
    login_count: 1,
  }
}

function ledger(delta = -28) {
  return {
    id: delta < 0 ? first : second,
    delta,
    balance_after: delta < 0 ? 72 : 100,
    entry_type: delta < 0 ? "generation_debit" : "recharge_credit",
    reason: "Local mocked fixture",
    order_id: delta > 0 ? second : null,
    task_id: delta < 0 ? first : null,
    created_at: "2026-10-18T13:08:41Z",
  }
}

function wallet(overrides: Record<string, unknown> = {}) {
  return {
    app_user_id: first,
    balance: 72,
    account_initialized: true,
    ledger: [ledger(), ledger(100)],
    count: 2,
    skip: 0,
    limit: 25,
    ...overrides,
  }
}

async function mock(page: Page, superuser = true) {
  const writes: string[] = []
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/") && request.method() !== "GET") {
      writes.push(request.url())
    }
  })
  await page.addInitScript(() =>
    localStorage.setItem("access_token", "local-readonly-test-token"),
  )
  await page.route("**/api/v1/**", (route) => {
    return route.fulfill({
      status: 404,
      json: { detail: "Only mocked local API is available" },
    })
  })
  await page.route("**/api/v1/users/me", (route) =>
    route.fulfill({
      json: {
        id: first,
        email: "admin@example.com",
        is_active: true,
        is_superuser: superuser,
      },
    }),
  )
  await page.route("**/api/v1/admin/app/users?**", (route) =>
    route.fulfill({ json: { data: [user(), user(second)], count: 2 } }),
  )
  await page.route(`**/api/v1/admin/app/users/${first}/wallet?**`, (route) =>
    route.fulfill({ json: wallet() }),
  )
  return writes
}

test("selection and refresh show current balance and linked immutable entries without a write", async ({
  page,
}) => {
  const writes = await mock(page)
  let reads = 0
  await page.route(`**/api/v1/admin/app/users/${first}/wallet?**`, (route) => {
    reads++
    return route.fulfill({ json: wallet() })
  })
  await page.goto("/coin-wallet")
  await expect(
    page.getByText(
      "选择用户或输入有效的 App User ID 后查看，不会创建账户或调整余额。",
    ),
  ).toBeVisible()
  await page.getByRole("button", { name: /Clerk wallet user/ }).click()
  await expect(page.getByTestId("wallet-current-balance")).toHaveText(
    "当前余额：72 金币",
  )
  await expect(
    page.getByRole("cell", { name: "recharge_credit", exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole("cell", { name: "generation_debit", exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole("cell", { name: "+100", exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole("cell", { name: "-28", exact: true }),
  ).toBeVisible()
  await expect(page.getByRole("button", { name: "确认调整" })).toBeDisabled()
  await page.getByRole("button", { name: "刷新余额与流水" }).click()
  await expect.poll(() => reads).toBe(2)
  expect(writes).toEqual([])
})

test("ledger pagination keeps the current balance separate from historical snapshots", async ({
  page,
}) => {
  const writes = await mock(page)
  const skips: string[] = []
  await page.route(`**/api/v1/admin/app/users/${first}/wallet?**`, (route) => {
    const skip = new URL(route.request().url()).searchParams.get("skip") ?? "0"
    skips.push(skip)
    return route.fulfill({
      json: wallet({
        count: 26,
        skip: Number(skip),
        ledger: [ledger(skip === "0" ? -28 : 100)],
      }),
    })
  })
  await page.goto("/coin-wallet")
  await page.getByRole("button", { name: /Clerk wallet user/ }).click()
  await expect(page.getByTestId("wallet-current-balance")).toHaveText(
    "当前余额：72 金币",
  )
  await page.getByRole("button", { name: "下一页" }).click()
  await expect(
    page.getByRole("cell", { name: "100", exact: true }),
  ).toBeVisible()
  await expect(page.getByTestId("wallet-current-balance")).toHaveText(
    "当前余额：72 金币",
  )
  await expect(page.getByRole("button", { name: "下一页" })).toBeDisabled()
  expect(skips).toEqual(["0", "25"])
  expect(writes).toEqual([])
})

test("uninitialized wallet is displayed without account initialization", async ({
  page,
}) => {
  const writes = await mock(page)
  await page.route(`**/api/v1/admin/app/users/${first}/wallet?**`, (route) =>
    route.fulfill({
      json: wallet({
        balance: 0,
        account_initialized: false,
        ledger: [],
        count: 0,
      }),
    }),
  )
  await page.goto("/coin-wallet")
  await page.getByRole("button", { name: /Clerk wallet user/ }).click()
  await expect(
    page.getByText("该用户尚未初始化金币账户；本次查看不会创建账户。"),
  ).toBeVisible()
  await expect(page.getByText("暂无流水。")).toBeVisible()
  expect(writes).toEqual([])
})

test("failed lookup after switching user never displays the previous user's balance", async ({
  page,
}) => {
  const writes = await mock(page)
  await page.route(`**/api/v1/admin/app/users/${second}/wallet?**`, (route) =>
    route.fulfill({ status: 500, json: { detail: "Mock unavailable" } }),
  )
  await page.goto("/coin-wallet")
  await page.getByRole("button", { name: /Clerk wallet user/ }).click()
  await expect(page.getByTestId("wallet-current-balance")).toBeVisible()
  await page.getByRole("button", { name: /Other wallet user/ }).click()
  await expect(page.getByRole("alert")).toContainText("未进行任何调整")
  await expect(page.getByTestId("wallet-current-balance")).toHaveCount(0)
  expect(writes).toEqual([])
})

test("empty Clerk provider list is not falsely labeled device", async ({
  page,
}) => {
  await mock(page)
  await page.route("**/api/v1/admin/app/users?**", (route) =>
    route.fulfill({
      json: { data: [user(), user(second, "legacy_test")], count: 2 },
    }),
  )
  await page.goto("/app-users")
  await expect(
    page.getByRole("cell", {
      name: "Clerk (method not returned)",
      exact: true,
    }),
  ).toBeVisible()
  await expect(
    page.getByRole("cell", { name: "Legacy test", exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole("cell", { name: "device", exact: true }),
  ).toHaveCount(0)
})

test("expired administrator authorization still clears the session and returns to login", async ({
  page,
}) => {
  await mock(page)
  await page.route(`**/api/v1/admin/app/users/${first}/wallet?**`, (route) =>
    route.fulfill({
      status: 403,
      json: { detail: "Mock expired administrator session" },
    }),
  )
  await page.goto("/coin-wallet")
  await page.getByRole("button", { name: /Clerk wallet user/ }).click()
  await expect(page).toHaveURL("http://127.0.0.1:5181/login")
  await expect(page.getByTestId("wallet-current-balance")).toHaveCount(0)
})

test("non-superuser is redirected before reading another user's wallet", async ({
  page,
}) => {
  await mock(page, false)
  let walletReads = 0
  await page.route("**/api/v1/admin/app/users/*/wallet?**", (route) => {
    walletReads++
    return route.fulfill({ status: 403, json: {} })
  })
  await page.goto("/coin-wallet")
  await expect(page).toHaveURL("http://127.0.0.1:5181/")
  expect(walletReads).toBe(0)
})
