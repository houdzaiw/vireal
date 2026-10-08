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

async function mockSignedInApi(page: Page) {
  await mockPublicApi(page)
  await page.route("**/assets/vireal-auth.js", async (route) => {
    await route.fulfill({
      contentType: "application/javascript",
      body: `window.VirealClerk = {
        session: {id: 'qa-session', getToken: async () => 'qa-session-token'},
        user: {id: 'qa-user'}, addListener() {},
      }`,
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
}

test("signing out clears the previous account's cached generation details", async ({ page }) => {
  await mockSignedInApi(page)
  await page.route("**/assets/vireal-auth.js", async (route) => {
    await route.fulfill({
      contentType: "application/javascript",
      body: `window.VirealClerk = {
        session: {id: 'session-a', getToken: async () => 'qa-token-a'},
        user: {id: 'user-a'},
        addListener(listener) { window.qaClerkNotify = listener },
      }`,
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
    await route.fulfill({ json: { ...task, status: "failed" } })
  })
  await page.goto("/#works")
  await expect(page.getByRole("button", { name: "查看金币余额", exact: true })).toContainText("488")
  await page.getByRole("button", { name: "排队中", exact: true }).click()
  await expect(page.getByRole("heading", { name: "失败已退款" })).toBeVisible()
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
