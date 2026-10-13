(() => {
  "use strict"

  const apiOrigin = (document.querySelector('meta[name="vireal-api-base-url"]')?.content || "").replace(/\/+$/, "")
  const API = apiOrigin.startsWith("__VIREAL_") ? "http://localhost:8000" : apiOrigin
  const POLL_MS = 3500
  const terminalStatuses = new Set(["succeeded", "failed", "canceled", "expired"])
  const icons = {
    home: '<svg viewBox="0 0 24 24" fill="none"><path d="M3.5 10.8 12 4l8.5 6.8V20H15v-5.3H9V20H3.5v-9.2Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
    works: '<svg viewBox="0 0 24 24" fill="none"><path d="M4 6.5h16v12H4zM8 3.5h8" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="m10 10 5 2.5-5 2.5v-5Z" fill="currentColor"/></svg>',
    user: '<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="8" r="3.5" stroke="currentColor" stroke-width="1.7"/><path d="M5.5 20c.6-4 2.8-6 6.5-6s5.9 2 6.5 6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
    back: '<svg viewBox="0 0 24 24" fill="none"><path d="m15 5-7 7 7 7" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    arrow: '<svg viewBox="0 0 24 24" fill="none"><path d="m9 5 7 7-7 7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    plus: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none"><path d="M5 7h14M9 7V4h6v3m2 0-1 13H8L7 7" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none"><path d="m5 12 4.2 4.2L19 6.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  }

  const state = {
    catalog: null,
    catalogError: "",
    categorySlug: "",
    wallet: null,
    tasks: [],
    appUser: null,
    authReady: false,
    authSyncedSessionId: "",
    uploads: [],
    selectedVariants: {},
    generationAttempt: null,
    isSubmitting: false,
    currentTask: null,
    polling: null,
    pollingVersion: 0,
    pollingErrors: 0,
    pollingError: "",
    playbackTimer: null,
    playbackRefreshing: false,
    playbackRetryUrl: new Map(),
    savingTaskId: null,
    commerce: null,
    commerceError: "",
    authView: "login",
    rechargeOrders: [],
    rechargeProduct: "coins_100",
    paymentPolling: null,
    checkoutActive: false,
  }
  const observedClerks = new WeakSet()

  function observeClerk(clerk) {
    if (!observedClerks.has(clerk)) {
      observedClerks.add(clerk)
      clerk.addListener(() => void syncSession())
    }
    void syncSession()
  }

  const app = () => document.getElementById("app")
  const esc = (value = "") => String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char])
  const apiUrl = (path) => new URL(path, `${API}/`).toString()
  const mediaUrl = (path) => path ? new URL(path, `${API}/`).toString() : ""
  const formatDate = (value) => value ? new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value)) : ""
  const statusText = (status) => ({ submitting: "正在提交", pending: "排队中", running: "生成中", rendering_demo: "生成中", saving: "保存中", succeeded: "已完成", failed: "生成失败", canceled: "已取消", submission_unknown: "服务商确认中", expired: "作品已过期/删除" })[status] || status

  function route() {
    const raw = location.hash.slice(1) || "home"
    // Clerk's supported hash router owns slash-prefixed paths such as
    // #/factor-one. They must stay inside the mounted login component.
    if (raw.startsWith("/")) return { name: state.authView, params: new URLSearchParams() }
    const [path, query = ""] = raw.split("?")
    // Clerk appends a slash to its sign-in/sign-up links; keep those links
    // on the app's auth pages without changing Clerk's internal hash routes.
    const name = path.replace(/\/+$/, "")
    return { name: name === "create" ? "generate" : name, params: new URLSearchParams(query) }
  }

  function navigate(name, params = {}) {
    const query = new URLSearchParams(params).toString()
    location.hash = `${name}${query ? `?${query}` : ""}`
  }

  function toast(message, error = false) {
    const root = document.getElementById("toastRoot")
    root.innerHTML = `<div class="toast"${error ? ' style="border-color:rgba(255,159,159,.35);color:#ffd0d0"' : ""}>${esc(message)}</div>`
    clearTimeout(toast.timer)
    toast.timer = setTimeout(() => { root.innerHTML = "" }, 2800)
  }

  function errorDetail(error) {
    return error instanceof Error ? error.message : String(error)
  }

  async function parseResponse(response) {
    if (response.ok) return response.status === 204 ? null : response.json()
    let detail = `${response.status} ${response.statusText}`
    try {
      const payload = await response.json()
      detail = typeof payload.detail === "string" ? payload.detail : detail
    } catch (_) {}
    throw new Error(detail)
  }

  async function token() {
    const current = window.VirealClerk?.session
    if (!current) throw new Error("请先登录")
    const value = await current.getToken()
    if (!value) throw new Error("登录状态已失效")
    return value
  }

  async function authFetch(path, options = {}) {
    const response = await fetch(apiUrl(path), {
      ...options,
      headers: { ...options.headers, Authorization: `Bearer ${await token()}` },
    })
    if (response.status === 401 || (response.status === 403 && path === "/api/v1/app/auth/session")) state.appUser = null
    return response
  }

  async function loadCatalog() {
    state.catalogError = ""
    try {
      state.catalog = await parseResponse(await fetch(apiUrl("/api/v1/app/effect-catalog"), { headers: { Accept: "application/json" } }))
      if (!state.categorySlug) state.categorySlug = state.catalog.categories[0]?.slug || ""
    } catch (error) {
      state.catalogError = errorDetail(error)
    }
    render()
  }

  const paymentText = (zh, en) => /^zh\b/i.test(navigator.language) ? zh : en
  // Refunded describes the payment, not an unresolved case. Review availability
  // is shown separately using the wallet's current payment_hold flag.
  const paymentStatus = (order) => order.fulfilled_at && order.status === "paid"
    ? paymentText("已到账", "Credits received")
    : ({ created: paymentText("等待支付", "Awaiting payment"), approved: paymentText("正在确认", "Confirming payment"), capture_pending: paymentText("支付待确认", "Payment pending"), payment_review: paymentText("人工审核中", "Under review"), refunded: paymentText("已退款", "Refunded"), reversed: paymentText("付款已撤销", "Payment reversed"), canceled: paymentText("已取消", "Cancelled"), failed: paymentText("支付失败", "Payment failed") })[order.status] || paymentText("待确认", "Pending confirmation")

  async function loadCommerce(redraw = true) {
    try {
      const headers = window.VirealClerk?.session ? { Authorization: `Bearer ${await token()}` } : {}
      state.commerce = await parseResponse(await fetch(apiUrl("/api/v1/app/paypal/config"), { cache: "no-store", headers }))
      state.commerceError = ""
    } catch (_) {
      state.commerce = null
      state.commerceError = paymentText("暂时无法确认服务地区和充值状态", "Service availability could not be confirmed")
    }
    if (redraw) render()
  }

  async function loadRechargeOrders() {
    if (!state.appUser) return
    try {
      const result = await parseResponse(await authFetch("/api/v1/app/orders?limit=20"))
      state.rechargeOrders = result.data.filter(order => order.provider === "paypal")
    } catch (_) {}
  }

  async function refreshPayments() {
    await Promise.all([loadCommerce(false), loadWallet(false), loadRechargeOrders()])
    if (route().name === "wallet" && !state.checkoutActive) render()
    clearTimeout(state.paymentPolling)
    if (route().name === "wallet" && state.rechargeOrders.some(order => !order.fulfilled_at && ["created", "approved", "capture_pending", "payment_review"].includes(order.status))) {
      state.paymentPolling = setTimeout(refreshPayments, 10000)
    }
  }

  let paypalSdkPromise
  async function paypalSdk(config) {
    if (window.paypal?.createInstance) return window.paypal
    if (!paypalSdkPromise) paypalSdkPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script")
      script.src = config.environment === "live" ? "https://www.paypal.com/web-sdk/v6/core" : "https://www.sandbox.paypal.com/web-sdk/v6/core"
      script.async = true
      script.onload = () => window.paypal?.createInstance ? resolve(window.paypal) : reject(new Error("PayPal SDK unavailable"))
      script.onerror = () => { paypalSdkPromise = null; script.remove(); reject(new Error("PayPal SDK unavailable")) }
      document.head.append(script)
    })
    return paypalSdkPromise
  }

  async function mountPayPal() {
    const root = document.getElementById("paypalCheckout")
    const config = state.commerce
    const userId = state.appUser?.id
    const product = state.rechargeProduct
    if (!root || root.dataset.mounted || !userId || !config?.recharge_enabled || state.wallet?.payment_hold) return
    root.dataset.mounted = "true"
    const message = text => { if (root.isConnected) root.querySelector("[data-payment-message]").textContent = text }
    const key = `vireal-payment:${userId}`
    let activeOrder
    try {
      const sdk = await paypalSdk(config)
      const instance = await sdk.createInstance({ clientId: config.client_id, components: ["paypal-payments"] })
      const eligible = await instance.findEligibleMethods({ currencyCode: "USD" })
      if (!root.isConnected) return
      if (!eligible.isEligible("paypal")) { message(paymentText("PayPal 当前不可用，请联系客服", "PayPal is not available; please contact support")); return }
      const checkout = await instance.createPayPalOneTimePaymentSession({
        async onApprove(data) {
          state.checkoutActive = false
          if (!activeOrder || data.orderId !== activeOrder.provider_order_id || state.appUser?.id !== userId) {
            message(paymentText("订单需要重新确认，请刷新记录", "Please refresh to verify the order")); return
          }
          try {
            const order = await parseResponse(await authFetch(`/api/v1/app/paypal/orders/${activeOrder.id}/capture`, { method: "POST" }))
            if (order.fulfilled_at && order.status === "paid") {
              sessionStorage.removeItem(key)
              toast(paymentText("充值已到账", "Credits received"))
            } else toast(paymentText("支付正在确认，请勿重复付款", "Payment is being confirmed; do not pay again"))
          } catch (_) { toast(paymentText("支付结果待确认，请查看充值记录，不要重复付款", "Payment confirmation is pending; check your orders before paying again"), true) }
          await refreshPayments()
        },
        onCancel() { state.checkoutActive = false; toast(paymentText("支付已取消，请以订单状态为准", "Checkout cancelled; check your order status")); void refreshPayments() },
        onError() { state.checkoutActive = false; toast(paymentText("支付暂未确认，请查看记录后再操作", "Payment has not been confirmed; please check order history"), true); void refreshPayments() },
      })
      if (!root.isConnected) return
      const button = document.createElement("paypal-button")
      root.prepend(button)
      let starting = false
      button.addEventListener("click", async () => {
        if (starting || state.appUser?.id !== userId) return
        starting = true
        state.checkoutActive = true
        message(paymentText("正在创建安全支付订单…", "Creating a secure payment order…"))
        // Start immediately within the click's user activation; do not await creation first.
        const orderPromise = (async () => {
          let attempt
          try { attempt = JSON.parse(sessionStorage.getItem(key) || "null") } catch (_) {}
          if (!attempt || attempt.product_id !== product) attempt = { product_id: product, idempotency_key: crypto.randomUUID() }
          sessionStorage.setItem(key, JSON.stringify(attempt))
          activeOrder = await parseResponse(await authFetch("/api/v1/app/paypal/orders", { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": attempt.idempotency_key }, body: JSON.stringify({ product_id: product }) }))
          if (activeOrder.fulfilled_at || ["failed", "canceled", "refunded", "reversed"].includes(activeOrder.status) || !activeOrder.provider_order_id) {
            sessionStorage.removeItem(key)
            throw new Error("Please refresh your payment records")
          }
          sessionStorage.setItem(key, JSON.stringify({ ...attempt, order_id: activeOrder.id }))
          return { orderId: activeOrder.provider_order_id }
        })()
        try { await checkout.start({ presentationMode: "auto" }, orderPromise) }
        catch (_) { state.checkoutActive = false; message(paymentText("订单暂未确认，请刷新充值记录", "Order confirmation unavailable; refresh your payment records")); void refreshPayments() }
        finally { starting = false }
      })
      message(paymentText("由 PayPal 安全收款，后端确认后到账", "Secure PayPal checkout; credits are issued after server verification"))
    } catch (_) { message(paymentText("支付组件加载失败，请稍后刷新", "Checkout could not load; please refresh later")); root.dataset.mounted = "" }
  }

  async function syncSession() {
    const clerk = window.VirealClerk
    if (!clerk?.session || !clerk.user) {
      // Clerk also notifies while the signed-out form is being edited. Only
      // redraw on an auth transition; remounting would reset email/OTP state.
      const authChanged = !state.authReady || Boolean(state.appUser || state.wallet || state.authSyncedSessionId)
      state.appUser = null
      state.wallet = null
      state.tasks = []
      state.rechargeOrders = []
      clearTimeout(state.paymentPolling)
      state.checkoutActive = false
      state.currentTask = null
      state.generationAttempt = null
      state.uploads.forEach((item) => item?.preview && URL.revokeObjectURL(item.preview))
      state.uploads = []
      stopTaskPolling()
      state.authSyncedSessionId = ""
      state.authReady = true
      stopTaskPolling()
      clearTimeout(state.playbackTimer)
      if (authChanged) void loadCommerce(false)
      if (authChanged) render()
      return
    }
    if (state.authSyncedSessionId === clerk.session.id && state.appUser) return
    try {
      const response = await authFetch("/api/v1/app/auth/session", { method: "POST", headers: { "Content-Type": "application/json" } })
      const payload = await parseResponse(response)
      if (state.appUser?.id !== payload.app_user.id) {
        state.rechargeOrders = []
        clearTimeout(state.paymentPolling)
        state.checkoutActive = false
        state.currentTask = null
        state.tasks = []
        state.generationAttempt = null
        state.uploads.forEach((item) => item?.preview && URL.revokeObjectURL(item.preview))
        state.uploads = []
        stopTaskPolling()
      }
      state.appUser = payload.app_user
      state.authSyncedSessionId = clerk.session.id
      state.authReady = true
      await Promise.all([loadWallet(false), loadTasks(false), loadRechargeOrders(), loadCommerce(false)])
      const afterLogin = sessionStorage.getItem("vireal-after-login")
      if (afterLogin) {
        sessionStorage.removeItem("vireal-after-login")
        location.hash = afterLogin
      }
      // Clerk may already have redirected to this hash. In that case no
      // hashchange event fires, so render the newly authenticated state here.
      render()
      if (route().name === "wallet") void refreshPayments()
      else if (route().name === "generation" && route().params.get("id")) startPolling(route().params.get("id"))
    } catch (error) {
      state.authReady = true
      toast(`登录同步失败：${errorDetail(error)}`, true)
      render()
    }
  }

  function requireAuth(targetHash) {
    if (state.appUser) return true
    sessionStorage.setItem("vireal-after-login", targetHash || location.hash || "#home")
    navigate("login")
    return false
  }

  async function loadWallet(shouldRender = true) {
    if (!state.appUser) return
    try { state.wallet = await parseResponse(await authFetch("/api/v1/app/wallet")) }
    catch (error) { if (shouldRender) toast(errorDetail(error), true) }
    if (shouldRender) render()
  }

  async function loadTasks(shouldRender = true) {
    if (!state.appUser) return
    try {
      const payload = await parseResponse(await authFetch("/api/v1/app/video-tasks?skip=0&limit=50"))
      state.tasks = payload.data
    } catch (error) { if (shouldRender) toast(errorDetail(error), true) }
    if (shouldRender) render()
  }

  function categories() { return state.catalog?.categories || [] }
  function activeCategory() { return categories().find((item) => item.slug === state.categorySlug) || categories()[0] }
  function allEffects() { return categories().flatMap((category) => category.effects) }
  function effectBySlug(slug) { return allEffects().find((effect) => effect.slug === slug) }
  function categoryFor(effect) { return categories().find((category) => category.id === effect?.category_id) }
  function selectedVariant(effect) {
    return effect?.variants.find((variant) => variant.id === state.selectedVariants[effect.id]) || effect?.variants.find((variant) => variant.is_default) || effect?.variants[0]
  }

  function surface(effect, category, index = 0) {
    const tones = category?.tones?.length === 3 ? category.tones : ["#476b70", "#18262c", "#98d9de"]
    const style = `--tone-a:${esc(tones[0])};--tone-b:${esc(tones[1])};--tone-light:${esc(tones[2])};--tone-dark:${esc(tones[1])}`
    const media = effect?.preview_video_url
      ? `<video muted loop playsinline preload="metadata" poster="${esc(mediaUrl(effect.poster_url))}"><source src="${esc(mediaUrl(effect.preview_video_url))}"></video>`
      : effect?.poster_url ? `<img src="${esc(mediaUrl(effect.poster_url))}" alt="" loading="lazy">` : ""
    return `<span class="media-surface${media ? " has-media" : ""}" style="${style}">${media}<i class="surface-orb"></i>${media ? "" : `<span class="surface-label">VIREAL / EFFECT</span><span class="surface-number">${String(index + 1).padStart(2, "0")}</span>`}</span>`
  }

  function header() {
    const initials = state.appUser?.nickname?.slice(0, 2).toUpperCase() || "登录"
    return `<header class="public-header top-safe"><button class="brand-button" data-route="home"><span class="brand-mark">VIREAL</span><span class="brand-sub">AI MOTION STUDIO</span></button><div class="header-actions"><button class="energy-pill" data-route="wallet" aria-label="查看金币余额">✦ <span>${state.wallet ? state.wallet.balance : "--"}</span></button><button class="avatar-button" data-route="${state.appUser ? "account" : "login"}" aria-label="账户">${esc(initials)}</button></div></header>`
  }

  function nav(active) {
    return `<div class="nav-dock"><nav class="utility-nav" aria-label="底部导航"><button data-route="home" aria-current="${active === "home" ? "page" : "false"}">${icons.home}发现</button><button data-route="works" aria-current="${active === "works" ? "page" : "false"}">${icons.works}作品</button><button data-route="account" aria-current="${active === "account" ? "page" : "false"}">${icons.user}我的</button></nav></div>`
  }

  function homePage() {
    if (!state.catalog && !state.catalogError) return shell(`<section class="page screen-page"><p class="loading-copy">正在读取效果目录…</p></section>`)
    if (state.catalogError) return shell(`<section class="page home-page">${header()}<div class="catalog-error">目录暂时无法读取<br>${esc(state.catalogError)}<br><button class="secondary-button" data-retry-catalog>重新加载</button></div>${nav("home")}</section>`)
    const category = activeCategory()
    const categoryTabs = categories().map((item) => `<button class="segment" data-category="${esc(item.slug)}" aria-selected="${item.slug === category?.slug}">${esc(item.name_zh)}</button>`).join("")
    const cards = (category?.effects || []).map((effect, index) => {
      const lowest = Math.min(...effect.variants.map((variant) => variant.coin_cost))
      return `<button class="effect-card" data-effect="${esc(effect.slug)}">${surface(effect, category, index)}<span class="card-shade"></span><span class="play-orb">${icons.arrow}</span><span class="card-meta"><small>${esc(effect.title_en)}</small><h2>${esc(effect.title_zh)}</h2><p>${effect.input_image_count} 张照片 · ${lowest} ✦ 起</p></span></button>`
    }).join("")
    return shell(`<section class="page home-page page-enter"><div class="home-spacer"></div>${header()}<div class="segmented-scroll" role="tablist">${categoryTabs}</div><div class="section-head"><div><div class="category-meta">${esc(category?.name_en || "")}</div><h1>选择一种<span>心动效果</span></h1></div><div class="live-hint"><i></i>实时目录</div></div><div class="effect-grid">${cards || '<div class="catalog-error" style="grid-column:1/-1">该分类暂时没有已发布效果</div>'}</div><div class="catalog-footer"><div><strong>效果数量由运营后台决定</strong><span>价格、时长与可上传图片数以服务端为准</span></div><span class="arrow-orb">${icons.arrow}</span></div>${nav("home")}</section>`)
  }

  function generatePage(params) {
    const effect = effectBySlug(params.get("video")) || allEffects()[0]
    if (!effect) return homePage()
    const category = categoryFor(effect)
    const variant = selectedVariant(effect)
    const enough = state.wallet && variant && state.wallet.balance >= variant.coin_cost
    const uploaded = state.uploads.filter((entry) => entry?.id).length
    const uploading = state.uploads.some((entry) => entry?.pending)
    const uploadTiles = Array.from({ length: effect.input_image_count }, (_, index) => {
      const entry = state.uploads[index]
      return `<label class="upload-tile" aria-pressed="${Boolean(entry)}" aria-busy="${Boolean(entry?.pending)}"><input type="file" accept="image/jpeg,image/png,image/webp" data-upload-index="${index}" ${uploading ? "disabled" : ""}>${entry ? `<img src="${esc(entry.preview)}" alt="${entry.pending ? "正在上传照片" : "已上传照片"} ${index + 1}"><button class="remove-upload" type="button" data-remove-upload="${index}" ${uploading ? "disabled" : ""}>×</button>` : `<span class="upload-center"><span class="plus-ring">${icons.plus}</span><span class="upload-title">上传照片 ${index + 1}</span><span class="upload-hint">JPG / PNG / WebP</span></span>`}</label>`
    }).join("")
    const variants = effect.variants.map((item) => `<button class="duration-button" data-variant="${item.id}" aria-pressed="${item.id === variant?.id}"><b>${item.duration_seconds} 秒</b><small>${item.coin_cost} ✦</small></button>`).join("")
    const recommendations = (effect.recommendations || []).map((slug) => effectBySlug(slug)).filter(Boolean).slice(0, 4).map((item, index) => `<button class="recommend-card" data-effect="${esc(item.slug)}">${surface(item, categoryFor(item), index)}<strong>${esc(item.title_zh)}</strong></button>`).join("")
    let buttonText = "登录后生成"
    let disabled = false
    if (state.appUser) {
      buttonText = uploaded < effect.input_image_count ? `还需上传 ${effect.input_image_count - uploaded} 张照片` : !enough ? "金币余额不足" : "确认并生成"
      disabled = uploaded < effect.input_image_count
    }
    if (uploading) { buttonText = "正在上传照片"; disabled = true }
    if (state.isSubmitting) { buttonText = "正在提交"; disabled = true }
    return shell(`<section class="page page-enter"><div class="detail-hero">${surface(effect, category)}<div class="detail-shade"></div><div class="detail-bar"><button class="icon-button" data-route="home">${icons.back}</button><button class="energy-pill" data-route="wallet">✦ ${state.wallet ? state.wallet.balance : "--"}</button></div><div class="hero-copy"><div class="eyeline">${esc(effect.title_en)}</div><h1>${esc(effect.title_zh)}</h1><p>${esc(effect.description || "上传照片，由 AI 生成自然流畅的动态时刻。")}</p></div></div><div class="generator-panel"><div class="panel-head"><div><h2>上传${effect.input_image_count}张照片</h2><p>图片仅用于本次生成，并按当前素材保留策略处理。</p></div><span class="data-badge">服务端配置</span></div><div class="upload-grid${effect.input_image_count === 2 ? " two" : ""}">${uploadTiles}</div><div class="duration-wrap"><div class="field-label">选择时长 <span>实际金币价格</span></div><div class="duration-group">${variants}</div></div><div class="balance-line"><div><span>本次消耗</span><b>${variant?.coin_cost ?? "--"} ✦</b></div><div><span>剩余余额</span><b class="${state.appUser && !enough ? "insufficient" : ""}">${state.wallet ? state.wallet.balance : "登录后查看"} ${state.wallet ? "✦" : ""}</b></div><div><span>今日 / 并发可用</span><b>${state.wallet ? `${state.wallet.daily_remaining} / ${state.wallet.concurrent_remaining}` : "-- / --"}</b></div></div><button class="generate-button" data-generate ${disabled ? "disabled" : ""}>${buttonText}<small>${variant ? `${variant.duration_seconds}s` : ""}</small></button></div>${recommendations ? `<div class="subsection"><div class="subsection-head"><h2>${esc(effect.recommendation_label || "推荐效果")}</h2><span>继续探索</span></div><div class="recommend-grid">${recommendations}</div></div>` : ""}<div style="padding:0 16px 28px">${nav("")}</div></section>`)
  }

  function taskVisual(task) {
    if (task?.status === "succeeded" && task.playback_url) return `<video class="task-video" data-task-video="${esc(task.id)}" controls playsinline preload="metadata" src="${esc(task.playback_url)}"></video>`
    const failed = task && ["failed", "canceled", "expired"].includes(task.status)
    return `<div class="status-visual"><div class="status-center">${failed ? `<div><span style="color:var(--danger);font-size:42px">!</span><h2>${statusText(task.status)}</h2><p>${esc(task.error || "请查看任务记录，或联系客服核查。")}</p><p>${task.coin_refunded_at ? "金币已退回钱包" : task.status === "expired" ? "素材保留期已结束或作品已删除；这不代表发生退款。" : "金币结算以钱包流水为准"}</p></div>` : `<div><div class="status-spinner"></div><h2>${statusText(task?.status || "pending")}</h2><p>${task?.status === "submission_unknown" ? "正在核对服务商状态，确认前不会自动退款，避免重复补偿。" : "生成将在后台继续，可以先去浏览其他效果。"}</p><div class="progress-track"><i></i></div></div>`}</div></div>`
  }

  function taskDelivery(task) {
    if (!task) return ""
    const deadline = task.expires_at ? formatDate(task.expires_at) : ""
    const ready = task.status === "succeeded" && task.playback_url && (!task.expires_at || Date.parse(task.expires_at) > Date.now())
    return `<div class="catalog-footer"><div><strong>${ready ? `作品保留至 ${esc(deadline)}` : "任务与钱包流水可供核查"}</strong><span>输入照片上传后保留 24 小时；成品保存成功后保留 24 小时，请及时下载。</span>${state.pollingError ? `<span role="status">状态更新暂时中断，正在重试；不会重新生成。</span>` : ""}</div></div><div class="status-actions"><button class="secondary-button" data-refresh-task="${esc(task.id)}">刷新任务状态</button>${ready ? `<button class="primary-button" data-download-task="${esc(task.id)}" ${state.savingTaskId ? "disabled" : ""}>${state.savingTaskId ? "正在下载…" : "下载 MP4"}</button><button class="secondary-button" data-share-task="${esc(task.id)}" ${state.savingTaskId ? "disabled" : ""}>系统保存/分享</button>` : ""}</div>`
  }

  function generationPage(params) {
    const task = state.currentTask?.id === params.get("id") ? state.currentTask : state.tasks.find((item) => item.id === params.get("id"))
    if (!state.appUser) return loginPage()
    return shell(`<section class="page screen-page page-enter">${header()}<h1 class="screen-title">${esc(task?.effect_title || "生成任务")}</h1><p class="screen-copy">任务状态、实际消耗与剩余余额均来自服务端。</p><div class="status-panel">${taskVisual(task)}${taskDelivery(task)}<div class="status-actions"><button class="secondary-button" data-route="works">查看作品</button><button class="primary-button" data-route="home">继续浏览</button></div></div>${task ? `<div class="catalog-footer"><div><strong>${task.duration} 秒 · ${task.coin_cost ?? 0} ✦</strong><span>${esc(task.execution_type)} · ${esc(task.resolution)} · ${esc(task.aspect_ratio)}</span></div><span class="status-chip ${terminalStatuses.has(task.status) && task.status !== "succeeded" ? "failed" : "pending"}">${statusText(task.status)}</span></div>` : '<div class="catalog-error">正在读取任务状态…</div>'}${nav("works")}</section>`)
  }

  function worksPage() {
    if (!state.appUser) return loginPage()
    const rows = state.tasks.map((task, index) => {
      const effect = effectBySlug(task.effect_slug)
      const category = categoryFor(effect)
      return `<div class="list-item"><button class="list-thumb" data-open-task="${task.id}">${effect ? surface(effect, category, index) : ""}</button><div class="list-content"><strong>${esc(task.effect_title || task.template_id)} · ${task.duration} 秒</strong><span>${formatDate(task.created_at)} · ${task.coin_cost ?? 0} ✦</span></div><button class="status-chip ${["failed", "canceled", "expired"].includes(task.status) ? "failed" : task.status === "succeeded" ? "" : "pending"}" data-open-task="${task.id}">${statusText(task.status)}</button>${terminalStatuses.has(task.status) && task.status !== "expired" ? `<button class="icon-button" style="min-width:36px;min-height:36px" data-delete-task="${task.id}" aria-label="删除作品">${icons.trash}</button>` : ""}</div>`
    }).join("")
    return shell(`<section class="page screen-page page-enter">${header()}<h1 class="screen-title">我的作品</h1><p class="screen-copy">生成任务与结果统一保存在当前账户下。</p>${rows ? `<div class="list-stack">${rows}</div>` : `<div class="empty-panel">${icons.works}<h2>还没有作品</h2><p>选择一个效果，上传照片生成你的第一条 AI 视频。</p><button class="primary-button" style="margin-top:18px;padding:0 20px" data-route="home">开始创作</button></div>`}${nav("works")}</section>`)
  }

  function walletPage() {
    if (!state.appUser) return loginPage()
    const wallet = state.wallet
    const ledger = (wallet?.ledger || []).map((item) => `<div class="ledger-row"><div><strong>${esc(item.reason)}</strong><small>${formatDate(item.created_at)} · ${esc(item.entry_type)}</small></div><b class="${item.delta > 0 ? "positive" : ""}">${item.delta > 0 ? "+" : ""}${item.delta} ✦</b></div>`).join("")
    const config = state.commerce
    const available = config?.recharge_enabled && !wallet?.payment_hold
    const notice = wallet?.payment_hold ? paymentText("支付账户正在人工审核，请联系客服。", "Your payment account is under review. Please contact support.") : config?.region_allowed === false ? paymentText("当前地区暂未开放充值。", "Recharge is unavailable in this region.") : config?.global_real_remaining === 0 ? paymentText("今日全站额度已用完，暂停新充值和生成。", "Daily generation capacity is exhausted. New recharge and generation are paused.") : state.commerceError || (!available ? paymentText("充值尚未开放；等待收款验收完成。", "Recharge will open after payment verification is complete.") : paymentText("注册不赠币；充值不会解除生成额度限制。", "No signup credits. Recharge does not bypass generation limits."))
    const products = (config?.products || []).map(product => `<button class="recharge-product ${product.product_id === state.rechargeProduct ? "selected" : ""}" data-recharge-product="${esc(product.product_id)}" ${available ? "" : "disabled"}><b>${product.coins} ✦</b><span>$${(product.amount / 100).toFixed(2)} USD</span></button>`).join("")
    const orders = state.rechargeOrders.map(order => `<div class="ledger-row"><div><strong>${esc(paymentStatus(order))} · ${order.coin_quantity || 0} ✦</strong><small>${formatDate(order.created_at)} · ${esc(order.id)}</small></div><b>$${((order.amount || 0) / 100).toFixed(2)}</b></div>`).join("")
    if (available) setTimeout(mountPayPal, 0)
    return shell(`<section class="page screen-page page-enter">${header()}<h1 class="screen-title">${paymentText("金币与充值", "Credits & recharge")}</h1><p class="screen-copy">${esc(notice)}</p><div class="wallet-card"><small>AVAILABLE BALANCE</small><strong>${wallet?.balance ?? "--"} ✦</strong><p>今日剩余 ${wallet?.daily_remaining ?? "--"} 次 · 当前可并发 ${wallet?.concurrent_remaining ?? "--"} 个任务</p><p>${paymentText("全站今日剩余", "Site daily capacity remaining")}: ${wallet?.global_real_remaining ?? config?.global_real_remaining ?? "--"} / ${config?.global_real_limit ?? 30}</p>${config?.resets_at ? `<p>${paymentText("额度恢复时间", "Capacity resets")}: ${esc(new Date(config.resets_at).toLocaleString())}</p>` : ""}</div><div class="recharge-products">${products}</div>${available ? '<div id="paypalCheckout" class="profile-card"><p data-payment-message class="screen-copy">Loading PayPal…</p></div>' : ""}<p class="screen-copy">${paymentText("点击支付即确认服务条款与充值说明。", "By paying, you accept the terms and recharge information.")} <a href="#terms">${paymentText("服务条款", "Terms")}</a> · <a href="#privacy">${paymentText("隐私", "Privacy")}</a> · <a href="#refunds">${paymentText("充值与退款帮助", "Recharge & refunds")}</a></p><button class="secondary-button" data-refresh-payments>${paymentText("刷新余额与充值记录", "Refresh balance & orders")}</button><div class="subsection-head"><h2>${paymentText("充值记录", "Recharge orders")}</h2></div><div class="profile-card">${orders || paymentText("暂无充值订单", "No recharge orders")}</div><div class="subsection-head" style="margin-top:24px"><h2>余额流水</h2><span>最近 50 条</span></div><div class="profile-card">${ledger || '<p class="screen-copy" style="margin:0">暂无金币流水</p>'}</div>${nav("")}</section>`)
  }

  function accountPage() {
    if (!state.appUser) return loginPage()
    return shell(`<section class="page screen-page page-enter">${header()}<h1 class="screen-title">账户与偏好</h1><div class="profile-card"><div class="profile-row"><div class="profile-avatar">${esc((state.appUser.nickname || "VI").slice(0, 2).toUpperCase())}</div><div><strong>${esc(state.appUser.nickname || "Vireal User")}</strong><span style="display:block;margin-top:5px;color:#84979e;font-size:10px">${esc(state.appUser.id)}</span></div></div><div class="settings-list"><button data-route="wallet"><span><b>金币与额度</b><small>查看真实余额和流水</small></span>${icons.arrow}</button><button data-route="works"><span><b>作品记录</b><small>查看生成状态与结果</small></span>${icons.arrow}</button><button data-toast="素材和生成结果按当前服务端保留策略处理"><span><b>隐私与数据</b><small>私有素材与短期签名访问</small></span>${icons.arrow}</button></div></div><button class="danger-button" style="width:100%;margin-top:14px" data-logout>退出登录</button>${nav("account")}</section>`)
  }

  function legalPage(kind) {
    const texts = {
      terms: [paymentText("服务条款", "Terms of service"), paymentText("经营者：李启辉（品牌 Vireal）。Vireal 提供 AI 视频生成服务，仅限已开放地区使用。请仅上传你拥有使用权、获得必要授权且符合平台和服务商规则的成年人物素材，禁止侵权、色情及违法内容。生成可能失败或被安全规则拒绝；失败退回金币不代表现金退款。金币仅用于本站生成服务，不可转让、提现或作为通用支付工具。时长、价格、额度和结果保留时间以服务端说明为准。受控验收不代表公众注册或充值已经开放。", "Operator: Li Qihui (李启辉), trading as Vireal. Vireal provides AI video generation in supported regions. Upload only adult-person images that you have rights and necessary consent to use. Illegal, infringing and sexually explicit content is prohibited. Generation may fail or be rejected by safety checks; returned generation credits are not cash refunds. Credits are non-transferable, cannot be withdrawn, and are only usable for this service. Server-side pricing, limits and retention rules apply. Controlled acceptance does not mean public registration or recharge is open.")],
      privacy: [paymentText("隐私与数据", "Privacy & data"), paymentText("邮箱与身份验证由 Clerk 提供，支付由 PayPal 处理，生成由模型服务商处理，文件存于私有 Cloudflare R2。本站不接收银行卡密码或支付密码。输入照片从上传起保留24小时，成品从保存成功起保留24小时；实际有效期以作品页面的服务端时间为准，播放链接短期有效。订单、账本和审计记录与媒体分别保留，以支持到账、退款和争议处理。请勿上传未经授权的个人信息。联系下方客服申请数据相关处理。", "Clerk handles identity verification, PayPal processes payments, model providers process generation, and private Cloudflare R2 stores media. We do not collect card or payment passwords. Input images are retained for 24 hours from upload; results for 24 hours from successful persistence. The server deadline displayed with your work applies; playback links are short-lived. Orders, ledgers and audit records are retained separately for payment, refund and dispute handling. Do not upload unauthorized personal data. Contact support for data requests.")],
      refunds: [paymentText("充值与退款帮助", "Recharge & refund help"), paymentText("美元套餐为100金币/$5.99、220金币/$11.99、500金币/$24.99，注册不赠币。只有后端确认真实收款后才到账；显示待确认时请不要重复付款。每人每天最多5次、同时1个任务，全站每天最多30次真实生成，按UTC日界恢复。充值不保证即时生成名额。退款请提供订单号联系人工客服，按照订单消费情况和适用规则审核，不影响适用法律赋予的权利。退款、拒付和撤销可能暂停新充值和生成，记录仍可查看。", "USD packages: 100 credits/$5.99, 220/$11.99, 500/$24.99. No signup credits. Credits are issued only after server-side payment verification; do not repay a pending order. Limits: 5 submissions per user/day, 1 concurrent task, 30 site-wide submissions/day, resetting at UTC midnight. Recharge does not reserve generation capacity. Contact support with your order ID for manual refund review under applicable rules and legal rights. Refunds, disputes and reversals may suspend new purchases and generation while records remain available.")],
    }
    const [title, copy] = texts[kind]
    const support = state.commerce?.support_email || "li522903183@gmail.com"
    return shell(`<section class="page screen-page">${header()}<h1 class="screen-title">${esc(title)}</h1><div class="profile-card"><p class="screen-copy">${esc(copy)}</p><p class="screen-copy">${paymentText("客服", "Support")}: <a href="mailto:${esc(support)}">${esc(support)}</a></p><p class="screen-copy">2026-10-13</p></div><button class="secondary-button" data-route="home">${paymentText("返回首页", "Back to home")}</button></section>`)
  }

  function loginPage() {
    const signup = route().name === "register"
    if (state.commerce?.region_allowed === false) return shell(`<section class="page screen-page">${header()}<h1 class="screen-title">${paymentText("当前地区暂未开放服务", "Service unavailable in this region")}</h1><p class="screen-copy">${paymentText("你仍可浏览公开效果。", "You can still browse public effects.")}</p><button data-route="home" class="primary-button">${paymentText("浏览效果", "Browse effects")}</button></section>`)
    if (signup && !state.commerce?.registration_enabled) return shell(`<section class="page screen-page">${header()}<h1 class="screen-title">${paymentText("注册暂未开放", "Registration is not yet open")}</h1><p class="screen-copy">${esc(state.commerceError || paymentText("注册与充值将在收款验收后一起开放。", "Registration and recharge will open together after payment verification."))}</p><button data-route="login" class="secondary-button">${paymentText("已有账号登录", "Sign in")}</button></section>`)
    const ready = Boolean(window.VirealClerk)
    setTimeout(mountSignIn, 0)
    return shell(`<section class="page screen-page page-enter"><header><button class="icon-button" data-route="home">${icons.back}</button><span class="brand-mark">VIREAL</span></header><h1 class="screen-title">${signup ? paymentText("验证邮箱，创建账号", "Verify your email to register") : "登录后继续创作"}</h1><p class="screen-copy">${signup ? paymentText("无需邀请，注册不赠币。请先阅读服务条款与隐私说明。", "No invitation required. No signup credits. Please read the terms and privacy notice.") : "登录用于同步金币、额度、任务状态和作品记录。"}</p><div id="clerkSignIn" class="clerk-mount"></div><p id="clerkStatus" class="network-badge">${ready ? paymentText("安全邮箱验证", "Secure email verification") : "正在载入安全登录…"}</p>${state.commerce?.registration_enabled ? `<button class="secondary-button" data-route="${signup ? "login" : "register"}">${signup ? paymentText("已有账号登录", "Sign in") : paymentText("没有账号？免费注册", "New here? Register")}</button>` : ""}<p class="screen-copy"><a href="#terms">${paymentText("服务条款", "Terms")}</a> · <a href="#privacy">${paymentText("隐私说明", "Privacy")}</a></p></section>`)
  }

  function shell(content) { return `<main class="phone-shell">${content}</main>` }

  function render() {
    const current = route()
    const loginRoot = document.getElementById("clerkSignIn")
    const showsLogin = ["login", "register"].includes(current.name) || (!state.appUser && ["generation", "works", "wallet", "account"].includes(current.name))
    if (loginRoot && (state.commerce?.region_allowed === false || loginRoot.dataset.clerkKind !== (current.name === "register" ? "register" : "login"))) {
      window.VirealClerk?.[loginRoot.dataset.clerkKind === "register" ? "unmountSignUp" : "unmountSignIn"]?.(loginRoot)
      loginRoot.remove()
    }
    if (loginRoot?.isConnected && showsLogin) { mountSignIn(); return }
    if (loginRoot?.isConnected) window.VirealClerk?.[loginRoot.dataset.clerkKind === "register" ? "unmountSignUp" : "unmountSignIn"]?.(loginRoot)
    const pages = {
      home: homePage,
      generate: () => generatePage(current.params),
      generation: () => generationPage(current.params),
      works: worksPage,
      wallet: walletPage,
      account: accountPage,
      login: loginPage,
      register: loginPage,
      terms: () => legalPage("terms"),
      privacy: () => legalPage("privacy"),
      refunds: () => legalPage("refunds"),
    }
    app().innerHTML = (pages[current.name] || homePage)()
    document.querySelectorAll("video[autoplay], .effect-card video").forEach((video) => video.play?.().catch(() => {}))
  }

  function mountSignIn() {
    const root = document.getElementById("clerkSignIn")
    const clerk = window.VirealClerk
    if (!root || !clerk || clerk.session || root.dataset.clerkMounted || !state.commerce || state.commerce.region_allowed === false) return
    const signup = route().name === "register"
    if (signup && !state.commerce?.registration_enabled) return
    try {
      const afterLogin = sessionStorage.getItem("vireal-after-login") || "#account"
      state.authView = signup ? "register" : "login"
      clerk[signup ? "mountSignUp" : "mountSignIn"](root, { routing: "hash", signInUrl: `${location.origin}/#login`, signUpUrl: `${location.origin}/#register`, forceRedirectUrl: `${location.origin}/${afterLogin}`, appearance: { variables: { colorPrimary: "#71d8ed", colorBackground: "#151a1d", colorText: "#f7fbfc", colorInputBackground: "#0d1113", colorInputText: "#f7fbfc", borderRadius: "0.9rem" } } })
      root.dataset.clerkKind = signup ? "register" : "login"
      root.dataset.clerkMounted = "true"
      const status = document.getElementById("clerkStatus")
      if (status) status.textContent = paymentText("安全邮箱验证", "Secure email verification")
    } catch (_) {}
  }

  async function uploadImage(index, file) {
    if (!requireAuth(location.hash)) return
    if (state.uploads.some((entry) => entry?.pending)) return
    if (!file?.type.startsWith("image/")) return toast("请选择 JPG、PNG 或 WebP 图片", true)
    const preview = URL.createObjectURL(file)
    state.uploads[index] = { preview, pending: true }
    render()
    const body = new FormData()
    body.append("file", file)
    try {
      const payload = await parseResponse(await authFetch("/api/v1/app/uploads/images", { method: "POST", body }))
      state.uploads[index] = { ...payload, preview }
      toast(`照片 ${index + 1} 上传成功`)
    } catch (error) {
      URL.revokeObjectURL(preview)
      state.uploads[index] = null
      toast(`上传失败：${errorDetail(error)}`, true)
    }
    render()
  }

  function confirmGeneration(effect, variant) {
    const root = document.getElementById("overlayRoot")
    root.innerHTML = `<div class="drawer-root" data-close-drawer><section class="drawer" role="dialog" aria-modal="true"><h2>确认生成</h2><p>价格和模型配置将由服务端再次校验，客户端不能修改实际扣币金额。</p><div class="confirm-detail"><span>${esc(effect.title_zh)} · ${variant.duration_seconds} 秒</span><strong>本次消耗 ${variant.coin_cost} ✦</strong><span>生成后可在“作品”中查看进度。</span></div><div class="drawer-actions"><button class="secondary-button" data-close-drawer>取消</button><button class="primary-button" data-confirm-generation>确认并生成</button></div></section></div>`
  }

  async function createTask() {
    if (state.isSubmitting) return
    const current = route()
    const effect = effectBySlug(current.params.get("video")) || allEffects()[0]
    const variant = selectedVariant(effect)
    if (!effect || !variant) return
    document.getElementById("overlayRoot").innerHTML = ""
    const uploadIds = state.uploads.slice(0, effect.input_image_count).map((item) => item?.id).filter(Boolean)
    const body = JSON.stringify({ effect_id: effect.id, variant_id: variant.id, upload_ids: uploadIds })
    const fingerprint = `${state.appUser?.id}:${body}`
    // A lost response can hide a successful debit. Retry the same intent with
    // the same key; new photos, variant, or user establish a different intent.
    if (state.generationAttempt?.fingerprint !== fingerprint) {
      state.generationAttempt = { fingerprint, key: crypto.randomUUID() }
    }
    const attempt = state.generationAttempt
    state.isSubmitting = true
    render()
    try {
      const response = await authFetch("/api/v1/app/video-tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": attempt.key },
        body,
      })
      const task = await parseResponse(response)
      if (state.generationAttempt === attempt) state.generationAttempt = null
      state.currentTask = task
      state.uploads.forEach((item) => item?.preview && URL.revokeObjectURL(item.preview))
      state.uploads = []
      await Promise.all([loadWallet(false), loadTasks(false)])
      navigate("generation", { id: task.id })
      startPolling(task.id)
    } catch (error) {
      const message = errorDetail(error)
      if (/insufficient coin/i.test(message)) navigate("wallet")
      toast(`提交失败：${message}`, true)
    } finally {
      state.isSubmitting = false
      if (route().name === "generate") render()
    }
  }

  function stopTaskPolling() {
    clearTimeout(state.polling)
    state.pollingVersion++
  }

  function cacheTask(task) {
    state.currentTask = task
    const index = state.tasks.findIndex((item) => item.id === task.id)
    if (index >= 0) state.tasks[index] = task
    else state.tasks.unshift(task)
  }

  function startPolling(taskId) {
    stopTaskPolling()
    const version = state.pollingVersion
    const owner = state.appUser?.id
    state.pollingErrors = 0
    state.pollingError = ""
    const poll = async () => {
      if (!state.appUser || version !== state.pollingVersion) return
      try {
        const task = await parseResponse(await authFetch(`/api/v1/app/video-tasks/${taskId}`))
        if (version !== state.pollingVersion || state.appUser?.id !== owner) return
        cacheTask(task)
        state.pollingErrors = 0
        state.pollingError = ""
        if (terminalStatuses.has(task.status)) await loadWallet(false)
        if (version !== state.pollingVersion || state.appUser?.id !== owner) return
        render()
        if (!terminalStatuses.has(task.status)) state.polling = setTimeout(poll, POLL_MS)
        else schedulePlaybackRefresh(task)
      } catch (error) {
        if (version !== state.pollingVersion || state.appUser?.id !== owner) return
        state.pollingError = errorDetail(error)
        if (state.pollingErrors === 0) toast("状态查询中断，正在重试；后台任务会继续", true)
        state.pollingErrors++
        render()
        state.polling = setTimeout(poll, Math.min(2000 * 2 ** (state.pollingErrors - 1), 30000))
      }
    }
    void poll()
  }

  function schedulePlaybackRefresh(task) {
    clearTimeout(state.playbackTimer)
    if (route().name !== "generation" || route().params.get("id") !== task.id) return
    if (task.status !== "succeeded" || !task.playback_url_expires_at) return
    state.playbackTimer = setTimeout(() => void refreshPlayback(task.id), Math.max(1000, Date.parse(task.playback_url_expires_at) - Date.now() - 5000))
  }

  async function refreshPlayback(taskId) {
    if (!state.appUser || state.playbackRefreshing) return
    state.playbackRefreshing = true
    const owner = state.appUser.id
    try {
      const task = await parseResponse(await authFetch(`/api/v1/app/video-tasks/${taskId}`))
      if (state.appUser?.id !== owner || route().name !== "generation" || route().params.get("id") !== taskId) return
      cacheTask(task)
      const video = document.querySelector(`[data-task-video="${taskId}"]`)
      if (video && task.status === "succeeded" && task.playback_url) {
        const time = video.currentTime
        const playing = !video.paused && !video.ended
        video.addEventListener("loadedmetadata", () => {
          if (Number.isFinite(time) && time > 0 && time < video.duration) video.currentTime = time
          if (playing) void video.play().catch(() => {})
        }, { once: true })
        video.src = mediaUrl(task.playback_url)
        video.load()
      } else render()
      schedulePlaybackRefresh(task)
    } catch (_) {
      toast("播放地址暂时无法更新，请刷新任务状态", true)
    } finally { state.playbackRefreshing = false }
  }

  async function saveTask(taskId, share = false) {
    if (!state.appUser || state.savingTaskId) return
    state.savingTaskId = taskId
    document.querySelectorAll("[data-download-task], [data-share-task]").forEach(button => { button.disabled = true })
    try {
      const response = await authFetch(`/api/v1/app/video-tasks/${taskId}/download`)
      if (!response.ok) {
        if (response.status === 410) startPolling(taskId)
        await parseResponse(response)
      }
      const blob = await response.blob()
      if (!response.headers.get("content-type")?.startsWith("video/mp4") || blob.size < 12) throw new Error("下载响应不是有效视频，请刷新任务状态")
      const file = new File([blob], `vireal-${taskId}.mp4`, { type: "video/mp4" })
      if (share && navigator.canShare?.({ files: [file] })) {
        try { await navigator.share({ files: [file], title: "Vireal video" }); return }
        catch (error) { if (error.name === "AbortError") return }
      }
      const url = URL.createObjectURL(file)
      const link = document.createElement("a")
      link.href = url; link.download = file.name
      document.body.append(link); link.click(); link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 60000)
      toast("下载已开始；可在浏览器下载或文件中查看")
    } catch (error) { toast(errorDetail(error), true) }
    finally { state.savingTaskId = null; document.querySelectorAll("[data-download-task], [data-share-task]").forEach(button => { button.disabled = false }) }
  }

  function resumeTaskView() {
    const current = route()
    if (!state.appUser) return
    if (current.name === "generation" && current.params.get("id")) startPolling(current.params.get("id"))
    else if (current.name === "works") void loadTasks(false).then(render)
    else if (current.name === "wallet") void refreshPayments()
  }

  async function deleteTask(id) {
    try {
      await parseResponse(await authFetch(`/api/v1/app/video-tasks/${id}`, { method: "DELETE" }))
      state.tasks = state.tasks.filter((item) => item.id !== id)
      toast("作品已删除")
      render()
    } catch (error) { toast(errorDetail(error), true) }
  }

  document.addEventListener("click", (event) => {
    const product = event.target.closest("[data-recharge-product]")
    if (product) {
      if (state.checkoutActive) return
      state.rechargeProduct = product.dataset.rechargeProduct
      render()
      return
    }
    if (event.target.closest("[data-refresh-payments]")) { void refreshPayments(); return }
    const routeButton = event.target.closest("[data-route]")
    if (routeButton) {
      const target = routeButton.dataset.route
      if (["works", "wallet", "account"].includes(target) && !state.appUser) requireAuth(`#${target}`)
      else navigate(target)
      return
    }
    const categoryButton = event.target.closest("[data-category]")
    if (categoryButton) { state.categorySlug = categoryButton.dataset.category; render(); return }
    const effectButton = event.target.closest("[data-effect]")
    if (effectButton) {
      const effect = effectBySlug(effectButton.dataset.effect)
      state.uploads.forEach((item) => item?.preview && URL.revokeObjectURL(item.preview))
      state.uploads = []
      navigate("generate", { category: effect.category_slug, video: effect.slug })
      return
    }
    const variantButton = event.target.closest("[data-variant]")
    if (variantButton) {
      const effect = effectBySlug(route().params.get("video")) || allEffects()[0]
      state.selectedVariants[effect.id] = variantButton.dataset.variant
      render()
      return
    }
    const remove = event.target.closest("[data-remove-upload]")
    if (remove) {
      event.preventDefault()
      const index = Number(remove.dataset.removeUpload)
      if (state.uploads[index]?.preview) URL.revokeObjectURL(state.uploads[index].preview)
      state.uploads[index] = null
      render()
      return
    }
    if (event.target.closest("[data-generate]")) {
      if (!requireAuth(location.hash)) return
      const effect = effectBySlug(route().params.get("video")) || allEffects()[0]
      const variant = selectedVariant(effect)
      if (!variant) return
      if (state.uploads.filter((item) => item?.id).length < effect.input_image_count) return toast("请先完成图片上传", true)
      if (!state.wallet || state.wallet.balance < variant.coin_cost) return navigate("wallet")
      confirmGeneration(effect, variant)
      return
    }
    if (event.target.closest("[data-confirm-generation]")) { void createTask(); return }
    if (event.target.closest("[data-close-drawer]")) { document.getElementById("overlayRoot").innerHTML = ""; return }
    const refreshButton = event.target.closest("[data-refresh-task]")
    if (refreshButton) { state.playbackRetryUrl.delete(refreshButton.dataset.refreshTask); startPolling(refreshButton.dataset.refreshTask); return }
    const downloadButton = event.target.closest("[data-download-task]")
    if (downloadButton) { void saveTask(downloadButton.dataset.downloadTask); return }
    const shareButton = event.target.closest("[data-share-task]")
    if (shareButton) { void saveTask(shareButton.dataset.shareTask, true); return }
    const taskButton = event.target.closest("[data-open-task]")
    if (taskButton) {
      const task = state.tasks.find((item) => item.id === taskButton.dataset.openTask)
      state.currentTask = task
      navigate("generation", { id: task.id })
      if (!terminalStatuses.has(task.status)) startPolling(task.id)
      return
    }
    const deleteButton = event.target.closest("[data-delete-task]")
    if (deleteButton) { void deleteTask(deleteButton.dataset.deleteTask); return }
    if (event.target.closest("[data-retry-catalog]")) { state.catalog = null; void loadCatalog(); render(); return }
    const messageButton = event.target.closest("[data-toast]")
    if (messageButton) toast(messageButton.dataset.toast)
    if (event.target.closest("[data-logout]")) {
      void (async () => {
        try { await authFetch("/api/v1/app/auth/logout", { method: "POST" }) } catch (_) {}
        await window.VirealClerk?.signOut()
      state.appUser = null; state.wallet = null; state.tasks = []; state.currentTask = null; state.authSyncedSessionId = ""
        navigate("home")
      })()
    }
  })

  document.addEventListener("change", (event) => {
    const input = event.target.closest("[data-upload-index]")
    if (input) void uploadImage(Number(input.dataset.uploadIndex), input.files?.[0])
  })

  window.addEventListener("hashchange", () => {
    stopTaskPolling()
    clearTimeout(state.playbackTimer)
    const current = route()
    if (["login", "register"].includes(current.name)) state.authView = current.name
    if (current.name !== "wallet") clearTimeout(state.paymentPolling)
    if (current.name === "works") void loadTasks(false).then(render)
    else if (current.name === "wallet") void refreshPayments()
    else if (current.name === "generation" && current.params.get("id")) startPolling(current.params.get("id"))
    render()
  })
  window.addEventListener("online", () => { toast("网络已恢复"); resumeTaskView() })
  document.addEventListener("visibilitychange", () => { if (!document.hidden) resumeTaskView() })
  document.addEventListener("error", (event) => {
    const video = event.target
    if (!video?.dataset?.taskVideo || !state.appUser) return
    if (state.playbackRetryUrl.has(video.dataset.taskVideo)) return
    state.playbackRetryUrl.set(video.dataset.taskVideo, video.src)
    void refreshPlayback(video.dataset.taskVideo)
  }, true)
  window.addEventListener("offline", () => toast("网络连接已断开", true))
  window.addEventListener("vireal:clerk-ready", (event) => {
    observeClerk(event.detail)
  })
  window.addEventListener("vireal:clerk-error", (event) => { state.authReady = true; toast(event.detail?.message || "登录组件加载失败", true); render() })

  render()
  void loadCatalog()
  void loadCommerce()
  if (window.VirealClerk) observeClerk(window.VirealClerk)
})()
