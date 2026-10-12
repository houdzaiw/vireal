# Public registration and PayPal recharge release

## Release state

Implementation is on `codex/paypal-public-registration`. As of **2026-10-12**,
the compatible production API/worker, signed-region Worker and H5 are deployed
with independently configured **Live** credentials. Production registration,
recharge and commerce-terms approval remain **off**; region enforcement is **on**.
This is closed integration preparation, **not** a public launch or a verified Live
payment. The dated checkpoints below are historical; the October 12 production
checkpoint supersedes their statements that production was unchanged/config was 404.
Controlled **staging-only** registration and Sandbox recharge are now enabled;
the Development Clerk allowlist admits only the owner-approved new test email.
The new test user completed verified signup with zero initial credits. All three
actual Sandbox purchases/captures have passed, with exactly 820 credits across
three recharge ledger entries. A completed $5.99 Sandbox refund triggered the
verified refund event, one open manual-review case and the expected account hold.
Audited administrator recovery/closure has also passed: exactly one 100-credit
recovery, the correlated reconciliation review closed without a second debit,
wallet balance **720**, and the account hold cleared. The actual H5 wallet agrees.
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
from commit `e6c51fe`. After the owner reauthenticated PayPal and explicitly approved
Cloudflare CLI authorization, sandbox credentials and a separate staging edge secret
were provisioned, the region Worker/H5 were deployed, and staging region enforcement
was enabled. Public registration and recharge were kept disabled at that checkpoint.
The staging PayPal
config endpoint is 200 and reports the three USD packages, Sandbox mode and a
30-submission global daily limit. Production remains unchanged; its health endpoint
is 200 and PayPal config remains 404.

Pending gates are final owner merchant/product/terms review, the generation safety
cap and stable release-source checks described below, and owner-operated Live
acceptance. The production backup/deployment preparation is now complete. Old QA
users remain disabled. The owner was asked
for a new test email/alias; controlled acceptance activation must not be mistaken
for a public or Live release. Any financial account upgrade, identity verification
or binding agreement remains owner-only. The owner has now unlocked the Mac and
provided a new test email/alias and logged into Clerk Dashboard. Following the
owner's explicit staging-only confirmation, the Development instance remains Open
with its allowlist enabled for exactly that one identifier, and the staging
registration/Sandbox recharge flags are active. The owner completed password entry
and email verification. Refreshing the existing Chrome H5 tab synchronized the
verified Clerk session to a new active business account and a zero-balance wallet.
The subsequent Sandbox transaction checkpoint below records the three real test
orders and first refund; it supersedes the earlier zero-order checkpoint.

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

## Staging sandbox/edge/H5 checkpoint — 2026-10-09

- After owner reauthentication, read credentials only from the dedicated
  **Vireal Staging Sandbox** app. Its linked sandbox seller is Business/Verified;
  the UI still requires a Business upgrade for Live credentials. No Live merchant
  eligibility or permitted-product approval has been established.
- Provisioned `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_MERCHANT_ID` and
  `PAYPAL_WEBHOOK_ID` to staging API and the existing staging worker through CLI
  standard input, with automatic deployments suppressed until configuration was
  complete. Values were not printed, committed, or saved to a local plaintext file.
  Read-back comparison confirmed both services use identical sandbox credentials.
- Successfully obtained a sandbox OAuth token and read the registered webhook
  through PayPal's official Sandbox API. Its receiver URL and all 10 specific
  subscribed events matched. Tokens were retained in memory only. This is API
  credential/configuration validation, **not** a buyer payment/capture, a verified
  real transaction webhook, a refund acceptance, or Live acceptance.
- Official Wrangler 4.149.0 was authorized on account
  `03f299cf050fbb5da51340d76e8b24c3`, restricted to `account:read`, `user:read`,
  `zone:read`, `workers_scripts:write`, `workers_routes:write`, `pages:write` and
  the required `offline_access`. Ignored the CLI's suggestion to add unrelated
  default permissions. Two localhost-callback attempts timed out; official device
  authorization succeeded without changing scopes.
- Applied the axiom-security credential-storage guidance by forcing
  `CLOUDFLARE_AUTH_USE_KEYRING=true` with `--use-keyring`, preventing plaintext
  fallback. CLI read-back confirmed persisted keyring mode: credentials reside in
  encrypted `default.enc`, protected by a macOS Keychain key (`wrangler/default`).
  No custom keychain implementation or browser password storage was added.
- Generated an independent random 64-character staging `APP_EDGE_SIGNING_SECRET`
  in memory, provisioned matching values to staging API/worker and Cloudflare's
  Worker secret binding, then cleared temporary secret variables. Production
  credentials were not read/copied/changed for this provisioning step.
- Region Worker `vireal-api-region-staging` version
  `b9e05b59-d178-4e01-8a2a-b3976cc4a0b4` deployed successfully to **only**
  `staging-api.usevireal.com/api/*`. Backend first verified a non-null signed edge
  country with enforcement off; forged `CF-IPCountry` and `x-vireal-edge-*` headers
  were ignored. Only then enabled region enforcement and redeployed both services.
