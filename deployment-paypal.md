# Public registration and PayPal recharge release

## Release state

Implementation is on `codex/paypal-public-registration`. Production registration,
recharge and region enforcement have **not** been switched on by this change.
Unit/UI mocks are not PayPal sandbox acceptance or evidence of live merchant eligibility.
The owner must confirm eligibility, merchant identity, permitted products and terms
before any live release. Do not reactivate the previously disabled QA accounts.

Read-only release check on 2026-10-08: neither Railway API environment has the four
PayPal credentials configured. The production API health endpoint is healthy and
the new PayPal config endpoint is still 404, confirming this feature is not deployed.
After the owner reauthenticated in Chrome, the Sandbox seller showed Business,
Verified and region C2. The owner created a dedicated `Vireal Staging` Merchant
application; its JavaScript SDK v6 and Customer disputes capabilities are selected.
The agent registered and verified the ten specific webhook events listed below at
`https://staging-api.usevireal.com/api/v1/webhooks/payments/paypal`. This is configuration
verification only, not actual transaction or webhook-signature acceptance. Live
credentials still require the owner to upgrade the account to Business.

On 2026-10-09 the owner explicitly approved discarding all three unrelated staging
drafts. The two `CLERK_SECRET_KEY` drafts were discarded; the identical old/new API
Healthcheck Path draft then disappeared automatically. The staging UI showed no
remaining drafts, and clearing them did not trigger a runtime deployment. No old
Clerk key draft was applied.

The compatible API and existing worker have now been deployed to **staging only**
from commit `e6c51fe`, with public registration, recharge and region enforcement
still disabled. The staging PayPal config endpoint is 200 and reports the three
USD packages, Sandbox mode and a 30-submission global daily limit. Production
remains unchanged; its health endpoint is 200 and PayPal config remains 404.

Pending gates are PayPal Sandbox secret/merchant provisioning, Cloudflare CLI
authorization and signed region Worker/H5 deployment, actual sandbox acceptance,
owner Live readiness, fresh production backup/deployment and owner-operated live
acceptance. The PayPal browser session expired before reading the merchant ID or
Client Secret; reauthentication was requested. Cloudflare CLI is not authenticated;
authorization with macOS Keychain credential storage was requested but has not yet
been granted. No PayPal or edge signing secrets have been provisioned. Any financial
account upgrade, identity verification or binding agreement remains owner-only.

## Staging operational checkpoint — 2026-10-09

- Before migration, created a mode-0600 custom-format staging database backup:
  `/Users/huili/Documents/vireal-backups/staging-20261009-pre-paypal-1791512329800.dump`.
  Size: 85,258 bytes; SHA-256:
  `e4d0045a1b108ba151239a06e5ae94fec3f6f318f99d8bd7856442b69f17902c`.
  Restoration was verified in an isolated local database; staging and production
  database identities were checked to differ. The companion `.verification.json`
  records the backup/restoration result without connection credentials.
- Rehearsed `f2a3b4c5d6e7` → `a3b4c5d6e7f8` against a second isolated restored copy.
  API deployment then applied the compatible migration using its existing
  `bash scripts/prestart.sh` predeploy command. Remote schema head was verified.
- Post-deployment read-only comparison with the restored backup, using **UTC in
  both database sessions**, confirmed all existing user, coin account and ledger
  columns unchanged. The initial timestamp-serialization fingerprint mismatch
  disappeared after normalizing session timezones; it was not a row mutation.
  There are 2 users, 2 wallets, 12 ledger rows, 0 orders and 0 payment holds.
- Staging API deployment `36e0e0f9-0500-4b04-a90b-ef0ed512e67e`: **SUCCESS**.
  Existing worker deployment `f5be7c24-d8d1-4a9d-9a76-14c065da5326`: **SUCCESS**.
  Start commands remain unchanged; no new Railway service was created.
- Both staging services use `ENVIRONMENT=staging`, `PAYPAL_ENVIRONMENT=sandbox`,
  `PAYPAL_ENABLED=false`, `APP_PUBLIC_REGISTRATION_ENABLED=false`,
  `APP_REGION_ENFORCEMENT_ENABLED=false`, `ADMIN_PUBLIC_SIGNUP_ENABLED=false`,
  and global/Wan daily limits of 30. Support email is
  `li522903183@gmail.com`. Credentials remain unconfigured; payment acceptance
  cannot be claimed from a successful deployment or config response.
- No Cloudflare route, region enforcement, Pages release, Clerk access policy or
  production service/database was changed in this checkpoint. Do not deploy the
  existing mock H5 test output as a release artifact.

## Locked business rules

- Overseas registration with verified Clerk email; new business wallets start at zero.
- Mainland China and unknown edge regions: public browsing only. Region proof does
  not establish residence and cannot guarantee VPN detection.
- USD packages: `coins_100` = 100 credits/$5.99; `coins_220` = 220/$11.99;
  `coins_500` = 500/$24.99. The server owns these snapshots; client amounts are rejected.
- 5/10 seconds only. Per-user 5 real submissions/UTC day and 1 concurrent task;
  all supported real models combined 30/UTC day. Wan's old test ceiling must also be 30.
