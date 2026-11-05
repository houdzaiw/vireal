import test from 'node:test'
import assert from 'node:assert/strict'
import worker, { check, scheduled } from './monitor.mjs'

const healthy = { database_available: true, monitoring_required: true, new_business_available: true, worker_recent: true, backup_recent: true }
function environment() {
  const values = new Map()
  return { OPS_MONITOR_URL: 'https://api.usevireal.com/api/v1/operations/monitor', OPS_MONITOR_READ_TOKEN: 'synthetic-read-token',
    STATE: { async get(k) { return values.get(k) }, async put(k, v) { values.set(k, v) }, async delete(k) { values.delete(k) } } }
}
const json = value => new Response(JSON.stringify(value), { status: 200 })
for (const [name, field] of [['worker_stale', 'worker_recent'], ['backup_stale', 'backup_recent'], ['business_paused', 'new_business_available']]) {
  test(name, async () => assert.equal(await check(environment(), async () => json({ ...healthy, [field]: false })), name))
}
test('unavailable and malformed responses fail closed', async () => {
  assert.equal(await check(environment(), async () => { throw new Error('synthetic') }), 'api_or_database_unavailable')
  assert.equal(await check(environment(), async () => new Response('', { status: 503 })), 'api_or_database_unavailable')
  assert.equal(await check(environment(), async () => json({})), 'monitor_response_invalid')
})
test('configured read target only, no token forwarding to arbitrary hosts', async () => {
  let calls = 0
  for (const url of ['http://api.usevireal.com/api/v1/operations/monitor', 'https://other.invalid/api/v1/operations/monitor', 'https://api.usevireal.com/api/v1/operations/pause', 'https://api.usevireal.com/api/v1/operations/monitor?token=bad']) {
    await assert.rejects(check({ ...environment(), OPS_MONITOR_URL: url }, async () => { calls++; return json(healthy) }))
  }
  assert.equal(calls, 0)
})
test('no notification unless opted in; healthy and scheduled-off states stay quiet', async () => {
  const env = environment()
  assert.deepEqual(await scheduled(env, async () => json(healthy)), { incident: null, attempted: false })
  assert.deepEqual(await scheduled(env, async () => json({ ...healthy, monitoring_required: false, worker_recent: false })), { incident: null, attempted: false })
  assert.deepEqual(await scheduled(env, async () => new Response('', { status: 500 })), { incident: 'api_or_database_unavailable', attempted: false })
  assert.equal(worker.fetch().status, 404)
})
test('uncertain email attempt is not repeated; no credentials in message', async () => {
  const env = { ...environment(), ALERTS_ENABLED: 'true', RESEND_API_KEY: 'synthetic-send-token', ALERT_FROM: 'ops@example.invalid', ALERT_TO: 'owner@example.invalid' }
  let sends = 0
  const transport = async (url, options) => {
    if (url.includes('api.resend.com')) {
      sends++
      assert.equal(options.redirect, 'error')
      assert.ok(!options.body.includes('synthetic-read-token') && !options.body.includes('synthetic-send-token'))
      throw new Error('synthetic timeout')
    }
    return new Response('', { status: 503 })
  }
  assert.equal((await scheduled(env, transport)).providerAccepted, false)
  assert.equal((await scheduled(env, transport)).attempted, false)
  assert.equal(sends, 1)
})
