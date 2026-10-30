// Fully offline: execute the real app in an isolated VM with fake DOM, clock,
// storage, SDK and fetch. No browser, provider, real credential or database.
import { test } from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import vm from "node:vm"

const source = readFileSync(new URL("../../src/vireal-app.js", import.meta.url), "utf8")
const authSource = readFileSync(new URL("../../outputs/vireal-wan-video-h5/prototype/vireal-auth.js", import.meta.url), "utf8")
const closed = { region_allowed: true, registration_enabled: false, recharge_enabled: false, uploads_enabled: false, generation_enabled: false }
const effect = { id: "effect-offline", slug: "kiss-1", category_slug: "kiss", title_zh: "测试效果", input_image_count: 2, variants: [{ id: "variant-offline", coin_cost: 20, duration_seconds: 5, is_default: true }] }
const catalog = { categories: [{ id: "category-offline", slug: "kiss", name_zh: "测试分类", tones: ["#000", "#111", "#222"], effects: [effect] }] }
const flush = async () => { for (let i = 0; i < 40; i++) await Promise.resolve() }
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }

function clock() {
  let now = 0, id = 0
  const timers = new Map()
  return {
    get now() { return now },
    setTimeout(fn, delay = 0) { timers.set(++id, { at: now + delay, fn }); return id },
    clearTimeout(key) { timers.delete(key) },
    async tick(ms = 0) {
      const end = now + ms
      for (let safety = 0; safety < 1000; safety++) {
        await flush()
        const due = [...timers].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0]
        if (!due) { now = end; await flush(); return }
        now = due[1].at; timers.delete(due[0]); due[1].fn()
      }
      throw new Error("Offline timer loop")
    },
  }
}

function runtime({ hash = "#login", search = "", config = closed, sdk = null, request, effectCatalog = catalog, language = "zh-CN" } = {}) {
  const time = clock(), documentEvents = new Map(), windowEvents = new Map(), nodes = new Map(), requests = [], observers = new Set(), storage = new Map()
  const epoch = Date.now()
  class FakeDate extends Date {
    constructor(...args) { super(...(args.length ? args : [epoch + time.now])) }
    static now() { return epoch + time.now }
  }
  let objectURLs = 0, reloads = 0, html = ""
  function node(id) {
    let content = ""
    return {
      id, dataset: {}, isConnected: true,
      get innerHTML() { return content },
      set innerHTML(value) {
        content = value
        if (id === "app") {
          html = value
          for (const key of ["clerkSignIn", "authFeedback"]) {
            const old = nodes.get(key); if (old) old.isConnected = false
            nodes.delete(key)
            if (value.includes(`id="${key}"`)) nodes.set(key, node(key))
          }
        }
        for (const observer of observers) if (observer.root === this) observer.callback()
      },
      querySelector(selector) { return /input|button/.test(selector) && /<(input|button)\b/.test(content) ? {} : null },
      querySelectorAll() { return [] },
      remove() { this.isConnected = false; nodes.delete(id) },
    }
  }
  for (const id of ["app", "overlayRoot", "toastRoot"]) nodes.set(id, node(id))
  let currentHash = hash
  const location = {
    origin: "https://offline.invalid", pathname: "/", search,
    get hash() { return currentHash },
    set hash(value) { currentHash = value.startsWith("#") ? value : `#${value}` },
    reload() { reloads++ },
  }
  const document = {
    hidden: false,
    querySelector(selector) { return selector.includes("vireal-api-base-url") ? { content: "https://api.offline.invalid" } : null },
    getElementById: id => nodes.get(id) || null,
    querySelectorAll: () => [],
    addEventListener(type, listener) { documentEvents.set(type, listener) },
  }
  const window = { VirealClerk: sdk, addEventListener(type, listener) { windowEvents.set(type, listener) } }
  const context = {
    document, window, location, navigator: { language },
    history: { replaceState(_state, _title, path) { const url = new URL(path, location.origin); location.search = url.search; currentHash = url.hash } },
    setTimeout: time.setTimeout, clearTimeout: time.clearTimeout, AbortController,
    URL: class extends URL { static createObjectURL() { objectURLs++; return "blob:offline" } static revokeObjectURL() {} },
    URLSearchParams, Intl, Date: FakeDate, WeakSet, Map, Set,
    crypto: { randomUUID: () => "offline-idempotency-key" },
    sessionStorage: { getItem: key => storage.get(key) || null, setItem: (k, v) => storage.set(k, v), removeItem: k => storage.delete(k) },
    FormData: class { append() {} },
    MutationObserver: class { constructor(callback) { this.callback = callback } observe(root) { this.root = root; observers.add(this) } disconnect() { observers.delete(this) } },
    fetch: async (url, options = {}) => {
      const path = new URL(url).pathname
      requests.push({ path, method: options.method || "GET", signal: options.signal, headers: options.headers })
      const value = request ? await request(path, options) : undefined
      const data = value === undefined ? path.endsWith("/config") ? config : path.endsWith("/effect-catalog") ? effectCatalog
        : path.endsWith("/auth/session") ? { app_user: { id: "offline-app-user", nickname: "Offline" } }
        : path.endsWith("/wallet") ? { balance: 0, ledger: [] } : { data: [] } : value
      return { ok: true, status: 200, json: async () => data }
    },
    __test: {},
  }
  vm.createContext(context)
  const end = source.lastIndexOf("})()")
  vm.runInContext(source.slice(0, end) + `Object.assign(__test, { state, render, loginPage, generatePage, mountSignIn, loadCommerce, syncSession, authFetch, uploadsAllowed, generationAllowed, uploadImage, confirmGeneration, createTask, signInRegionAllowed, signupAvailable, selectedVariant, paymentCheckout, originalPaymentOrder, inspectPayment, paypalMounts, paymentContext, stagingSignInAllowed, stagingSignInWindowOpen });\n` + source.slice(end), context)
  const api = context.__test
  return {
    ...api, time, requests, nodes, storage, context,
    get html() { return html }, get objectURLs() { return objectURLs }, get reloads() { return reloads },
    async settle() { await flush(); await time.tick(0) },
    async sdkReady(clerk) { window.VirealClerk = clerk; windowEvents.get("vireal:clerk-ready")({ detail: clerk }); await this.settle() },
    async sdkError(detail) { windowEvents.get("vireal:clerk-error")({ detail }); await this.settle() },
    async visit(value) { location.hash = value; windowEvents.get("hashchange")(); await this.settle() },
    async click(selector) { documentEvents.get("click")({ target: { closest: s => s === selector ? {} : null } }); await this.settle() },
  }
}

