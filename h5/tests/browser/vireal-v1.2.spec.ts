import { expect, test, type Page } from "@playwright/test"

const variants = [
  { id: "variant-5", duration_seconds: 5, coin_cost: 12, is_default: true },
  { id: "variant-10", duration_seconds: 10, coin_cost: 20, is_default: false },
]

const catalog = {
  categories: [
    {
      id: "category-kiss",
      slug: "kiss",
      name_zh: "亲吻",
      name_en: "KISS",
      tones: ["#8a4050", "#2b1728", "#d8908f"],
      sort_order: 10,
      effects: Array.from({ length: 4 }, (_, index) => ({
        id: `kiss-${index + 1}`,
        category_id: "category-kiss",
        category_slug: "kiss",
        slug: `kiss-${index + 1}`,
        title_zh: ["心动靠近", "温柔侧吻", "电影感拥吻", "雪夜相拥"][index],
        title_en: `KISS MOTION 0${index + 1}`,
        description: "保留人物身份特征，生成自然、克制、电影感的亲密时刻。",
        input_image_count: 2,
        poster_url: null,
        preview_video_url: null,
        sort_order: (index + 1) * 10,
        recommendation_label: "更多心动效果",
        variants,
        recommendations: [],
      })),
    },
    {
      id: "category-dance",
      slug: "dance",
      name_zh: "舞蹈",
      name_en: "DANCE",
      tones: ["#3e6f73", "#111d38", "#a2e8d6"],
      sort_order: 20,
      effects: [
        {
          id: "dance-1",
          category_id: "category-dance",
          category_slug: "dance",
          slug: "dance-1",
          title_zh: "节拍律动",
          title_en: "DANCE MOTION 01",
          description: "从一张照片生成流畅舞蹈。",
          input_image_count: 1,
          poster_url: null,
          preview_video_url: null,
          sort_order: 10,
          recommendation_label: null,
          variants,
          recommendations: [],
        },
      ],
    },
  ],
}

async function mockPublicApi(page: Page) {
  await page.route("https://api.example.com/**", async (route) => {
    await route.fulfill({ status: 401, contentType: "application/json", body: '{"detail":"Not authenticated"}' })
  })
  await page.route("https://api.example.com/api/v1/app/effect-catalog", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog) })
  })
  await page.route("https://api.example.com/api/v1/app/paypal/config", async (route) => {
    await route.fulfill({ json: { region_allowed: true, registration_enabled: false, recharge_enabled: false, products: [], global_real_limit: 30, global_real_remaining: 30, support_email: "li522903183@gmail.com" } })
  })
  await page.route(/https:\/\/(?!api\.example\.com).*/, async (route) => route.abort())
}

async function mockSignedInApi(page: Page) {
  await mockPublicApi(page)
  await page.route("**/assets/vireal-auth.js", async (route) => {
    await route.fulfill({
      contentType: "application/javascript",
      body: `window.VirealClerk = {
        session: {id: 'qa-session', getToken: async () => 'qa-session-token'},
        user: {id: 'qa-user'}, addListener() {},
      }; window.dispatchEvent(new CustomEvent('vireal:clerk-ready', {detail: window.VirealClerk}))`,
    })
  })
  await page.route("https://api.example.com/api/v1/app/auth/session", async (route) => {
    await route.fulfill({ json: { app_user: { id: "qa-app-user", nickname: "QA User" } } })
  })
  await page.route("https://api.example.com/api/v1/app/wallet", async (route) => {
    await route.fulfill({ json: { balance: 500, daily_remaining: 5, concurrent_remaining: 1, ledger: [] } })
  })
  await page.route("https://api.example.com/api/v1/app/video-tasks?**", async (route) => {
    await route.fulfill({ json: { data: [] } })
  })
  await page.route("https://api.example.com/api/v1/app/orders?**", async (route) => {
    await route.fulfill({ json: { data: [] } })
  })
}

const paymentConfig = {
  region_allowed: true, registration_enabled: true, recharge_enabled: true,
  client_id: "qa-sandbox-public", environment: "sandbox", global_real_limit: 30,
  global_real_remaining: 30, resets_at: "2026-10-09T00:00:00Z",
  support_email: "li522903183@gmail.com",
  products: [
    { product_id: "coins_100", coins: 100, amount: 599, currency: "USD" },
    { product_id: "coins_220", coins: 220, amount: 1199, currency: "USD" },
    { product_id: "coins_500", coins: 500, amount: 2499, currency: "USD" },
  ],
}

test("internal CN landing only mounts sign-in; signup and checkout stay closed", async ({ page }, testInfo) => {
  await mockControlledRegistration(page, false, false)
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({ json: {
    ...paymentConfig, region_allowed: false, internal_sign_in_enabled: true,
    registration_enabled: false, recharge_enabled: false, controlled_registration_enabled: false,
  } }))
  await page.goto("/?internal_acceptance=1#login")
  await expect(page.getByRole("heading", { name: "Internal acceptance sign-in" })).toBeVisible()
  await expect(page.locator("#clerkSignIn")).toContainText("Clerk login (UI mock)")
  await expect(page.locator("[data-route='register']")).toHaveCount(0)
  await page.evaluate(() => { location.hash = "/factor-one" })
  await expect(page.locator("#clerkSignIn")).toContainText("Clerk login (UI mock)")
  await page.screenshot({ path: testInfo.outputPath("internal-sign-in.png"), fullPage: true, animations: "disabled" })
  await page.evaluate(() => { location.hash = "register" })
  await expect(page.getByText("Service unavailable in this region", { exact: true })).toBeVisible()
  await expect(page.locator("#clerkSignIn")).toHaveCount(0)
})

for (const scenario of ["no-private-landing", "gate-off", "unknown-region", "config-unavailable"]) {
  test(`internal sign-in stays closed for ${scenario}`, async ({ page }) => {
    await mockControlledRegistration(page, false, false)
    await page.route("https://api.example.com/api/v1/app/paypal/config", route => scenario === "config-unavailable"
      ? route.fulfill({ status: 503, json: { detail: "Unavailable" } })
      : route.fulfill({ json: { region_allowed: false, internal_sign_in_enabled: scenario === "no-private-landing", registration_enabled: false, recharge_enabled: false } }))
    await page.goto(scenario === "no-private-landing" ? "/#login" : "/?internal_acceptance=1#login")
    if (scenario === "config-unavailable") await expect(page.locator("#clerkSignIn")).toBeEmpty()
    else await expect(page.locator("#clerkSignIn")).toHaveCount(0)
    await expect(page.getByText("Clerk login (UI mock)")).toHaveCount(0)
    await expect(page.getByText("Controlled Clerk signup (UI mock)")).toHaveCount(0)
  })
}

test("authenticated internal notice is server supplied, with zero wallet and no checkout", async ({ page }, testInfo) => {
  await mockSignedInApi(page)
  await page.route("https://api.example.com/api/v1/app/auth/session", route => route.fulfill({ json: {
    app_user: { id: "qa-app-user", nickname: "Internal QA" }, internal_generation_allowed: true,
  } }))
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({ json: {
    ...paymentConfig, region_allowed: false, internal_sign_in_enabled: true,
    registration_enabled: false, recharge_enabled: false,
  } }))
  await page.route("https://api.example.com/api/v1/app/wallet", route => route.fulfill({ json: { balance: 0, daily_remaining: 5, concurrent_remaining: 1, ledger: [] } }))
  const payments: string[] = []
  page.on("request", request => { if (request.url().includes("/paypal/orders") || request.url().includes("/web-sdk/v6")) payments.push(request.url()) })
  await page.goto("/?internal_acceptance=1#wallet")
  await expect(page.locator("[data-internal-acceptance]")).toContainText("not Live payment verification")
  await expect(page.locator(".wallet-card > strong")).toHaveText("0 ✦")
  await expect(page.locator("paypal-button")).toHaveCount(0)
  await expect(page.locator("[data-route='register']")).toHaveCount(0)
  expect(payments).toEqual([])
  await page.screenshot({ path: testInfo.outputPath("internal-wallet.png"), fullPage: true, animations: "disabled" })
})

test("private URL alone never grants an internal account notice", async ({ page }) => {
  await mockSignedInApi(page)
  await page.goto("/?internal_acceptance=1#wallet")
  await expect(page.locator(".wallet-card > strong")).toBeVisible()
  await expect(page.locator("[data-internal-acceptance]")).toHaveCount(0)
})

async function mockControlledRegistration(page: Page, regionAllowed = true, enabled = true) {
  await mockPublicApi(page)
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({ json: {
    region_allowed: regionAllowed, registration_enabled: false, recharge_enabled: false,
    controlled_registration_enabled: enabled, products: [], global_real_remaining: 30,
  } }))
  await page.route("**/assets/vireal-auth.js", route => route.fulfill({
    contentType: "application/javascript",
    body: `window.VirealClerk = {addListener() {},
      mountSignUp(root) { root.innerHTML = '<p>Controlled Clerk signup (UI mock)</p>'; document.body.dataset.signupMounts = String(Number(document.body.dataset.signupMounts || 0) + 1); },
      mountSignIn(root) { root.innerHTML = '<p>Clerk login (UI mock)</p>'; },
      unmountSignUp(root) { root.innerHTML = ''; }, unmountSignIn(root) { root.innerHTML = ''; },
    }; window.dispatchEvent(new CustomEvent('vireal:clerk-ready', {detail: window.VirealClerk}))`,
  }))
}

test("controlled invitation preserves the signup component through Clerk hash steps", async ({ page }) => {
  await mockControlledRegistration(page)
  await page.goto("/?controlled_registration=1&__clerk_ticket=isolated-ui-ticket")
  await expect(page.getByText("Controlled Clerk signup (UI mock)", { exact: true })).toBeVisible()
  await expect(page.getByText(/Public signup and recharge remain closed/)).toBeVisible()
  await page.evaluate(() => { location.hash = "/verify-email-address" })
  await expect(page.getByText("Controlled Clerk signup (UI mock)", { exact: true })).toBeVisible()
  await expect(page.locator("body")).toHaveAttribute("data-signup-mounts", "1")
  await page.reload()
  await expect(page.getByText("Controlled Clerk signup (UI mock)", { exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "New here? Register", exact: true })).toHaveCount(0)
  await page.goto("/#register")
  await expect(page.getByRole("heading", { name: "Registration is not yet open" })).toBeVisible()
  await expect(page.getByText("Controlled Clerk signup (UI mock)", { exact: true })).toHaveCount(0)
})

for (const scenario of ["blocked-region", "disabled-gate", "no-ticket", "bare-route"]) {
  test(`controlled signup fails closed for ${scenario}`, async ({ page }) => {
    await mockControlledRegistration(page, scenario !== "blocked-region", scenario !== "disabled-gate")
    const url = scenario === "bare-route" ? "/#controlled-register" : "/?controlled_registration=1" + (scenario === "no-ticket" ? "" : "&__clerk_ticket=isolated-ui-ticket")
    await page.goto(url)
    const heading = scenario === "blocked-region" ? "Service unavailable in this region" : "A valid controlled invitation is required"
    await expect(page.getByRole("heading", { name: heading })).toBeVisible()
    await expect(page.getByText("Controlled Clerk signup (UI mock)", { exact: true })).toHaveCount(0)
    await expect(page.locator("paypal-button")).toHaveCount(0)
  })
}

test("refreshing an invitation after the controlled gate closes cannot mount signup", async ({ page }) => {
  await mockControlledRegistration(page)
  await page.goto("/?controlled_registration=1&__clerk_ticket=isolated-ui-ticket")
  await expect(page.getByText("Controlled Clerk signup (UI mock)", { exact: true })).toBeVisible()
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({ json: {
    region_allowed: true, registration_enabled: false, recharge_enabled: false, controlled_registration_enabled: false,
  } }))
  // A reload fetches the current server gate, never trusts the invitation alone.
  await page.reload()
  await expect(page.getByRole("heading", { name: "A valid controlled invitation is required" })).toBeVisible()
  await expect(page.getByText("Controlled Clerk signup (UI mock)", { exact: true })).toHaveCount(0)
})

