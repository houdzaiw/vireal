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