function signedOutSDK({ empty = false, fail = false } = {}) {
  const listeners = []
  return {
    addListener(listener) { listeners.push(listener) },
    notify(resources) { for (const listener of listeners) listener(resources) },
    mounts: 0, unmounts: 0, options: null,
    mountSignIn(root, options) { this.mounts++; this.options = options; if (fail) throw new Error("fake credential must never be shown"); if (!empty) root.innerHTML = '<input value="offline typed value"><button>Sign in</button>' },
    mountSignUp(root, options) { this.mountSignIn(root, options) },
    unmountSignIn() { this.unmounts++ }, unmountSignUp() { this.unmounts++ },
  }
}
function signedInSDK() { return { ...signedOutSDK(), session: { id: "offline-session", getToken: async () => "synthetic-not-a-real-token" }, user: { id: "offline-user" } } }
function assertNoBusiness(r) {
  assert.equal(r.requests.filter(q => q.method !== "GET" && /uploads|video-tasks|paypal\/orders/.test(q.path)).length, 0)
  assert.equal(r.objectURLs, 0)
}

test("missing auth bundle stops loading with durable sanitized error", async () => {
  const r = runtime(); await r.settle(); assert.match(r.html, /正在载入安全登录/)
  await r.time.tick(15000); assert.match(r.html, /AUTH_LOAD_TIMEOUT/); assert.match(r.html, /data-retry-auth/)
  await r.time.tick(3000); assert.match(r.html, /AUTH_LOAD_TIMEOUT/); assertNoBusiness(r)
})
for (const [language, downloading, mounting, ready] of [
  ["zh-CN", "正在载入安全登录…", "正在载入登录表单…", "安全邮箱验证"],
  ["en-US", "Loading secure sign-in…", "Loading sign-in form…", "Secure email verification"],
]) {
  test(`auth feedback reports exact localized loading and readiness phases: ${language}`, async () => {
    const r = runtime({ language }); await r.settle()
    assert.ok(r.html.includes(`<p id="clerkStatus" role="status" class="network-badge">${downloading}</p>`))
    const sdk = signedOutSDK({ empty: true }); await r.sdkReady(sdk)
    assert.ok(r.html.includes(`<p id="clerkStatus" role="status" class="network-badge">${mounting}</p>`))
    r.nodes.get("clerkSignIn").innerHTML = '<input aria-label="Offline email">'
    await r.settle()
    assert.equal(r.nodes.get("authFeedback").innerHTML, `<p id="clerkStatus" role="status" class="network-badge">${ready}</p>`)
    assert.equal(sdk.mounts, 1); assert.equal(r.reloads, 0)
    assert.equal(r.requests.some(q => q.path.endsWith("/auth/session")), false); assertNoBusiness(r)
  })
}
test("SDK error details are not reflected in the page", async () => {
  const r = runtime(); await r.settle(); await r.sdkError({ code: "raw-sensitive-value", message: "fake-sensitive-value" })
  assert.match(r.html, /AUTH_LOAD_FAILED/); assert.doesNotMatch(r.html, /fake-sensitive|raw-sensitive/)
})
test("SDK before config mounts when a non-redrawing config read completes", async () => {
  const pending = deferred(), sdk = signedOutSDK()
  const r = runtime({ request: path => path.endsWith("/config") ? pending.promise : undefined }); await r.settle()
  await r.sdkReady(sdk); assert.equal(sdk.mounts, 0)
  pending.resolve(closed); await r.settle()
  assert.equal(sdk.mounts, 1); assert.equal(r.nodes.get("clerkSignIn").dataset.clerkUiReady, "true")
  assert.match(r.nodes.get("authFeedback").innerHTML, /安全邮箱验证/)
})
test("config before SDK mounts without a page reload", async () => {
  const r = runtime(); await r.settle(); const sdk = signedOutSDK(); await r.sdkReady(sdk)
  assert.equal(sdk.mounts, 1); assert.equal(r.reloads, 0)
})
test("late resource readiness replaces a prior load error without business replay", async () => {
  const r = runtime(); await r.settle(); await r.time.tick(15000)
  await r.sdkReady(signedOutSDK()); assert.equal(r.state.authErrorCode, "")
  assert.equal(r.nodes.get("clerkSignIn").dataset.clerkUiReady, "true"); assertNoBusiness(r)
})
test("repeated renders preserve mounted form and its entered data", async () => {
  const r = runtime(), sdk = signedOutSDK(); await r.settle(); await r.sdkReady(sdk)
  const root = r.nodes.get("clerkSignIn"); r.render(); r.render()
  assert.equal(r.nodes.get("clerkSignIn"), root); assert.match(root.innerHTML, /offline typed value/); assert.equal(sdk.mounts, 1)
})
test("Clerk hash steps preserve the existing mounted input", async () => {
  const r = runtime(), sdk = signedOutSDK(); await r.settle(); await r.sdkReady(sdk)
  const root = r.nodes.get("clerkSignIn"); await r.visit("#/factor-one")
  assert.equal(r.nodes.get("clerkSignIn"), root); assert.equal(sdk.mounts, 1)
})
test("availability revalidation preserves entered sign-in data until a decision", async () => {
  const r = runtime(), sdk = signedOutSDK(); await r.settle(); await r.sdkReady(sdk)
  const root = r.nodes.get("clerkSignIn"), pending = deferred()
  r.context.fetch = async () => ({ ok: true, json: () => pending.promise })
  const read = r.loadCommerce(false); r.render(); await r.settle()
  assert.equal(r.nodes.get("clerkSignIn"), root); assert.match(root.innerHTML, /offline typed value/)
  pending.resolve({ ...closed, region_allowed: false }); await read; await r.settle()
  assert.match(r.html, /当前地区暂未开放服务/); assert.equal(r.nodes.has("clerkSignIn"), false)
})
test("empty SDK mount is not marked ready and times out", async () => {
  const r = runtime(), sdk = signedOutSDK({ empty: true }); await r.settle(); await r.sdkReady(sdk)
  assert.notEqual(r.nodes.get("clerkSignIn").dataset.clerkUiReady, "true")
  await r.time.tick(15000); assert.match(r.html, /AUTH_FORM_TIMEOUT/)
})
test("synchronous SDK mount exception yields persistent safe feedback", async () => {
  const r = runtime(); await r.settle(); await r.sdkReady(signedOutSDK({ fail: true }))
  assert.match(r.html, /AUTH_MOUNT_FAILED/); assert.doesNotMatch(r.html, /fake credential/)
})
test("config timeout fails closed and is not reported as form-ready", async () => {
  const r = runtime({ request: path => path.endsWith("/config") ? new Promise(() => {}) : undefined }); await r.settle(); await r.sdkReady(signedOutSDK())
  await r.time.tick(10000); assert.match(r.html, /AVAILABILITY_UNAVAILABLE/)
  assert.equal(r.uploadsAllowed(), false); assert.equal(r.generationAllowed(), false)
})
test("malformed availability cannot leave an unmountable loading form", async () => {
  const r = runtime({ config: {} }); await r.settle(); await r.sdkReady(signedOutSDK())
  assert.match(r.html, /AVAILABILITY_UNAVAILABLE/); assert.equal(r.nodes.get("clerkSignIn").dataset.clerkMounted, undefined)
})
test("config rejection only exposes a fixed safe error code", async () => {
  const r = runtime({ request: path => { if (path.endsWith("/config")) throw new Error("synthetic-sensitive-error") } }); await r.settle()
  assert.match(r.html, /AVAILABILITY_UNAVAILABLE/); assert.doesNotMatch(r.html, /synthetic-sensitive-error/)
})
test("a disallowed region never mounts a login or signup component", async () => {
  const sdk = signedOutSDK(), r = runtime({ config: { ...closed, region_allowed: false } }); await r.settle(); await r.sdkReady(sdk)
  assert.match(r.html, /当前地区暂未开放服务/); assert.equal(sdk.mounts, 0)
})
test("existing session visiting login renders account without an empty form", async () => {
  const r = runtime({ sdk: signedInSDK() }); await r.settle(); r.render()
  assert.equal(r.state.appUser.id, "offline-app-user"); assert.match(r.html, /账户与偏好/)
  assert.doesNotMatch(r.html, /id="clerkSignIn"/); assertNoBusiness(r)
})
test("signed-in resource emission restores account even before SDK getters publish", async () => {
  const sdk = signedOutSDK(), r = runtime({ hash: "#account" })
  await r.settle(); await r.sdkReady(sdk)
  const resources = signedInSDK()
  sdk.notify({ session: resources.session, user: resources.user })
  await r.settle()
  assert.match(r.html, /账户与偏好/)
  assert.equal(r.state.appUser.id, "offline-app-user")
  assert.equal(r.requests.filter(q => q.path.endsWith("/auth/session")).length, 1)
  assert.doesNotMatch(r.html, /id="clerkSignIn"/); assertNoBusiness(r)
})
test("new active session unmounts old form while App synchronization is pending", async () => {
  const pending = deferred(), sdk = signedOutSDK()
  const r = runtime({ request: path => path.endsWith("/auth/session") ? pending.promise : undefined })
  await r.settle(); await r.sdkReady(sdk)
  const oldRoot = r.nodes.get("clerkSignIn"), resources = signedInSDK()
  sdk.session = resources.session; sdk.user = resources.user
  sdk.notify({ session: sdk.session, user: sdk.user }); await r.settle()
  assert.equal(oldRoot.isConnected, false)
  assert.equal(sdk.unmounts, 1)
  assert.doesNotMatch(r.nodes.get("clerkSignIn")?.innerHTML || "", /offline typed value/)
  assert.match(r.html, /正在同步登录状态/)
  pending.resolve({ app_user: { id: "offline-app-user", nickname: "Offline" } }); await r.settle()
  assert.match(r.html, /账户与偏好/); assert.equal(sdk.mounts, 1); assertNoBusiness(r)
})
test("Clerk account redirect resumes a published session without another sign-in", async () => {
  const sdk = signedOutSDK(), r = runtime()
  await r.settle(); await r.sdkReady(sdk)
  const resources = signedInSDK()
  sdk.session = resources.session; sdk.user = resources.user
  await r.visit("#account")
  assert.match(r.html, /账户与偏好/)
  assert.equal(r.requests.filter(q => q.path.endsWith("/auth/session")).length, 1)
  assert.equal(sdk.mounts, 1); assertNoBusiness(r)
})
test("signed-out resource emission discards pending result while SDK getters lag", async () => {
  const pending = deferred(), sdk = signedOutSDK()
  const r = runtime({ request: path => path.endsWith("/auth/session") ? pending.promise : undefined })
  await r.settle(); await r.sdkReady(sdk)
  const resources = signedInSDK()
  sdk.session = resources.session; sdk.user = resources.user
  sdk.notify({ session: sdk.session, user: sdk.user }); await r.settle()
  sdk.notify({ session: null, user: null }); await r.settle()
  pending.resolve({ app_user: { id: "must-not-restore-old-owner" } }); await r.settle()
  assert.equal(r.state.appUser, null)
  assert.doesNotMatch(r.html, /账户与偏好|must-not-restore-old-owner/); assertNoBusiness(r)
})
test("duplicate resource emissions during handoff remain one App sync", async () => {
  const pending = deferred(), sdk = signedOutSDK()
  const r = runtime({ request: path => path.endsWith("/auth/session") ? pending.promise : undefined })
  await r.settle(); await r.sdkReady(sdk)
  const resources = signedInSDK()
  sdk.session = resources.session; sdk.user = resources.user
  for (let n = 0; n < 5; n++) sdk.notify({ session: sdk.session, user: sdk.user })
  await r.settle()
  assert.equal(r.requests.filter(q => q.path.endsWith("/auth/session")).length, 1)
  pending.resolve({ app_user: { id: "offline-app-user" } }); await r.settle()
  sdk.notify({ session: sdk.session, user: sdk.user }); await r.settle()
  assert.equal(r.requests.filter(q => q.path.endsWith("/auth/session")).length, 1); assertNoBusiness(r)
})
test("sign-out during handoff restores a usable form and cancels token-wait requests", async () => {
  const token = deferred(), sdk = signedOutSDK(), resources = signedInSDK()
  resources.session.getToken = () => token.promise
  const r = runtime(); await r.settle(); await r.sdkReady(sdk)
  sdk.notify({ session: resources.session, user: resources.user }); await r.settle()
  assert.equal(r.state.authSyncing, true)
  sdk.notify({ session: null, user: null }); await r.settle()
  assert.equal(r.state.authSyncing, false)
  assert.equal(r.nodes.get("clerkSignIn").dataset.clerkUiReady, "true")
  token.resolve("synthetic-obsolete-token"); await r.settle()
  assert.equal(r.state.appUser, null)
  assert.equal(r.requests.filter(q => q.path.endsWith("/auth/session")).length, 0)
  assertNoBusiness(r)
})
test("a signed-out snapshot cannot be resurrected by a redirect with stale getters", async () => {
  const sdk = signedInSDK(), r = runtime({ sdk }); await r.settle()
  sdk.notify({ session: sdk.session, user: sdk.user }); await r.settle()
  sdk.notify({ session: null, user: null }); await r.settle()
  const before = r.requests.filter(q => q.path.endsWith("/auth/session")).length
  await r.visit("#account")
  assert.equal(r.state.appUser, null)
  assert.equal(r.requests.filter(q => q.path.endsWith("/auth/session")).length, before)
  assert.doesNotMatch(r.html, /账户与偏好/); assertNoBusiness(r)
})
test("resource emissions from a replaced SDK cannot restore its old account", async () => {
  const oldSDK = signedInSDK(), r = runtime({ sdk: oldSDK }); await r.settle()
  const nextSDK = signedOutSDK(); await r.sdkReady(nextSDK)
  const before = r.requests.filter(q => q.path.endsWith("/auth/session")).length
  oldSDK.notify({ session: oldSDK.session, user: oldSDK.user }); await r.settle()
  assert.equal(r.state.appUser, null)
  assert.equal(r.requests.filter(q => q.path.endsWith("/auth/session")).length, before)
  assertNoBusiness(r)
})
test("an account switch hides old owner data before the new App sync completes", async () => {
  const pending = deferred(), sdk = signedInSDK()
  let syncs = 0
  const r = runtime({ hash: "#account", sdk,
    request: path => path.endsWith("/auth/session") && ++syncs === 2 ? pending.promise : undefined })
  await r.settle()
  r.state.wallet = { balance: 777 }; r.state.tasks = [{ id: "old-task" }]
  r.state.rechargeOrders = [{ id: "old-order" }]; r.state.internalGenerationAllowed = true
  const session = { id: "offline-other-session", getToken: async () => "synthetic-other-token" }
  sdk.notify({ session, user: { id: "offline-other-user" } }); await r.settle()
  assert.equal(r.state.appUser, null); assert.equal(r.state.wallet, null)
  assert.equal(r.state.tasks.length, 0); assert.equal(r.state.rechargeOrders.length, 0)
  assert.equal(r.state.internalGenerationAllowed, false)
  assert.doesNotMatch(r.html, /账户与偏好|offline-app-user/)
  pending.resolve({ app_user: { id: "offline-other-app-user" } }); await r.settle()
  assert.equal(r.state.appUser.id, "offline-other-app-user"); assertNoBusiness(r)
})
test("explicit logout clears the emitted snapshot even if SDK getters remain stale", async () => {
  const sdk = signedInSDK(), r = runtime({ sdk }); await r.settle()
  sdk.notify({ session: sdk.session, user: sdk.user }); await r.settle()
  sdk.signOut = async () => {}
  await r.click("[data-logout]")
  assert.equal(r.state.appUser, null)
  const before = r.requests.filter(q => q.path.endsWith("/auth/session")).length
  await r.visit("#account")
  assert.equal(r.requests.filter(q => q.path.endsWith("/auth/session")).length, before)
  assert.equal(r.nodes.get("clerkSignIn").dataset.clerkUiReady, "true")
  assertNoBusiness(r)
})
test("session emission without a user fails closed instead of borrowing stale user getters", async () => {
  const sdk = signedInSDK(), r = runtime({ sdk }); await r.settle()
  const before = r.requests.filter(q => q.path.endsWith("/auth/session")).length
  sdk.notify({ session: { id: "offline-incomplete-session" } }); await r.settle()
  assert.equal(r.state.appUser, null)
  assert.equal(r.requests.filter(q => q.path.endsWith("/auth/session")).length, before)
  assertNoBusiness(r)
})
test("slow ancillary reads cannot hold an authenticated visitor on login", async () => {
  const r = runtime({ sdk: signedInSDK(), request: path => /wallet|video-tasks|orders/.test(path) ? new Promise(() => {}) : undefined }); await r.settle()
  assert.match(r.html, /账户与偏好/); assert.equal(r.state.authSyncing, false)
})
test("session synchronization is single-flight and timeout is explicit", async () => {
  const pending = deferred(), sdk = signedInSDK()
  const r = runtime({ sdk, request: path => path.endsWith("/auth/session") ? pending.promise : undefined }); await r.settle()
  void r.syncSession(); void r.syncSession(); await r.settle()
  assert.equal(r.requests.filter(q => q.path.endsWith("/auth/session")).length, 1)
  await r.time.tick(10000); assert.match(r.html, /AUTH_SYNC_TIMEOUT/)
  pending.resolve({ app_user: { id: "late-offline-user" } }); await r.settle(); assert.equal(r.state.appUser, null)
})
test("a signed-out transition discards an old in-flight auth response", async () => {
  const pending = deferred(), sdk = signedInSDK()
  const r = runtime({ sdk, request: path => path.endsWith("/auth/session") ? pending.promise : undefined }); await r.settle()
  sdk.session = null; sdk.user = null; await r.syncSession()
  pending.resolve({ app_user: { id: "stale-offline-user" } }); await r.settle(); assert.equal(r.state.appUser, null)
})
test("late ancillary reads cannot repopulate a signed-out user's data", async () => {
  const pending = deferred(), sdk = signedInSDK()
  const r = runtime({ sdk, request: path => /wallet|video-tasks|orders/.test(path) ? pending.promise : undefined }); await r.settle()
  sdk.session = null; sdk.user = null; await r.syncSession()
  pending.resolve({ balance: 999, data: [{ id: "stale-offline-row", provider: "paypal" }] }); await r.settle()
  assert.equal(r.state.wallet, null); assert.equal(r.state.tasks.length, 0); assert.equal(r.state.rechargeOrders.length, 0)
})
test("registration-closed mount disables combined signup and hides signup footer", async () => {
  const sdk = signedOutSDK(), r = runtime(); await r.settle(); await r.sdkReady(sdk)
  assert.equal(sdk.options.withSignUp, false); assert.equal(sdk.options.appearance.elements.footerAction.display, "none")
  await r.visit("#register"); assert.match(r.html, /注册暂未开放/); assert.equal(r.nodes.has("clerkSignIn"), false)
})
for (const config of [null, {}, closed, { ...closed, uploads_enabled: "true", generation_enabled: "true" }, { ...closed, region_allowed: false, uploads_enabled: true, generation_enabled: true }, { ...closed, uploads_enabled: true }, { ...closed, generation_enabled: true }]) {
  test(`closed or incomplete capabilities remove upload and generate controls: ${JSON.stringify(config)}`, async () => {
    const r = runtime({ hash: "#generate?video=kiss-1", config }); await r.settle()
    assert.match(r.html, /data-service-closed/); assert.doesNotMatch(r.html, /type="file"|data-generate\b|data-confirm-generation/)
    await r.uploadImage(0, { type: "image/png" }); r.confirmGeneration(effect, effect.variants[0]); await r.createTask()
    // A split capability may permit one handler, but authentication must still
    // reject it without starting an upload, creating a URL, or submitting.
    await r.click("[data-generate]"); await r.click("[data-confirm-generation]"); assertNoBusiness(r)
  })
}
test("closed handlers remain blocked for a synthetically authenticated app user", async () => {
  const r = runtime({ hash: "#generate?video=kiss-1", sdk: signedInSDK() }); await r.settle()
  await r.uploadImage(0, { type: "image/png" }); r.confirmGeneration(effect, effect.variants[0]); await r.createTask()
  await r.click("[data-generate]"); await r.click("[data-confirm-generation]"); assertNoBusiness(r)
})
test("ordinary capabilities do not derive from signup or recharge", async () => {
  const r = runtime({ hash: "#generate?video=kiss-1", config: { ...closed, uploads_enabled: true, generation_enabled: true } }); await r.settle()
  assert.equal(r.uploadsAllowed(), true); assert.equal(r.generationAllowed(), true)
  assert.match(r.html, /type="file"/); assert.match(r.html, /data-generate/); assertNoBusiness(r)
})
test("new config read invalidates stale open state and ignores an older response", async () => {
  const r = runtime({ hash: "#generate?video=kiss-1", config: { ...closed, uploads_enabled: true, generation_enabled: true } }); await r.settle()
  const first = deferred(), second = deferred(); let n = 0
  r.context.fetch = async () => ({ ok: true, json: async () => ++n === 1 ? first.promise : second.promise })
  const one = r.loadCommerce(false); await r.settle(); assert.equal(r.uploadsAllowed(), false)
  const two = r.loadCommerce(false); await r.settle(); second.resolve(closed); await two
  first.resolve({ ...closed, uploads_enabled: true, generation_enabled: true }); await one
  assert.equal(r.uploadsAllowed(), false); assert.match(r.html, /data-service-closed/)
})
test("closing availability removes an existing confirmation drawer", async () => {
  const r = runtime({ hash: "#generate?video=kiss-1", config: { ...closed, uploads_enabled: true, generation_enabled: true } }); await r.settle()
  r.confirmGeneration(effect, effect.variants[0]); assert.match(r.nodes.get("overlayRoot").innerHTML, /data-confirm-generation/)
  r.state.commerce = closed; r.render(); assert.equal(r.nodes.get("overlayRoot").innerHTML, "")
})
for (const path of ["/api/v1/app/uploads/images", "/api/v1/app/video-tasks"]) {
  test(`closure during token wait blocks the request boundary: ${path}`, async () => {
    const r = runtime({ config: { ...closed, uploads_enabled: true, generation_enabled: true } }); await r.settle()
    const pending = deferred(), sdk = signedInSDK(); sdk.session.getToken = () => pending.promise; r.context.window.VirealClerk = sdk
    const action = r.authFetch(path, { method: "POST" }); r.state.commerce = closed; pending.resolve("synthetic-only")
    await assert.rejects(action, /unavailable/); assertNoBusiness(r)
  })
}
test("retry control only reloads the current page; no business calls", async () => {
  const r = runtime(); await r.settle(); await r.time.tick(15000); await r.click("[data-retry-auth]")
  assert.equal(r.reloads, 1); assertNoBusiness(r)
})