function cnSetupConfig(overrides = {}) {
  return {
    ...paymentConfig, country: "CN", region_allowed: false,
    registration_enabled: false, recharge_enabled: false,
    controlled_registration_enabled: true, controlled_account_setup_mode: true,
    controlled_account_setup_enabled: true,
    controlled_account_setup_expires_at: new Date(Date.now() + 60_000).toISOString(),
    ...overrides,
  }
}

test("CN account setup requires the private invitation and preserves verified-email steps", async ({ page }) => {
  await mockControlledRegistration(page, false)
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({ json: cnSetupConfig() }))
  await page.goto("/?controlled_registration=1&__clerk_ticket=isolated-ui-ticket")
  await expect(page.getByText("Controlled Clerk signup (UI mock)", { exact: true })).toBeVisible()
  await expect(page.getByText(/not overseas registration acceptance/)).toBeVisible()
  await page.evaluate(() => { location.hash = "/verify-email-address" })
  await expect(page.locator("body")).toHaveAttribute("data-signup-mounts", "1")
  await page.reload()
  await expect(page.getByText("Controlled Clerk signup (UI mock)", { exact: true })).toBeVisible()
  await expect(page.locator("paypal-button")).toHaveCount(0)
  await page.goto("/#register")
  await expect(page.getByRole("heading", { name: "Service unavailable in this region" })).toBeVisible()
  await expect(page.locator("#clerkSignIn")).toHaveCount(0)
})

test("CN private account sign-in stays sign-in across Clerk hash steps and reload", async ({ page }) => {
  await mockControlledRegistration(page, false)
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({ json: cnSetupConfig() }))
  await page.goto("/?controlled_account_setup=1#login")
  await expect(page.locator("#clerkSignIn")).toContainText("Clerk login (UI mock)")
  await page.evaluate(() => { location.hash = "/factor-one" })
  await page.reload()
  await expect(page.locator("#clerkSignIn")).toContainText("Clerk login (UI mock)")
  await expect(page.getByText("Controlled Clerk signup (UI mock)", { exact: true })).toHaveCount(0)
})

for (const scenario of ["no-private-url", "no-ticket", "unknown-region", "other-region", "disabled", "expired", "overlong", "invalid-expiry"]) {
  test(`CN account setup fails closed for ${scenario}`, async ({ page }) => {
    await mockControlledRegistration(page, false)
    const overrides = scenario === "unknown-region" ? {country: null}
      : scenario === "other-region" ? {country: "US", region_allowed: true}
      : scenario === "disabled" ? {controlled_account_setup_enabled: false}
      : scenario === "expired" ? {controlled_account_setup_expires_at: new Date(Date.now() - 1000).toISOString()}
      : scenario === "overlong" ? {controlled_account_setup_expires_at: new Date(Date.now() + 9 * 3600_000).toISOString()}
      : scenario === "invalid-expiry" ? {controlled_account_setup_expires_at: "not-a-date"} : {}
    await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({ json: cnSetupConfig(overrides) }))
    await page.goto(scenario === "no-private-url" ? "/#login" : scenario === "no-ticket" ? "/?controlled_registration=1" : "/?controlled_registration=1&__clerk_ticket=isolated-ui-ticket")
    await expect(page.getByRole("heading", { name: "Service unavailable in this region" })).toBeVisible()
    await expect(page.locator("#clerkSignIn")).toHaveCount(0)
    await expect(page.locator("paypal-button")).toHaveCount(0)
  })
}

test("CN account setup unmounts signup when its authorization expires", async ({ page }) => {
  await mockControlledRegistration(page, false)
  const config = cnSetupConfig({controlled_account_setup_expires_at: new Date(Date.now() + 2500).toISOString()})
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({ json: config }))
  await page.goto("/?controlled_registration=1&__clerk_ticket=isolated-ui-ticket")
  await expect(page.getByText("Controlled Clerk signup (UI mock)", { exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Service unavailable in this region" })).toBeVisible({timeout: 7000})
  await expect(page.locator("#clerkSignIn")).toHaveCount(0)
})

test("CN setup with an existing session and credits still cannot checkout or generate", async ({ page }) => {
  await mockSignedInApi(page)
  // Even inconsistent UI flags may not turn a setup session into commerce.
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({ json: cnSetupConfig({region_allowed: true, recharge_enabled: true, registration_enabled: true}) }))
  const writes: string[] = []
  page.on("request", req => { if (/web-sdk|paypal\/orders|uploads|video-tasks/.test(req.url()) && (req.method() === "POST" || req.url().includes("web-sdk"))) writes.push(req.url()) })
  await page.goto("/?controlled_account_setup=1#wallet")
  await expect(page.locator(".wallet-card > strong")).toHaveText("500 ✦")
  await expect(page.locator("paypal-button")).toHaveCount(0)
  await page.evaluate(() => { location.hash = "generate?video=dance-1" })
  await expect(page.getByRole("heading", { name: "Account setup only" })).toBeVisible()
  await expect(page.locator("input[type=file]")).toHaveCount(0)
  expect(writes).toEqual([])
})

async function mockPayPalLifecycle(page: Page, failFirst = false, environment = "sandbox") {
  await page.route(environment === "live" ? "https://www.paypal.com/web-sdk/v6/core" : "https://www.sandbox.paypal.com/web-sdk/v6/core", route => route.fulfill({
    contentType: "application/javascript",
    body: `if (!customElements.get('paypal-button')) customElements.define('paypal-button', class extends HTMLElement {
      connectedCallback() { this.textContent = 'PayPal checkout (UI mock)'; this.style.display = 'block'; this.style.padding = '12px'; }
    }); window.paypal = { createInstance: async () => {
      document.body.dataset.sdkInstances = String(Number(document.body.dataset.sdkInstances || 0) + 1);
      if (${failFirst} && document.body.dataset.sdkInstances === '1') throw new Error('Temporary SDK initialization failure');
      return {
        findEligibleMethods: async () => ({isEligible: () => true}),
        createPayPalOneTimePaymentSession: callbacks => {
          const owned = document.createElement('div'); owned.dataset.sdkSession = 'true'; document.body.append(owned);
          return {
            start: async (_, orderPromise) => { const order = await orderPromise; await callbacks.onApprove({orderId: order.orderId}); },
            destroy: () => { owned.remove(); document.body.dataset.sdkDestroyed = String(Number(document.body.dataset.sdkDestroyed || 0) + 1); },
          };
        },
      };
    }};`,
  }))
}

function paymentOnlyConfig(overrides = {}) {
  return {
    ...paymentConfig, environment: "live", country: "CN", region_allowed: false,
    registration_enabled: false, controlled_registration_enabled: false,
    payment_only_acceptance_mode: true, payment_only_sign_in_enabled: true,
    payment_only_acceptance_allowed: true, payment_only_order_created: false,
    payment_only_expires_at: "2099-01-01T01:00:00Z", ...overrides,
  }
}

test("payment-only private landing allows sign-in, never signup", async ({ page }) => {
  await mockControlledRegistration(page, false, false)
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({json: paymentOnlyConfig({recharge_enabled: false, payment_only_acceptance_allowed: false})}))
  await page.goto("/?payment_only_acceptance=1#login")
  await expect(page.getByRole("heading", {name: "Payment-only acceptance sign-in"})).toBeVisible()
  await expect(page.locator("#clerkSignIn")).toContainText("Clerk login (UI mock)")
  await page.evaluate(() => { location.hash = "/factor-one" })
  await expect(page.locator("#clerkSignIn")).toContainText("Clerk login (UI mock)")
  await page.evaluate(() => { location.hash = "register" })
  await expect(page.getByRole("heading", {name: "Service unavailable in this region"})).toBeVisible()
  await expect(page.locator("#clerkSignIn")).toHaveCount(0)
  await page.goto("/#login")
  await expect(page.getByRole("heading", {name: "Service unavailable in this region"})).toBeVisible()
})

test("payment-only wallet shows one package and disables upload and generation deep links", async ({ page }, testInfo) => {
  await mockSignedInApi(page)
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({json: paymentOnlyConfig()}))
  await mockPayPalLifecycle(page, false, "live")
  const writes: string[] = []
  page.on("request", req => { if (req.method() === "POST" && /paypal\/orders|uploads|video-tasks/.test(req.url())) writes.push(req.url()) })
  await page.goto("/?payment_only_acceptance=1#wallet")
  await expect(page.locator(".recharge-product")).toHaveCount(1)
  await expect(page.locator(".recharge-product")).toContainText("$5.99 USD")
  await expect(page.getByText(/credits belong to the signed-in account/)).toBeVisible()
  await expect(page.locator("paypal-button")).toHaveCount(1)
  await page.screenshot({ path: testInfo.outputPath("payment-only-wallet.png"), fullPage: true, animations: "disabled" })
  await page.evaluate(() => { location.hash = "generate?video=dance-1" })
  await expect(page.getByRole("heading", {name: "Payment-only acceptance"})).toBeVisible()
  await expect(page.locator("input[type=file], [data-generate], [data-confirm-generation]")).toHaveCount(0)
  expect(writes).toEqual([])
})

for (const scenario of ["server-mode-without-private-url", "private-url-config-unavailable"]) {
  test(`payment-only generation remains closed for ${scenario}`, async ({ page }) => {
    await mockSignedInApi(page)
    await page.route("https://api.example.com/api/v1/app/paypal/config", route => scenario === "private-url-config-unavailable"
      ? route.fulfill({status: 503, json: {detail: "Unavailable"}})
      : route.fulfill({json: paymentOnlyConfig({recharge_enabled: false})}))
    const calls: string[] = []
    page.on("request", req => { if (req.method() === "POST" && /paypal\/orders|uploads|video-tasks/.test(req.url())) calls.push(req.url()) })
    await page.goto(scenario === "private-url-config-unavailable"
      ? "/?payment_only_acceptance=1#generate?video=dance-1" : "/#generate?video=dance-1")
    await expect(page.getByRole("heading", {name: "Payment-only acceptance"})).toBeVisible()
    await expect(page.locator("input[type=file], [data-generate], [data-confirm-generation]")).toHaveCount(0)
    expect(calls).toEqual([])
  })
}

for (const scenario of ["not-selected", "expired", "slot-used"]) {
  test(`payment-only checkout stays closed for ${scenario}`, async ({ page }) => {
    await mockSignedInApi(page)
    await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({json: paymentOnlyConfig({
      recharge_enabled: false, payment_only_acceptance_allowed: scenario === "slot-used",
      payment_only_order_created: scenario === "slot-used", payment_only_sign_in_enabled: scenario !== "expired",
    })}))
    const calls: string[] = []
    page.on("request", req => { if (/paypal\/orders|web-sdk/.test(req.url())) calls.push(req.url()) })
    await page.goto("/?payment_only_acceptance=1#wallet")
    await expect(page.locator(".wallet-card strong")).toBeVisible()
    await expect(page.locator(".recharge-product")).toBeDisabled()
    await expect(page.locator("paypal-button")).toHaveCount(0)
    if (scenario === "slot-used") await expect(page.getByText(/single order already exists/)).toBeVisible()
    expect(calls).toEqual([])
  })
}

