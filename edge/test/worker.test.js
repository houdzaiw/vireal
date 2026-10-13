import assert from "node:assert/strict"
import { test } from "node:test"
import { createHmac } from "node:crypto"
import worker, { signRequest } from "../src/worker.js"

test("edge context strips forged headers and agrees with backend signing format", async () => {
  const secret = "local-edge-test-secret-at-least-32-characters"
  const request = new Request("https://api.usevireal.com/api/v1/app/paypal/config", {
    headers: { "cf-ipcountry": "US", "x-vireal-edge-country": "CN", "x-vireal-edge-signature": "forged", "x-vireal-edge-private": "untrusted" },
  })
  const signed = await signRequest(request, "US", secret, "1791456000")
  assert.equal(signed.headers.get("x-vireal-edge-country"), "US")
  assert.equal(signed.headers.get("x-vireal-edge-private"), null)
  assert.equal(signed.headers.get("cf-ipcountry"), null)
  assert.equal(signed.headers.get("x-vireal-edge-signature"), createHmac("sha256", secret).update("GET\n/api/v1/app/paypal/config\n1791456000\nUS").digest("hex"))
})

test("worker preserves origin status/body and fails closed on missing country", async () => {
  const originalFetch = globalThis.fetch
  let received
  globalThis.fetch = async request => {
    received = request
    return new Response('{"region_allowed":false}', { status: 403, headers: { "content-type": "application/json", "x-vireal-edge-private": "do-not-expose" } })
  }
  try {
    const response = await worker.fetch(new Request("https://api.usevireal.com/api/v1/app/paypal/config"), { APP_EDGE_SIGNING_SECRET: "local-edge-test-secret-at-least-32-characters" })
    assert.equal(received.headers.get("x-vireal-edge-country"), "XX")
    assert.equal(response.status, 403)
    assert.equal(response.headers.get("content-type"), "application/json")
    assert.equal(response.headers.get("x-vireal-edge-private"), null)
    assert.deepEqual(await response.json(), { region_allowed: false })
  } finally { globalThis.fetch = originalFetch }
})

test("missing deployment secret returns 503 without forwarding", async () => {
  const response = await worker.fetch(new Request("https://api.usevireal.com/api/v1/app/paypal/config"), {})
  assert.equal(response.status, 503)
})