const dance = { ...effect, slug: "dance-1", input_image_count: 1,
  variants: [{ id: "dance-5", coin_cost: 28, duration_seconds: 5 }] }
const danceCatalog = { categories: [{ ...catalog.categories[0], effects: [dance, effect] }] }
const genConfig = () => ({ ...closed, region_allowed: false, country: "CN",
  generation_acceptance_mode: true, generation_acceptance_sign_in_enabled: true,
  generation_acceptance_allowed: true, generation_acceptance_task_id: null,
  generation_acceptance_expires_at: new Date(Date.now() + 3600000).toISOString() })
const setupConfig = () => ({ ...closed, region_allowed: false, country: "CN",
  controlled_account_setup_mode: true, controlled_account_setup_enabled: true,
  controlled_registration_enabled: true,
  controlled_account_setup_expires_at: new Date(Date.now() + 3600000).toISOString() })

for (const [name, override] of [
  ["valid-private-window", {}],
  ["expired", { generation_acceptance_expires_at: new Date(Date.now() - 1000).toISOString() }],
  ["other-account", { generation_acceptance_allowed: false }],
  ["used-slot", { generation_acceptance_allowed: false, generation_acceptance_task_id: "offline-existing-task" }],
  ["HK", { country: "HK" }],
  ["unavailable-config", {}],
]) {
  test(`initial signed-in private registration stays closed after session sync: ${name}`, async () => {
    const sdk = signedInSDK()
    const r = runtime({ hash: "#register", search: "?generation_acceptance=1", sdk,
      config: { ...genConfig(), ...override },
      request: path => { if (name === "unavailable-config" && path.endsWith("/config")) throw new Error("offline unavailable") } })
    await r.settle(); assert.equal(r.state.appUser.id, "offline-app-user")
    assert.match(r.html, /<h1[^>]*>注册暂未开放<\/h1>/)
    assert.equal(r.context.location.hash, "#register"); assert.equal(r.nodes.has("clerkSignIn"), false)
    assert.equal(sdk.mounts, 0); assertNoBusiness(r)
  })
  test(`signed-in private registration stays closed before account fallback: ${name}`, async () => {
    const sdk = signedInSDK()
    const r = runtime({ hash: "#generate?video=dance-1", search: "?generation_acceptance=1", sdk,
      config: { ...genConfig(), ...override }, effectCatalog: danceCatalog,
      request: path => { if (name === "unavailable-config" && path.endsWith("/config")) throw new Error("offline unavailable") } })
    await r.settle(); assert.equal(r.state.appUser.id, "offline-app-user")
    await r.visit("#register")
    assert.match(r.html, /<h1[^>]*>注册暂未开放<\/h1>/)
    assert.doesNotMatch(r.html, /账户与偏好/); assert.equal(r.nodes.has("clerkSignIn"), false)
    assert.equal(r.signupAvailable(false), false); assert.equal(sdk.mounts, 0); assertNoBusiness(r)
  })
}
for (const [name, hash, config, heading] of [
  ["public-signup-closed", "#register", closed, "注册暂未开放"],
  ["missing-invitation", "#controlled-register", { ...closed, controlled_registration_enabled: true }, "受控注册需要有效邀请"],
  ["disallowed-region", "#register", { ...closed, region_allowed: false }, "当前地区暂未开放服务"],
]) {
  test(`initial signed-in account redirect cannot bypass ${name}`, async () => {
    const sdk = signedInSDK(), r = runtime({ hash, config, sdk }); await r.settle()
    assert.equal(r.state.appUser.id, "offline-app-user")
    assert.match(r.html, new RegExp(`<h1[^>]*>${heading}</h1>`))
    assert.equal(r.context.location.hash, hash); assert.equal(r.nodes.has("clerkSignIn"), false)
    assert.equal(sdk.mounts, 0); assertNoBusiness(r)
  })
  test(`signed-in account fallback cannot bypass ${name}`, async () => {
    const sdk = signedInSDK(), r = runtime({ config, sdk }); await r.settle()
    assert.equal(r.state.appUser.id, "offline-app-user"); await r.visit(hash)
    assert.match(r.html, new RegExp(`<h1[^>]*>${heading}</h1>`))
    assert.doesNotMatch(r.html, /账户与偏好/); assert.equal(r.nodes.has("clerkSignIn"), false)
    assert.equal(sdk.mounts, 0); assertNoBusiness(r)
  })
}
for (const [name, hash, search, config] of [
  ["public", "#register", "", { ...closed, registration_enabled: true }],
  ["invited", "#controlled-register", "?controlled_registration=1&__clerk_ticket=offline-ticket", { ...closed, controlled_registration_enabled: true }],
]) {
  test(`permitted ${name} signup route still shows an existing user's account`, async () => {
    const sdk = signedInSDK(), r = runtime({ search, config, sdk }); await r.settle()
    await r.visit(hash); assert.match(r.html, /账户与偏好/)
    assert.equal(r.nodes.has("clerkSignIn"), false); assert.equal(sdk.mounts, 0); assertNoBusiness(r)
  })
}