test("payment-only paid order survives reload with 100 retained credits and no second checkout", async ({ page }) => {
  await mockSignedInApi(page)
  let created = 0
  let captured = 0
  let balance = 0
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({json: paymentOnlyConfig({recharge_enabled: !created, payment_only_order_created: Boolean(created)})}))
  await page.route("https://api.example.com/api/v1/app/wallet", route => route.fulfill({json: {balance, ledger: []}}))
  await page.route("https://api.example.com/api/v1/app/paypal/orders", route => {
    created++
    expect(route.request().postDataJSON()).toEqual({product_id: "coins_100"})
    return route.fulfill({json: {id: "payment-only-order", provider_order_id: "PAY-ONLY", status: "created"}})
  })
  await page.route("https://api.example.com/api/v1/app/paypal/orders/payment-only-order/capture", route => {
    captured++
    balance = 100
    return route.fulfill({json: {id: "payment-only-order", status: "paid", fulfilled_at: "2026-10-16T00:00:00Z"}})
  })
  await mockPayPalLifecycle(page, false, "live")
  await page.goto("/?payment_only_acceptance=1#wallet")
  await expect(page.locator("paypal-button")).toHaveCount(1)
  await page.locator("paypal-button").click()
  await expect(page.locator(".wallet-card strong")).toHaveText("100 ✦")
  await expect(page.locator("paypal-button")).toHaveCount(0)
  await page.reload()
  await expect(page.locator(".wallet-card strong")).toHaveText("100 ✦")
  await expect(page.getByText(/single order already exists/)).toBeVisible()
  await expect(page.locator("paypal-button")).toHaveCount(0)
  expect(created).toBe(1)
  expect(captured).toBe(1)
})

function originalPayment(overrides = {}) {
  return {
    id: "qa-original-order", app_user_id: "qa-app-user", provider: "paypal", payment_environment: "live",
    provider_order_id: "QA-EXISTING-PAYPAL", product_id: "coins_100", amount: 599,
    currency: "USD", coin_quantity: 100, status: "created", fulfilled_at: null,
    paid_at: null, capture_id: null, transaction_id: null, ...overrides,
  }
}

async function mockOriginalPayment(page: Page, order = originalPayment(), config = {}) {
  await mockSignedInApi(page)
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({json: paymentOnlyConfig({
    recharge_enabled: false, payment_only_order_created: true, ...config,
  })}))
  await page.route("https://api.example.com/api/v1/app/orders?**", route => route.fulfill({json: {data: [order]}}))
  await page.route("https://api.example.com/api/v1/app/wallet", route => route.fulfill({json: {balance: 0, payment_hold: false, ledger: []}}))
  await page.route("https://api.example.com/api/v1/app/paypal/orders/qa-original-order/checkout", route => route.fulfill({json: order}))
}

async function mockResumeSession(page: Page, outcome = "cancel") {
  await page.route("https://www.paypal.com/web-sdk/v6/core", route => route.fulfill({
    contentType: "application/javascript",
    body: `if (!customElements.get('paypal-button')) customElements.define('paypal-button', class extends HTMLElement {
      connectedCallback() { this.textContent = 'PayPal checkout (UI mock)'; this.style.display = 'block'; this.style.padding = '12px'; }
    }); window.paypal = { createInstance: async () => ({
      findEligibleMethods: async () => ({isEligible: () => true}),
      createPayPalOneTimePaymentSession: callbacks => ({
        start: async (_, orderPromise) => {
          document.body.dataset.resumeStarts = String(Number(document.body.dataset.resumeStarts || 0) + 1);
          const order = await orderPromise;
          document.body.dataset.resumedOrder = order.orderId;
          if (${JSON.stringify(outcome)} === 'approve') await callbacks.onApprove({orderId: order.orderId});
          else if (${JSON.stringify(outcome)} === 'cancel') callbacks.onCancel();
          else if (${JSON.stringify(outcome)} === 'error') callbacks.onError();
        }, destroy() {},
      }),
    }) };`,
  }))
}

for (const outcome of ["cancel", "error"]) {
  test(`original payment survives refresh and ${outcome} without creating or capturing an order`, async ({page}) => {
    await mockOriginalPayment(page)
    await mockResumeSession(page, outcome)
    let preflights = 0
    const writes: string[] = []
    page.on("request", req => {
      if (req.url().endsWith("/qa-original-order/checkout")) preflights++
      if (req.method() !== "GET" && /paypal\/orders|uploads|video-tasks/.test(req.url())) writes.push(req.url())
    })
    await page.goto("/?payment_only_acceptance=1#wallet")
    await expect(page.getByRole("heading", {name: "Continue original payment", exact: true})).toBeVisible()
    await expect(page.locator(".recharge-product")).toBeDisabled()
    await expect(page.locator("paypal-button")).toBeVisible()
    expect(preflights).toBe(0)
    for (let i = 0; i < 3; i++) await page.getByRole("button", {name: "Refresh balance & orders", exact: true}).click()
    await page.reload()
    await expect(page.locator("paypal-button")).toBeVisible()
    expect(preflights).toBe(0)
    await page.locator("paypal-button").click()
    await expect(page.locator("body")).toHaveAttribute("data-resumed-order", "QA-EXISTING-PAYPAL")
    await expect(page.locator("paypal-button")).toBeVisible()
    expect(preflights).toBe(1)
    expect(writes).toEqual([])
  })
}

test("original payment uses one existing capture only after mocked buyer approval, then removes checkout", async ({page}) => {
  await mockOriginalPayment(page)
  await mockResumeSession(page, "approve")
  let paid = false
  const writes: string[] = []
  page.on("request", req => { if (req.method() === "POST" && /paypal\/orders/.test(req.url())) writes.push(req.url()) })
  await page.route("https://api.example.com/api/v1/app/orders?**", route => route.fulfill({json: {data: [originalPayment(paid ? {status: "paid", fulfilled_at: "2026-10-17T00:00:00Z"} : {})]}}))
  await page.route("https://api.example.com/api/v1/app/wallet", route => route.fulfill({json: {balance: paid ? 100 : 0, ledger: []}}))
  await page.route("https://api.example.com/api/v1/app/paypal/orders/qa-original-order/capture", route => {
    paid = true
    return route.fulfill({json: originalPayment({status: "paid", fulfilled_at: "2026-10-17T00:00:00Z"})})
  })
  await page.goto("/?payment_only_acceptance=1#wallet")
  await expect(page.locator("paypal-button")).toBeVisible()
  expect(writes).toEqual([])
  await page.locator("paypal-button").click()
  await expect(page.locator(".wallet-card strong")).toHaveText("100 ✦")
  await expect(page.locator("paypal-button")).toHaveCount(0)
  await page.reload()
  await expect(page.locator(".wallet-card strong")).toHaveText("100 ✦")
  await expect(page.locator("paypal-button")).toHaveCount(0)
  expect(writes).toEqual(["https://api.example.com/api/v1/app/paypal/orders/qa-original-order/capture"])
})

test("original payment double click and refresh keep a single buyer-initiated checkout", async ({page}) => {
  await mockOriginalPayment(page)
  await mockResumeSession(page, "hold")
  let preflights = 0
  const writes: string[] = []
  page.on("request", req => {
    if (req.url().endsWith("/qa-original-order/checkout")) preflights++
    if (req.method() !== "GET" && /paypal\/orders/.test(req.url())) writes.push(req.url())
  })
  await page.goto("/?payment_only_acceptance=1#wallet")
  await page.locator("paypal-button").dblclick()
  await expect(page.locator("body")).toHaveAttribute("data-resumed-order", "QA-EXISTING-PAYPAL")
  await page.getByRole("button", {name: "Refresh balance & orders", exact: true}).click()
  await expect(page.locator("body")).toHaveAttribute("data-resume-starts", "1")
  expect(preflights).toBe(1)
  expect(writes).toEqual([])
})

for (const failure of ["unavailable", "network", "wrong-order", "paid"]) {
  test(`original payment preflight ${failure} never falls back to a new order or capture`, async ({page}) => {
    await mockOriginalPayment(page)
    await mockResumeSession(page)
    await page.route("https://api.example.com/api/v1/app/paypal/orders/qa-original-order/checkout", route => failure === "network"
      ? route.abort() : failure === "unavailable"
        ? route.fulfill({status: 409, json: {detail: "Original order unavailable"}})
        : route.fulfill({json: originalPayment(failure === "wrong-order" ? {provider_order_id: "OTHER-ORDER"} : {status: "paid"})}))
    const writes: string[] = []
    page.on("request", req => { if (req.method() !== "GET" && /paypal\/orders/.test(req.url())) writes.push(req.url()) })
    await page.goto("/?payment_only_acceptance=1#wallet")
    await page.locator("paypal-button").click()
    await expect(page.getByText("The original order cannot continue; refresh or contact support. No new order was created.", {exact: true})).toBeVisible()
    await expect(page.locator("body")).not.toHaveAttribute("data-resumed-order")
    expect(writes).toEqual([])
  })
}

for (const status of ["approved", "capture_pending", "payment_review", "paid", "failed", "canceled", "refunded", "reversed"]) {
  test(`original payment ${status} shows records without a payment restart`, async ({page}) => {
    await mockOriginalPayment(page, originalPayment({status}))
    const checkoutRequests: string[] = []
    page.on("request", req => { if (/paypal\/orders|web-sdk/.test(req.url())) checkoutRequests.push(req.url()) })
    await page.goto("/?payment_only_acceptance=1#wallet")
    await expect(page.locator(".wallet-card strong")).toBeVisible()
    await expect(page.locator("paypal-button")).toHaveCount(0)
    await expect(page.getByRole("heading", {name: "Continue original payment", exact: true})).toHaveCount(0)
    expect(checkoutRequests).toEqual([])
  })
}

test("original payment expiry, hold and wrong-owner snapshots cannot mount checkout", async ({page}) => {
  await mockOriginalPayment(page, originalPayment(), {payment_only_expires_at: "2020-01-01T00:00:00Z"})
  await page.goto("/?payment_only_acceptance=1#wallet")
  await expect(page.locator(".wallet-card strong")).toBeVisible()
  await expect(page.locator("paypal-button")).toHaveCount(0)
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({json: paymentOnlyConfig({recharge_enabled: false, payment_only_order_created: true})}))
  await page.route("https://api.example.com/api/v1/app/wallet", route => route.fulfill({json: {balance: 0, payment_hold: true, ledger: []}}))
  await page.reload()
  await expect(page.getByText("Your payment account is under review. Please contact support.", {exact: true})).toBeVisible()
  await expect(page.locator("paypal-button")).toHaveCount(0)
  await page.route("https://api.example.com/api/v1/app/wallet", route => route.fulfill({json: {balance: 0, payment_hold: false, ledger: []}}))
  await page.route("https://api.example.com/api/v1/app/orders?**", route => route.fulfill({json: {data: [originalPayment({app_user_id: "other-user"})]}}))
  await page.reload()
  await expect(page.locator(".wallet-card strong")).toBeVisible()
  await expect(page.locator("paypal-button")).toHaveCount(0)
})

test("one explicitly approved replacement uses only its dedicated endpoint and resumes the child", async ({page}, testInfo) => {
  const old = originalPayment({status: "canceled"})
  const child = originalPayment({id: "qa-replacement", provider_order_id: "PAY-REPLACEMENT"})
  await mockOriginalPayment(page, old, {payment_only_replacement_original_id: old.id})
  await mockResumeSession(page, "cancel")
  let replaced = false
  const writes: string[] = []
  page.on("request", req => { if (req.method() !== "GET" && /paypal\/orders/.test(req.url())) writes.push(req.url()) })
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({json: paymentOnlyConfig({
    recharge_enabled: false, payment_only_order_created: true,
    payment_only_replacement_original_id: replaced ? null : old.id,
    payment_only_checkout_order_id: replaced ? child.id : null,
  })}))
  await page.route("https://api.example.com/api/v1/app/orders?**", route => route.fulfill({json: {data: replaced ? [child, old] : [old]}}))
  await page.route("https://api.example.com/api/v1/app/paypal/orders/qa-original-order/replacement", route => {
    expect(route.request().method()).toBe("POST")
    expect(route.request().postData()).toBeNull()
    expect(route.request().headers()["idempotency-key"]).toBeTruthy()
    replaced = true
    return route.fulfill({json: child})
  })
  await page.route("https://api.example.com/api/v1/app/paypal/orders/qa-replacement/checkout", route => route.fulfill({json: child}))
  await page.goto("/?payment_only_acceptance=1#wallet")
  const button = page.getByLabel("Use the one approved replacement with PayPal", {exact: true})
  await expect(button).toBeVisible()
  await expect(page.getByRole("heading", {name: "One approved replacement", exact: true})).toBeVisible()
  expect(writes).toEqual([])
  await page.locator("#paypalCheckout").scrollIntoViewIfNeeded()
  await page.locator("#paypalCheckout").screenshot({path: testInfo.outputPath("approved-replacement-mock.png"), animations: "disabled"})
  await button.click()
  await expect(page.locator("body")).toHaveAttribute("data-resumed-order", "PAY-REPLACEMENT")
  await expect(page.getByRole("heading", {name: "Continue original payment", exact: true})).toBeVisible()
  await page.reload()
  await expect(page.getByLabel("Continue original payment with PayPal", {exact: true})).toBeVisible()
  await page.getByLabel("Continue original payment with PayPal", {exact: true}).click()
  await expect(page.locator("body")).toHaveAttribute("data-resumed-order", "PAY-REPLACEMENT")
  expect(writes).toEqual(["https://api.example.com/api/v1/app/paypal/orders/qa-original-order/replacement"])
  await expect(page.locator(".wallet-card strong")).toHaveText("0 ✦")
})