- Final Railway staging API deployment
  `e0f34ace-a21a-409a-a972-b7d03dc8a0ec`: **SUCCESS**; worker
  `7531e42c-b70a-41f7-8d2e-92777c783af7`: **SUCCESS**.
  Flags: `APP_REGION_ENFORCEMENT_ENABLED=true`, `PAYPAL_ENABLED=false`,
  `APP_PUBLIC_REGISTRATION_ENABLED=false`, `ADMIN_PUBLIC_SIGNUP_ENABLED=false`.
  Schema, existing user/wallet/ledger fingerprints, zero orders and zero payment
  holds were verified again against the restored backup using UTC sessions.
- Rebuilt H5 with `https://staging-api.usevireal.com` and the actual staging
  `pk_test_…` Clerk key, whose issuer matches the backend. Published only Pages
  project **vireal-h5-staging**: deployment
  `355901a1-8a7e-40a6-9a76-259d3a280759`, source `5373bcb`, at
  `https://staging-app.usevireal.com`. The project's existing production branch
  `codex/vireal-v1-2-h5` was preserved for this direct upload; this is the staging
  project's main release, not the production Vireal project. No Git push occurred.
- Re-ran H5 contract tests: **29 passed**; edge signing tests: **3 passed**.
  Browser AX check at `/#register` displayed “注册暂未开放” and the message that
  signup/recharge await payment acceptance. No signup form was presented.
- Direct mainland network checks returned signed `country=CN`,
  `region_allowed=false`, registration/recharge false, including with forged
  region headers. Mainland public effect catalog remained accessible: 6 categories,
  18 effects, only 5/10-second variants; health returned 200. An unsigned PayPal
  callback returned 403, not an Access login page, and did not create financial rows.
  Requests via the pre-existing proxy returned a signed US edge country; this does
  **not** establish overseas residence or count as genuine overseas buyer acceptance.
  No system proxy was changed, no valid country proof was fabricated, and no real
  generation or payment was submitted.
- Production API/worker deployment IDs remain
  `72e6587b-b6a6-4c92-bcd4-bb31165579da` /
  `d35d95e5-67db-4267-843b-4ee184483376`. Production Pages remains deployment
  `6e4f185e-30c2-4247-985a-06c631acbd4c` in **vireal-h5-houdzaiw**.
  No production schema, service, route, Pages release or Clerk access policy changed.

## H5 auth-link regression checkpoint — 2026-10-09

- Native Chrome verification found that Clerk's real `Sign up` link targets
  `/#register/`. The H5 router previously treated that trailing-slash route as
  unknown and rendered the home page. Commit `0b02d19` normalizes trailing slashes
  on app routes without changing Clerk's slash-prefixed internal verification routes.
- Added browser regressions for the closed-registration link, login/signup
  switching, query strings and preservation of the in-progress email verification
  form. Full H5 browser suite: **20 passed**; H5 contract suite: **29 passed**.
  These use explicit UI mocks and do not constitute real payment acceptance.
- Rebuilt against the actual staging API origin and staging Clerk publishable key.
  Published only **vireal-h5-staging**, deployment
  `d1ef24e0-90c1-4d0e-957a-429ef5eb112f`, source `0b02d19`, preserving branch
  `codex/vireal-v1-2-h5`. No Git push, API/worker redeploy or production change.
  The custom-domain JavaScript SHA-256 matched the local release artifact.
- Retested the actual Clerk login-to-signup link in Chrome: it now displays the
  closed-registration gate, not home. Public recharge/refund help displays the
  three correct USD packages, zero signup credits, UTC limits and support contact.
- Read-only Clerk checks verified this is a development instance matching the
  staging issuer; the new test identifier has no user or allowlist entry. The
  instance response does not expose the signup/restriction policy, so its mode
  must not be inferred from the empty allowlist. Dashboard administrator login is
  required to finish that check before controlled test activation. No Clerk
  access changes, invitations, business users, orders or payments were created.
  Registration/recharge remain off and region enforcement remains on; mainland
  config reports `region_allowed=false`. Production PayPal config is still 404.

## Clerk/Sandbox buyer readiness checkpoint — 2026-10-09

- Owner completed Clerk administrator login. Read-only Dashboard inspection
  selected the **Development** instance `ins_3JhjJFXX0gfMy23mLRSqAEIWxtQ`, matching
  the existing staging backend issuer/key. No production instance setting changed.
- Email signup, required email and verification at signup are on, with email
  verification codes selected. Email-code sign-in is on. Access mode is **Open**
  and Allowlist is **off**, so do not enable backend registration until controlled
  signup restrictions are explicitly approved and applied. Adding an identifier
  without enabling the allowlist would not restrict who can sign up.
- Requested action-time confirmation for a staging-only single-email allowlist
  plus registration and Sandbox recharge activation. No toggle, identifier,
  invitation or business-user write has occurred while confirmation is pending.
  CLI read-only checks confirm the new identifier has no Clerk user or allowlist
  entry. Both backend flags remain false; signed mainland region remains denied.
- Restored the existing authorized PayPal Developer session with its existing
  passkey; no credential was changed or saved. Both default Sandbox accounts were
  C2. Created an additional **virtual US Personal Sandbox buyer** using PayPal's
  automatic test-data/credential generation, distinct from the C2 Business seller.
  New mock buyer account identifier: `4830785487038637637`. Dashboard confirmed
  successful creation and lists three sandbox accounts. This does not create a
  Live financial account or assert the owner's real country/residency.
