# Vireal: Cloudflare Pages + Railway + Neon

This runbook deploys the current FastAPI and PostgreSQL worker implementation without rewriting it for Cloudflare Workers.

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

## 5. Safe rollout

1. Deploy Neon, `vireal-api`, and `vireal-video-worker` with `REPLICATE_ENABLED=False` and `LOCAL_DEMO_ENABLED=True`.
2. Deploy Pages and bind both custom domains.
3. Run the edge checks:

   ```bash
   H5_URL=https://app.usevireal.com \
   API_URL=https://api.usevireal.com \
   bash scripts/verify-production.sh
   ```

4. Confirm `/device-login` returns 410, `/docs` returns 404, and the deployed H5
   source contains no fixed OTP or legacy device-token code.
5. With an invited account, verify email code, Google, and Apple sign-in. Confirm
   refresh restores the session and sign-out calls `/app/auth/logout`; replaying
   the previous token must return 403 immediately.
6. Confirm the first login creates exactly one Clerk AppUser and that the admin UI
   shows email, providers, registration time, recent login, and login count.
7. Disable the user in the Access-protected admin UI and confirm the H5 receives
   403 on its next API call.
8. Verify authenticated upload, R2 private read, and a direct unsigned R2 denial.
9. Submit one task and confirm the Worker produces a labeled local demo without any Replicate prediction.
10. Confirm the worker is running and polling without database, FFmpeg, or R2 errors.
11. Set `REPLICATE_ENABLED=True` in both Railway services and redeploy them only when the Replicate account is ready.
12. Submit one authorized adult full-body photo in standard mode and confirm one MiniMax prediction, signed webhook receipt, R2 transfer, and H5 playback.
13. Verify the shared user limit of five real predictions per UTC day and the Wan global limit of three per UTC day; quota overflow must produce a labeled local demo without another prediction.

Never automatically resubmit or locally downgrade a task in `submission_unknown`. Inspect the task, Replicate dashboard, and billing before resolving it.

## 6. Post-PoC checks

- Confirm no R2 object can be opened without a signed URL.
- Keep the application worker running for precise expiration and configure an R2 lifecycle rule for prefix `vireal/` as a backup cleanup mechanism.
- Review Railway API/worker logs, Neon connection count, Replicate billing, and R2 objects.
- Rotate any Replicate or R2 credential that has previously appeared in plaintext before production traffic.
