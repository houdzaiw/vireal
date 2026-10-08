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
  await page.route(/https:\/\/(?!api\.example\.com).*/, async (route) => route.abort())
}

async function expectNoHorizontalOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    body: document.body.scrollWidth,
    root: document.documentElement.scrollWidth,
    viewport: window.innerWidth,
  }))
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport)
  expect(dimensions.root).toBeLessThanOrEqual(dimensions.viewport)
}

test("390px home uses dynamic count, fallback media, and three-item nav", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockPublicApi(page)
  await page.goto("/#home")
  await expect(page.locator(".effect-card")).toHaveCount(4)
  await expect(page.locator(".surface-number")).toHaveCount(4)
  await expect(page.locator(".utility-nav button")).toHaveCount(3)
  await expect(page.locator(".utility-nav")).not.toContainText("金币")
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: "../.impeccable/review/user-390.png", fullPage: true, animations: "disabled" })
})

test("430px kiss generation presents two real upload inputs", async ({ page }) => {
  await page.setViewportSize({ width: 430, height: 932 })
  await mockPublicApi(page)
  await page.goto("/#generate?category=kiss&video=kiss-1")
  await expect(page.locator(".upload-tile")).toHaveCount(2)
  await expect(page.locator("input[type=file]")).toHaveCount(2)
  await expect(page.locator(".duration-button")).toHaveCount(2)
  await expect(page.locator(".generator-panel")).toContainText("12 ✦")
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: "../.impeccable/review/generate-mobile.png", fullPage: true, animations: "disabled" })
  await page.goto("/#home")
  await expect(page.locator(".effect-card")).toHaveCount(4)
  await page.screenshot({ path: "../.impeccable/review/mobile.png", fullPage: true, animations: "disabled" })
})

test("desktop keeps the approved phone composition centered", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await mockPublicApi(page)
  await page.goto("/#home")
  await expect(page.locator(".phone-shell")).toBeVisible()
  const box = await page.locator(".phone-shell").boundingBox()
  expect(box?.width).toBeLessThanOrEqual(432)
  expect(box?.x).toBeGreaterThan(450)
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: "../.impeccable/review/desktop.png", fullPage: true, animations: "disabled" })
})

test("signed-out Clerk notifications preserve the in-progress login form", async ({ page }) => {
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
  await page.goto("/#home")
  await expect(page.locator(".effect-card")).toHaveCount(4)
  await page.getByRole("button", { name: "账户", exact: true }).click()
  await page.getByRole("textbox", { name: "QA email" }).fill("qa@example.com")
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
  await expect(page.locator("#clerkStatus")).toContainText("仅限受邀请用户登录")
})

test("already-loaded Clerk still observes the subsequent signed-in session", async ({ page }) => {
  await mockPublicApi(page)
  await page.route("**/assets/vireal-auth.js", async (route) => {
    await route.fulfill({
      contentType: "application/javascript",
      body: `(() => {
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
      })()`,
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
  await page.goto("/#home")
  await expect(page.locator(".effect-card")).toHaveCount(4)
  await page.evaluate(() => (window as unknown as { activateQaSession: () => void }).activateQaSession())
  await expect(page.getByRole("button", { name: "查看金币余额", exact: true })).toContainText("500")
  await page.getByRole("button", { name: "账户", exact: true }).click()
  await expect(page.getByRole("heading", { name: "账户与偏好" })).toBeVisible()
})