for (const [search, flag, heading] of [
  ["?generation_acceptance=1", "generation_acceptance_sign_in_enabled", "一次性生成验收登录"],
  ["?payment_only_acceptance=1", "payment_only_sign_in_enabled", "支付专用验收登录"],
  ["?internal_acceptance=1", "internal_sign_in_enabled", "内部验收登录"],
]) {
  test(`accepted private login keeps routing and real form feedback: ${flag}`, async () => {
    const r = runtime({ search, config: { ...closed, region_allowed: false, [flag]: true } })
    const sdk = signedOutSDK(); await r.settle(); await r.sdkReady(sdk)
    assert.match(r.html, new RegExp(heading)); assert.equal(sdk.mounts, 1)
    assert.equal(sdk.options.signInUrl, `https://offline.invalid/${search}#login`)
    assert.equal(sdk.options.forceRedirectUrl, `https://offline.invalid/${search}#account`)
    assert.equal(sdk.options.appearance.elements.footerAction.display, "none")
    const root = r.nodes.get("clerkSignIn"); await r.visit("#/factor-one")
    assert.equal(root, r.nodes.get("clerkSignIn")); assert.equal(sdk.mounts, 1)
    assert.match(r.nodes.get("authFeedback").innerHTML, /安全邮箱验证/); assertNoBusiness(r)
  })
  test(`private URL alone cannot mount or create: ${flag}`, async () => {
    const r = runtime({ search, config: { ...closed, region_allowed: false } })
    const sdk = signedOutSDK(); await r.settle(); await r.sdkReady(sdk)
    assert.equal(sdk.mounts, 0); assert.equal(r.generationAllowed(), false)
    assertNoBusiness(r)
  })
}
test("CN controlled invitation keeps verified-email form and expires locally", async () => {
  const r = runtime({ hash: "", search: "?controlled_registration=1&__clerk_ticket=offline-ticket", config: setupConfig() })
  const sdk = signedOutSDK(); await r.settle(); await r.sdkReady(sdk)
  assert.equal(sdk.mounts, 1); assert.equal(r.signupAvailable(true), true)
  assert.equal(sdk.options.signInUrl, "https://offline.invalid/?controlled_account_setup=1#login")
  assert.equal(r.generationAllowed(), false); assertNoBusiness(r)
  await r.time.tick(3600100); assert.equal(r.signupAvailable(true), false)
  assert.equal(r.nodes.has("clerkSignIn"), false)
})
test("server-authorized one-time generation retains its narrow variant and expiry", async () => {
  const r = runtime({ hash: "#generate?video=dance-1", search: "?generation_acceptance=1", config: genConfig(), effectCatalog: danceCatalog, sdk: signedInSDK() })
  await r.settle(); assert.equal(r.generationAllowed(), true); assert.equal(r.uploadsAllowed(), true)
  assert.equal(r.state.commerce.generation_enabled, false)
  assert.equal(r.selectedVariant(dance).coin_cost, 28); assert.equal(r.signupAvailable(false), false)
  assert.match(r.html, /type="file"/); assertNoBusiness(r)
  await r.visit("#generate?video=kiss-1"); assert.equal(r.generationAllowed(), false)
  assert.doesNotMatch(r.html, /type="file"|data-generate\b/)
  await r.visit("#generate?video=dance-1"); await r.time.tick(3600100)
  assert.equal(r.generationAllowed(), false); assert.doesNotMatch(r.html, /type="file"|data-generate\b/)
})
for (const [name, override] of [
  ["expired", { generation_acceptance_expires_at: new Date(Date.now() - 1000).toISOString() }],
  ["far-future-invalid-window", { generation_acceptance_expires_at: "2099-01-01T00:00:00Z" }],
  ["missing-window", { generation_acceptance_expires_at: null }],
  ["wrong-account", { generation_acceptance_allowed: false }],
  ["used-slot", { generation_acceptance_task_id: "offline-existing-task" }],
  ["HK-not-CN", { country: "HK" }],
  ["mode-off", { generation_acceptance_mode: false }],
]) {
  test(`ordinary true hints cannot bypass private generation ${name}`, async () => {
    const r = runtime({ hash: "#generate?video=dance-1", search: "?generation_acceptance=1", sdk: signedInSDK(), effectCatalog: danceCatalog,
      config: { ...genConfig(), region_allowed: true, uploads_enabled: true, generation_enabled: true, ...override } })
    await r.settle(); assert.equal(r.uploadsAllowed(), false); assert.equal(r.generationAllowed(), false)
    await r.uploadImage(0, { type: "image/png" }); r.confirmGeneration(dance, dance.variants[0]); await r.createTask()
    assert.doesNotMatch(r.html, /type="file"|data-generate\b/); assertNoBusiness(r)
  })
}
for (const mode of ["payment_only_acceptance_mode", "controlled_account_setup_mode"]) {
  test(`raw ${mode} stays restrictive after configuration error`, async () => {
    const r = runtime({ hash: "#generate?video=kiss-1", sdk: signedInSDK(), config: { ...closed, [mode]: true, uploads_enabled: true, generation_enabled: true } })
    await r.settle(); r.context.fetch = async () => { throw new Error("offline unavailable") }
    await r.loadCommerce(false); assert.equal(r.state.commerce[mode], true)
    assert.equal(r.generationAllowed(), false); assert.equal(r.uploadsAllowed(), false)
    assert.equal(r.signupAvailable(false), false); assertNoBusiness(r)
  })
}
test("signed-out transition clears server internal grant and recovery ownership", async () => {
  const sdk = signedInSDK(), r = runtime({ sdk }); await r.settle()
  r.state.internalGenerationAllowed = true; r.state.paymentRecovery.set("old:order", { resume_allowed: true })
  r.state.paymentRecoveryBusy = {}; sdk.session = null; sdk.user = null
  await r.syncSession(); assert.equal(r.state.internalGenerationAllowed, false)
  assert.equal(r.state.paymentRecovery.size, 0); assert.equal(r.state.paymentRecoveryBusy, null)
})
test("expired auth sync cannot send its POST after token wait eventually resolves", async () => {
  const sdk = signedInSDK(), pending = deferred(); sdk.session.getToken = () => pending.promise
  const r = runtime({ sdk }); await r.settle(); await r.time.tick(10000)
  pending.resolve("synthetic-only"); await r.settle()
  assert.equal(r.requests.some(q => q.path.endsWith("/auth/session")), false)
  assert.equal(r.state.appUser, null); assertNoBusiness(r)
})
test("lost one-time submission response refreshes existing task, never replays", async () => {
  let submitted = 0
  const r = runtime({ hash: "#generate?video=dance-1", search: "?generation_acceptance=1", sdk: signedInSDK(), effectCatalog: danceCatalog,
    request(path, options) {
      if (path.endsWith("/video-tasks") && options.method === "POST") { submitted++; throw new Error("offline response lost") }
      if (path.endsWith("/config")) return { ...genConfig(), generation_acceptance_allowed: !submitted, generation_acceptance_task_id: submitted ? "offline-existing-task" : null }
    } })
  await r.settle(); r.state.uploads = [{ id: "synthetic-upload" }]
  await r.createTask(); await r.settle(); await r.createTask()
  assert.equal(submitted, 1); assert.equal(r.generationAllowed(), false)
  assert.match(r.html, /data-open-task="offline-existing-task"/)
  assert.equal(r.requests.filter(q => q.path.includes("paypal/orders")).length, 0)
})