- Sandbox buyer password was not revealed, exported or committed. Following
  axiom-security guidance, the staging Clerk secret used for read-only API checks
  stayed in process memory; CLI/provider diagnostics suppress sensitive outputs.
  No payment approval/capture, actual transaction webhook, refund or generation
  acceptance has been performed. Production remains unchanged.

## Controlled staging activation checkpoint — 2026-10-09

- Owner explicitly authorized **only controlled staging acceptance**. Enabled the
  Allowlist on the Development Clerk instance, added only the approved new email,
  then refreshed the Dashboard to verify the saved restriction. Read-only API
  checks confirmed one allowlist entry, no user for that identifier, and only the
  two known old QA Clerk users. No production Clerk access setting changed.
- Set `APP_PUBLIC_REGISTRATION_ENABLED=true` and `PAYPAL_ENABLED=true` on **only**
  the staging API and existing staging worker. Retained Sandbox credentials,
  signed region enforcement, closed admin registration and all existing limits.
  Read-back checks confirmed matching nonempty secrets across both services;
  official Sandbox OAuth/webhook configuration verification passed again.
- Staging API deployment `4b317fc5-c0bf-4969-9ba7-14a72bea7d10`: **SUCCESS**;
  worker `d5e293fb-c558-4417-9653-fbd17df81293`: **SUCCESS**. API build logs
  confirmed its health check succeeded, and the public health endpoint is 200.
  No source upload, new Railway service, Cloudflare release or Git push occurred.
- Actual signed US-edge configuration reports Sandbox, registration/recharge
  enabled, the three correct USD products and 30/30 global submissions remaining.
  This request used the pre-existing proxy and does **not** establish residence
  or qualify as genuine overseas/Live buyer acceptance. Direct mainland requests,
  including forged region headers, still report signed CN and deny both actions.
  No network/system proxy setting or region-proof validation was changed.
- After the API rollout and before signup, repeated the read-only UTC comparison
  against the restored backup: schema `a3b4c5d6e7f8`, all existing user/wallet/ledger
  columns unchanged, 2 users, 2 wallets, 12 ledger rows, 0 orders and 0 payment holds.
  Worker diagnostics found no payment-reconciliation failure markers.
- Refreshed `https://staging-app.usevireal.com/#register` in Chrome and verified
  the real Clerk **Create your account** email/password form. Prefilled only the
  authorized email and handed new-password entry, submission and email-code
  verification to the owner. No password, code, session or verified identity was
  fabricated, and no old QA account was reactivated or given coins.
- Production API/worker remain **SUCCESS** at the same deployment IDs recorded
  above. Production PayPal config remains 404; no production configuration,
  schema, account policy, route or Pages change was made. Sandbox purchase/capture,
  transaction-webhook, refund and real generation acceptance remain **pending**.

## Verified staging signup/zero-wallet checkpoint — 2026-10-09

- Owner reported completed signup/login. Official Clerk read-only checks confirm
  the approved email is verified, its user is neither banned nor locked, and it has
  one active session. The Development instance still has exactly one allowlist
  entry, three users total (the two old QA users and this new test user), and no
  unexpected user. No credential/session was fabricated or manually provisioned.
- The existing Chrome H5 tab initially displayed the sign-in form while the
  backend had no business identity for the new user. One ordinary page refresh
  restored the signed-in account view and synchronized through the real auth API.
  No code/configuration change or deployment was needed. This observed refresh
  recovery is not proof that all signup redirect/error cases have passed.
- Chrome `/#wallet` now shows **0 credits**, all three server-owned USD packages,
  the real Sandbox PayPal button, user capacity 5/day and 1 concurrent, global
  capacity 30/30, and no recharge order or coin ledger entry.
- Read-only database verification confirms the new account is active, Clerk-based,
  email-verified, has one synchronized login and no payment hold. Total users: 3;
  both old QA users remain **disabled**, and all their user/wallet/ledger columns
  still match the restored backup. New-user ledger count and total order count
  are zero. A wallet row is created only on the first financial adjustment;
  `get_coin_balance()` correctly returns zero before that, without granting coins.
- Direct mainland checks, including forged region headers, still deny signup and
  recharge with signed CN proof and retain the 30/day global limit. Production API
  remains at the same successful deployment and its PayPal config remains 404.
- The payment UI says clicking PayPal confirms its service terms/recharge notice.
  Requested action-time confirmation for **only Sandbox** notice confirmation and
  three virtual purchases (combined $42.97), followed by sandbox refund acceptance.
  This does not approve production legal notices, merchant readiness or Live
  funds. No payment button, buyer approval, capture, refund or paid generation has
  been executed while this confirmation is pending.

## Sandbox purchases and first refund checkpoint — 2026-10-09

- The owner explicitly authorized Sandbox payment-notice confirmation, the three
  virtual purchases (combined **$42.97**) and Sandbox refund acceptance. All
  payments used the dedicated **virtual US Personal** buyer and its generated
  test Visa, not a Live account/card or evidence of the owner's real residence.
- Tested closing the first unpaid checkout, refreshing and reloading H5, and
  retrying checkout. The same pending order was retained; before approval there
  was one order, zero captures, zero credits and zero ledger rows. This covers
  unpaid-window closure/recovery, not every provider/network failure condition.
