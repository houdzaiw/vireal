import { expect, type Page, test } from "@playwright/test"
import { firstSuperuser, firstSuperuserPassword } from "./config.ts"
import { logInUser } from "./utils/user.ts"

const apiUrl = process.env.VITE_API_URL ?? "http://localhost:8000"

interface TokenResponse {
  access_token: string
}

interface AppLoginResponse {
  access_token: string
  app_user: {
    id: string
  }
}

interface AppContentResponse {
  id: string
}

interface AppOrderResponse {
  id: string
  status: string
}

interface PaymentCallbackResponse {
  order: AppOrderResponse | null
  is_duplicate: boolean
}

function uniqueId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

async function requestJson<T>(
  path: string,
  init: RequestInit,
  token?: string,
): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`, {
    ...init,
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  })

  if (!response.ok) {
    throw new Error(
      `${init.method ?? "GET"} ${path} failed: ${response.status} ${await response.text()}`,
    )
  }

  return response.json() as Promise<T>
}

async function getAdminToken() {
  const body = new URLSearchParams()
  body.set("username", firstSuperuser)
  body.set("password", firstSuperuserPassword)

  const response = await fetch(`${apiUrl}/api/v1/login/access-token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  })

  if (!response.ok) {
    throw new Error(`Admin login failed: ${response.status}`)
  }

  const data = (await response.json()) as TokenResponse
  return data.access_token
}

async function createAppUser(nickname: string) {
  const login = await requestJson<AppLoginResponse>(
    "/api/v1/app/auth/device-login",
    {
      method: "POST",
      body: JSON.stringify({
        device_uuid: uniqueId("ios-e2e-device"),
        platform: "ios",
      }),
    },
  )

  await requestJson(
    "/api/v1/app/users/me",
    {
      method: "PATCH",
      body: JSON.stringify({ nickname }),
    },
    login.access_token,
  )

  return {
    appToken: login.access_token,
    appUserId: login.app_user.id,
  }
}

async function createAppContent(appToken: string, text: string) {
  return requestJson<AppContentResponse>(
    "/api/v1/app/contents/",
    {
      method: "POST",
      body: JSON.stringify({ text, image_urls: [] }),
    },
    appToken,
  )
}

async function createPaidOrder(appToken: string) {
  const productId = uniqueId("pro.monthly.e2e")
  const transactionId = uniqueId("tx-e2e")
  const eventId = uniqueId("event-e2e")
  const order = await requestJson<AppOrderResponse>(
    "/api/v1/app/orders",
    {
      method: "POST",
      body: JSON.stringify({
        provider: "apple",
        product_id: productId,
        amount: 990,
        currency: "USD",
      }),
    },
    appToken,
  )

  const callback = await requestJson<PaymentCallbackResponse>(
    "/api/v1/webhooks/payments/apple-iap",
    {
      method: "POST",
      body: JSON.stringify({
        order_id: order.id,
        event_id: eventId,
        event_type: "DID_RENEW",
        status: "paid",
        transaction_id: transactionId,
        raw_data: { source: "playwright" },
      }),
    },
  )

  expect(callback.order?.status).toBe("paid")

  return {
    eventId,
    productId,
    transactionId,
  }
}

async function openRowActions(page: Page, rowText: string) {
  const row = page.getByRole("row").filter({ hasText: rowText })
  await expect(row).toBeVisible()
  await row.getByRole("button", { name: "Open actions" }).click()
  return row
}

