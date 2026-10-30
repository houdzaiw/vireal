import { expect, test, type Page } from "@playwright/test"

test.use({ locale: "zh-CN" })

const flags = [
  "registration_enabled", "controlled_registration_enabled", "recharge_enabled",
  "uploads_enabled", "generation_enabled", "generation_acceptance_mode",
  "controlled_account_setup_mode", "payment_only_acceptance_mode",
  "internal_sign_in_enabled", "generation_acceptance_sign_in_enabled",
  "generation_acceptance_read_allowed", "generation_acceptance_allowed",
  "controlled_account_setup_enabled", "payment_only_sign_in_enabled",
  "payment_only_acceptance_allowed", "payment_only_order_created",
]
const config = (overrides = {}) => ({
  ...Object.fromEntries(flags.map(name => [name, false])),
  country: "CN", region_allowed: false, environment: "sandbox",
  staging_sign_in_enabled: true,
  staging_sign_in_expires_at: new Date(Date.now() + 20 * 60 * 1000).toISOString(),
  products: [], global_real_limit: 30, global_real_remaining: 30,
  ...overrides,
})

async function isolated(page: Page, options: { denied?: boolean; empty?: boolean; enabled?: boolean; expiry?: string;
  ordinaryHandoff?: boolean; pendingSync?: Promise<void>; signOutDuringSync?: boolean } = {}) {
  let current = config({ staging_sign_in_enabled: options.enabled !== false,
    ...(options.expiry ? { staging_sign_in_expires_at: options.expiry } : {}),
    ...(options.ordinaryHandoff ? { country: "US", region_allowed: true, staging_sign_in_enabled: false } : {}) })
  const writes: { path: string; marker: string | undefined }[] = []
  await page.route(/https:\/\/(?!api\.example\.com).*/, route => route.abort())
  await page.route("https://api.example.com/**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (request.method() !== "GET") writes.push({ path, marker: request.headers()["x-vireal-staging-login-acceptance"] })
    if (path.endsWith("/paypal/config")) return route.fulfill({ json: current })
    if (path.endsWith("/effect-catalog")) return route.fulfill({ json: { categories: [] } })
    if (path.endsWith("/auth/session")) {
      if (options.pendingSync) await options.pendingSync
      if (options.denied) return route.fulfill({ status: 403, json: { detail: "SYNTHETIC_PRIVATE_ACCOUNT_DETAIL" } })
      return route.fulfill({ json: { app_user: { id: "synthetic-staging-user", nickname: "QA" }, is_new_user: false } })
    }
    if (path.endsWith("/wallet")) return route.fulfill({ json: { balance: 0, ledger: [] } })
    return route.fulfill({ json: { data: [] } })
  })
  await page.route("**/assets/vireal-auth.js", route => route.fulfill({ contentType: "application/javascript", body: `
    const listeners = [];
    const clerk = {
      addListener(fn) {
        listeners.push(fn);
        if (${Boolean(options.ordinaryHandoff)}) fn({ session: null, user: null });
      },
      unmountSignIn(root) { root.innerHTML = '' },
      mountSignIn(root) {
        if (${Boolean(options.empty)}) return;
        root.innerHTML = '<label>Offline email<input aria-label="Offline email"></label><button type="button">模拟本人登录</button>';
        root.querySelector('button').onclick = () => {
          if (${Boolean(options.ordinaryHandoff)}) {
            const session = { id: 'synthetic-session', getToken: async () => 'synthetic-not-a-real-token' };
            const user = { id: 'synthetic-clerk-user' };
            for (let n = 0; n < 3; n++) for (const listener of listeners) listener({ session, user });
            location.hash = 'account';
            if (${Boolean(options.signOutDuringSync)}) setTimeout(() => {
              for (const listener of listeners) listener({ session: null, user: null });
            }, 50);
            return;
          }
          clerk.session = { id: 'synthetic-session', getToken: async () => 'synthetic-not-a-real-token' };
          clerk.user = { id: 'synthetic-clerk-user' };
          for (const listener of listeners) listener();
        };
      }
    };
    window.VirealClerk = clerk;
    window.dispatchEvent(new CustomEvent('vireal:clerk-ready', {detail: clerk}));
  ` }))
  return { writes, close() { current = { ...current, staging_sign_in_enabled: false } } }
}

