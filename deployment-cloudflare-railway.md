# Vireal v1.2: Cloudflare Pages + Railway + Neon

This runbook deploys the v1.2 dynamic effect catalog, real coin wallet, FastAPI task API, and PostgreSQL worker without rewriting them for Cloudflare Workers.

## Resource map

| Component | Provider | Production address |
| --- | --- | --- |
| H5 | Cloudflare Pages | `https://app.usevireal.com` |
| API and Replicate webhook | Railway `vireal-api` | `https://api.usevireal.com` |
| Protected administration | Railway `vireal-api` + Cloudflare Access | `https://admin.usevireal.com` |
| Video persistence and cleanup | Railway `vireal-video-worker` | Private service, no domain |
| Database | Neon PostgreSQL | Private credentials through `DATABASE_URL` |
| Images and videos | Cloudflare R2 | Private S3 endpoint |

The production `main` branch is the single deployment source. Railway builds the
backend from the repository root, while Cloudflare Pages builds the H5 from the
`h5/` directory imported into the same branch.

The production domain is `usevireal.com`.

### v1.2 duration release gate

Keep `APP_EFFECT_MAX_DURATION_SECONDS=10` on both API and worker for the initial
5/10-second release. The API omits longer variants from the public catalog and
effect detail, and rejects new tasks using those variants before charging coins
or contacting the provider. Administrator configuration and historical tasks
remain intact. After separate 15-second acceptance, set the value to `15` and
redeploy; no database migration or recreation of variants is needed.

Set `APP_LEGACY_VIDEO_TASKS_ENABLED=False` for the paid v1.2 release. The legacy
request has no priced catalog variant, so permitting it with real generation
enabled would bypass the coin charge. This gate rejects only new legacy tasks;
historical reads and idempotent retries of accepted tasks remain supported. For
an old-H5 rollback, first disable real generation and enable local demo mode
before reopening legacy submissions; do not downgrade the database.

## Domain registration and hostnames

Keep the registered `usevireal.com` domain on Cloudflare DNS and Registrar.

Use these hostnames:

| Hostname | Purpose |
| --- | --- |
| `app.usevireal.com` | Cloudflare Pages H5 |
| `api.usevireal.com` | Railway API and exact Replicate webhook origin |
| `admin.usevireal.com` | Same Railway API image, protected by Cloudflare Access |
| `www.usevireal.com` | Redirect to the root marketing domain |
| `usevireal.com` | Marketing site or redirect to the H5 |

Do not create a public hostname for the video worker or a public R2 custom domain.
Use the provider-generated `*.pages.dev` and `*.up.railway.app` addresses only for
initial smoke tests, then perform the Replicate PoC through the custom HTTPS names.

## 0. Source-control gate

Railway deploys committed GitHub code, so the selected `main` branch must contain the Replicate task API, webhook, worker, migration, and the deployment files in this runbook.

Before connecting Railway:

```bash
git fetch origin main
git status --short
git rev-list --left-right --count HEAD...origin/main
cd backend
uv run alembic heads
```

Do not deploy until the working tree changes have been reviewed and committed, local `main` is synchronized with `origin/main`, and `alembic heads` prints exactly one head. If another branch added migrations from the same parent, create a new merge-safe migration revision instead of reusing or overwriting a revision ID.

## 1. Neon PostgreSQL

1. Create a Neon project in a North American region, preferably US East, using PostgreSQL 18 when available.
2. Create a production database and a dedicated application role.
3. Copy the direct SSL connection string. Keep `sslmode=require` in the URL.
4. Do not expose the connection string in H5, Cloudflare Pages variables, source control, or build logs.

The initial release uses the direct Neon URL because the API and worker have low, fixed connection counts. Add pooling only when service replicas increase.

## 2. Railway services

Create an empty Railway project in a North American region, then create two services from the GitHub repository and select branch `main`.

Configure both services with:

```text
Root directory: /
Dockerfile path: backend/Dockerfile
```

Copy the variables from `deploy/railway-variables.example` into both services, replace every placeholder, and use the same values for both. Keep `FASTAPI_ENV` unset. Set `DATABASE_URL` to the Neon direct SSL URL.

### vireal-api

```text
Start command: fastapi run --host 0.0.0.0 --port 8000 --workers 2
Pre-deploy command: bash scripts/prestart.sh
Pre-deploy timeout: 300 seconds
Healthcheck path: /api/v1/utils/health-check/
Healthcheck timeout: 300 seconds
Restart policy: ALWAYS
Public target port: 8000
```

Bind both `api.usevireal.com` and `admin.usevireal.com` to this service. Run
migrations here only; do not configure a pre-deploy command on the worker. The
admin frontend uses relative `/api` requests, so Cloudflare Access protects both
the page and its same-origin API calls and FastAPI can verify the forwarded Access
JWT. FastAPI requires that assertion on the admin login, users, items, and Vireal
admin routes. Add a Cloudflare rule that blocks non-`/api/` paths on
`api.usevireal.com`.

### vireal-video-worker

```text
Start command: python -m app.workers.video_tasks
Restart policy: ALWAYS
Public networking: disabled
```

The worker needs outbound HTTPS access to Replicate and R2 and the same `DATABASE_URL`, R2, and Replicate secrets as the API.

## 3. Cloudflare Pages

Connect the GitHub repository to Cloudflare Pages and configure:

```text
Production branch: main
Root directory: /h5
Build command: bash scripts/build-vireal-pages.sh
Build output directory: dist/vireal-pages
VIREAL_API_BASE_URL: https://api.usevireal.com
VITE_CLERK_PUBLISHABLE_KEY: pk_live_replace-with-clerk-publishable-key
```

