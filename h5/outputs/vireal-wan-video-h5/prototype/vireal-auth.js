import { Clerk } from "@clerk/clerk-js"
import { ui } from "@clerk/ui"

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
      (async () => { await clerk.load({ ui }) })(),
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