- Attempts with an unknown submission result reserve capacity until clarified.
  Accepted submissions that later fail retain their daily slot but use the existing
  coin-refund mechanism. Recharge never reserves a generation slot.
- Public support: `li522903183@gmail.com`. Refunds/chargebacks require manual review.
  No cash-refund API or automatic negative coin balances.

## Account readiness — owner-only steps

1. In PayPal Developer, inspect Apps & Credentials for **Sandbox** and **Live**.
   A mainland personal account is not, by itself, verified merchant/API readiness.
2. The owner completes any required upgrade, identity verification, business details
   and binding agreements using truthful information. The agent must not do these.
3. Create a separate sandbox business seller, personal buyer and sandbox REST app.
   The buyer must not be the seller. Enable Disputes read capability for case review.
4. Register this environment's webhook endpoint and retain its corresponding ID.
   Use independently created Live credentials/merchant/webhook only when eligibility
   is confirmed. Never copy sandbox credentials or financial records to production.
5. Confirm final operating identity and legal notices, including product eligibility,
   refund rules and privacy/contact details. Then approve `APP_COMMERCE_TERMS_APPROVED`.
   The H5 notices currently require that owner review; the flag is not legal clearance.

Official references: [China seller account selection](https://www.paypal.cn/portal/account-selection?locale.x=zh),
[PayPal checkout](https://developer.paypal.com/checkout/integrate),
[webhook verification](https://developer.paypal.com/api/rest/webhooks/rest/),
[Disputes API](https://developer.paypal.com/api/customer-disputes/v1),
[Clerk restrictions](https://clerk.com/docs/guides/secure/restricting-access).

## Secret/configuration isolation

Configure the API and the existing Railway video worker for the **same environment**:

- `ENVIRONMENT=staging` or `production` explicitly.
- `PAYPAL_ENVIRONMENT=sandbox` in staging, `live` in production.
- `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_MERCHANT_ID`, `PAYPAL_WEBHOOK_ID`.
- `PAYPAL_ENABLED=false`, `APP_PUBLIC_REGISTRATION_ENABLED=false` initially.
- `PAYPAL_RECONCILE_INTERVAL_SECONDS=60`, `PAYPAL_REQUEST_TIMEOUT_SECONDS=20`.
- `APP_GLOBAL_DAILY_REAL_SUBMISSIONS=30`, `APP_WAN_DAILY_GLOBAL_SUBMISSIONS=30`.
- `APP_USER_DAILY_REAL_SUBMISSIONS=5`, `APP_USER_MAX_CONCURRENT_VIDEO_TASKS=1`.
- `APP_EFFECT_MAX_DURATION_SECONDS=10`, `APP_LEGACY_VIDEO_TASKS_ENABLED=false`,
  `LOCAL_DEMO_ENABLED=false`. Do not enable unpriced/demo generation with paid users.
- `APP_AUTH_MODE=clerk`, `ADMIN_PUBLIC_SIGNUP_ENABLED=false`.
- `APP_SUPPORT_EMAIL=li522903183@gmail.com`.

Each environment needs its own random `APP_EDGE_SIGNING_SECRET` (at least 32
characters), identical in its API and Cloudflare region Worker. Store keys only in
Railway/Cloudflare secrets. Do not echo values, paste them into chat, or commit them.
The PayPal client ID is public; none of the other credentials are returned to H5.
Do not apply unrelated existing Railway configuration drafts.

## Compatible rollout order

1. Record API/worker/Pages versions and current flags. Take a **new** production
   `pg_dump -Fc` backup before migration; verify restoration to an isolated database.
   Preserve existing production files, accounts, coin balances and financial history.
2. Rehearse migration `a3b4c5d6e7f8` against a restored database with old orders/ledgers.
   Run `uv run alembic upgrade head` from `backend` with the intended database.
   This migration adds columns/table/indexes and does not rewrite old rows.
3. Deploy the compatible API and existing worker with public registration/recharge
   **off**. The worker now reconciles payments in its own bounded background thread;
   no new Railway service is required.
4. Provision the matching Cloudflare Worker secret, then deploy from `edge` using
   the verified account and environment, e.g. `wrangler deploy --env staging`.
   Routes are `staging-api.usevireal.com/api/*` and `api.usevireal.com/api/*`.
   Verify the route matches the actual staging hostname before applying it.
5. Only after successful proxy verification enable `APP_REGION_ENFORCEMENT_ENABLED`.
   Worker strips client-supplied region proof and signs method/path/time/country from
   `request.cf.country`. Backend rejects missing, expired or mismatched signatures.
   Never bypass this with fabricated headers, a VPN claim or hardcoded US country.
   The secret is required at the Worker even while backend enforcement is off.
6. Build/deploy H5 with the verified target API origin and that environment's Clerk
   publishable key. Do not publish the `api.example.com`/dummy-key test build.
7. Perform sandbox acceptance below. Keep production closed until merchant readiness
   and the owner-operated live smoke acceptance are complete.
8. For a controlled owner-operated live smoke test, enable the registration and
   recharge flags together **while Clerk remains restricted** to approved overseas
   smoke buyers. No uninvited user can register at this point. Production backend
   refuses new business identities when its registration flag is off, even if
   someone uses Clerk directly. Do not silently re-enable old QA users. This is a
   deliberate, recorded release step, not permission for the agent to pay.
9. After successful acceptance confirm both flags remain enabled and switch the
   **H5 Clerk instance**, not the admin auth system, to Open for the public launch.
   Changing access controls through the browser requires action-time confirmation.
   Check local account synchronization still enforces verified email and zero coins.

## Webhooks and recovery

Endpoint: `POST /api/v1/webhooks/payments/paypal` without redirect or browser Access
login. Subscribe to `CHECKOUT.ORDER.APPROVED`, `CHECKOUT.ORDER.COMPLETED`,
`PAYMENT.CAPTURE.COMPLETED`, `PAYMENT.CAPTURE.PENDING`, `PAYMENT.CAPTURE.DENIED`,
`PAYMENT.CAPTURE.REFUNDED`, `PAYMENT.CAPTURE.REVERSED`, and the available
`CUSTOMER.DISPUTE.CREATED/UPDATED/RESOLVED` events.

The server posts the exact event plus transmission headers to PayPal's official
signature-verification API with that environment's Webhook ID. Invalid signatures
return 403; transient provider failures return 503 so PayPal can retry. Do not count
webhook simulator success as signature verification of an actual sandbox transaction.

Capture and webhook processing use order locks, unique capture IDs and coin-ledger
idempotency keys. Provider amount/USD/merchant/local order association are checked
before the atomic order+ledger transaction. Browser cancellation, HTTP timeouts,
pending captures and closed windows do not grant credits or imply success.
Existing orders continue reconciliation even after the purchase flag or global
daily capacity closes. Missing/unassociated events are retained as minimal identifier
envelopes for replay, without payer contact/address data.

Review at least daily: due/old unfulfilled orders, `payment_review`, worker reconcile
errors, unassociated events, open payment cases and global remaining capacity.
Do not resubmit unknown real generation attempts blindly.

## Manual refund/chargeback operations

1. Human operator reviews the request and performs any cash refund **in PayPal**.
   The admin UI only handles coin/audit cases; its button never sends cash.
2. A verified refund/reversal/dispute freezes new recharge, uploads and generation.
   Wallet/order/work records remain readable.
3. In admin Orders > events, enter a substantive review reason before resolving.
   Refund/reversal recovery is idempotent and capped to that order's credited coins.
   Partial refunds use integer-rounded proportional coins from verified amounts.
4. Dispute dismissal requires an API-confirmed seller win or buyer cancellation.
   Dispute recovery requires a resolved buyer win, matching capture and verified
   USD refund amount. Unresolved/ambiguous cases stay open.
5. A partial-refund review without a refund event cannot guess the amount: have the
   operator resend the actual transaction webhook through PayPal and confirm receipt.
   Full-refund/reversal reconciliation can create a review even if its webhook is lost.
6. Insufficient coin balance returns 409 and keeps the case/account frozen with no
   negative wallet. Any other manual wallet adjustment must use the existing audited,
   reason-required admin operation; never edit the balance or ledger directly.
7. An account unfreezes only after every open case is resolved. Historical credits,
   recovery entries, events and admin audit records remain intact.

## Acceptance gates

- Local: backend tests/90% application coverage, mypy/ty/ruff, H5 contract tests,
  browser tests, edge signature tests, admin build and incremental migration.
- Staging: actual isolated sandbox buyer approvals for all three packages; one
  credit per capture, cancellation/pending/timeout/refresh recovery, verified webhook
  duplication/out-of-order delivery, manual sandbox refund and audited coin recovery.
- Region: genuine overseas edge country permits registration; CN/unknown blocks
  business creation/uploads/orders/new generation. Fake/bare client country headers
  must fail; public catalog/health and separately verified callbacks remain usable.
- Quota: concurrent cross-model race at slot 30 rejects slot 31; UTC rollover works;
  unknown submissions keep slots; exhausted capacity still fulfils existing payments.
- Live: human overseas buyer explicitly confirms **$5.99** purchase, checks merchant
  receipt and one 100-coin credit. Obtain separate generation-cost authorization
  before one real 5-second task; verify one debit and playable private result.
  No simulated live payment and no use of mainland browsing as financial acceptance.

## Rollback

Disable `APP_PUBLIC_REGISTRATION_ENABLED` and `PAYPAL_ENABLED`; re-restrict H5 Clerk.
Keep the compatible API, worker, PayPal credentials/Webhook ID, region proxy and
financial database migration. Continue receiving verified callbacks and fulfilling
already-paid orders. Do not deploy an older receiver that lacks these endpoints,
remove secrets, truncate ledgers or downgrade the financial migration.
The migration intentionally refuses destructive downgrade; feature flags are the
rollback mechanism. Restore a backup only as a separately approved incident action
that accounts for all subsequent payments, not a routine deployment rollback.