- Approved each checkout once. Official Sandbox Orders API reads verified the
  dedicated merchant/buyer, local custom/invoice references, exact USD snapshots,
  `COMPLETED` order status and exactly one completed capture per purchase:

  | Package | USD | Credits | Local order | PayPal order |
  | --- | --- | --- | --- | --- |
  | `coins_100` | 5.99 | 100 | `7a717439-07dc-42e5-b136-506172eb9d17` | `7V0331164U679591C` |
  | `coins_220` | 11.99 | 220 | `e24f5606-8344-4b0b-ad59-acf021228b19` | `8PH67527LE334442R` |
  | `coins_500` | 24.99 | 500 | `761d738b-8c93-4c10-bca9-ebed9368c38c` | `2KM45763H2158252B` |

- H5 and read-only database verification showed balances **100 → 320 → 820**,
  exactly three `recharge_credit` rows (`+100`, `+220`, `+500`) and no payment
  holds before refund. Actual `CHECKOUT.ORDER.APPROVED` and
  `PAYMENT.CAPTURE.COMPLETED` webhooks were recorded for every order. These are
  genuine Sandbox transaction events, not simulator events or mocked signatures.
- PayPal accepted resending the first order's existing capture-completed event to
  only the registered staging webhook. The additional receiver request returned
  **204**; subsequent verification still showed three orders, three credit rows,
  six unique approval/capture events and 820 credits, with no duplicate credit.
- Submitted one full **virtual $5.99 USD** refund for the first verified capture
  through PayPal's official Sandbox Payments API, with a fixed idempotency key
  and strict staging/merchant/buyer/order/amount guards. Refund
  `8DP38818WN780541H` is **COMPLETED**. No public cash-refund endpoint was added.
- The independently verified `PAYMENT.CAPTURE.REFUNDED` event marked the first
  order `refunded`, created one **open refund case**
  `241a3781-ae47-4c79-b811-db7ac69eb0e1` requiring recovery of **100 credits**, and
  set `payment_hold=true`. No coins were automatically recovered or made negative:
  the wallet remains **820**, with three original credit ledger rows. H5 refresh
  showed the manual-review notice, disabled package selection, removed the PayPal
  checkout button and retained readable records/help.
- Resent the same authentic capture-completed event **after** refund as a late
  delivery test. The receiver returned 204 again; the first order stayed
  `refunded`, its one case stayed open, the payment hold remained set, and the
  wallet/three credit ledger rows were unchanged. There are seven unique provider
  events, not an extra credit or a restored paid-order status.
- **Remaining controlled acceptance step:** sign in at the staging admin, open
  the first order's payment case, enter a substantive Sandbox-refund review reason,
  and use **Recover credits & resolve**. Verify one audited `recharge_recovery -100`
  ledger row, wallet **720**, resolved case/reviewer/reason and cleared hold.
  Do not mark this step passed before those observations, and do not manipulate
  the database or use the production admin to bypass staging authentication.
- The staging admin's expired Cloudflare Access session recovered through the
  already-authorized provider login; its own admin login now requires the owner.
  Chrome is left at `https://staging-admin.usevireal.com/login` for that handoff.
- Applied axiom-security credential handling: the Sandbox buyer's masked password
  was copied through the official UI only into its matching Sandbox login, the
  clipboard was replaced with a public URL, temporary credential variables were
  cleared, and Chrome's password-save prompt was declined. No plaintext password,
  bearer token, raw buyer payload or screenshot of a revealed password was saved.
- Evidence screenshots (outside Git):
  `/tmp/vireal-sandbox-config-ukwVtF/staging-three-packages-paid.png` and
  `/tmp/vireal-sandbox-config-ukwVtF/staging-refund-account-frozen.png`.
  Read-only probes still match both disabled QA users' original user/wallet/ledger
  data to the isolated backup. No new generation was submitted: global capacity
  remains 30/30, user capacity 5/day and 1 concurrent. Production health is 200,
  and its PayPal config endpoint remains 404. No source/runtime release, production
  configuration/database/Clerk/Cloudflare change or Git push occurred in this test.
- This checkpoint does not claim Live merchant eligibility, Live payment/refund
  acceptance, every dispute/partial-refund scenario or a newly paid video test.

## Sandbox audited recovery and H5 correction checkpoint — 2026-10-09

- After the owner completed **staging** administrator login, selected only the
  first refunded Sandbox order. Its verified refund case still required 100
  credits. The existing Worker had also created a `refund_reconcile` case for the
  same capture; this was associated review evidence, not another refund/payment.
- Submitted **Recover credits & resolve** once for verified refund case
  `241a3781-ae47-4c79-b811-db7ac69eb0e1`, with a substantive review reason referencing
  its full USD 5.99 Sandbox refund/capture and explicitly excluding Live funds.
  The case became `resolved`, recovered 100 credits and retained its reviewer,
  reason and resolution time. Correlated case
  `525eb3ad-df8c-463c-8f55-8f6845086bc2` became resolved with **0** recovered credits.
  No generic wallet adjustment or manual database write was used.
- Two successive **read-only** database transactions verified the approved test
  identity, active account, `payment_hold=false`, balance **720**, three original
  recharge entries and exactly one `recharge_recovery -100` entry. The recovery
  references the first order, the administrator and idempotency key
  `paypal-case:241a3781-ae47-4c79-b811-db7ac69eb0e1`. There is exactly one
  `app_payment_case.resolve` admin audit record for the submitted case, recording
  `recover` and 100 recovered credits. Both cases are resolved and total recovered
  credits are 100. The first order remains `refunded`, the other two remain paid,
  and seven unique provider events remain recorded. Old QA accounts stay disabled;
  schema remains `a3b4c5d6e7f8`.