for (const condition of ["expired", "denied", "hold", "capacity", "wrong-owner"]) {
  test(`replacement checkout stays closed for ${condition}`, async ({page}) => {
    const old = originalPayment({status: "canceled", ...(condition === "wrong-owner" ? {app_user_id: "other-user"} : {})})
    await mockOriginalPayment(page, old, {payment_only_replacement_original_id: old.id,
      ...(condition === "expired" ? {payment_only_expires_at: "2020-01-01T00:00:00Z"} : {}),
      ...(condition === "denied" ? {payment_only_acceptance_allowed: false} : {}),
      ...(condition === "capacity" ? {global_real_remaining: 0} : {}),
    })
    if (condition === "hold") await page.route("https://api.example.com/api/v1/app/wallet", route => route.fulfill({json: {balance: 0, payment_hold: true, ledger: []}}))
    const requests: string[] = []
    page.on("request", req => { if (/web-sdk|\/replacement$/.test(req.url())) requests.push(req.url()) })
    await page.goto("/?payment_only_acceptance=1#wallet")
    await expect(page.locator(".wallet-card strong")).toBeVisible()
    await expect(page.locator("paypal-button")).toHaveCount(0)
    expect(requests).toEqual([])
  })
}

test("replacement network failure cannot fall back to ordinary create or fake a credit", async ({page}) => {
  const old = originalPayment({status: "canceled"})
  await mockOriginalPayment(page, old, {payment_only_replacement_original_id: old.id})
  await mockResumeSession(page, "cancel")
  const writes: string[] = []
  page.on("request", req => { if (req.method() !== "GET" && /paypal\/orders/.test(req.url())) writes.push(req.url()) })
  await page.route("https://api.example.com/api/v1/app/paypal/orders/qa-original-order/replacement", route => route.abort("failed"))
  await page.goto("/?payment_only_acceptance=1#wallet")
  await page.getByLabel("Use the one approved replacement with PayPal", {exact: true}).click()
  await expect(page.locator(".wallet-card strong")).toHaveText("0 ✦")
  await expect(page.locator("body")).not.toHaveAttribute("data-resumed-order")
  expect(writes).toEqual(["https://api.example.com/api/v1/app/paypal/orders/qa-original-order/replacement"])
})

function recoveryResult(overrides = {}) {
  return {order_id: "qa-original-order", checked_at: "2026-10-17T15:00:00Z",
    decision: "manual_review", reason_code: "provider_order_unavailable", provider_http_status: 404,
    resume_allowed: false, replacement_candidate: false, replacement_allowed: false, ...overrides}
}

test("expired original order offers GET-only diagnosis without mounting SDK or resetting the slot", async ({page}, testInfo) => {
  await mockOriginalPayment(page, originalPayment(), {payment_only_acceptance_allowed: false, payment_only_expires_at: null})
  let queries = 0
  const writes: string[] = []
  const sdkRequests: string[] = []
  page.on("request", req => {
    if (req.method() !== "GET" && /paypal\/orders|uploads|video-tasks/.test(req.url())) writes.push(req.url())
    if (/web-sdk/.test(req.url())) sdkRequests.push(req.url())
  })
  await page.route("https://api.example.com/api/v1/app/paypal/orders/qa-original-order/recovery", route => {
    queries++
    return route.fulfill({json: recoveryResult()})
  })
  await page.goto("/?payment_only_acceptance=1#wallet")
  const check = page.getByRole("button", {name: "Check original order (read-only)", exact: true})
  await expect(check).toBeVisible()
  expect(queries).toBe(0)
  await check.click()
  await expect(page.locator("[data-payment-inspection]")).toContainText("This does not prove no charge or a refund")
  await page.getByRole("button", {name: "Refresh balance & orders", exact: true}).click()
  await expect(page.locator("[data-payment-inspection]")).toContainText("PayPal cannot find the original order (404)")
  await expect(page.locator("paypal-button")).toHaveCount(0)
  await expect(page.locator(".recharge-product")).toBeDisabled()
  await expect(page.locator(".wallet-card strong")).toHaveText("0 ✦")
  expect(queries).toBe(1)
  expect(writes).toEqual([])
  expect(sdkRequests).toEqual([])
  // A full-page screenshot needs no scroll of a node replaced by wallet refresh.
  await page.screenshot({path: testInfo.outputPath("original-order-readonly-404.png"), fullPage: true, animations: "disabled"})
})

for (const decision of ["settlement_pending", "authorization_required", "replacement_candidate"]) {
  test(`original order diagnosis ${decision} cannot authorize a replacement, payment or renewal`, async ({page}) => {
    await mockOriginalPayment(page, originalPayment(), {payment_only_acceptance_allowed: false, payment_only_expires_at: null})
    await page.route("https://api.example.com/api/v1/app/paypal/orders/qa-original-order/recovery", route => route.fulfill({json: recoveryResult({decision, replacement_candidate: decision === "replacement_candidate"})}))
    const writes: string[] = []
    page.on("request", req => { if (req.method() !== "GET" && /paypal\/orders/.test(req.url())) writes.push(req.url()) })
    await page.goto("/?payment_only_acceptance=1#wallet")
    await page.getByRole("button", {name: "Check original order (read-only)", exact: true}).click()
    await expect(page.locator("[data-payment-inspection]")).toContainText({
      settlement_pending: "do not pay again",
      authorization_required: "This query did not extend it",
      replacement_candidate: "no replacement or new payment is authorized",
    }[decision]!)
    await expect(page.locator("paypal-button")).toHaveCount(0)
    await expect(page.locator(".wallet-card strong")).toHaveText("0 ✦")
    expect(writes).toEqual([])
  })
}

for (const failure of ["network", "wrong-order", "replacement-authorized", "invalid-resume"]) {
  test(`original order inspection ${failure} stays unknown without another payment`, async ({page}) => {
    await mockOriginalPayment(page)
    await mockResumeSession(page)
    await page.route("https://api.example.com/api/v1/app/paypal/orders/qa-original-order/recovery", route => failure === "network" ? route.abort()
      : route.fulfill({json: recoveryResult(failure === "wrong-order" ? {order_id: "someone-else"} : failure === "replacement-authorized" ? {replacement_allowed: true} : {resume_allowed: true})}))
    const writes: string[] = []
    page.on("request", req => { if (req.method() !== "GET" && /paypal\/orders/.test(req.url())) writes.push(req.url()) })
    await page.goto("/?payment_only_acceptance=1#wallet")
    await expect(page.locator("paypal-button")).toBeVisible()
    await page.getByRole("button", {name: "Check original order (read-only)", exact: true}).click()
    await expect(page.locator("[data-payment-inspection]")).toContainText("needs manual verification")
    await expect(page.locator("paypal-button")).toHaveCount(0)
    await page.getByRole("button", {name: "Refresh balance & orders", exact: true}).click()
    await expect(page.locator("paypal-button")).toHaveCount(0)
    expect(writes).toEqual([])
  })
}

test("in-flight original order inspection blocks payment and ignores a signed-out response", async ({page}) => {
  await mockOriginalPayment(page)
  await mockResumeSession(page)
  let release!: () => void
  const blocked = new Promise<void>(resolve => { release = resolve })
  await page.route("https://api.example.com/api/v1/app/paypal/orders/qa-original-order/recovery", async route => {
    await blocked
    return route.fulfill({json: recoveryResult()})
  })
  const paymentRequests: string[] = []
  page.on("request", req => { if (/paypal\/orders/.test(req.url()) && !req.url().endsWith("/recovery")) paymentRequests.push(req.url()) })
  await page.goto("/?payment_only_acceptance=1#wallet")
  await expect(page.locator("paypal-button")).toBeVisible()
  await page.getByRole("button", {name: "Check original order (read-only)", exact: true}).click()
  await expect(page.getByRole("button", {name: "Check original order (read-only)", exact: true})).toBeDisabled()
  await page.locator("paypal-button").click()
  expect(paymentRequests).toEqual([])
  await page.evaluate(() => {
    window.VirealClerk.session = null
    window.VirealClerk.user = null
    window.dispatchEvent(new CustomEvent("vireal:clerk-ready", {detail: window.VirealClerk}))
  })
  release()
  await expect(page.locator("[data-payment-inspection]")).toHaveCount(0)
  await expect(page.locator("paypal-button")).toHaveCount(0)
  expect(paymentRequests).toEqual([])
})

test("wallet refresh and scheduled payment polling reuse the SDK and checkout", async ({ page }) => {
  await page.clock.install()
  await mockSignedInApi(page)
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({ json: paymentConfig }))
  let balance = 500
  let queries = 0
  await page.route("https://api.example.com/api/v1/app/wallet", route => route.fulfill({ json: { balance, payment_hold: false, ledger: [] } }))
  await page.route("https://api.example.com/api/v1/app/orders?**", route => {
    queries++
    return route.fulfill({ json: { data: [{ id: "qa-pending", provider: "paypal", status: "capture_pending", coin_quantity: 100, amount: 599 }] } })
  })
  await mockPayPalLifecycle(page)
  await page.goto("/#wallet")
  await page.clock.runFor(100)
  await expect(page.locator("paypal-button")).toHaveCount(1)
  for (let i = 0; i < 4; i++) {
    balance++
    await page.getByRole("button", { name: "Refresh balance & orders", exact: true }).click()
    await expect(page.locator(".wallet-card strong")).toHaveText(`${balance} ✦`)
    await page.clock.runFor(100)
    await expect(page.locator("body")).toHaveAttribute("data-sdk-instances", "1")
    await expect(page.locator("[data-sdk-session]")).toHaveCount(1)
  }
  const previousQueries = queries
  balance = 750
  await page.clock.runFor(10100)
  await expect.poll(() => queries).toBeGreaterThan(previousQueries)
  await expect(page.locator(".wallet-card strong")).toHaveText("750 ✦")
  await expect(page.locator("body")).toHaveAttribute("data-sdk-instances", "1")
  await expect(page.locator("[data-sdk-session]")).toHaveCount(1)
})