const originalOrder = () => ({ id: "offline-order", app_user_id: "offline-app-user", provider: "paypal", payment_environment: "live",
  product_id: "coins_100", amount: 599, currency: "USD", coin_quantity: 100, status: "created", provider_order_id: "OFFLINE-NOT-A-REAL-ORDER" })
const paymentOnly = () => ({ ...closed, payment_only_acceptance_mode: true, payment_only_acceptance_allowed: true,
  payment_only_order_created: true, payment_only_expires_at: "2099-01-01T00:00:00Z" })
test("original payment selection survives passive config revalidation without mutations", async () => {
  const r = runtime({ sdk: signedInSDK(), config: paymentOnly() }); await r.settle()
  r.state.rechargeOrders = [originalOrder()]; const initial = r.paymentContext()
  assert.equal(r.originalPaymentOrder().id, "offline-order")
  const pending = deferred(); r.context.fetch = async () => ({ ok: true, json: () => pending.promise })
  const query = r.loadCommerce(false); await flush()
  assert.equal(r.paymentContext(), initial); assert.equal(r.paymentCheckout().resumeOrder.id, "offline-order")
  pending.resolve(paymentOnly()); await query; assert.equal(r.paymentContext(), initial)
  assertNoBusiness(r)
})
for (const [name, override] of [
  ["foreign-owner", { app_user_id: "foreign-user" }], ["different-amount", { amount: 600 }],
  ["different-product", { product_id: "coins_500" }], ["captured", { capture_id: "offline-capture" }],
  ["credited", { fulfilled_at: "2026-01-01" }], ["wrong-environment", { payment_environment: "sandbox" }],
]) {
  test(`original payment recovery rejects ${name} with no new checkout`, async () => {
    const r = runtime({ sdk: signedInSDK(), config: paymentOnly() }); await r.settle()
    r.state.rechargeOrders = [{ ...originalOrder(), ...override }]
    assert.equal(r.originalPaymentOrder(), null); assert.equal(r.paymentCheckout(), null); assertNoBusiness(r)
  })
}
test("original-order inspection is GET-only and cannot issue a replacement grant", async () => {
  const r = runtime({ sdk: signedInSDK(), config: paymentOnly(), request(path) {
    if (path.endsWith("/recovery")) return { order_id: "offline-order", replacement_allowed: false, resume_allowed: false, decision: "settlement_pending" }
  } }); await r.settle(); r.state.rechargeOrders = [originalOrder()]
  await r.inspectPayment("offline-order"); await r.settle()
  const reads = r.requests.filter(q => q.path.endsWith("/recovery"))
  assert.equal(reads.length, 1); assert.equal(reads[0].method, "GET")
  assert.equal(r.originalPaymentOrder(), null); assert.equal(r.paymentCheckout(), null); assertNoBusiness(r)
})
test("one replacement requires exact original lineage and an unused remaining slot", async () => {
  const r = runtime({ sdk: signedInSDK(), config: { ...paymentOnly(), payment_only_replacement_original_id: "offline-order", global_real_remaining: 1 } })
  await r.settle(); r.state.rechargeOrders = [originalOrder()]
  assert.equal(r.paymentCheckout().replacementOf, "offline-order")
  r.state.commerce.global_real_remaining = 0; assert.equal(r.paymentCheckout(), null)
  r.state.commerce.global_real_remaining = 1; r.state.rechargeOrders[0].id = "foreign-order"
  assert.equal(r.paymentCheckout(), null); assertNoBusiness(r)
})