- Actual authenticated Chrome H5 displayed **720 credits**, the recovery ledger
  row, all three original recharge rows and a restored PayPal button. User capacity
  remains 5/day and 1 concurrent, global capacity 30/30. No fourth payment, further
  cash refund or new real video generation was submitted.
- Acceptance exposed one inaccurate status label: refunded orders always said
  "credits under review", even after case closure. Changed only the bilingual
  refund status to **已退款 / Refunded**; the separate wallet `payment_hold` notice
  still controls review messaging and recharge availability. This does not add a
  public API or change financial/account-freeze behavior.
- Added four UI regressions covering English/Chinese and held/cleared accounts:
  held accounts retain their review notice and disabled recharge; cleared accounts
  show the recovery row and available PayPal checkout without stale review wording.
  Full H5 browser suite: **24 passed**; Python page contracts: **29 passed**.
  These local mocked tests remain distinct from the actual Sandbox transaction
  and authenticated administrator acceptance above.
- The existing local esbuild binary was killed and a Tailwind native dependency
  was missing. Rebuilt successfully using isolated official-registry esbuild
  **0.28.2** and Tailwind **4.3.3** through the build script's explicit overrides,
  then reran the complete browser suite against the complete artifact. No project
  dependency/lockfile or system security setting was changed.
- Source commit **635523e** was rebuilt with the actual staging `pk_test_…` key,
  matching its Development Clerk issuer, and only `https://staging-api.usevireal.com`.
  Guarded publication rejected mock/incomplete artifacts and kept the staging
  Pages project's branch `codex/vireal-v1-2-h5`. Deployment
  **da642a18-4bf8-42c3-aa28-6705de472302** in **vireal-h5-staging** succeeded.
  The public custom-domain app bundle SHA-256 matches the real release artifact;
  Chrome refresh verified the corrected refund label and unchanged balance/ledger.
- Production Pages remains **6e4f185e-30c2-4247-985a-06c631acbd4c** before and after
  the staging publication. Production API health is 200 and its PayPal config is
  still 404. No Railway service/configuration, database schema, Clerk policy,
  region Worker/route or production release was changed, and no Git push occurred.
- Applied axiom-security guidance to the read-only verifier: Railway/database
  credentials stayed in subprocess memory, sensitive provider diagnostics were
  suppressed and nothing secret was saved to source/evidence. Wrangler retained
  encrypted configuration backed by macOS Keychain; its suggested unrelated
  additional OAuth scopes were not granted.
- Durable screenshots outside Git:
  `/Users/huili/Documents/vireal-acceptance/2026-10-09-sandbox/refund-case-resolved.png`,
  `/Users/huili/Documents/vireal-acceptance/2026-10-09-sandbox/wallet-720-restored.png`,
  `/Users/huili/Documents/vireal-acceptance/2026-10-09-sandbox/refund-history-and-recovery.png`.
- The controlled three-package purchase and **lowest-package full-refund/manual
  credit recovery** flow is complete. Live merchant qualification, production
  backup/rollout, owner-operated eligible-buyer payment and separately authorized
  paid video acceptance remain release gates. This is not acceptance of every
  partial-refund/dispute case or a Live launch.

## Closed production Live integration checkpoint — 2026-10-12

- The owner explicitly authorized creation of **Vireal Production** Live app, then
  production credential/webhook preparation and compatible rollout while keeping
  signup, recharge and terms approval off. No public Clerk policy was changed, old
  QA account reactivated, actual payment/refund initiated or paid video submitted.
  The owner performed the Business-account conversion/onboarding personally.
  Dashboard availability and API scopes do not establish all merchant/product
  qualifications, a genuine buyer payment or receipt/capture acceptance.
- Created exactly one Live app and one webhook at
  `https://api.usevireal.com/api/v1/webhooks/payments/paypal`, subscribed to the ten
  explicit events below. Fresh official Live OAuth and webhook GET checks passed
  (HTTP 200); payments, webhook and seller-dispute-read scopes are present. Final
  read-only verification matched the configured Webhook ID, URL and all ten events.
  Disabled the unused optional Subscriptions, Payouts and Mobile SDK capabilities;
  advanced cards, Apple Pay and Google Pay were not provisioned or advertised.
- Matching Live Client ID/Secret, Merchant ID and Webhook ID were configured in
  production API and the **existing** worker through standard input. An independent
  production edge signing secret was provisioned to Railway/Cloudflare. Final
  read-back verifies all five values agree across production services and differ
  from staging. Actual secrets/tokens were never printed or persisted in plaintext
  source/evidence; the public Client ID was visible on the ordinary Developer UI.
  axiom-security guided memory/stdin transfer and the reuse of encrypted Wrangler
  configuration protected by macOS Keychain, with no expanded Cloudflare scopes.