test.describe("App admin pages", () => {
  test("Admin can create, edit, and disable App configs", async ({ page }) => {
    const key = uniqueId("e2e_config")
    const updatedValue = uniqueId("updated")

    await page.goto("/app-configs")
    await expect(
      page.getByRole("heading", { name: "App Configs", exact: true }),
    ).toBeVisible()

    await page.getByRole("button", { name: "Add Config" }).click()
    await page.getByLabel("Key").fill(key)
    await page.getByLabel("Value").fill("on")
    await page.getByLabel("Description").fill("Created by Playwright")
    await page.getByRole("button", { name: "Save" }).click()

    await expect(page.getByText("Config created successfully")).toBeVisible()

    let row = page.getByRole("row").filter({ hasText: key })
    await expect(row).toBeVisible()
    await expect(row.getByText("Enabled", { exact: true })).toBeVisible()

    await row.getByRole("button", { name: "Open actions" }).click()
    await page.getByRole("menuitem", { name: "Edit Config" }).click()
    await page.getByLabel("Value").fill(updatedValue)
    await page.getByRole("button", { name: "Save" }).click()

    await expect(page.getByText("Config updated successfully")).toBeVisible()
    row = page.getByRole("row").filter({ hasText: key })
    await expect(row.getByText(updatedValue)).toBeVisible()

    await row.getByRole("button", { name: "Open actions" }).click()
    await page.getByRole("menuitem", { name: "Disable Config" }).click()
    await page.getByRole("button", { name: "Disable" }).click()

    await expect(page.getByText("Config disabled successfully")).toBeVisible()
    await expect(row.getByText("Disabled", { exact: true })).toBeVisible()
  })

  test("Admin can disable and re-enable an App user", async ({ page }) => {
    const nickname = uniqueId("App User E2E")
    await createAppUser(nickname)

    await page.goto("/app-users")
    await expect(
      page.getByRole("heading", { name: "App Users", exact: true }),
    ).toBeVisible()

    let row = await openRowActions(page, nickname)
    await page.getByRole("menuitem", { name: "Disable User" }).click()
    await page.getByRole("button", { name: "Disable" }).click()

    await expect(page.getByText("App user disabled successfully")).toBeVisible()
    await expect(row.getByText("disabled")).toBeVisible()

    row = await openRowActions(page, nickname)
    await page.getByRole("menuitem", { name: "Enable User" }).click()
    await page.getByRole("button", { name: "Enable" }).click()

    await expect(page.getByText("App user enabled successfully")).toBeVisible()
    await expect(row.getByText("active")).toBeVisible()
  })

  test("Admin can delete App content from the content page", async ({
    page,
  }) => {
    const nickname = uniqueId("Content User E2E")
    const contentText = uniqueId("content e2e")
    const { appToken } = await createAppUser(nickname)
    await createAppContent(appToken, contentText)

    await page.goto("/app-contents")
    await expect(
      page.getByRole("heading", { name: "App Contents", exact: true }),
    ).toBeVisible()

    const row = await openRowActions(page, contentText)
    await page.getByRole("menuitem", { name: "Delete Content" }).click()
    await page.getByRole("button", { name: "Delete" }).click()

    await expect(page.getByText("Content deleted successfully")).toBeVisible()
    await expect(row).not.toBeVisible()
  })

  test("Admin can inspect payment order events", async ({ page }) => {
    const nickname = uniqueId("Order User E2E")
    const { appToken } = await createAppUser(nickname)
    const { eventId, productId, transactionId } =
      await createPaidOrder(appToken)

    await page.goto("/app-orders")
    await expect(
      page.getByRole("heading", { name: "App Orders", exact: true }),
    ).toBeVisible()

    const row = page.getByRole("row").filter({ hasText: productId })
    await expect(row).toBeVisible()
    await expect(row.getByText("paid")).toBeVisible()
    await row.getByRole("button", { name: "View events" }).click()

    await expect(
      page.getByRole("heading", { name: "Order Events" }),
    ).toBeVisible()
    await expect(page.locator("dd").filter({ hasText: eventId })).toBeVisible()
    await expect(
      page.locator("dd").filter({ hasText: transactionId }),
    ).toBeVisible()
    await expect(
      page.locator("span").filter({ hasText: "DID_RENEW" }),
    ).toBeVisible()
  })

  test("Admin can review App operation logs", async ({ page }) => {
    const adminToken = await getAdminToken()
    const key = uniqueId("e2e_log_config")

    await requestJson(
      "/api/v1/admin/app/configs",
      {
        method: "POST",
        body: JSON.stringify({
          key,
          value: "on",
          description: "Created for operation log E2E",
          is_enabled: true,
        }),
      },
      adminToken,
    )

    await page.goto("/app-operation-logs")
    await expect(
      page.getByRole("heading", { name: "App Logs", exact: true }),
    ).toBeVisible()

    const row = page.getByRole("row").filter({ hasText: key })
    await expect(row).toBeVisible()
    await expect(row.getByText("app_config.create")).toBeVisible()
    await row.getByRole("button", { name: "View operation details" }).click()

    await expect(
      page.getByRole("heading", { name: "Operation Details" }),
    ).toBeVisible()
    await expect(page.locator("pre").filter({ hasText: key })).toBeVisible()
    await expect(
      page.getByRole("dialog").getByText(firstSuperuser),
    ).toBeVisible()
  })

  test("Admin can publish an effect, upload media, grant coins, and audit it", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      Object.defineProperty(crypto, "randomUUID", { value: undefined })
    })
    const categorySlug = uniqueId("e2e-effects")
    const categoryName = uniqueId("效果分类")
    const nickname = uniqueId("Wallet User E2E")
    const { appUserId } = await createAppUser(nickname)

    await page.goto("/effect-categories")
    await expect(
      page.getByRole("heading", { name: "Effect Categories", exact: true }),
    ).toBeVisible()
    await page.getByRole("button", { name: "新建分类" }).click()
    const createForm = page
      .getByRole("button", { name: "保存" })
      .first()
      .locator("xpath=ancestor::div[contains(@class,'grid')][1]")
    await createForm.locator("input").nth(0).fill(categoryName)
    await createForm.locator("input").nth(1).fill("PLAYWRIGHT EFFECTS")
    await createForm.locator("input").nth(2).fill(categorySlug)
    await createForm.getByRole("button", { name: "保存" }).click()
    await expect(page.getByText("分类已保存")).toBeVisible()
    const categoryCard = page
      .locator('[data-slot="card"]')
      .filter({ has: page.locator(`input[value="${categorySlug}"]`) })
    await expect(categoryCard.getByText("3 个效果")).toBeVisible()

    await page.goto("/effects")
    await expect(
      page.getByRole("heading", { name: "Effects", exact: true }),
    ).toBeVisible()
    await page.locator("select").first().selectOption({ label: categoryName })
    const effectList = page
      .locator('[data-slot="card"]')
      .filter({ has: page.locator("select") })
      .first()
    await expect(effectList.getByRole("button")).toHaveCount(3)

    await page.getByRole("button", { name: "发布" }).click()
    await expect(page.getByText(/发布失败/)).toBeVisible()

    const posterUpload = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/v1/admin/app/media-assets") &&
        response.request().method() === "POST",
    )
    await page
      .locator("label")
      .filter({ hasText: "上传封面" })
      .locator('input[type="file"]')
      .setInputFiles({
        name: "poster.png",
        mimeType: "image/png",
        buffer: Buffer.from("89504e470d0a1a0a706c6179777269676874", "hex"),
      })
    expect((await posterUpload).ok()).toBeTruthy()
    await expect(page.getByText(/封面\s+已绑定/)).toBeVisible()
    const previewUpload = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/v1/admin/app/media-assets") &&
        response.request().method() === "POST",
    )
    await page
      .locator("label")
      .filter({ hasText: "上传预览视频" })
      .locator('input[type="file"]')
      .setInputFiles({
        name: "preview.mp4",
        mimeType: "video/mp4",
        buffer: Buffer.from("00000018667479706d703432766964656f", "hex"),
      })
    expect((await previewUpload).ok()).toBeTruthy()
    await expect(
      page.getByText(/封面\s+已绑定\s+·\s*视频\s+已绑定/),
    ).toBeVisible()
    await page.getByRole("button", { name: "保存", exact: true }).click()
    await expect(page.getByText("效果已保存")).toBeVisible()

    await page.getByRole("button", { name: "添加变体" }).click()
    await expect(page.getByText("已添加变体")).toBeVisible()
    await expect(page.locator("select").last()).toHaveValue("minimax/video-01")
    await page.getByRole("button", { name: "发布" }).click()
    await expect(page.getByText("效果已发布")).toBeVisible()
    await expect(page.getByText("published").first()).toBeVisible()

    await page.goto("/coin-wallet")
    await expect(
      page.getByRole("heading", { name: "Coin Wallet", exact: true }),
    ).toBeVisible()
    await page.getByLabel("App User ID", { exact: true }).fill(appUserId)
    await page.getByLabel("调整数量（可为负数）").fill("50")
    await page
      .getByPlaceholder("例如：活动赠送 / 客诉补偿")
      .fill("Playwright staging grant")
    const adjustment = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/v1/admin/app/coin-adjustments") &&
        response.request().method() === "POST",
    )
    await page.getByRole("button", { name: "确认调整" }).click()
    const adjustmentResponse = await adjustment
    expect(adjustmentResponse.ok()).toBeTruthy()
    expect(await adjustmentResponse.json()).toMatchObject({
      balance: 50,
      applied: true,
    })
    await expect(page.getByText("调整成功，余额 50")).toBeVisible()

    await page.goto("/app-operation-logs")
    const auditRow = page
      .getByRole("row")
      .filter({ hasText: appUserId })
      .first()
    await expect(auditRow).toBeVisible()
    await expect(auditRow.getByText("coin.adjust")).toBeVisible()
  })

  test("Non-superuser cannot log in as an administrator or access App admin pages", async ({
    page,
  }) => {
    const adminToken = await getAdminToken()
    const email = `${uniqueId("app-admin-e2e")}@example.com`
    const password = "playwright123"

    await requestJson(
      "/api/v1/users/",
      {
        method: "POST",
        body: JSON.stringify({
          email,
          password,
          full_name: "App Admin E2E Non Superuser",
          is_active: true,
          is_superuser: false,
        }),
      },
      adminToken,
    )

    await page.goto("/")
    await page.evaluate(() => localStorage.removeItem("access_token"))
    await page.goto("/login")
    await page.getByTestId("email-input").fill(email)
    await page.getByTestId("password-input").fill(password)
    const deniedLogin = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/v1/admin/login/access-token") &&
        response.request().method() === "POST",
    )
    await page.getByRole("button", { name: "Log In" }).click()
    expect((await deniedLogin).status()).toBe(403)
    await expect(page).toHaveURL(/\/login$/)
    await expect
      .poll(() => page.evaluate(() => localStorage.getItem("access_token")))
      .toBeNull()

    await logInUser(page, email, password)

    await page.goto("/app-users")

    await expect(
      page.getByRole("heading", { name: "App Users", exact: true }),
    ).not.toBeVisible()
    await expect(page).not.toHaveURL(/\/app-users/)
  })
})