function authRuntime(load) {
  const time = clock(), events = []
  const context = {
    document: { querySelector: () => ({ content: "pk_test_synthetic_offline_only" }) },
    window: { dispatchEvent: event => events.push(event) },
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail } },
    Clerk: class { load() { return load() } }, ui: {},
    setTimeout: time.setTimeout, clearTimeout: time.clearTimeout,
  }
  vm.createContext(context); vm.runInContext(authSource.replace(/^import .*\n/gm, ""), context)
  return { time, events, context }
}
test("auth wrapper publishes no late ready event after its deadline", async () => {
  const pending = deferred(), r = authRuntime(() => pending.promise)
  await r.time.tick(15000); assert.equal(r.events[0].detail.code, "AUTH_LOAD_TIMEOUT")
  pending.resolve(); await flush(); assert.equal(r.events.length, 1); assert.equal(r.context.window.VirealClerk, undefined)
})
test("auth wrapper sanitizes vendor errors", async () => {
  const r = authRuntime(async () => { throw new Error("fake sensitive SDK URL") }); await flush()
  assert.equal(r.events[0].detail.code, "AUTH_LOAD_FAILED"); assert.equal("message" in r.events[0].detail, false)
})
test("auth wrapper publishes ready on successful isolated SDK load", async () => {
  const r = authRuntime(async () => {}); await flush(); assert.equal(r.events[0].type, "vireal:clerk-ready")
  await r.time.tick(15000); assert.equal(r.events.length, 1)
})

