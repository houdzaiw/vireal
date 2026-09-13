# Vireal: Cloudflare Pages + Railway + Neon

This runbook deploys the current FastAPI and PostgreSQL worker implementation without rewriting it for Cloudflare Workers.

## Resource map

| Component | Provider | Production address |
| --- | --- | --- |
| H5 | Cloudflare Pages | `https://app.example.com` |
| API and Replicate webhook | Railway `vireal-api` | `https://api.example.com` |
| Video persistence and cleanup | Railway `vireal-video-worker` | Private service, no domain |
| Database | Neon PostgreSQL | Private credentials through `DATABASE_URL` |
| Images and videos | Cloudflare R2 | Private S3 endpoint |

The workspace currently contains two Git checkouts of the same GitHub repository. Cloudflare Pages uses the outer repository's `master` branch, which contains `outputs/vireal-wan-video-h5`. Railway uses the nested `server` repository's `main` branch, which contains the backend.

Replace `example.com` in every step with the real production domain before enabling Replicate.

## Domain registration and hostnames

Register the production domain with Cloudflare Registrar when the desired name and
top-level domain are supported, and keep Cloudflare DNS authoritative. Check live
availability before purchase; suggested candidates, in order, are `vireal.app`,
`vireal.video`, and `getvireal.com`.

Use these hostnames:

| Hostname | Purpose |
| --- | --- |
| `app.example.com` | Cloudflare Pages H5 |
| `api.example.com` | Railway API and exact Replicate webhook origin |
| `www.example.com` | Redirect to the root marketing domain |
| `example.com` | Marketing site or redirect to the H5 |

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

The PoC uses the direct Neon URL because the API and worker have low, fixed connection counts. Add pooling only when service replicas increase.

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

Only this service receives a public domain. Run migrations here only; do not configure a pre-deploy command on the worker.

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
Production branch: master
Root directory: /
Build command: bash scripts/build-vireal-pages.sh
Build output directory: dist/vireal-pages
VIREAL_API_BASE_URL: https://api.example.com
```

Bind `app.example.com` as the Pages custom domain. The generated page uses the injected API origin and enables real backend mode without query parameters.

## 4. API domain and Cloudflare DNS

1. In Railway, add `api.example.com` to `vireal-api` and select target port 8000.
2. Add both the CNAME and TXT verification records shown by Railway to Cloudflare DNS.
3. Use the Cloudflare proxy on the first-level `api` subdomain and set SSL/TLS mode to `Full`, as required by Railway's proxied-domain setup.
4. Do not create a Cloudflare redirect rule for `/api/v1/webhooks/replicate`.
5. Confirm that a POST to the exact HTTPS webhook path returns an authentication error without any redirect.

Set these final origins in both Railway services:

```env
FRONTEND_HOST=https://app.example.com
BACKEND_CORS_ORIGINS=["https://app.example.com"]
REPLICATE_WEBHOOK_URL=https://api.example.com/api/v1/webhooks/replicate
```

Do not add arbitrary `*.pages.dev` preview origins to CORS. Use the custom H5 domain for real API verification.

## 5. Safe rollout

1. Deploy Neon, `vireal-api`, and `vireal-video-worker` with `REPLICATE_ENABLED=False`.
2. Deploy Pages and bind both custom domains.
3. Run the edge checks:

   ```bash
   H5_URL=https://app.example.com \
   API_URL=https://api.example.com \
   bash scripts/verify-production.sh
   ```

4. Verify device login, authenticated upload, R2 private read, and a direct unsigned R2 denial.
5. Confirm the worker is running and polling without database or R2 errors.
6. Change `REPLICATE_ENABLED=True` in both Railway services and redeploy them.
7. Upload one authorized adult full-body image and submit one five-second dance task.
8. Confirm exactly one Replicate prediction, signed webhook receipt, R2 transfer, H5 playback, and the global `REPLICATE_POC_MAX_SUBMISSIONS=1` ceiling.

Never automatically resubmit a task in `submission_unknown`. Inspect the task, Replicate dashboard, and billing before changing the submission ceiling.

## 6. Post-PoC checks

- Confirm no R2 object can be opened without a signed URL.
- Keep the application worker running for precise expiration and configure an R2 lifecycle rule for prefix `vireal/` as a backup cleanup mechanism.
- Review Railway API/worker logs, Neon connection count, Replicate billing, and R2 objects.
- Rotate any Replicate or R2 credential that has previously appeared in plaintext before production traffic.