test("changing package or leaving the wallet releases the old checkout", async ({ page }) => {
  await mockSignedInApi(page)
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({ json: paymentConfig }))
  await mockPayPalLifecycle(page)
  let product: string | undefined
  await page.route("https://api.example.com/api/v1/app/paypal/orders", async route => {
    product = route.request().postDataJSON().product_id
    await route.fulfill({ json: { id: "qa-new-package", provider_order_id: "QA-NEW-PACKAGE", status: "created" } })
  })
  await page.route("https://api.example.com/api/v1/app/paypal/orders/qa-new-package/capture", route => route.fulfill({ json: { status: "capture_pending" } }))
  await page.goto("/#wallet")
  await expect(page.locator("[data-sdk-session]")).toHaveCount(1)
  await page.getByRole("button", { name: "220 ✦ $11.99 USD", exact: true }).click()
  await expect(page.locator("body")).toHaveAttribute("data-sdk-destroyed", "1")
  await expect(page.locator("[data-sdk-session]")).toHaveCount(1)
  await page.getByRole("button", { name: "发现", exact: true }).click()
  await expect(page.locator("[data-sdk-session]")).toHaveCount(0)
  await page.getByRole("button", { name: "查看金币余额", exact: true }).click()
  await expect(page.locator("paypal-button")).toBeVisible()
  await page.locator("paypal-button").click()
  await expect.poll(() => product).toBe("coins_220")
  await expect(page.locator("body")).toHaveAttribute("data-sdk-instances", "1")
  await expect(page.locator("[data-sdk-session]")).toHaveCount(1)
})

test("leaving during SDK initialization does not create an orphan checkout", async ({ page }) => {
  await mockSignedInApi(page)
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({ json: paymentConfig }))
  await mockPayPalLifecycle(page)
  let release: () => void = () => {}
  const gate = new Promise<void>(resolve => { release = resolve })
  let requested = false
  await page.route("https://www.sandbox.paypal.com/web-sdk/v6/core", async route => {
    requested = true
    await gate
    await route.fallback()
  })
  await page.goto("/#wallet")
  await expect.poll(() => requested).toBe(true)
  await page.getByRole("button", { name: "发现", exact: true }).click()
  release()
  await expect(page.locator("body")).toHaveAttribute("data-sdk-instances", "1")
  await expect(page.locator("[data-sdk-session]")).toHaveCount(0)
  await page.getByRole("button", { name: "查看金币余额", exact: true }).click()
  await expect(page.locator("paypal-button")).toBeVisible()
  await expect(page.locator("body")).toHaveAttribute("data-sdk-instances", "1")
  await expect(page.locator("[data-sdk-session]")).toHaveCount(1)
})

test("an SDK initialization failure can recover without a payment retry", async ({ page }) => {
  await mockSignedInApi(page)
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({ json: paymentConfig }))
  await mockPayPalLifecycle(page, true)
  let orders = 0
  page.on("request", request => { if (request.method() === "POST" && request.url().includes("/paypal/orders")) orders++ })
  await page.goto("/#wallet")
  await expect(page.getByText("Checkout could not load; please refresh later", { exact: true })).toBeVisible()
  for (let i = 0; i < 3; i++) {
    await page.evaluate(() => window.dispatchEvent(new HashChangeEvent("hashchange")))
    await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))))
    await expect(page.getByText("Checkout could not load; please refresh later", { exact: true })).toBeVisible()
    await expect(page.locator("body")).toHaveAttribute("data-sdk-instances", "1")
    await expect(page.locator("[data-sdk-session]")).toHaveCount(0)
    expect(orders).toBe(0)
  }
  await page.getByRole("button", { name: "Refresh balance & orders", exact: true }).click()
  await expect(page.locator("paypal-button")).toBeVisible()
  await expect(page.locator("body")).toHaveAttribute("data-sdk-instances", "2")
  await expect(page.locator("[data-sdk-session]")).toHaveCount(1)
  expect(orders).toBe(0)
})

test("a payment hold releases checkout resources and disables new payments", async ({ page }) => {
  await mockSignedInApi(page)
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({ json: paymentConfig }))
  let held = false
  await page.route("https://api.example.com/api/v1/app/wallet", route => route.fulfill({ json: { balance: 500, payment_hold: held, ledger: [] } }))
  await mockPayPalLifecycle(page)
  await page.goto("/#wallet")
  await expect(page.locator("paypal-button")).toBeVisible()
  held = true
  await page.getByRole("button", { name: "Refresh balance & orders", exact: true }).click()
  await expect(page.locator("[data-sdk-session]")).toHaveCount(0)
  await expect(page.locator("paypal-button")).toHaveCount(0)
  await expect(page.getByRole("button", { name: "100 ✦ $5.99 USD", exact: true })).toBeDisabled()
  await expect(page.locator("body")).toHaveAttribute("data-sdk-destroyed", "1")
})

test("leaving an open checkout does not leave the wallet permanently busy", async ({ page }) => {
  await mockSignedInApi(page)
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({ json: paymentConfig }))
  let orders = 0
  let captures = 0
  await page.route("https://api.example.com/api/v1/app/paypal/orders", route => {
    orders++
    return route.fulfill({ json: { id: "qa-open-checkout", status: "created", provider_order_id: "QA-OPEN-CHECKOUT" } })
  })
  page.on("request", request => { if (request.url().endsWith("/capture")) captures++ })
  await page.route("https://www.sandbox.paypal.com/web-sdk/v6/core", route => route.fulfill({
    contentType: "application/javascript",
    body: `if (!customElements.get('paypal-button')) customElements.define('paypal-button', class extends HTMLElement {
      connectedCallback() { this.textContent = 'PayPal checkout (UI mock)'; this.style.display = 'block'; this.style.padding = '12px'; }
    }); window.paypal = { createInstance: async () => ({
      findEligibleMethods: async () => ({isEligible: () => true}),
      createPayPalOneTimePaymentSession: () => {
        let stop;
        return {
          start: async (_, orderPromise) => { await orderPromise; await new Promise(resolve => { stop = resolve }); },
          destroy: () => { stop?.(); },
        };
      },
    }) };`,
  }))
  await page.goto("/#wallet")
  await expect(page.locator("paypal-button")).toBeVisible()
  await page.locator("paypal-button").click()
  await expect.poll(() => orders).toBe(1)
  await page.getByRole("button", { name: "Refresh balance & orders", exact: true }).click()
  await page.locator("paypal-button").click()
  expect(orders).toBe(1)
  await page.getByRole("button", { name: "发现", exact: true }).click()
  await page.getByRole("button", { name: "查看金币余额", exact: true }).click()
  await expect(page.locator("paypal-button")).toBeVisible()
  await page.locator("paypal-button").click()
  await expect.poll(() => orders).toBe(2)
  expect(captures).toBe(0)
})

// UI contract mocks only; these do not constitute PayPal sandbox acceptance.
for (const outcome of ["cancel", "pending", "error", "completed"] as const) {
test(`PayPal wallet: ${outcome} never grants unverified credits`, async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockSignedInApi(page)
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({ json: paymentConfig }))
  let paid = false
  let created = false
  let captures = 0
  const order = () => ({ id: "qa-payment-order", provider_order_id: "QA-PAYPAL", provider: "paypal", app_user_id: "qa-app-user", coin_quantity: 100, amount: 599, created_at: "2026-10-08T10:00:00Z", status: paid ? "paid" : "capture_pending", fulfilled_at: paid ? "2026-10-08T10:01:00Z" : null })
  await page.route("https://api.example.com/api/v1/app/orders?**", route => route.fulfill({ json: { data: created ? [order()] : [] } }))
  await page.route("https://api.example.com/api/v1/app/wallet", route => route.fulfill({ json: { balance: paid ? 100 : 0, daily_remaining: 5, concurrent_remaining: 1, payment_hold: false, global_real_remaining: 30, ledger: [] } }))
  await page.route("https://api.example.com/api/v1/app/paypal/orders", async route => {
    expect(route.request().postDataJSON()).toEqual({ product_id: "coins_100" })
    expect(route.request().headers()["idempotency-key"]).toBeTruthy()
    created = true
    await route.fulfill({ json: { ...order(), status: "created" } })
  })
  await page.route("https://api.example.com/api/v1/app/paypal/orders/qa-payment-order/capture", async route => {
    captures++
    paid = outcome === "completed"
    await route.fulfill(outcome === "error" ? { status: 502, json: { detail: "Confirmation unavailable" } } : { json: order() })
  })
  await page.route("https://www.sandbox.paypal.com/web-sdk/v6/core", route => route.fulfill({
    contentType: "application/javascript",
    body: `if (!customElements.get('paypal-button')) customElements.define('paypal-button', class extends HTMLElement { connectedCallback() { this.textContent='PayPal checkout (UI mock)'; this.style.display='block'; this.style.padding='12px'; } }); window.paypal = { createInstance: async () => ({
      findEligibleMethods: async () => ({isEligible: () => true}),
      createPayPalOneTimePaymentSession: async callbacks => ({start: async (_, orderPromise) => {
        const order = await orderPromise;
        if (${JSON.stringify(outcome)} === 'cancel') callbacks.onCancel();
        else await callbacks.onApprove({orderId: order.orderId});
      }}),
    }) }`,
  }))
  await page.goto("/#wallet")
  await expect(page.locator(".recharge-product")).toHaveCount(3)
  for (const price of ["$5.99 USD", "$11.99 USD", "$24.99 USD"]) await expect(page.locator(".recharge-products")).toContainText(price)
  await expect(page.locator(".wallet-card strong")).toHaveText("0 ✦")
  await expect(page.locator("paypal-button")).toBeVisible()
  await expectNoHorizontalOverflow(page)
  if (outcome === "completed") await page.screenshot({ path: testInfo.outputPath("wallet-390.png"), fullPage: true, animations: "disabled" })
  await page.locator("paypal-button").click()
  if (outcome === "completed") {
    await expect(page.locator(".wallet-card strong")).toHaveText("100 ✦")
    await expect(page.getByText("Credits received · 100 ✦", { exact: true })).toBeVisible()
  } else {
    await expect(page.locator(".wallet-card strong")).toHaveText("0 ✦")
    await expect(page.getByText("Credits received · 100 ✦", { exact: true })).toHaveCount(0)
    await expect(page.locator(".profile-card").filter({ hasText: "Payment pending" })).toBeVisible()
    // Simulate independent server reconciliation after the buyer closes checkout.
    paid = true
    await page.reload()
    await expect(page.locator(".wallet-card strong")).toHaveText("100 ✦")
    await expect(page.getByText("Credits received · 100 ✦", { exact: true })).toBeVisible()
  }
  expect(captures).toBe(outcome === "cancel" ? 0 : 1)
})
}

for (const locale of ["en-US", "zh-CN"]) {
  test.describe(`refund status (${locale})`, () => {
    test.use({ locale })
    for (const held of [true, false]) {
      test(`refund record stays accurate when payment hold is ${held}`, async ({ page }) => {
        await mockSignedInApi(page)
        await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({ json: paymentConfig }))
        await page.route("https://api.example.com/api/v1/app/orders?**", route => route.fulfill({ json: { data: [{
          id: "qa-refunded-order", status: "refunded", provider: "paypal", coin_quantity: 100,
          amount: 599, currency: "USD", created_at: "2026-10-08T10:00:00Z", fulfilled_at: "2026-10-08T10:01:00Z",
        }] } }))
        await page.route("https://api.example.com/api/v1/app/wallet", route => route.fulfill({ json: {
          balance: held ? 820 : 720, payment_hold: held, daily_remaining: 5, concurrent_remaining: 1,
          global_real_remaining: 30, ledger: held ? [] : [{
            entry_type: "recharge_recovery", delta: -100, balance_after: 720,
            reason: "Payment recovery: QA-REFUND", created_at: "2026-10-08T10:02:00Z",
          }],
        } }))
        await page.route("https://www.sandbox.paypal.com/web-sdk/v6/core", route => route.fulfill({
          contentType: "application/javascript",
          body: `if (!customElements.get('paypal-button')) customElements.define('paypal-button', class extends HTMLElement { connectedCallback() { this.textContent='PayPal checkout (UI mock)'; } }); window.paypal = { createInstance: async () => ({ findEligibleMethods: async () => ({isEligible: () => true}), createPayPalOneTimePaymentSession: () => ({ start() {throw new Error('Refund UI contract must not start a payment')} }) }) }`,
        }))
        await page.goto("/#wallet")
        const zh = locale === "zh-CN"
        await expect(page.locator(".wallet-card strong")).toHaveText(`${held ? 820 : 720} ✦`)
        await expect(page.getByText(`${zh ? "已退款" : "Refunded"} · 100 ✦`, { exact: true })).toBeVisible()
        const reviewNotice = page.getByText(zh ? "支付账户正在人工审核，请联系客服。" : "Your payment account is under review. Please contact support.", { exact: true })
        if (held) {
          await expect(reviewNotice).toBeVisible()
          await expect(page.locator("paypal-button")).toHaveCount(0)
          for (const product of await page.locator(".recharge-product").all()) await expect(product).toBeDisabled()
        } else {
          await expect(reviewNotice).toHaveCount(0)
          await expect(page.locator("paypal-button")).toBeVisible()
          for (const product of await page.locator(".recharge-product").all()) await expect(product).toBeEnabled()
          await expect(page.getByText(zh ? "已退款，待核对金币" : "Refunded; credits under review", { exact: false })).toHaveCount(0)
          await expect(page.getByText("Payment recovery: QA-REFUND", { exact: true })).toBeVisible()
        }
      })
    }
  })
}

