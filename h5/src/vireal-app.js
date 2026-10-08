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
  const statusText = (status) => ({ submitting: "正在提交", pending: "排队中", running: "生成中", rendering_demo: "生成中", saving: "保存中", succeeded: "已完成", failed: "失败已退款", canceled: "已取消", submission_unknown: "服务商确认中", expired: "已删除" })[status] || status

  function route() {
    const raw = location.hash.slice(1) || "home"
    // Clerk's supported hash router owns slash-prefixed paths such as
    // #/factor-one. They must stay inside the mounted login component.
    if (raw.startsWith("/")) return { name: "login", params: new URLSearchParams() }
    const [name, query = ""] = raw.split("?")
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
    if ([401, 403].includes(response.status)) state.appUser = null
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

  async function syncSession() {
    const clerk = window.VirealClerk
    if (!clerk?.session || !clerk.user) {
      // Clerk also notifies while the signed-out form is being edited. Only
      // redraw on an auth transition; remounting would reset email/OTP state.
      const authChanged = !state.authReady || Boolean(state.appUser || state.wallet || state.authSyncedSessionId)
      state.appUser = null
      state.wallet = null
      state.authSyncedSessionId = ""
      state.authReady = true
      if (authChanged) render()
      return
    }
    if (state.authSyncedSessionId === clerk.session.id && state.appUser) return
    try {
      const response = await authFetch("/api/v1/app/auth/session", { method: "POST", headers: { "Content-Type": "application/json" } })
      const payload = await parseResponse(response)
      state.appUser = payload.app_user
      state.authSyncedSessionId = clerk.session.id
      state.authReady = true
      await Promise.all([loadWallet(false), loadTasks(false)])
      const afterLogin = sessionStorage.getItem("vireal-after-login")
      if (afterLogin) {
        sessionStorage.removeItem("vireal-after-login")
        location.hash = afterLogin
      } else render()
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
    const uploadTiles = Array.from({ length: effect.input_image_count }, (_, index) => {
      const entry = state.uploads[index]
      return `<label class="upload-tile" aria-pressed="${Boolean(entry)}"><input type="file" accept="image/jpeg,image/png,image/webp" data-upload-index="${index}">${entry ? `<img src="${esc(entry.preview)}" alt="已上传照片 ${index + 1}"><button class="remove-upload" type="button" data-remove-upload="${index}">×</button>` : `<span class="upload-center"><span class="plus-ring">${icons.plus}</span><span class="upload-title">上传照片 ${index + 1}</span><span class="upload-hint">JPG / PNG / WebP</span></span>`}</label>`
    }).join("")
    const variants = effect.variants.map((item) => `<button class="duration-button" data-variant="${item.id}" aria-pressed="${item.id === variant?.id}"><b>${item.duration_seconds} 秒</b><small>${item.coin_cost} ✦</small></button>`).join("")
    const recommendations = (effect.recommendations || []).map((slug) => effectBySlug(slug)).filter(Boolean).slice(0, 4).map((item, index) => `<button class="recommend-card" data-effect="${esc(item.slug)}">${surface(item, categoryFor(item), index)}<strong>${esc(item.title_zh)}</strong></button>`).join("")
    let buttonText = "登录后生成"
    let disabled = false
    if (state.appUser) {
      buttonText = uploaded < effect.input_image_count ? `还需上传 ${effect.input_image_count - uploaded} 张照片` : !enough ? "金币余额不足" : "确认并生成"
      disabled = uploaded < effect.input_image_count
    }
    if (state.isSubmitting) { buttonText = "正在提交"; disabled = true }
    return shell(`<section class="page page-enter"><div class="detail-hero">${surface(effect, category)}<div class="detail-shade"></div><div class="detail-bar"><button class="icon-button" data-route="home">${icons.back}</button><button class="energy-pill" data-route="wallet">✦ ${state.wallet ? state.wallet.balance : "--"}</button></div><div class="hero-copy"><div class="eyeline">${esc(effect.title_en)}</div><h1>${esc(effect.title_zh)}</h1><p>${esc(effect.description || "上传照片，由 AI 生成自然流畅的动态时刻。")}</p></div></div><div class="generator-panel"><div class="panel-head"><div><h2>上传${effect.input_image_count}张照片</h2><p>图片仅用于本次生成，并按当前素材保留策略处理。</p></div><span class="data-badge">服务端配置</span></div><div class="upload-grid${effect.input_image_count === 2 ? " two" : ""}">${uploadTiles}</div><div class="duration-wrap"><div class="field-label">选择时长 <span>实际金币价格</span></div><div class="duration-group">${variants}</div></div><div class="balance-line"><div><span>本次消耗</span><b>${variant?.coin_cost ?? "--"} ✦</b></div><div><span>剩余余额</span><b class="${state.appUser && !enough ? "insufficient" : ""}">${state.wallet ? state.wallet.balance : "登录后查看"} ${state.wallet ? "✦" : ""}</b></div><div><span>今日 / 并发可用</span><b>${state.wallet ? `${state.wallet.daily_remaining} / ${state.wallet.concurrent_remaining}` : "-- / --"}</b></div></div><button class="generate-button" data-generate ${disabled ? "disabled" : ""}>${buttonText}<small>${variant ? `${variant.duration_seconds}s` : ""}</small></button></div>${recommendations ? `<div class="subsection"><div class="subsection-head"><h2>${esc(effect.recommendation_label || "推荐效果")}</h2><span>继续探索</span></div><div class="recommend-grid">${recommendations}</div></div>` : ""}<div style="padding:0 16px 28px">${nav("")}</div></section>`)
  }

  function taskVisual(task) {
    if (task?.status === "succeeded" && task.playback_url) return `<video class="task-video" controls playsinline preload="metadata" src="${esc(task.playback_url)}"></video>`
    const failed = task && ["failed", "canceled", "expired"].includes(task.status)
    return `<div class="status-visual"><div class="status-center">${failed ? `<div><span style="color:var(--danger);font-size:42px">!</span><h2>${statusText(task.status)}</h2><p>${esc(task.error || "本次任务没有完成；若产生扣币，系统已自动退款。")}</p></div>` : `<div><div class="status-spinner"></div><h2>${statusText(task?.status || "pending")}</h2><p>${task?.status === "submission_unknown" ? "正在核对服务商状态，确认前不会自动退款，避免重复补偿。" : "生成将在后台继续，可以先去浏览其他效果。"}</p><div class="progress-track"><i></i></div></div>`}</div></div>`
  }

  function generationPage(params) {
    const task = state.currentTask?.id === params.get("id") ? state.currentTask : state.tasks.find((item) => item.id === params.get("id"))
    if (!state.appUser) return loginPage()
    return shell(`<section class="page screen-page page-enter">${header()}<h1 class="screen-title">${task?.effect_title || "生成任务"}</h1><p class="screen-copy">任务状态、实际消耗与剩余余额均来自服务端。</p><div class="status-panel">${taskVisual(task)}<div class="status-actions"><button class="secondary-button" data-route="works">查看作品</button><button class="primary-button" data-route="home">继续浏览</button></div></div>${task ? `<div class="catalog-footer"><div><strong>${task.duration} 秒 · ${task.coin_cost ?? 0} ✦</strong><span>${esc(task.execution_type)} · ${esc(task.resolution)} · ${esc(task.aspect_ratio)}</span></div><span class="status-chip ${terminalStatuses.has(task.status) && task.status !== "succeeded" ? "failed" : "pending"}">${statusText(task.status)}</span></div>` : '<div class="catalog-error">正在读取任务状态…</div>'}${nav("works")}</section>`)
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
    return shell(`<section class="page screen-page page-enter">${header()}<h1 class="screen-title">金币与额度</h1><p class="screen-copy">本期不开放 H5 充值；金币由管理员发放，所有变动都有不可变流水。</p><div class="wallet-card"><small>AVAILABLE BALANCE</small><strong>${wallet?.balance ?? "--"} ✦</strong><p>今日剩余 ${wallet?.daily_remaining ?? "--"} 次 · 当前可并发 ${wallet?.concurrent_remaining ?? "--"} 个任务</p></div><div class="subsection-head" style="margin-top:24px"><h2>余额流水</h2><span>最近 50 条</span></div><div class="profile-card">${ledger || '<p class="screen-copy" style="margin:0">暂无金币流水</p>'}</div>${nav("")}</section>`)
  }

  function accountPage() {
    if (!state.appUser) return loginPage()
    return shell(`<section class="page screen-page page-enter">${header()}<h1 class="screen-title">账户与偏好</h1><div class="profile-card"><div class="profile-row"><div class="profile-avatar">${esc((state.appUser.nickname || "VI").slice(0, 2).toUpperCase())}</div><div><strong>${esc(state.appUser.nickname || "Vireal User")}</strong><span style="display:block;margin-top:5px;color:#84979e;font-size:10px">${esc(state.appUser.id)}</span></div></div><div class="settings-list"><button data-route="wallet"><span><b>金币与额度</b><small>查看真实余额和流水</small></span>${icons.arrow}</button><button data-route="works"><span><b>作品记录</b><small>查看生成状态与结果</small></span>${icons.arrow}</button><button data-toast="素材和生成结果按当前服务端保留策略处理"><span><b>隐私与数据</b><small>私有素材与短期签名访问</small></span>${icons.arrow}</button></div></div><button class="danger-button" style="width:100%;margin-top:14px" data-logout>退出登录</button>${nav("account")}</section>`)
  }

  function loginPage() {
    const ready = Boolean(window.VirealClerk)
    setTimeout(mountSignIn, 0)
    return shell(`<section class="page screen-page page-enter"><header><button class="icon-button" data-route="home">${icons.back}</button><span class="brand-mark">VIREAL</span></header><h1 class="screen-title">登录后继续创作</h1><p class="screen-copy">登录用于同步金币、额度、任务状态和作品记录。</p><div id="clerkSignIn" class="clerk-mount"></div><p id="clerkStatus" class="network-badge">${ready ? "仅限受邀请用户登录" : "正在载入安全登录…"}</p></section>`)
  }

  function shell(content) { return `<main class="phone-shell">${content}</main>` }

  function render() {
    const current = route()
    const loginRoot = document.getElementById("clerkSignIn")
    const showsLogin = current.name === "login" || (!state.appUser && ["works", "wallet", "account"].includes(current.name))
    if (loginRoot && showsLogin) { mountSignIn(); return }
    if (loginRoot) window.VirealClerk?.unmountSignIn?.(loginRoot)
    const pages = {
      home: homePage,
      generate: () => generatePage(current.params),
      generation: () => generationPage(current.params),
      works: worksPage,
      wallet: walletPage,
      account: accountPage,
      login: loginPage,
    }
    app().innerHTML = (pages[current.name] || homePage)()
    document.querySelectorAll("video[autoplay], .effect-card video").forEach((video) => video.play?.().catch(() => {}))
  }

  function mountSignIn() {
    const root = document.getElementById("clerkSignIn")
    const clerk = window.VirealClerk
    if (!root || !clerk || clerk.session || root.dataset.clerkMounted) return
    try {
      const afterLogin = sessionStorage.getItem("vireal-after-login") || "#account"
      clerk.mountSignIn(root, { routing: "hash", forceRedirectUrl: `${location.origin}/${afterLogin}`, appearance: { variables: { colorPrimary: "#71d8ed", colorBackground: "#151a1d", colorText: "#f7fbfc", colorInputBackground: "#0d1113", colorInputText: "#f7fbfc", borderRadius: "0.9rem" } } })
      root.dataset.clerkMounted = "true"
      const status = document.getElementById("clerkStatus")
      if (status) status.textContent = "仅限受邀请用户登录"
    } catch (_) {}
  }

  async function uploadImage(index, file) {
    if (!requireAuth(location.hash)) return
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

  function startPolling(taskId) {
    clearTimeout(state.polling)
    const poll = async () => {
      if (!state.appUser) return
      try {
        const task = await parseResponse(await authFetch(`/api/v1/app/video-tasks/${taskId}`))
        state.currentTask = task
        const index = state.tasks.findIndex((item) => item.id === task.id)
        if (index >= 0) state.tasks[index] = task
        else state.tasks.unshift(task)
        if (terminalStatuses.has(task.status)) await loadWallet(false)
        render()
        if (!terminalStatuses.has(task.status)) state.polling = setTimeout(poll, POLL_MS)
      } catch (error) { toast(errorDetail(error), true) }
    }
    void poll()
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
        state.appUser = null; state.wallet = null; state.tasks = []; state.authSyncedSessionId = ""
        navigate("home")
      })()
    }
  })

  document.addEventListener("change", (event) => {
    const input = event.target.closest("[data-upload-index]")
    if (input) void uploadImage(Number(input.dataset.uploadIndex), input.files?.[0])
  })

  window.addEventListener("hashchange", () => {
    clearTimeout(state.polling)
    const current = route()
    if (current.name === "works") void loadTasks(false).then(render)
    else if (current.name === "wallet") void loadWallet(false).then(render)
    else if (current.name === "generation" && current.params.get("id")) startPolling(current.params.get("id"))
    render()
  })
  window.addEventListener("online", () => toast("网络已恢复"))
  window.addEventListener("offline", () => toast("网络连接已断开", true))
  window.addEventListener("vireal:clerk-ready", (event) => {
    observeClerk(event.detail)
  })
  window.addEventListener("vireal:clerk-error", (event) => { state.authReady = true; toast(event.detail?.message || "登录组件加载失败", true); render() })

  render()
  void loadCatalog()
  if (window.VirealClerk) observeClerk(window.VirealClerk)
})()
