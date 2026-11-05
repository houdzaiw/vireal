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

export async function scheduled(env, transport = fetch) {
  const incident = await check(env, transport)
  if (!env.STATE) throw new Error('monitor_state_missing')
  if (!incident) {
    await env.STATE.delete('active-incident')
    return { incident: null, attempted: false }
  }
  if (env.ALERTS_ENABLED !== 'true') return { incident, attempted: false }
  if (!env.RESEND_API_KEY || !env.ALERT_FROM || !env.ALERT_TO) throw new Error('sender_not_configured')
  const previous = await env.STATE.get('active-incident')
  if (previous === incident) return { incident, attempted: false }
  // Persist the claim first: unknown transport outcomes never auto-resend.
  // The future cron must be single-dispatch (no overlapping monitor producers).
  await env.STATE.put('active-incident', incident)
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
  scheduled(_event, env, context) { context.waitUntil(scheduled(env)) },
}