- Before migration, took a fresh mode-0600 production custom-format backup:
  `/Users/huili/Documents/vireal-backups/production-20261012-pre-paypal-1791775412345.dump`.
  Size **84,844 bytes**, SHA-256
  `1df41795492eb455dba5015b172c48634953a1df88d04447329e156e74ae175d`.
  Its companion `.verification.json` records restoration and rehearsal without
  connection secrets. Used one exported read-only repeatable-read snapshot;
  restored all **24 historical tables** in an isolated local PostgreSQL cluster
  with Unix-socket peer authentication, rejected TCP access and no TCP listener.
  Rehearsed `f2a3b4c5d6e7` → `a3b4c5d6e7f8`; all original-column row/count
  fingerprints matched, excluding only the expected Alembic revision change.
  The isolated server was stopped after verification. No pytest cleanup was run
  against production or this restored production dataset.
- Released immutable tracked source **bca8336fd742ea99e4fd4665b0120a72b01aff25**
  through explicit project/environment/service CLI uploads, not a Git push.
  API predeploy retained `bash scripts/prestart.sh` and applied the compatible
  additive migration. API/worker start commands and service identities were
  preserved; no new Railway service or unrelated draft was applied.
- Final production API deployment
  **40b4b8be-2f89-4ca5-8019-70fe396e6d12**: **SUCCESS**;
  existing worker **ed77fa65-8e17-475d-a3a4-7099a3f48376**: **SUCCESS**.
  Schema is `a3b4c5d6e7f8`. Post-rollout read-only UTC comparison still matches
  every historical table's original columns (except Alembic); new payment cases
  and payment holds are both **0**. Recent worker logs contain no payment
  reconciliation failure markers. Existing financial/account records were not reset.
- Production region Worker **vireal-api-region-production**, version
  **9f28e752-32e9-4014-a7f8-6aea165db396**, serves only
  `api.usevireal.com/api/*`; `workers_dev` remains false. First proved non-null
  signed edge country and stripping of forged headers with enforcement off;
  only then enabled enforcement and redeployed API/worker from the existing
  approved snapshot (without `--from-source`). Final **direct mainland** requests,
  including forged US country/proof headers, return signed **CN**, region denied
  and both commerce actions disabled. Direct unsigned Railway-origin requests
  return unknown country/region denied. Health and public catalog remain 200:
  **6 categories, 18 effects, only 5/10-second variants**. An unsigned negative
  PayPal event returns **403 Invalid PayPal webhook signature**, not an Access
  login redirect, and creates no financial rows. This is rejection testing, not
  acceptance of a genuine Live transaction or proof of overseas residence.
- Re-ran local H5 page contracts (**29 passed**), complete mocked browser suite
  (**24 passed**) and edge signing tests (**3 passed**). Rebuilt after the mock
  tests against **only** `https://api.usevireal.com` and the actual production
  `pk_live_…` Clerk key, whose decoded issuer matches the production API.
  Official-registry isolated compiler overrides avoided the host's broken local
  binaries; project dependencies/lockfiles were not changed.
- Published only production Pages **vireal-h5-houdzaiw**, preserving its existing
  production branch **main**: deployment
  **fe937a9c-9a33-462a-94e9-2a3d3a53cf8e**, status **success**, source `bca8336`.
  The custom-domain HTML and all four principal JS/CSS asset SHA-256 values match
  the real production artifact. Native Chrome at `/#register` displays
  **注册暂未开放** with no registration form; `/#refunds` displays all three correct
  packages, zero signup credits, UTC limits and the support address.
- Final production flags, identically verified in API/worker:
  `PAYPAL_ENVIRONMENT=live`, `PAYPAL_ENABLED=false`,
  `APP_PUBLIC_REGISTRATION_ENABLED=false`, `APP_COMMERCE_TERMS_APPROVED=false`,
  `APP_REGION_ENFORCEMENT_ENABLED=true`, `ADMIN_PUBLIC_SIGNUP_ENABLED=false`.
  Global/Wan daily limits are **30**, user daily/concurrent limits **5/1**,
  max duration **10**, legacy video API and local demo **off**.
- Staging remains controlled Sandbox: API/worker deployments
  `4b317fc5-c0bf-4969-9ba7-14a72bea7d10` /
  `d5e293fb-c558-4417-9653-fbd17df81293`, Pages
  `da642a18-4bf8-42c3-aa28-6705de472302`. Its credentials, policies, domains,
  balances and three-package/full-refund acceptance were not changed by this rollout.
- **Remaining release blockers:** production still has its prior conservative
  `REPLICATE_POC_MAX_SUBMISSIONS=1` lifetime attempt cap. It was deliberately not
  removed under this no-new-generation-cost preparation authorization. That cap
  overrides the advertised daily allowance and must be reviewed/explicitly
  released before paid generation; setting it to 30 would still be a lifetime cap,
  not 30/day. Retain the real daily/user/concurrency controls when removing it.
  Also reconcile the approved feature source with the durable Git/CI production
  release source before public financial traffic: this rollout was a CLI-uploaded
  snapshot, not a merge/push to `main`. Never let a later auto-deploy restore an
  older receiver lacking the payment endpoints while retaining Live credentials.
- Owner must still confirm truthful operating identity, permitted-product/merchant
  conditions and final terms/privacy/refund notices, then authorize terms approval
  and restricted Live smoke activation. A region-eligible real buyer must manually
  confirm the **$5.99** payment; verify merchant receipt and exactly one 100-credit
  entry. Obtain separate generation-cost authorization before one 5-second task,
  verify exactly one coin debit and playable output. Only after this acceptance
  and action-time approval may H5 Clerk/public signup and recharge open together.
  Feature rollback closes new signup/recharge but retains the compatible receiver,
  credentials, reconciliation and financial ledger for already-paid orders.