Bind `app.usevireal.com` as the Pages custom domain. The generated page uses the injected API origin and enables real backend mode without query parameters.

Before the H5 release, finish the Clerk production instance:

1. Enable restricted sign-ups in invite-only mode.
2. Enable email one-time-code, Google, and Apple sign-in.
3. Add `https://app.usevireal.com` to the allowed origins and callback URLs.
4. Customize the normal Clerk session token claims with
   `{"aud":"vireal-api"}`. The backend rejects tokens without this audience.
5. Put the live publishable key in Pages only. Put the secret key in Railway only.

## 4. API domain and Cloudflare DNS

1. In Railway, add both `api.usevireal.com` and `admin.usevireal.com` to `vireal-api` and select target port 8000.
2. Add both the CNAME and TXT verification records shown by Railway to Cloudflare DNS.
3. Use the Cloudflare proxy on the first-level `api` subdomain and set SSL/TLS mode to `Full`, as required by Railway's proxied-domain setup.
4. Do not create a Cloudflare redirect rule for `/api/v1/webhooks/replicate`.
5. Confirm that a POST to the exact HTTPS webhook path returns an authentication error without any redirect.

Set these final origins in both Railway services:

```env
FRONTEND_HOST=https://app.usevireal.com
BACKEND_CORS_ORIGINS=["https://app.usevireal.com","https://admin.usevireal.com"]
REPLICATE_WEBHOOK_URL=https://api.usevireal.com/api/v1/webhooks/replicate
APP_AUTH_MODE=clerk
CLERK_AUTHORIZED_PARTIES=["https://app.usevireal.com"]
CLOUDFLARE_ACCESS_REQUIRED=true
PUBLIC_API_DOCS_ENABLED=false
```

Do not add arbitrary `*.pages.dev` preview origins to CORS. Use the custom H5 domain for real API verification.

## 5. Preproduction acceptance

Use a separate preproduction database, R2 prefix, Clerk instance, and domains. The
runtime configuration must use `REPLICATE_ENABLED=True` and
`LOCAL_DEMO_ENABLED=False`; v1.2 does not substitute a simulated result when a
real-generation quota or provider is unavailable.

1. Take a restorable database snapshot and record its identifier and timestamp.
2. Deploy the API migration, then confirm `alembic current` reports
   `f2a3b4c5d6e7` and the catalog contains 6 categories and 18 effects.
3. Deploy the API and worker, then the protected administration UI. Grant test
   coins to an invited test account through the coin adjustment page and confirm
   the corresponding operation log and immutable wallet entry.
4. Deploy the v1.2 H5 build to the preproduction Pages project. Confirm the
   bottom navigation contains only Discover, Works, and Account; prices, balance,
   duration, daily quota, and concurrency are server values.
5. Run one paid generation through each whitelisted model: MiniMax Video-01, Wan
   2.7 R2V, and Seedance 2.0. Include at least one two-image kiss or romance task.
6. For every task, verify the signed webhook, worker transfer into private R2,
   short-lived playback URL, wallet debit, task history, and absence of prompts,
   model identifiers, object keys, tokens, or image URLs in application logs.
7. Force one definitive provider failure and confirm exactly one refund. Force one
   ambiguous submission timeout and confirm the task remains
   `submission_unknown` without automatic refund or resubmission.
8. Verify the configured daily and per-user concurrency limits return a real
   quota error and do not create another paid prediction.

Never automatically resubmit, refund, or locally downgrade a task in
`submission_unknown`. Inspect the task, Replicate dashboard, and billing before
resolving it.

## 6. Full production cutover

The production release is an all-traffic switch, not a percentage rollout.

1. Preserve the current v1.1 Pages deployment and verify that the new build also
   contains `fallback/v1.1/index.html`.
2. Take and verify a fresh production database backup.
3. Apply the single incremental migration and confirm revision
   `f2a3b4c5d6e7`; do not run a downgrade during an incident.
4. Deploy the backward-compatible API and worker. The old v1.1
   `template_id/mode/duration` request remains accepted during this step.
5. Verify the 6 seeded categories and 18 effects, then grant production users any
   required launch balance through the administration UI. New and existing users
   otherwise start at zero coins.
6. Deploy and smoke-test the protected administration UI, including category,
   effect, variant, media, recommendation, coin, and audit workflows.
7. Publish the v1.2 Pages build to `app.usevireal.com`, replacing all H5 traffic.
8. Run the production edge checks:

   ```bash
   H5_URL=https://app.usevireal.com \
   API_URL=https://api.usevireal.com \
   R2_PRIVATE_OBJECT_URL=https://example-private-object \
   bash scripts/verify-production.sh
   ```

9. Complete one low-cost production generation and verify balance, task state,
   R2 playback, worker health, and sanitized logs.

If the H5 must be rolled back, republish the preserved v1.1 artifact only. Keep
the v1.2 database structures, migration revision, seed data, and compatible APIs
in place.

## 7. Post-release checks

- Confirm no R2 object can be opened without a signed URL.
- Keep the application worker running for precise expiration and configure an R2 lifecycle rule for prefix `vireal/` as a backup cleanup mechanism.
- Review Railway API/worker logs, Neon connection count, Replicate billing, coin
  ledger reconciliation, failure refunds, and R2 objects.
- Rotate any Replicate or R2 credential that has previously appeared in plaintext before production traffic.
