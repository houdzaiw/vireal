import { Clerk } from "@clerk/clerk-js"
import { ui } from "@clerk/ui"

function navigateAuth(to, metadata, replace = false) {
  let current, target
  try {
    current = new URL(window.location.href)
    target = new URL(to, current)
  } catch (_) {
    throw new Error("AUTH_NAVIGATION_UNAVAILABLE")
  }
  if (target.origin !== current.origin || target.pathname !== current.pathname
    || target.search !== current.search) {
    // Keep document changes and SDK-managed auth parameters on Clerk's own
    // navigation path. This callback only owns this document's fragment router.
    if (typeof metadata?.windowNavigate !== "function") throw new Error("AUTH_NAVIGATION_UNAVAILABLE")
    return metadata.windowNavigate(target)
  }
  if (target.hash === current.hash) return
  if (replace) {
    window.history.replaceState(null, "", target.href)
    window.dispatchEvent(new HashChangeEvent("hashchange", { oldURL: current.href, newURL: target.href }))
  } else {
    window.location.hash = target.hash
  }
}

async function initializeClerk() {
  const meta = document.querySelector('meta[name="clerk-publishable-key"]')
  const publishableKey = meta?.content.trim() || ""
  if (!publishableKey || publishableKey.startsWith("__VIREAL_")) {
    throw new Error("AUTH_NOT_CONFIGURED")
  }

  const clerk = new Clerk(publishableKey)
  let timer
  try {
    // A timed-out attempt must not publish a late ready event. This does not
    // cancel the vendor's internal request or automatically retry any action.
    await Promise.race([
      (async () => {
        await clerk.load({
          ui,
          // A same-document return must finish setActive and notify listeners,
          // rather than use Clerk's full-document unloading path for a hash.
          routerPush: (to, metadata) => navigateAuth(to, metadata),
          routerReplace: (to, metadata) => navigateAuth(to, metadata, true),
        })
      })(),
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error("AUTH_LOAD_TIMEOUT")), 15000)
      }),
    ])
  } finally {
    clearTimeout(timer)
  }
  window.VirealClerk = clerk
  window.dispatchEvent(new CustomEvent("vireal:clerk-ready", { detail: clerk }))
}

initializeClerk().catch((error) => {
  // Never expose a raw SDK/network exception, URL, token or configuration.
  const code = ["AUTH_NOT_CONFIGURED", "AUTH_LOAD_TIMEOUT"].includes(error?.message)
    ? error.message : "AUTH_LOAD_FAILED"
  window.dispatchEvent(
    new CustomEvent("vireal:clerk-error", { detail: { code } }),
  )
})