test("private staging form requires the explicit server grant", async ({ page }) => {
  const api = await isolated(page, { enabled: false })
  await page.goto("/#staging-login")
  await expect(page.getByText("验收入口未开放或已过期。普通地区与业务限制保持不变。")).toBeVisible()
  await expect(page.getByRole("textbox")).toHaveCount(0)
  expect(api.writes).toEqual([])
})

test("staging form survives redraw, Clerk factor navigation and a full refresh", async ({ page }) => {
  const api = await isolated(page)
  await page.goto("/#staging-login")
  await expect(page.getByRole("heading", { name: "预发布短时登录验收" })).toBeVisible()
  await page.getByRole("textbox", { name: "Offline email" }).fill("synthetic@example.test")
  await page.goto(page.url().split("#")[0] + "#/factor-one")
  await expect(page.getByRole("textbox", { name: "Offline email" })).toHaveValue("synthetic@example.test")
  expect(new URL(page.url()).searchParams.get("staging_login_acceptance")).toBe("1")
  await page.reload()
  await expect(page.getByRole("textbox", { name: "Offline email" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "预发布短时登录验收" })).toBeVisible()
  await expect(page.getByRole("button", { name: /注册|生成|上传/ })).toHaveCount(0)
  expect(api.writes).toEqual([])
})

test("ordinary CN login and registration never borrow the staging exception", async ({ page }) => {
  const api = await isolated(page)
  for (const route of ["login", "register", "controlled-register"]) {
    await page.goto(`/#${route}`)
    await expect(page.getByRole("heading", { name: "当前地区暂未开放服务" })).toBeVisible()
    await expect(page.getByRole("textbox")).toHaveCount(0)
  }
  expect(api.writes).toEqual([])
})

test("only the simulated staging session request carries the marker", async ({ page }) => {
  const api = await isolated(page)
  await page.goto("/#staging-login")
  await page.getByRole("button", { name: "模拟本人登录" }).click()
  await expect(page).toHaveURL(url => url.hash === "#account" && !url.searchParams.has("staging_login_acceptance"))
  expect(new URL(page.url()).searchParams.has("staging_login_acceptance")).toBe(false)
  expect(api.writes).toEqual([{ path: "/api/v1/app/auth/session", marker: "1" }])
  // Read-only works navigation mentions generation; check the mutation controls.
  await expect(page.locator("[data-upload-index], [data-generate], [data-confirm-generation]")).toHaveCount(0)
})

test("denied subject does not enter account or expose provider details", async ({ page }) => {
  const api = await isolated(page, { denied: true })
  await page.goto("/#staging-login")
  await page.getByRole("button", { name: "模拟本人登录" }).click()
  await expect(page.getByText(/AUTH_SYNC_FAILED/)).toBeVisible()
  await expect(page.getByText("SYNTHETIC_PRIVATE_ACCOUNT_DETAIL")).toHaveCount(0)
  await expect(page).toHaveURL(/#staging-login$/)
  expect(api.writes).toEqual([{ path: "/api/v1/app/auth/session", marker: "1" }])
})

test("absolute expiry closes the form and refresh cannot renew its deadline", async ({ page }) => {
  const now = new Date("2030-01-01T00:00:00Z")
  await page.clock.install({ time: now })
  const api = await isolated(page, { expiry: "2030-01-01T00:20:00Z" })
  await page.goto("/#staging-login")
  await expect(page.getByRole("textbox")).toBeVisible()
  await page.clock.fastForward(20 * 60 * 1000 + 20)
  await expect(page.getByText("验收入口未开放或已过期。普通地区与业务限制保持不变。")).toBeVisible()
  await expect(page.getByRole("textbox")).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole("textbox")).toHaveCount(0)
  expect(api.writes).toEqual([])
})

test("leaving acceptance removes its routing flag without business requests", async ({ page }) => {
  const api = await isolated(page)
  await page.goto("/?unrelated=keep#staging-login")
  await expect(page.getByRole("textbox")).toBeVisible()
  await page.getByRole("button", { name: "结束验收并返回浏览" }).click()
  await expect(page).toHaveURL(url => url.hash === "#home" && !url.searchParams.has("staging_login_acceptance"))
  expect(new URL(page.url()).searchParams.get("unrelated")).toBe("keep")
  expect(new URL(page.url()).searchParams.has("staging_login_acceptance")).toBe(false)
  expect(api.writes).toEqual([])
})

