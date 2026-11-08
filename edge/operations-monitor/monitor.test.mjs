import test from 'node:test'
import assert from 'node:assert/strict'
import worker, { check, scheduled } from './monitor.mjs'

const healthy = { database_available: true, monitoring_required: true, new_business_available: true, worker_recent: true, backup_recent: true }
function environment() {
  const values = new Map()
  let queue = Promise.resolve()
  const state = { async get(k) { return structuredClone(values.get(k)) }, async put(k, v) { values.set(k, structuredClone(v)) }, async delete(k) { values.delete(k) }, transaction(fn) { const work = queue.then(() => fn(state)); queue = work.catch(() => {}); return work } }
  return { OPS_MONITOR_URL: 'https://api.usevireal.com/api/v1/operations/monitor', OPS_MONITOR_READ_TOKEN: 'synthetic-read-token', QUOTA_VERIFIED_UNTIL: new Date(new Date().setUTCHours(24,0,0,0)).toISOString(), STATE: state }
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

const sender = () => ({ ...environment(), ALERTS_ENABLED: 'true', RESEND_API_KEY: 'synthetic', ALERT_FROM: 'ops@example.invalid', ALERT_TO: 'owner@example.invalid' })
test('20/day and 600/month persist across healthy flapping and UTC rollover', async () => {
  const env = sender()
  let sends = 0
  const down = async url => { if (url.includes('api.resend.com')) { sends++; return json({}) }; return new Response('', { status: 503 }) }
  for (let i = 0; i < 24; i++) {
    env.QUOTA_VERIFIED_UNTIL = '2026-11-09T00:00:00Z'
    await scheduled(env, async () => json(healthy), new Date(`2026-11-08T${String(i).padStart(2, '0')}:00:00Z`))
    await scheduled(env, down, new Date(`2026-11-08T${String(i).padStart(2, '0')}:01:00Z`))
  }
  assert.equal(sends, 20)
  await env.STATE.put('send-quota', { day: '2026-11-08', month: '2026-11', daily: 20, monthly: 600, last: 0 })
  env.QUOTA_VERIFIED_UNTIL = '2026-11-10T00:00:00Z'
  await scheduled(env, down, new Date('2026-11-09T02:00:00Z'))
  assert.equal(sends, 20)
  env.QUOTA_VERIFIED_UNTIL = '2026-12-02T00:00:00Z'
  await scheduled(env, down, new Date('2026-12-01T02:00:00Z'))
  assert.equal(sends, 21)
})
test('parallel dispatch and ten minute flapping cooldown cannot oversend', async () => {
  const env = sender(); let sends = 0
  const down = async url => { if (url.includes('api.resend.com')) { sends++; throw new Error('timeout') }; return new Response('', { status: 503 }) }
  const at = new Date('2026-11-08T02:00:00Z')
  env.QUOTA_VERIFIED_UNTIL = '2026-11-09T00:00:00Z'
  await Promise.all(Array.from({ length: 10 }, () => scheduled(env, down, at)))
  assert.equal(sends, 1)
  await scheduled(env, async () => json(healthy), at)
  await scheduled(env, down, new Date('2026-11-08T02:09:59Z'))
  assert.equal(sends, 1)
  await scheduled(env, down, new Date('2026-11-08T02:10:00Z'))
  assert.equal(sends, 2)
})
test('nontransactional state and failed durable claims never send', async () => {
  const env = sender(); let sends = 0
  const down = async url => { if (url.includes('api.resend.com')) sends++; return new Response('', { status: 503 }) }
  env.STATE.transaction = undefined
  await assert.rejects(scheduled(env, down), /atomic_monitor_state_required/)
  env.STATE.transaction = async () => { throw new Error('storage failed') }
  await assert.rejects(scheduled(env, down), /storage failed/)
  assert.equal(sends, 0)
})

test('expired quota evidence or corrupt counters never send', async () => {
  const env = sender(); let sends = 0
  const down = async url => { if (url.includes('api.resend.com')) sends++; return new Response('', { status: 503 }) }
  env.QUOTA_VERIFIED_UNTIL = '2026-01-01T00:00:00Z'
  assert.equal((await scheduled(env, down)).attempted, false)
  env.QUOTA_VERIFIED_UNTIL = new Date(new Date().setUTCHours(24,0,0,0)).toISOString()
  const day = new Date().toISOString().slice(0,10)
  await env.STATE.put('send-quota', { day, month: day.slice(0,7), daily: 'corrupt', monthly: 0, last: null })
  await assert.rejects(scheduled(env, down), /monitor_quota_state_invalid/)
  assert.equal(sends, 0)
})
