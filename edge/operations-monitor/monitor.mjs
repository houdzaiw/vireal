// Offline-review source only: no account, DNS, KV namespace, key or cron is created.
// A separately provisioned read-only monitor token cannot pause, pay or generate.
const API_HOSTS = new Set(['api.usevireal.com', 'staging-api.usevireal.com'])

export async function check(env, transport = fetch) {
  const url = new URL(env.OPS_MONITOR_URL)
  if (url.protocol !== 'https:' || !API_HOSTS.has(url.hostname)
    || url.pathname !== '/api/v1/operations/monitor' || url.search || url.hash
    || url.username || url.password || url.port || !env.OPS_MONITOR_READ_TOKEN) {
    throw new Error('monitor_configuration_invalid')
  }
  try {
    const response = await transport(url.href, {
      headers: { Authorization: `Bearer ${env.OPS_MONITOR_READ_TOKEN}` },
      redirect: 'error', signal: AbortSignal.timeout(10000),
    })
    if (response.status !== 200) return 'api_or_database_unavailable'
    const status = await response.json()
    for (const name of ['database_available', 'monitoring_required', 'new_business_available', 'worker_recent', 'backup_recent']) {
      if (typeof status[name] !== 'boolean') return 'monitor_response_invalid'
    }
    if (!status.database_available) return 'api_or_database_unavailable'
    if (status.monitoring_required && !status.worker_recent) return 'worker_stale'
    if (status.monitoring_required && !status.backup_recent) return 'backup_stale'
    if (status.monitoring_required && !status.new_business_available) return 'business_paused'
    return null
  } catch {
    return 'api_or_database_unavailable' // No body, URL, headers or credentials in errors.
  }
}

export async function scheduled(env, transport = fetch, now = new Date()) {
  const incident = await check(env, transport)
  if (!env.STATE) throw new Error('monitor_state_missing')
  if (!incident) {
    await env.STATE.delete('active-incident')
    return { incident: null, attempted: false }
  }
  if (env.ALERTS_ENABLED !== 'true') return { incident, attempted: false }
  if (!env.RESEND_API_KEY || !env.ALERT_FROM || !env.ALERT_TO) throw new Error('sender_not_configured')
  const quotaUntil = Date.parse(env.QUOTA_VERIFIED_UNTIL)
  const tomorrow = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1)
  if (!Number.isFinite(quotaUntil) || !(now.getTime() < quotaUntil && quotaUntil <= tomorrow)) return { incident, attempted: false }
  // KV alone cannot atomically reserve a quota across concurrent dispatches.
  // A single Durable Object owns this storage; never fall back to weak state.
  if (typeof env.STATE.transaction !== 'function') throw new Error('atomic_monitor_state_required')
  const claimed = await env.STATE.transaction(async state => {
    const previous = await state.get('active-incident')
    if (previous === incident) return false
    const timestamp = now.getTime()
    const day = now.toISOString().slice(0, 10)
    const month = day.slice(0, 7)
    const quota = await state.get('send-quota') || { day, month, daily: 0, monthly: 0, last: null }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(quota.day) || !/^\d{4}-\d{2}$/.test(quota.month)
      || !Number.isInteger(quota.daily) || quota.daily < 0 || quota.daily > 20
      || !Number.isInteger(quota.monthly) || quota.monthly < 0 || quota.monthly > 600
      || (quota.last !== null && (!Number.isSafeInteger(quota.last) || quota.last < 0))
      || quota.day > day || quota.month > month) throw new Error('monitor_quota_state_invalid')
    if (quota.day !== day) { quota.day = day; quota.daily = 0 }
    if (quota.month !== month) { quota.month = month; quota.monthly = 0 }
    if (quota.daily >= 20 || quota.monthly >= 600
      || (quota.last !== null && timestamp - quota.last < 600000)) return false
    quota.daily++; quota.monthly++; quota.last = timestamp
    await state.put('send-quota', quota)
    await state.put('active-incident', incident)
    return true
  })
  if (!claimed) return { incident, attempted: false }
  // Persist the claim first: unknown transport outcomes never auto-resend.
  try {
    const response = await transport('https://api.resend.com/emails', {
      method: 'POST', redirect: 'error', signal: AbortSignal.timeout(10000),
      headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ from: env.ALERT_FROM, to: [env.ALERT_TO], subject: 'Vireal independent operations alert',
        text: `Operational event: ${incident}. Review and acknowledge in the private operations console.` }),
    })
    return { incident, attempted: true, providerAccepted: [200, 201, 202].includes(response.status) }
  } catch {
    return { incident, attempted: true, providerAccepted: false }
  }
}

export default {
  fetch() { return new Response(null, { status: 404 }) },
  scheduled(_event, env, context) {
    if (env.ALERTS_ENABLED !== 'true') return
    if (!env.MONITOR_COORDINATOR) throw new Error('atomic_monitor_state_required')
    const id = env.MONITOR_COORDINATOR.idFromName('vireal-operations-alerts-v1')
    context.waitUntil(env.MONITOR_COORDINATOR.get(id).fetch('https://monitor.internal/check', { method: 'POST' }))
  },
}

// Not deployed by this package. New binding/migration and cost review are explicit
// future release scope, separate from Railway's four PostgreSQL tables.
export class MonitorCoordinator {
  constructor(state, env) { this.state = state; this.env = env; this.queue = Promise.resolve() }
  async fetch(request) {
    if (request.method !== 'POST' || new URL(request.url).pathname !== '/check') return new Response(null, { status: 404 })
    const work = this.queue.then(() => scheduled({ ...this.env, STATE: this.state.storage }))
    this.queue = work.catch(() => {})
    return Response.json(await work)
  }
}