## Selected public release — local convergence checkpoint, 2026-10-12

This checkpoint is **local implementation**, not a deployment, public opening,
Live payment or newly authorized prediction. Production remains at the closed
Live-preparation deployments above; never equate mock/API tests with real payment
or model-output acceptance.

- Production catalog/deep links/recommendations and new task submissions are
  restricted by `APP_LAUNCH_EFFECT_SLUGS=["dance-1","romance-1"]`. Other records
  remain intact. Retain the server-side 10-second maximum and existing Wan path.
- Incremental schema head `b4c5d6e7f8a9` adds nullable provider-last/next-check
  timestamps and indexes only. Fresh migration and a separate synthetic-history
  rehearsal preserved a paid order, 88-credit wallet, both ledger entries and an
  unresolved task exactly. This is **not** a substitute for a fresh production
  backup and verified restore immediately before the eventual production rollout.
- Cleanup no longer expires submitting, unknown, pending, running or saving tasks.
  Provider callbacks, administrator checks and the existing worker use one locked,
  idempotent settlement path. Provider reconciliation starts independently every
  minute, with at most five parallel 10-second GETs; video transfer and payment
  reconciliation cannot block its scheduler. No-ID tasks require investigation.
  A timeout, 404, malformed identity or missing observation cannot refund coins,
  release an unknown reservation or initiate another prediction. Repeated delivery
  transport/R2/local-processing outages stay saving and enter manual review; only
  verified invalid output or audited supplier evidence can settle delivery failure.
- H5 retries **queries only** with backoff, manual refresh and online/visible-page
  recovery. It refreshes expired/failed playback links, exposes authenticated MP4
  download/system sharing, and reports actual refund timestamps. Input retention
  starts at upload; result retention starts after successful persistence, each
  currently 24 hours. The result's server deadline, not a browser estimate, governs
  delivery. Expiry/deletion does not itself mean a coin or cash refund.
- Admin **Video Tasks** has list/detail/review queue, original coin ledger and
  provider ID/check clocks. Reconcile needs a reason/idempotency key; resolve needs
  supplier evidence and explicit confirmation. It verifies the original debit,
  forbids settlement while a submission or transfer is in flight, and audits one
  server-calculated compensation. There is no arbitrary balance, cash-refund or
  regenerate button. Investigate historical anomalies individually, never bulk
  rewrite balances or treat absence of a provider record as proof of non-submission.
- Local verification: **378 backend tests passed; 91% application coverage**;
  ruff formatting/checks, mypy and ty passed. **29 H5 contract, 31 mocked Chromium
  H5, 3 mocked admin UI and 3 edge tests passed**; admin/H5 builds and frontend
  Biome checks passed. The new admin UI has a dedicated read-only/mock CI workflow.
  Backend tests ran only in a freshly initialized Unix-socket PostgreSQL cluster;
  teardown now rejects remote/production DBs, and email transport is mocked.
  This does not yet establish GitHub CI, actual Safari/system-save compatibility,
  genuine overseas-region acceptance, or a real production media/payment flow.

### Remaining gates and evidence ledger

1. **Public material: blocked.** Owner answered "暂无" for both launch covers and
   previews. Earlier authorized adult photos and their generated outputs are
   internal acceptance evidence only; do not publish or substitute them. Obtain
   explicit website-display/image rights, then use the existing media/catalog
   administration. Confirm the two titles, descriptions, model and prompt versions
   against actual output. The seed's generic romance prompt is not evidence of a
   rain-scene promise; do not advertise an unverified scene or guaranteed motion.