test("region denied does not mount Clerk signup while public browsing works", async ({ page }) => {
  await mockPublicApi(page)
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({ json: { ...paymentConfig, region_allowed: false, registration_enabled: false, recharge_enabled: false } }))
  await page.route("**/assets/vireal-auth.js", route => route.fulfill({ contentType: "application/javascript", body: "window.VirealClerk = {session:null,user:null,addListener() {}, mountSignUp() {throw new Error('Must not mount')}, mountSignIn() {throw new Error('Must not mount')} }; window.dispatchEvent(new CustomEvent('vireal:clerk-ready', {detail: window.VirealClerk}))" }))
  await page.goto("/#register")
  await expect(page.getByText("Service unavailable in this region", { exact: true })).toBeVisible()
  await expect(page.locator("#clerkSignIn")).toHaveCount(0)
  await page.getByRole("button", { name: "Browse effects" }).click()
  await expect(page.locator(".effect-card")).toHaveCount(4)
})

test("Clerk's slash-suffixed signup link respects the closed registration gate", async ({ page }) => {
  await mockPublicApi(page)
  await page.route("**/assets/vireal-auth.js", route => route.fulfill({
    contentType: "application/javascript",
    body: `window.VirealClerk = {
      session:null, user:null, addListener() {},
      mountSignIn(root) { root.innerHTML='<a href="#register/">Sign up</a>' },
      unmountSignIn() {}, mountSignUp() {throw new Error('Closed signup must not mount')},
    }; window.dispatchEvent(new CustomEvent('vireal:clerk-ready', {detail: window.VirealClerk}))`,
  }))
  await page.goto("/#login")
  await page.getByRole("link", { name: "Sign up", exact: true }).click()
  await expect(page).toHaveURL(/#register\/$/)
  await expect(page.getByText("Registration is not yet open", { exact: true })).toBeVisible()
  await expect(page.locator("#clerkSignIn")).toHaveCount(0)
})

test("slash-suffixed auth routes switch Clerk components and preserve verification", async ({ page }) => {
  await mockPublicApi(page)
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({ json: paymentConfig }))
  await page.route("**/assets/vireal-auth.js", route => route.fulfill({
    contentType: "application/javascript",
    body: `window.VirealClerk = {
      session:null, user:null, addListener() {},
      mountSignIn(root) { root.innerHTML='<a href="#register/">Sign up</a>' },
      unmountSignIn() {}, unmountSignUp() {},
      mountSignUp(root) {
        root.innerHTML='<input aria-label="Signup email"><button>Verify QA email</button><a href="#login/">Sign in</a>';
        root.querySelector('button').onclick=()=>{
          root.innerHTML='<input aria-label="Signup OTP"><a href="#login/">Sign in</a>';
          location.hash='/verify-email-address';
        };
      },
    }; window.dispatchEvent(new CustomEvent('vireal:clerk-ready', {detail: window.VirealClerk}))`,
  }))
  await page.goto("/#login/")
  await page.getByRole("link", { name: "Sign up", exact: true }).click()
  await page.getByRole("textbox", { name: "Signup email" }).fill("verified@example.com")
  await page.getByRole("button", { name: "Verify QA email" }).click()
  await expect(page).toHaveURL(/#\/verify-email-address$/)
  await page.getByRole("textbox", { name: "Signup OTP" }).fill("123456")
  await page.evaluate(() => window.dispatchEvent(new HashChangeEvent("hashchange")))
  await expect(page.getByRole("textbox", { name: "Signup OTP" })).toHaveValue("123456")
  await page.getByRole("link", { name: "Sign in", exact: true }).click()
  await expect(page).toHaveURL(/#login\/$/)
  await expect(page.getByRole("link", { name: "Sign up", exact: true })).toBeVisible()
  await page.goto("/#register/?redirect_url=%23wallet")
  await expect(page.getByRole("textbox", { name: "Signup email" })).toBeVisible()
})

test("open signup preserves verification state and returns to a zero-credit wallet", async ({ page }) => {
  await mockSignedInApi(page)
  await page.route("https://api.example.com/api/v1/app/paypal/config", route => route.fulfill({ json: paymentConfig }))
  await page.route("https://api.example.com/api/v1/app/wallet", route => route.fulfill({ json: { balance: 0, daily_remaining: 5, concurrent_remaining: 1, ledger: [] } }))
  await page.route("**/assets/vireal-auth.js", route => route.fulfill({
    contentType: "application/javascript",
    body: `window.VirealClerk = {
      session:null, user:null, addListener(listener) {window.qaSignupNotify=listener;listener()},
      mountSignUp(root, options) {
        if (options.routing !== 'hash') throw new Error('Hash routing required');
        root.innerHTML='<input aria-label="Signup email"><button>Verify QA email</button>';
        root.querySelector('button').onclick=()=>{
          root.innerHTML='<input aria-label="Signup OTP"><button>Complete QA verification</button>';
          location.hash='/verify-email-address'; window.qaSignupNotify();
          root.querySelector('button').onclick=()=>{
            window.VirealClerk.session={id:'verified-session',getToken:async()=>'qa-token'};
            window.VirealClerk.user={id:'qa-user'}; window.qaSignupNotify();
            location.hash='wallet';
          };
        };
      }, unmountSignUp() {},
    }; window.dispatchEvent(new CustomEvent('vireal:clerk-ready', {detail: window.VirealClerk}))`,
  }))
  await page.goto("/#register")
  await page.getByRole("textbox", { name: "Signup email" }).fill("verified@example.com")
  await page.getByRole("button", { name: "Verify QA email" }).click()
  await expect(page).toHaveURL(/#\/verify-email-address$/)
  await page.getByRole("textbox", { name: "Signup OTP" }).fill("123456")
  await page.evaluate(() => window.dispatchEvent(new HashChangeEvent("hashchange")))
  await expect(page.getByRole("textbox", { name: "Signup OTP" })).toHaveValue("123456")
  await page.getByRole("button", { name: "Complete QA verification" }).click()
  await expect(page.locator(".wallet-card strong")).toHaveText("0 ✦")
  await expect(page.locator(".recharge-product")).toHaveCount(3)
})

test("signing out clears the previous account's cached generation details", async ({ page }) => {
  await mockSignedInApi(page)
  await page.route("**/assets/vireal-auth.js", async (route) => {
    await route.fulfill({
      contentType: "application/javascript",
      body: `window.VirealClerk = {
        session: {id: 'session-a', getToken: async () => 'qa-token-a'},
        user: {id: 'user-a'},
        addListener(listener) { window.qaClerkNotify = listener },
      }; window.dispatchEvent(new CustomEvent('vireal:clerk-ready', {detail: window.VirealClerk}))`,
    })
  })
  let account = "a"
  const task = { id: "private-a", status: "succeeded", duration: 5, coin_cost: 12, effect_title: "QA-A private work" }
  await page.route("https://api.example.com/api/v1/app/auth/session", async (route) => {
    await route.fulfill({ json: { app_user: { id: `qa-user-${account}`, nickname: `QA-${account}` } } })
  })
  await page.route("https://api.example.com/api/v1/app/video-tasks?**", async (route) => {
    await route.fulfill({ json: { data: account === "a" ? [task] : [] } })
  })
  await page.route("https://api.example.com/api/v1/app/video-tasks/private-a", async (route) => {
    await route.fulfill(account === "a" ? { json: task } : { status: 404, json: { detail: "Video task not found" } })
  })
  await page.goto("/#works")
  await page.getByRole("button", { name: "已完成", exact: true }).click()
  await expect(page.getByRole("heading", { name: "QA-A private work" })).toBeVisible()
  await page.evaluate(() => {
    const runtime = window as any
    runtime.VirealClerk.session = null
    runtime.VirealClerk.user = null
    runtime.qaClerkNotify()
  })
  await expect(page.getByRole("heading", { name: "登录后继续创作" })).toBeVisible()
  account = "b"
  await page.evaluate(() => {
    const runtime = window as any
    runtime.VirealClerk.session = { id: "session-b", getToken: async () => "qa-token-b" }
    runtime.VirealClerk.user = { id: "user-b" }
    runtime.qaClerkNotify()
  })
  await expect(page.getByRole("heading", { name: "生成任务", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "QA-A private work" })).toHaveCount(0)
})

test("photo uploads prevent another file picker from being replaced mid-selection", async ({ page }) => {
  await mockSignedInApi(page)
  let releaseUpload!: () => void
  const uploadFinished = new Promise<void>((resolve) => { releaseUpload = resolve })
  await page.route("https://api.example.com/api/v1/app/uploads/images", async (route) => {
    await uploadFinished
    await route.fulfill({ json: { id: "upload-1" } })
  })
  await page.goto("/#generate?category=kiss&video=kiss-1")
  await expect(page.locator(".energy-pill")).toContainText("500")
  await page.locator("[data-upload-index='0']").setInputFiles({ name: "qa.png", mimeType: "image/png", buffer: Buffer.from("qa-image") })
  try {
    await expect(page.locator("[data-upload-index='1']")).toBeDisabled()
    await expect(page.locator("[data-remove-upload='0']")).toBeDisabled()
    await expect(page.locator("[data-generate]")).toContainText("正在上传照片")
  } finally {
    releaseUpload()
  }
  await expect(page.locator("[data-upload-index='1']")).toBeEnabled()
  await expect(page.locator("[data-remove-upload='0']")).toBeEnabled()
  await expect(page.locator("[data-generate]")).toContainText("还需上传 1 张照片")
})

test("generation retries reuse the same idempotency key after a lost response", async ({ page }) => {
  await mockSignedInApi(page)
  await page.route("https://api.example.com/api/v1/app/uploads/images", async (route) => {
    await route.fulfill({ json: { id: "upload-1" } })
  })
  const keys: string[] = []
  const task = { id: "qa-task", status: "pending", duration: 5, coin_cost: 12, effect_title: "节拍律动" }
  await page.route("https://api.example.com/api/v1/app/video-tasks", async (route) => {
    keys.push(route.request().headers()["idempotency-key"])
    if (keys.length === 1) await route.abort("failed")
    else await route.fulfill({ json: task })
  })
  await page.route("https://api.example.com/api/v1/app/video-tasks/qa-task", async (route) => {
    await route.fulfill({ json: task })
  })
  await page.goto("/#generate?category=dance&video=dance-1")
  await expect(page.locator(".energy-pill")).toContainText("500")
  await page.locator("input[type=file]").setInputFiles({ name: "qa.png", mimeType: "image/png", buffer: Buffer.from("qa-image") })
  await expect(page.locator("[data-generate]")).toBeEnabled()
  await page.locator("[data-generate]").click()
  await page.locator("[data-confirm-generation]").click()
  await expect(page.locator("#toastRoot")).toContainText("提交失败")
  await page.locator("[data-generate]").click()
  await page.locator("[data-confirm-generation]").click()
  await expect(page).toHaveURL(/#generation\?id=qa-task$/)
  expect(keys).toHaveLength(2)
  expect(keys[0]).toBeTruthy()
  expect(keys[1]).toBe(keys[0])
})

test("terminal task refunds refresh the visible balance without leaving the page", async ({ page }) => {
  await mockSignedInApi(page)
  let balance = 488
  const task = { id: "qa-refund-task", status: "pending", duration: 5, coin_cost: 12, effect_title: "节拍律动" }
  await page.route("https://api.example.com/api/v1/app/wallet", async (route) => {
    await route.fulfill({ json: { balance, daily_remaining: 4, concurrent_remaining: 1, ledger: [] } })
  })
  await page.route("https://api.example.com/api/v1/app/video-tasks?**", async (route) => {
    await route.fulfill({ json: { data: [task] } })
  })
  await page.route("https://api.example.com/api/v1/app/video-tasks/qa-refund-task", async (route) => {
    balance = 500
    await route.fulfill({ json: { ...task, status: "failed", coin_refunded_at: new Date().toISOString() } })
  })
  await page.goto("/#works")
  await expect(page.getByRole("button", { name: "查看金币余额", exact: true })).toContainText("488")
  await page.getByRole("button", { name: "排队中", exact: true }).click()
  await expect(page.getByRole("heading", { name: "生成失败" })).toBeVisible()
  await expect(page.getByText("金币已退回钱包", { exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "查看金币余额", exact: true })).toContainText("500")
})

async function expectNoHorizontalOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    body: document.body.scrollWidth,
    root: document.documentElement.scrollWidth,
    viewport: window.innerWidth,
  }))
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport)
  expect(dimensions.root).toBeLessThanOrEqual(dimensions.viewport)
}

