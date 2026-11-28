import { expect, test, type Page } from "@playwright/test"

test.use({ locale: "zh-CN" })

async function isolated(page: Page, { member = false, region = true, signedIn = false } = {}) {
  const mutations: string[] = []
  await page.route(/https:\/\/(?!api\.example\.com).*/, route => route.abort())
  await page.route("https://api.example.com/**", route => {
    const path = new URL(route.request().url()).pathname
    if (route.request().method() !== "GET") {
      mutations.push(path)
      if (!path.endsWith("/auth/session")) throw new Error("Unexpected synthetic business request")
    }
    if (path.endsWith("/config")) return route.fulfill({ json: {
      country: region ? "US" : "CN", region_allowed: region,
      registration_enabled: false, recharge_enabled: false,
      uploads_enabled: false, generation_enabled: false,
      pilot_mode: true, pilot_registration_enabled: region,
      pilot_access_allowed: member, global_concurrent_limit: 1,
      products: [], global_real_remaining: 30,
    } })
    if (path.endsWith("/auth/session")) return route.fulfill({ json: { app_user: { id: "synthetic-pilot", nickname: "Offline Pilot" } } })
    if (path.endsWith("/wallet")) return route.fulfill({ json: { balance: 0, daily_remaining: 5, concurrent_remaining: 1, ledger: [] } })
    if (path.endsWith("/effect-catalog")) return route.fulfill({ json: { categories: [{ id: "category", slug: "kiss", name_zh: "测试分类", effects: [{ id: "effect", slug: "kiss-1", title_zh: "测试效果", input_image_count: 1, variants: [{ id: "variant", duration_seconds: 5, coin_cost: 12, is_default: true }] }] }] } })
    return route.fulfill({ json: { data: [] } })
  })
  await page.route("**/assets/vireal-auth.js", route => route.fulfill({ contentType: "application/javascript", body: `
    const clerk = {
      ${signedIn ? "session: {id:'synthetic-pilot-session', getToken: async () => 'synthetic-not-real'}, user: {id:'synthetic-pilot'}," : ""}
      addListener() {},
      mountSignIn(root, options) { document.documentElement.dataset.pilotSignupUrl = options.signUpUrl || ''; root.innerHTML = '<label>Offline email<input aria-label="Offline email"></label><button>Offline sign in</button>'; },
      mountSignUp(root) { root.innerHTML = '<label>Offline invited email<input aria-label="Offline invited email"></label><button>Offline invitation</button>'; },
      unmountSignIn(root) { root.innerHTML = ''; }, unmountSignUp(root) { root.innerHTML = ''; },
    }; window.VirealClerk = clerk; window.dispatchEvent(new CustomEvent('vireal:clerk-ready', {detail:clerk}));
  ` }))
  return mutations
}

test("pilot invite landing mounts signup and preserves invitation on sign-in", async ({ page }) => {
  const writes = await isolated(page)
  await page.goto("/?pilot=1#register")
  await expect(page.getByLabel("Offline invited email")).toBeVisible()
  await expect(page.locator("#app")).toContainText("最多5位受邀用户")
  await page.getByLabel("Offline invited email").fill("synthetic@example.com")
  await page.evaluate(() => { location.hash = "login" })
  await expect(page.getByLabel("Offline email")).toBeVisible()
  await expect(page.locator("html")).toHaveAttribute("data-pilot-signup-url", /\?pilot=1#register$/)
  expect(writes).toEqual([])
})

for (const scenario of ["public-url", "blocked-region"]) {
  test(`invitation link never expands public or regional signup: ${scenario}`, async ({ page }) => {
    const writes = await isolated(page, { region: scenario !== "blocked-region" })
    await page.goto(scenario === "public-url" ? "/#register" : "/?pilot=1#register")
    await expect(page.locator("#app")).toContainText(scenario === "public-url" ? "注册暂未开放" : "地区")
    await expect(page.getByLabel("Offline invited email")).toHaveCount(0)
    expect(writes).toEqual([])
  })
}

for (const member of [false, true]) {
  test(`closed business switches remain closed for pilot membership=${member}`, async ({ page }) => {
    const writes = await isolated(page, { signedIn: true, member })
    await page.goto("/#account")
    await expect(page.locator("#app")).toContainText("Offline Pilot")
    await page.goto("/#generate?video=kiss-1")
    await expect(page.locator("input[type=file], [data-generate]")).toHaveCount(0)
    await page.goto("/#wallet")
    await expect(page.locator("[data-recharge], [data-open-payment]")).toHaveCount(0)
    await expect(page.locator("#app")).toContainText("充值尚未开放")
    await page.reload()
    await expect(page.locator("#app")).toContainText("充值尚未开放")
    expect(writes.every(path => path.endsWith("/auth/session"))).toBe(true)
  })
}