2. **Stable source/review/CI: pending.** Owner authorized GitHub device login,
   feature-branch push and PR creation, not merge/deploy. Login verified as `houdzaiw`
   using the macOS system keyring. Read-only trigger audit: Railway production API
   and worker follow `main`; staging API/worker still follow the older
   `codex/vireal-dual-mode-backend` branch. Production Pages is Direct Upload,
   staging Pages follows `codex/vireal-v1-2-h5` and formerly previewed all branches.
   Owner explicitly authorized excluding only `codex/paypal-public-registration`
   before push; keep other previews included (`*`) with custom branch controls.
   This control follows [Cloudflare's branch deployment documentation](https://developers.cloudflare.com/pages/configuration/branch-build-controls/).
   The exclusion was applied and read back: custom preview mode includes `*` and
   excludes that exact branch. Production deployment `fe937a9c-9a33-462a-94e9-2a3d3a53cf8e`
   and staging `da642a18-4bf8-42c3-aa28-6705de472302`, domains, build settings and
   environment settings remained unchanged. GitHub CI is still enabled.
   Draft [PR #17](https://github.com/houdzaiw/vireal/pull/17) contains the feature
   source (`dc2ed87` implementation checkpoint) and is **not merged**. Initial CI
   backend/H5/admin checks passed with 91% coverage; the spelling hook identified
   the upstream `refert_num` request field, now explicitly retained as an API
   identifier rather than renaming the provider payload. Full PR CI/review remains
   a release gate; see the PR's latest checks, not a historical checkpoint alone.
   Do not push this release to the old staging source branch or change those source
   settings as a side effect. Record the approved commit,
   migration head and each service/Pages/Worker version after the later rollout.
   Do not apply unrelated Railway IaC/config drafts. Existing production CLI-upload
   source still needs reconciliation with the durable reviewed Git source.
3. **Sandbox exceptions: partial.** Reuse dated three-package/full-refund evidence;
   cancel/pending/refresh and disputes/reversals are covered by isolated mocks.
   Still perform owner-approved actual Sandbox partial-refund/freeze/closure and
   interruption recovery. Never manufacture a Live dispute or chargeback.
4. **Four effect-duration combinations: pending evidence audit.** Verify
   dance-1/5s, dance-1/10s, romance-1/5s, romance-1/10s against each exact model,
   prompt version and input count. Preserve private internal evidence. Request
   action-time count/cost authorization for missing combinations; no new fee was
   authorized by this implementation plan.
5. **Owner readiness and controlled Live acceptance: pending.** Merchant verification,
   truthful identity, product eligibility, final terms and a region-eligible buyer
   are owner gates. Then separately authorize restricted activation, a human $5.99
   payment (one 100-credit entry), and one 5-second generation (one debit, playable
   result and real download/save). `REPLICATE_POC_MAX_SUBMISSIONS=1` remains unchanged;
   removing the lifetime test cap with `=0` requires action-time authorization.

### Restricted acceptance and public-opening sequence

- Initial compatible rollout: keep `APP_LIVE_ACCEPTANCE_ENABLED=false`,
  `APP_LIVE_ACCEPTANCE_SUBJECTS=[]`, public signup/PayPal/terms approval **false**.
  Back up/restore-check first; publish migrations/API, existing worker, signed-region
  Worker, admin and H5 from the reviewed, CI-passing source, without downgrading any
  financial schema. Confirm closed gates and current versions independently.
- `APP_VIDEO_SUBMISSIONS_ENABLED` is an independent emergency pause for new task
  creation. Keep Replicate enabled/credentials retained for existing-task GETs and
  verified callbacks. The old free `/app/generations/` POST is always disabled in
  production, including restricted acceptance, so it cannot bypass catalog/coins/
  quota controls; old records remain readable.
- At explicitly approved Live acceptance, retain public signup **false** and the H5
  Clerk restriction; configure exact verified **Clerk subject IDs**, not emails or
  client headers, with `APP_LIVE_ACCEPTANCE_ENABLED=true`. It requires production,
  approved terms and Live PayPal enabled. Only listed identities can create a new
  business account, upload, recharge or generate; region, disabled-account and
  payment-hold rules still apply. Existing captures/callbacks/history are unaffected.
  Use the real Clerk session login then H5 wallet; anonymous registration remains
  closed. Do not reactivate disabled historical QA identities.
- After all evidence and explicit opening authorization, disable temporary acceptance,
  clear subjects, open the H5 Clerk instance and enable public signup/recharge
  together. Admin public signup stays false. Verify zero signup balance and all
  quota/region controls; never reopen 15 seconds or other effects via deep links.
- First **72 hours**: small public trial, no large promotion. Owner reviews at
  **09:00, 15:00, 21:00 Beijing time**: paid-but-uncredited orders, reconciliation
  failures, no-ID/unknown/saving tasks and payment cases. Worker logs/admin polling
  are not a notification service or 24/7 support. End-to-end automatic alerting is
  required before expanding promotion; no scheduled monitor was created here.
- Pause new signup, recharge and generation for duplicate credits/debits, confirmed
  receipt uncredited for >15 minutes, or unsafe settlement. Disable acceptance as
  well as public signup/recharge; preserve callback verification, provider/payment
  GET reconciliation, transfer, records and existing-order fulfilment. See rollback
  below; never restore an old receiver or financial ledger to undo traffic.

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
2. Rehearse migrations through `b4c5d6e7f8a9` against a restored database with old orders/ledgers.
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
8. For controlled owner-operated Live smoke acceptance, use the server-side exact
   Clerk subject allowlist sequence above; keep public registration **off** and
   Clerk restricted. This is a recorded action-time-authorized step, not permission
   for the agent to pay or silently re-enable old QA users.
9. After successful acceptance remove the temporary allowlist mode, enable public
   registration/recharge together, and switch the
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

Disable `APP_PUBLIC_REGISTRATION_ENABLED`, `APP_LIVE_ACCEPTANCE_ENABLED` and
`PAYPAL_ENABLED`; clear acceptance subjects and re-restrict H5 Clerk. To pause new
generation without disabling read-only reconciliation, set
`APP_VIDEO_SUBMISSIONS_ENABLED=false` on API and worker. This gate blocks only new
task submissions; retain the approved daily/concurrent limits. Restore it only
after incident review and renewed authorization. Do not turn off the worker or
provider credentials used to query/receive results of already accepted tasks.
Keep the compatible API, worker, PayPal credentials/Webhook ID, region proxy and
financial database migration. Continue receiving verified callbacks and fulfilling
already-paid orders. Do not deploy an older receiver that lacks these endpoints,
remove secrets, truncate ledgers or downgrade the financial migration.
The migration intentionally refuses destructive downgrade; feature flags are the
rollback mechanism. Restore a backup only as a separately approved incident action
that accounts for all subsequent payments, not a routine deployment rollback.