function existingDeliveryTask(overrides: Record<string, unknown> = {}) {
  return {
    id: "qa-delivery-task", status: "running", duration: 5, coin_cost: 12,
    effect_title: "节拍律动", execution_type: "wan", resolution: "720p", aspect_ratio: "9:16",
    expires_at: new Date(Date.now() + 24 * 3600000).toISOString(),
    coin_refunded_at: null, playback_url: null, ...overrides,
  }
}

async function mockExistingDelivery(page: Page, task = existingDeliveryTask()) {
  await mockSignedInApi(page)
  await page.route("https://api.example.com/api/v1/app/video-tasks?**", route => route.fulfill({ json: { data: [task] } }))
  await page.route("https://api.example.com/api/v1/app/video-tasks/qa-delivery-task", route => route.fulfill({ json: task }))
}

test("task polling retries transient failures and resumes online without creating a prediction", async ({ page }) => {
  await mockExistingDelivery(page)
  let queries = 0
  let submissions = 0
  await page.route("https://api.example.com/api/v1/app/video-tasks", async route => { submissions++; await route.fulfill({ status: 500, json: {} }) })
  await page.route("https://api.example.com/api/v1/app/video-tasks/qa-delivery-task", async route => {
    queries++
    await route.fulfill(queries === 1 ? { status: 503, json: { detail: "Temporary network failure" } } : { json: existingDeliveryTask() })
  })
  await page.goto("/#generation?id=qa-delivery-task")
  await expect(page.getByText("状态更新暂时中断，正在重试；不会重新生成。", { exact: true })).toBeVisible()
  await expect.poll(() => queries).toBeGreaterThanOrEqual(2)
  await expect(page.getByText("状态更新暂时中断，正在重试；不会重新生成。", { exact: true })).toHaveCount(0)
  const before = queries
  await page.evaluate(() => window.dispatchEvent(new Event("online")))
  await expect.poll(() => queries).toBeGreaterThan(before)
  const beforeVisible = queries
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")))
  await expect.poll(() => queries).toBeGreaterThan(beforeVisible)
  expect(submissions).toBe(0)
})

test("manual task refresh recovers status and uses actual refund timestamp", async ({ page }) => {
  await mockExistingDelivery(page)
  let recovered = false
  await page.route("https://api.example.com/api/v1/app/video-tasks/qa-delivery-task", route => route.fulfill(recovered ? { json: existingDeliveryTask({ status: "failed", coin_refunded_at: new Date().toISOString() }) } : { status: 503, json: { detail: "Unavailable" } }))
  await page.goto("/#generation?id=qa-delivery-task")
  await expect(page.getByRole("button", { name: "刷新任务状态" })).toBeVisible()
  recovered = true
  await page.getByRole("button", { name: "刷新任务状态" }).click()
  await expect(page.getByText("金币已退回钱包", { exact: true })).toBeVisible()
})

for (const status of ["failed", "expired"] as const) {
  test(`${status} without a server refund timestamp never promises a refund`, async ({ page }) => {
    await mockExistingDelivery(page, existingDeliveryTask({ status, expires_at: new Date(Date.now() - 1000).toISOString() }))
    await page.goto("/#generation?id=qa-delivery-task")
    await expect(page.getByRole("heading", { name: status === "failed" ? "生成失败" : "作品已过期/删除" })).toBeVisible()
    await expect(page.getByText("金币已退回钱包", { exact: true })).toHaveCount(0)
    await expect(page.getByRole("button", { name: "下载 MP4" })).toHaveCount(0)
  })
}

test("owned result download sends authentication and saves MP4 without a public object URL", async ({ page }) => {
  const task = existingDeliveryTask({ status: "succeeded", playback_url: "https://api.example.com/mock-video.mp4" })
  await mockExistingDelivery(page, task)
  const bytes = Buffer.from("00000018667479706d7034326d6f636b766964656f", "hex")
  await page.route("https://api.example.com/mock-video.mp4", route => route.fulfill({ contentType: "video/mp4", body: bytes }))
  let downloads = 0
  await page.route("https://api.example.com/api/v1/app/video-tasks/qa-delivery-task/download", async route => {
    expect(route.request().headers().authorization).toBe("Bearer qa-session-token")
    downloads++
    await route.fulfill({ contentType: "video/mp4", headers: { "Content-Disposition": 'attachment; filename="vireal-qa-delivery-task.mp4"' }, body: bytes })
  })
  await page.goto("/#generation?id=qa-delivery-task")
  await expect(page.getByText(/作品保留至/)).toBeVisible()
  const saved = page.waitForEvent("download")
  await page.getByRole("button", { name: "下载 MP4" }).click()
  expect((await saved).suggestedFilename()).toBe("vireal-qa-delivery-task.mp4")
  expect(downloads).toBe(1)
  await expectNoHorizontalOverflow(page)
})

test("playback error refreshes its signed address once and cannot loop on a bad video", async ({ page }) => {
  await mockExistingDelivery(page, existingDeliveryTask({ status: "succeeded", playback_url: "https://api.example.com/bad-video.mp4?token=old" }))
  let queries = 0
  await page.route("https://api.example.com/api/v1/app/video-tasks/qa-delivery-task", async route => {
    queries++
    await route.fulfill({ json: existingDeliveryTask({ status: "succeeded", playback_url: `https://api.example.com/bad-video.mp4?token=${queries > 1 ? "fresh" : "old"}` }) })
  })
  await page.route("https://api.example.com/bad-video.mp4?**", route => route.fulfill({ status: 403, body: "Expired mock signature" }))
  await page.goto("/#generation?id=qa-delivery-task")
  await expect(page.locator("[data-task-video]")).toHaveAttribute("src", /token=fresh/)
  await page.evaluate(() => document.querySelector("[data-task-video]")?.dispatchEvent(new Event("error")))
  // Initial lookup plus one playback recovery; repeat errors must not spam APIs.
  expect(queries).toBe(2)
})

test("signed-address refresh retries a transient query failure without another generation", async ({ page }) => {
  await mockExistingDelivery(page, existingDeliveryTask({ status: "succeeded", playback_url: "https://api.example.com/retry-video.mp4?token=old" }))
  let queries = 0
  let submissions = 0
  await page.route("https://api.example.com/api/v1/app/video-tasks", async route => { submissions++; await route.fulfill({ status: 500, json: {} }) })
  await page.route("https://api.example.com/api/v1/app/video-tasks/qa-delivery-task", async route => {
    queries++
    if (queries === 2) return route.fulfill({ status: 503, json: { detail: "Temporary refresh failure" } })
    await route.fulfill({ json: existingDeliveryTask({
      status: "succeeded", playback_url: `https://api.example.com/retry-video.mp4?token=${queries >= 3 ? "fresh" : "old"}`,
      playback_url_expires_at: new Date(Date.now() + (queries >= 3 ? 600000 : 6500)).toISOString(),
    }) })
  })
  // Keep the media request pending to isolate the scheduled address refresh
  // from the separate player-error recovery path.
  await page.route("https://api.example.com/retry-video.mp4?**", async () => {})
  await page.goto("/#generation?id=qa-delivery-task")
  await expect(page.locator("[data-task-video]")).toHaveAttribute("src", /token=old/)
  await expect(page.locator("[data-task-video]")).toHaveAttribute("src", /token=fresh/, { timeout: 10000 })
  expect(queries).toBe(3)
  expect(submissions).toBe(0)
})

test("player recovery re-arms only after a successful media load", async ({ page }) => {
  await mockExistingDelivery(page, existingDeliveryTask({ status: "succeeded", playback_url: "https://api.example.com/rearm-video.mp4?token=1" }))
  let queries = 0
  await page.route("https://api.example.com/api/v1/app/video-tasks/qa-delivery-task", async route => {
    queries++
    await route.fulfill({ json: existingDeliveryTask({ status: "succeeded", playback_url: `https://api.example.com/rearm-video.mp4?token=${queries}` }) })
  })
  await page.route("https://api.example.com/rearm-video.mp4?**", async () => {})
  await page.goto("/#generation?id=qa-delivery-task")
  await expect(page.locator("[data-task-video]")).toHaveAttribute("src", /token=1/)
  await page.evaluate(() => document.querySelector("[data-task-video]")?.dispatchEvent(new Event("error")))
  await expect(page.locator("[data-task-video]")).toHaveAttribute("src", /token=2/)
  await page.evaluate(() => document.querySelector("[data-task-video]")?.dispatchEvent(new Event("error")))
  expect(queries).toBe(2)
  // Synthetic browser events verify the recovery guard, not physical playback.
  await page.evaluate(() => document.querySelector("[data-task-video]")?.dispatchEvent(new Event("loadeddata")))
  await page.evaluate(() => document.querySelector("[data-task-video]")?.dispatchEvent(new Event("error")))
  await expect(page.locator("[data-task-video]")).toHaveAttribute("src", /token=3/)
  expect(queries).toBe(3)
})

test("failed playback refresh cannot poll a work after leaving its page", async ({ page }) => {
  await mockExistingDelivery(page, existingDeliveryTask({ status: "succeeded", playback_url: "https://api.example.com/leave-video.mp4" }))
  let queries = 0
  await page.route("https://api.example.com/api/v1/app/video-tasks/qa-delivery-task", async route => {
    queries++
    if (queries > 1) return route.fulfill({ status: 503, json: { detail: "Temporary refresh failure" } })
    await route.fulfill({ json: existingDeliveryTask({ status: "succeeded", playback_url: "https://api.example.com/leave-video.mp4", playback_url_expires_at: new Date(Date.now() + 6500).toISOString() }) })
  })
  await page.route("https://api.example.com/leave-video.mp4", async () => {})
  await page.goto("/#generation?id=qa-delivery-task")
  await expect.poll(() => queries).toBe(2)
  await page.getByRole("button", { name: "继续浏览", exact: true }).click()
  await expect(page.locator(".effect-card")).toHaveCount(4)
  await page.clock.install()
  await page.clock.runFor(35000)
  expect(queries).toBe(2)
})

