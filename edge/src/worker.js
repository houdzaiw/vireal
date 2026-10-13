// API-only route. Secrets are provisioned separately using wrangler secret put.
export async function signRequest(request, country, secret, timestamp = Math.floor(Date.now() / 1000).toString()) {
  const headers = new Headers(request.headers)
  headers.delete("cf-ipcountry")
  for (const name of [...headers.keys()]) {
    if (name.startsWith("x-vireal-edge-")) headers.delete(name)
  }
  const message = [request.method, new URL(request.url).pathname, timestamp, country].join("\n")
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"])
  const bytes = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message))
  headers.set("x-vireal-edge-time", timestamp)
  headers.set("x-vireal-edge-country", country)
  headers.set("x-vireal-edge-signature", [...new Uint8Array(bytes)].map(byte => byte.toString(16).padStart(2, "0")).join(""))
  return new Request(request, { headers })
}

export default {
  async fetch(request, env) {
    if (!env.APP_EDGE_SIGNING_SECRET || env.APP_EDGE_SIGNING_SECRET.length < 32) return new Response("Edge configuration unavailable", { status: 503 })
    // request.cf is supplied by Cloudflare, unlike a browser-provided header.
    const country = /^[A-Z]{2}$/.test(request.cf?.country || "") ? request.cf.country : "XX"
    const signed = await signRequest(request, country, env.APP_EDGE_SIGNING_SECRET)
    const upstream = await fetch(signed)
    const response = new Response(upstream.body, upstream)
    for (const name of [...response.headers.keys()]) if (name.startsWith("x-vireal-edge-")) response.headers.delete(name)
    return response
  },
}