test("staging form still reports an empty SDK mount as a timeout", async ({ page }) => {
  await page.clock.install()
  const api = await isolated(page, { empty: true })
  await page.goto("/#staging-login")
  await expect(page.locator("#clerkSignIn")).toBeAttached()
  await page.clock.fastForward(15010)
  await expect(page.getByText(/AUTH_FORM_TIMEOUT/)).toBeVisible()
  expect(api.writes).toEqual([])
})

test.describe("English staging form", () => {
  test.use({ locale: "en-US" })
  test("renders sign-in without opening any business action", async ({ page }) => {
    const api = await isolated(page)
    await page.goto("/#staging-login")
    await expect(page.getByRole("heading", { name: "Temporary staging sign-in acceptance" })).toBeVisible()
    await expect(page.getByRole("textbox", { name: "Offline email" })).toBeVisible()
    await expect(page.locator("[data-upload-index], [data-generate], [data-confirm-generation]")).toHaveCount(0)
    expect(api.writes).toEqual([])
  })
})

test("ordinary login hands emitted session to account without publishing SDK getters", async ({ page }) => {
  const api = await isolated(page, { ordinaryHandoff: true })
  await page.goto("/#login")
  await page.getByRole("textbox", { name: "Offline email" }).fill("synthetic@example.test")
  await page.getByRole("button", { name: "模拟本人登录" }).click()
  await expect(page.getByRole("heading", { name: "账户与偏好" })).toBeVisible()
  await expect(page.getByRole("textbox")).toHaveCount(0)
  await page.goto(page.url().split("#")[0] + "#works")
  await page.goto(page.url().split("#")[0] + "#account")
  await expect(page.getByRole("heading", { name: "账户与偏好" })).toBeVisible()
  expect(api.writes).toEqual([{ path: "/api/v1/app/auth/session", marker: undefined }])
  await expect(page.locator("[data-upload-index], [data-generate], [data-confirm-generation]")).toHaveCount(0)
})

test("slow App handoff removes the obsolete form without repeated sync on navigation", async ({ page }) => {
  let release!: () => void
  const pendingSync = new Promise<void>(resolve => { release = resolve })
  const api = await isolated(page, { ordinaryHandoff: true, pendingSync })
  try {
    await page.goto("/#login")
    await page.getByRole("button", { name: "模拟本人登录" }).click()
    await expect(page.getByText("正在同步登录状态…")).toBeVisible()
    await expect(page.getByRole("textbox")).toHaveCount(0)
    await page.goto(page.url().split("#")[0] + "#login")
    await page.goto(page.url().split("#")[0] + "#account")
    await expect.poll(() => api.writes.length).toBe(1)
    release()
    await expect(page.getByRole("heading", { name: "账户与偏好" })).toBeVisible()
    expect(api.writes).toEqual([{ path: "/api/v1/app/auth/session", marker: undefined }])
  } finally { release() }
})

test("signed-out emission cancels an in-flight handoff and restores sign-in", async ({ page }) => {
  let release!: () => void
  const pendingSync = new Promise<void>(resolve => { release = resolve })
  const api = await isolated(page, { ordinaryHandoff: true, pendingSync, signOutDuringSync: true })
  try {
    await page.goto("/#login")
    await page.getByRole("button", { name: "模拟本人登录" }).click()
    await expect.poll(() => api.writes.length).toBe(1)
    await expect(page.getByRole("textbox", { name: "Offline email" })).toBeVisible()
    const finished = page.waitForResponse(response => response.url().endsWith("/auth/session"))
    release(); await finished
    await page.goto(page.url().split("#")[0] + "#account")
    await expect(page.getByRole("textbox", { name: "Offline email" })).toBeVisible()
    await expect(page.getByRole("heading", { name: "账户与偏好" })).toHaveCount(0)
    expect(api.writes).toEqual([{ path: "/api/v1/app/auth/session", marker: undefined }])
  } finally { release() }
})