test("system-share cancellation does not trigger a second download", async ({ page }) => {
  await mockExistingDelivery(page, existingDeliveryTask({ status: "succeeded", playback_url: "https://api.example.com/mock-video.mp4" }))
  await page.route("https://api.example.com/mock-video.mp4", route => route.abort())
  let downloads = 0
  await page.route("https://api.example.com/api/v1/app/video-tasks/qa-delivery-task/download", async route => {
    downloads++
    await route.fulfill({ contentType: "video/mp4", body: Buffer.from("00000018667479706d7034326d6f636b766964656f", "hex") })
  })
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "canShare", { value: () => true })
    Object.defineProperty(navigator, "share", { value: async () => { throw new DOMException("User canceled", "AbortError") } })
  })
  let browserDownloads = 0
  page.on("download", () => { browserDownloads++ })
  await page.goto("/#generation?id=qa-delivery-task")
  await page.getByRole("button", { name: "系统保存/分享" }).click()
  await expect.poll(() => downloads).toBe(1)
  await expect(page.getByRole("button", { name: "系统保存/分享" })).toBeEnabled()
  expect(browserDownloads).toBe(0)
})

test("expired download refreshes task state and removes stale download controls", async ({ page }) => {
  await mockExistingDelivery(page, existingDeliveryTask({ status: "succeeded", playback_url: "https://api.example.com/mock-video.mp4" }))
  let expired = false
  await page.route("https://api.example.com/api/v1/app/video-tasks/qa-delivery-task", route => route.fulfill({ json: expired ? existingDeliveryTask({ status: "expired", expires_at: new Date(Date.now() - 1000).toISOString() }) : existingDeliveryTask({ status: "succeeded", playback_url: "https://api.example.com/mock-video.mp4" }) }))
  await page.route("https://api.example.com/api/v1/app/video-tasks/qa-delivery-task/download", async route => { expired = true; await route.fulfill({ status: 410, json: { detail: "Video has expired" } }) })
  await page.goto("/#generation?id=qa-delivery-task")
  await page.getByRole("button", { name: "下载 MP4" }).click()
  await expect(page.getByRole("heading", { name: "作品已过期/删除" })).toBeVisible()
  await expect(page.getByRole("button", { name: "下载 MP4" })).toHaveCount(0)
})

test("390px home uses dynamic count, fallback media, and three-item nav", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockPublicApi(page)
  await page.goto("/#home")
  await expect(page.locator(".effect-card")).toHaveCount(4)
  await expect(page.locator(".surface-number")).toHaveCount(4)
  await expect(page.locator(".utility-nav button")).toHaveCount(3)
  await expect(page.locator(".utility-nav")).not.toContainText("金币")
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: testInfo.outputPath("user-390.png"), fullPage: true, animations: "disabled" })
})

test("430px kiss generation presents two real upload inputs", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 430, height: 932 })
  await mockPublicApi(page)
  await page.goto("/#generate?category=kiss&video=kiss-1")
  await expect(page.locator(".upload-tile")).toHaveCount(2)
  await expect(page.locator("input[type=file]")).toHaveCount(2)
  await expect(page.locator(".duration-button")).toHaveCount(2)
  await expect(page.locator(".generator-panel")).toContainText("12 ✦")
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: testInfo.outputPath("generate-mobile.png"), fullPage: true, animations: "disabled" })
  await page.goto("/#home")
  await expect(page.locator(".effect-card")).toHaveCount(4)
  await page.screenshot({ path: testInfo.outputPath("mobile.png"), fullPage: true, animations: "disabled" })
})

test("desktop keeps the approved phone composition centered", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await mockPublicApi(page)
  await page.goto("/#home")
  await expect(page.locator(".phone-shell")).toBeVisible()
  const box = await page.locator(".phone-shell").boundingBox()
  expect(box?.width).toBeLessThanOrEqual(432)
  expect(box?.x).toBeGreaterThan(450)
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: testInfo.outputPath("desktop.png"), fullPage: true, animations: "disabled" })
})

for (const entry of ["account navigation", "generation deep link"]) {
test(`${entry}: signed-out Clerk notifications preserve the in-progress login form`, async ({ page }) => {
  await mockPublicApi(page)
  await page.route("**/assets/vireal-auth.js", async (route) => {
    await route.fulfill({
      contentType: "application/javascript",
      body: `(() => {
        const listeners = []
        window.VirealClerk = {
          session: null,
          user: null,
          addListener(listener) { listeners.push(listener); listener() },
          mountSignIn(root, options) {
            if (options.routing !== 'hash') throw new Error('Unsupported embedded routing')
            root.innerHTML = '<input aria-label="QA email"><button>Continue QA login</button>'
            const notify = () => listeners.forEach(listener => listener())
            root.querySelector('input').addEventListener('input', notify)
            root.querySelector('button').addEventListener('click', () => {
              root.innerHTML = '<input aria-label="QA verification code">'
              root.querySelector('input').addEventListener('input', notify)
              notify()
              location.hash = '/factor-one'
            })
          },
        }
        setTimeout(() => window.dispatchEvent(new CustomEvent('vireal:clerk-ready', {
          detail: window.VirealClerk,
        })), 0)
      })()`,
    })
  })
  if (entry === "account navigation") {
    await page.goto("/#home")
    await expect(page.locator(".effect-card")).toHaveCount(4)
    await page.getByRole("button", { name: "账户", exact: true }).click()
  } else {
    await page.goto("/#generation?id=qa-deep-link")
  }
  await page.getByRole("textbox", { name: "QA email" }).fill("qa@example.com")
  await page.evaluate(() => window.dispatchEvent(new HashChangeEvent("hashchange")))
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))))
  await expect(page.getByRole("textbox", { name: "QA email" })).toHaveValue("qa@example.com")
  await page.getByRole("button", { name: "Continue QA login" }).click()
  await expect(page).toHaveURL(/#\/factor-one$/)
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))))
  await expect(page.getByRole("textbox", { name: "QA verification code" })).toBeVisible()
  await page.getByRole("textbox", { name: "QA verification code" }).fill("123456")
  await expect(page.getByRole("textbox", { name: "QA verification code" })).toHaveValue("123456")
  await expect(page.getByRole("textbox", { name: "QA email" })).toHaveCount(0)
  await page.locator('[data-route="home"]').click()
  await expect(page.locator(".effect-card")).toHaveCount(4)
  await page.getByRole("button", { name: "账户", exact: true }).click()
  await expect(page.getByRole("textbox", { name: "QA email" })).toHaveValue("")
})
}

test("public browsing starts while the Clerk bundle is still downloading", async ({ page }) => {
  await mockPublicApi(page)
  let releaseAuth!: () => void
  const authDownload = new Promise<void>(resolve => { releaseAuth = resolve })
  let authDelivered = false
  let authRequests = 0
  await page.route("**/assets/vireal-auth.js", async route => {
    await authDownload
    await route.fulfill({
      contentType: "application/javascript",
      body: `window.VirealClerk = {
        session: null, user: null,
        addListener(listener) { listener() },
        mountSignIn(root) { root.innerHTML = '<input aria-label="Slow-bundle QA email">' },
      }; window.dispatchEvent(new CustomEvent('vireal:clerk-ready', {detail: window.VirealClerk}))`,
    })
    authDelivered = true
  })
  await page.route("https://api.example.com/api/v1/app/auth/session", async route => {
    authRequests++
    await route.fulfill({ status: 401, json: { detail: "Not authenticated" } })
  })
  try {
    await page.goto("/#home", { waitUntil: "commit" })
    await expect(page.locator(".effect-card")).toHaveCount(4)
    expect(authDelivered).toBe(false)
    expect(authRequests).toBe(0)
    await page.getByRole("button", { name: "账户", exact: true }).click()
    await expect(page.locator("#clerkStatus")).toContainText("正在载入")
    releaseAuth()
    await expect(page.getByRole("textbox", { name: "Slow-bundle QA email" })).toBeVisible()
    expect(authRequests).toBe(0)
  } finally {
    releaseAuth()
  }
})

test("an unavailable Clerk bundle keeps public browsing usable without a business session", async ({ page }) => {
  await mockPublicApi(page)
  await page.route("**/assets/vireal-auth.js", route => route.abort())
  let restrictedRequests = 0
  await page.route("https://api.example.com/api/v1/app/auth/session", async route => {
    restrictedRequests++
    await route.fulfill({ status: 401, json: { detail: "Not authenticated" } })
  })
  await page.goto("/#home")
  await expect(page.locator(".effect-card")).toHaveCount(4)
  await page.getByRole("button", { name: "账户", exact: true }).click()
  await expect(page.getByRole("heading", { name: "登录后继续创作" })).toBeVisible()
  await expect(page.locator("#clerkSignIn")).toBeEmpty()
  expect(restrictedRequests).toBe(0)
})

test("login mounts when Clerk becomes ready after the H5 shell", async ({ page }) => {
  await mockPublicApi(page)
  await page.route("**/assets/vireal-auth.js", async (route) => {
    await route.fulfill({
      contentType: "application/javascript",
      body: `window.addEventListener('qa-clerk-load', () => {
        window.VirealClerk = {
          session: null, user: null,
          addListener(listener) { listener() },
          mountSignIn(root) { root.innerHTML = '<input aria-label="Late QA email">' },
        }
        window.dispatchEvent(new CustomEvent('vireal:clerk-ready', {detail: window.VirealClerk}))
      }, {once: true})`,
    })
  })
  await page.goto("/#login")
  await expect(page.locator("#clerkStatus")).toContainText("正在载入")
  await page.evaluate(() => window.dispatchEvent(new Event("qa-clerk-load")))
  await expect(page.getByRole("textbox", { name: "Late QA email" })).toBeVisible()
  await expect(page.locator("#clerkStatus")).toContainText("Secure email verification")
})

for (const returnToAccount of [false, true]) {
  test(`already-loaded Clerk observes sign-in${returnToAccount ? " when the return hash is unchanged" : " from the home page"}`, async ({ page }) => {
    await mockPublicApi(page)
    // Exercise the already-ready path independently of HTML script order.
    await page.addInitScript(`(() => {
        const listeners = []
        window.VirealClerk = {
          session: null, user: null,
          addListener(listener) { listeners.push(listener) },
        }
        window.activateQaSession = () => {
          window.VirealClerk.session = {id: 'qa-session', getToken: async () => 'qa-session-token'}
          window.VirealClerk.user = {id: 'qa-clerk-user'}
          listeners.forEach(listener => listener())
        }
      })()`)
    await page.route("**/assets/vireal-auth.js", route => route.fulfill({
      contentType: "application/javascript", body: "/* Clerk is already initialized by this fixture. */",
    }))
    await page.route("https://api.example.com/api/v1/app/auth/session", async (route) => {
      await route.fulfill({ json: { app_user: { id: "qa-app-user", nickname: "QA User" } } })
    })
    await page.route("https://api.example.com/api/v1/app/wallet", async (route) => {
      await route.fulfill({ json: { balance: 500, daily_remaining: 5, concurrent_remaining: 1, ledger: [] } })
    })
    await page.route("https://api.example.com/api/v1/app/video-tasks?**", async (route) => {
      await route.fulfill({ json: { data: [] } })
    })
    await page.route("https://api.example.com/api/v1/app/orders?**", async (route) => {
      await route.fulfill({ json: { data: [] } })
    })
    if (returnToAccount) {
      await page.addInitScript(() => sessionStorage.setItem("vireal-after-login", "#account"))
    }
    await page.goto(returnToAccount ? "/#account" : "/#home")
    if (returnToAccount) {
      await expect(page.getByRole("heading", { name: "登录后继续创作" })).toBeVisible()
    } else {
      await expect(page.locator(".effect-card")).toHaveCount(4)
    }
    await page.evaluate(() => (window as unknown as { activateQaSession: () => void }).activateQaSession())
    await expect(page.getByRole("button", { name: "查看金币余额", exact: true })).toContainText("500")
    if (!returnToAccount) await page.getByRole("button", { name: "账户", exact: true }).click()
    await expect(page.getByRole("heading", { name: "账户与偏好" })).toBeVisible()
    await expect(page.locator("#clerkSignIn")).toHaveCount(0)
    expect(await page.evaluate(() => sessionStorage.getItem("vireal-after-login"))).toBeNull()
  })
}