const stagingConfig = () => ({
  ...closed, country: "CN", region_allowed: false,
  controlled_registration_enabled: false, generation_acceptance_mode: false,
  controlled_account_setup_mode: false, payment_only_acceptance_mode: false,
  internal_sign_in_enabled: false, generation_acceptance_sign_in_enabled: false,
  generation_acceptance_read_allowed: false, generation_acceptance_allowed: false,
  controlled_account_setup_enabled: false, payment_only_sign_in_enabled: false,
  payment_only_acceptance_allowed: false, payment_only_order_created: false,
  staging_sign_in_enabled: true,
  staging_sign_in_expires_at: new Date(Date.now() + 20 * 60 * 1000).toISOString(),
})
test("staging private URL is unavailable without a fresh server hint", async () => {
  const sdk = signedOutSDK(), r = runtime({ hash: "#staging-login", config: { ...closed, region_allowed: false }, sdk })
  await r.settle(); assert.equal(sdk.mounts, 0)
  assert.match(r.html, /验收入口未开放或已过期/); assertNoBusiness(r)
})
test("staging sign-in is separate, has no signup, and preserves routing through refresh", async () => {
  const config = stagingConfig(), sdk = signedOutSDK(), r = runtime({ hash: "#staging-login", config, sdk })
  await r.settle(); assert.equal(sdk.mounts, 1)
  assert.match(r.html, /预发布短时登录验收/)
  assert.equal(r.signupAvailable(), false); assert.equal(sdk.options.withSignUp, false)
  assert.match(sdk.options.signInUrl, /\?staging_login_acceptance=1#staging-login$/)
  assert.equal(sdk.options.forceRedirectUrl, sdk.options.signInUrl)
  const root = r.nodes.get("clerkSignIn")
  r.render(); await r.visit("#/factor-one")
  assert.equal(r.nodes.get("clerkSignIn"), root)
  assert.equal(r.context.location.search, "?staging_login_acceptance=1")
  const refreshedSDK = signedOutSDK()
  const refreshed = runtime({ hash: "#/factor-one", search: r.context.location.search, config, sdk: refreshedSDK })
  await refreshed.settle(); assert.equal(refreshedSDK.mounts, 1)
  assert.match(refreshed.html, /预发布短时登录验收/)
  assert.equal(r.uploadsAllowed(), false); assert.equal(r.generationAllowed(), false)
  assertNoBusiness(r); assertNoBusiness(refreshed)
})
for (const [name, override] of [
  ["off", { staging_sign_in_enabled: false }],
  ["malformed hint", { staging_sign_in_enabled: "true" }],
  ["expired", { staging_sign_in_expires_at: "2000-01-01T00:00:00Z" }],
  ["missing expiry", { staging_sign_in_expires_at: null }],
  ["far-future expiry", { staging_sign_in_expires_at: "2099-01-01T00:00:00Z" }],
  ["wrong country", { country: "US" }], ["unknown country", { country: null }],
  ["ordinary region rewritten", { region_allowed: true }],
  ["signup open", { registration_enabled: true }],
  ["controlled signup open", { controlled_registration_enabled: true }],
  ["recharge open", { recharge_enabled: true }], ["uploads open", { uploads_enabled: true }],
  ["generation open", { generation_enabled: true }],
  ["other acceptance mode", { payment_only_acceptance_mode: true }],
  ["missing business flag", { uploads_enabled: undefined }],
]) {
  test(`staging form rejects ${name} without mounting or requesting a session`, async () => {
    const sdk = signedOutSDK(), r = runtime({ hash: "#staging-login", sdk, config: { ...stagingConfig(), ...override } })
    await r.settle(); assert.equal(sdk.mounts, 0); assert.equal(r.stagingSignInAllowed(), false)
    assert.equal(r.requests.some(q => q.path.endsWith("/auth/session")), false); assertNoBusiness(r)
  })
}
test("staging availability never changes ordinary login or signup region policy", async () => {
  for (const hash of ["#login", "#register", "#controlled-register"]) {
    const sdk = signedOutSDK(), r = runtime({ hash, config: stagingConfig(), sdk })
    await r.settle(); assert.equal(sdk.mounts, 0)
    assert.match(r.html, /当前地区暂未开放服务/); assert.equal(r.signInRegionAllowed(), false)
    assertNoBusiness(r)
  }
})
test("staging form closes at its absolute deadline without renewing it", async () => {
  const config = stagingConfig(), sdk = signedOutSDK(), r = runtime({ hash: "#staging-login", config, sdk })
  await r.settle(); assert.equal(sdk.mounts, 1)
  await r.time.tick(20 * 60 * 1000 + 20)
  assert.equal(r.nodes.has("clerkSignIn"), false); assert.match(r.html, /未开放或已过期/)
  await r.loadCommerce(); await r.settle(); assert.equal(sdk.mounts, 1)
  assert.equal(r.stagingSignInAllowed(), false); assertNoBusiness(r)
})
test("a config error unmounts staging sign-in and clears stale permission", async () => {
  const sdk = signedOutSDK(), r = runtime({ hash: "#staging-login", config: stagingConfig(), sdk })
  await r.settle(); assert.equal(sdk.mounts, 1)
  r.context.fetch = async () => { throw new Error("synthetic network error") }
  await r.loadCommerce(); await r.settle()
  assert.equal(r.state.commerce.staging_sign_in_enabled, false)
  assert.equal(r.state.commerce.staging_sign_in_expires_at, null)
  assert.equal(r.nodes.has("clerkSignIn"), false); assertNoBusiness(r)
})
test("only staging session sync carries the non-secret marker", async () => {
  const r = runtime({ hash: "#staging-login", config: stagingConfig(), sdk: signedInSDK() })
  await r.settle()
  const requests = r.requests.filter(q => q.path.endsWith("/auth/session"))
  assert.equal(requests.length, 1)
  assert.equal(requests[0].headers["x-vireal-staging-login-acceptance"], "1")
  assert.equal(r.state.appUser.id, "offline-app-user")
  assert.equal(r.context.location.hash, "#account")
  assert.equal(r.requests.filter(q => !q.path.endsWith("/auth/session") && q.headers?.["x-vireal-staging-login-acceptance"]).length, 0)
  assertNoBusiness(r)
  const ordinary = runtime({ config: stagingConfig(), sdk: signedInSDK() }); await ordinary.settle()
  assert.equal(ordinary.requests.find(q => q.path.endsWith("/auth/session")).headers["x-vireal-staging-login-acceptance"], undefined)
})
for (const reason of ["expiry", "leave-page"]) {
  test(`staging request is blocked after token wait when ${reason}`, async () => {
    const sdk = signedOutSDK(), r = runtime({ hash: "#staging-login", config: stagingConfig(), sdk })
    await r.settle(); const pending = deferred()
    sdk.session = { id: "synthetic-staging-session", getToken: () => pending.promise }; sdk.user = { id: "synthetic-user" }
    const sync = r.syncSession(); await flush()
    if (reason === "expiry") await r.time.tick(20 * 60 * 1000 + 20)
    else await r.visit("#home")
    pending.resolve("synthetic-not-a-real-token"); await sync; await r.settle()
    assert.equal(r.requests.some(q => q.path.endsWith("/auth/session")), false)
    assert.equal(r.state.appUser, null); assertNoBusiness(r)
  })
}
test("leaving staging form removes only its routing context", async () => {
  const sdk = signedOutSDK(), r = runtime({ hash: "#staging-login", search: "?unrelated=keep", config: stagingConfig(), sdk })
  await r.settle(); assert.match(r.context.location.search, /staging_login_acceptance=1/)
  await r.visit("#home")
  assert.equal(r.context.location.search, "?unrelated=keep"); assert.equal(r.stagingSignInAllowed(), false)
  assert.equal(r.requests.some(q => q.path.endsWith("/auth/session")), false); assertNoBusiness(r)
})
