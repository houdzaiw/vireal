import { Clerk } from "@clerk/clerk-js"

async function initializeClerk() {
  const meta = document.querySelector('meta[name="clerk-publishable-key"]')
  const publishableKey = meta?.content.trim() || ""
  if (!publishableKey || publishableKey.startsWith("__VIREAL_")) {
    throw new Error("Clerk publishable key is not configured")
  }

  const clerk = new Clerk(publishableKey)
  await clerk.load()
  window.VirealClerk = clerk
  window.dispatchEvent(new CustomEvent("vireal:clerk-ready", { detail: clerk }))
}

initializeClerk().catch((error) => {
  const message = error instanceof Error ? error.message : String(error)
  window.dispatchEvent(
    new CustomEvent("vireal:clerk-error", { detail: { message } }),
  )
})
