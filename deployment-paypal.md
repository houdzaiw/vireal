# Public registration and PayPal recharge release

## Release state

**2026-10-13 authorization update:** the owner now authorizes merging PR #17
after review/green CI and deploying the selected release in the **closed** state.
A fresh backup `production-20261013-153609-pre-selected-release.dump` in
`/Users/huili/Documents/vireal-backups/` restored successfully: all 25 public
tables matched the exported snapshot. The isolated additive migration to
`b4c5d6e7f8a9` preserved every existing column/row in the other 24 tables.
Verification and migration-rehearsal JSON records sit alongside the dump (0600).
The completed closed deployment is recorded below; this authorization is not a
public-opening approval.

The owner initially confirmed Li Qihui (李启辉), brand Vireal, support
`li522903183@gmail.com`, prices, limits, 24-hour retention and manual-refund rules
**for controlled Live acceptance**. H5 now states that identity and the separate
upload/result retention start times. PayPal telephone advice (owner reported)
was that no advance product approval was required and compliance may be reviewed
after receipt; this is not independent legal/compliance clearance. The PayPal
contact-settings search fails for the owner as well; keep the site's support
email accessible and treat the PayPal profile issue as an open follow-up, not a
verified optional requirement.

**2026-10-14 owner readiness confirmation (recorded 15:06 Beijing):** the owner
reports that `li522903183@gmail.com` successfully received an external self-test
email. The owner also explicitly approves the current `#terms`, `#privacy` and
`#refunds` notices for **small-scale public operation**, not only controlled
acceptance: the stated operator/brand, three USD packages, UTC 5/1/30 limits,
24-hour media retention, manual refunds and non-transferable/non-withdrawable
credits. These two owner-assisted readiness checks are now complete for that
unchanged copy. This is an owner confirmation, not independent legal/compliance
clearance, proof of round-the-clock support or resolution of the PayPal profile
contact issue.

The answer explicitly keeps production closed. It authorizes recording consent
only: `APP_COMMERCE_TERMS_APPROVED`, registration, PayPal and Live acceptance
remain disabled. It does not authorize PR #21 merge/deployment, a Live payment,
new generation, submission-lock removal or general public opening. If the public
copy or business rules change, obtain renewed review of the changes.

Maximum newly authorized paid predictions: **four staging combinations plus one
production 5-second acceptance, five total and combined model spend <= USD 10**.
Confirm the provider's actual current price before submission; no blind retries.
The production cumulative test lock may be removed only at the production
acceptance stage. **No eligible independent overseas Live buyer is available**
(owner confirmed); production acceptance and lock removal must wait. Keep
public registration, payments, acceptance and terms flags closed meanwhile.
Synthetic concept covers are not genuine video previews; never publish the
earlier internally authorized real-person inputs/results. Public opening remains
separately authorized after all acceptance gates pass.

## Additional prelaunch convergence — 2026-10-14

Scope: non-spending readiness work while PayPal reviews the existing Sandbox
capture. No new payment, refund, prediction, production deployment, opening flag
or ledger change was made. Deployed source remains `a1c42cb`; the local correction
is on `codex/h5-public-first-load` and is not yet merged or deployed.

### Startup and payment-widget recovery

Three anonymous Mac-route samples measured the auth bundle at **1,199,802
compressed bytes**, versus 16,197 for the deployed app. Auth download took
2.44–2.83s in production / 2.26–3.27s in staging; catalog requests took
3.03–5.26s / 1.99–2.64s respectively. These include network and edge/origin time,
not backend-only latency or iPhone performance. The auth response is `no-store`;
that cache policy was not changed because assets do not yet have hashed names.

The deployed HTML executes deferred auth before the app. Deferred scripts execute
in document order ([MDN script reference](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/script#defer)).
A held-download regression proved the catalog remained invisible until auth
download completed. The local fix runs the app first, preserving Clerk ready
events, session validation and fail-closed region/registration gates. It does not
defer authentication for uploads, payments or generation.

Reordering exposed a wallet race: passive redraws replaced an SDK initialization
error and retried SDK creation. The fix preserves a failed checkout placeholder
for the same context; explicit wallet refresh releases it and retries **SDK
initialization only**, never a payment. Stale async mounts cannot overwrite the
current view. Fixtures now emit the real wrapper's ready event; the already-ready
path is independently exercised before either HTML script.

Local checks passed: **43 Chromium + 43 WebKit cases**, **30 targeted repeated
cases** (three cases on both engines, five repetitions), **49 H5/PRD checks**, three
edge checks and a mock-config build. Both defects were reproduced before their
corrections. These browser fixtures are not new Sandbox/Live payments. Backend
source/schema are unchanged; the earlier 396-test/91% backend CI result is retained
as that source's evidence, not a new backend run. New CI/review and separate
merge/closed-deployment approval remain required. Never deploy the local
`api.example.com` / dummy Clerk-key test build.

The owner reports **iPhone 16 Pro / iOS 26.5 / Safari**, VPN off, staging catalog
visible/clickable in approximately **2s Wi-Fi / 3s cellular**. This is a useful
owner-estimated baseline on the deployed version, not an instrumented benchmark,
a measurement of the local fix or proof of the earlier slow-loading cause.
`prelaunch-performance-evidence.json` retains the samples and their scope.

### Natural media expiry and operational readiness

At **14:43 Beijing**, read-only inspection found all four staging works succeeded
with results present and exactly **86,400 seconds** from persistence to expiry.
The owner could access all four before expiry: expected, not a post-expiry pass.
Both workers explicitly use private R2, 24-hour retention and 60-second cleanup,
with legacy generation and admin public signup disabled.

| Existing work | October 14 expiry, Beijing time |
| --- | --- |
| dance-1 / 5s | 16:02:27 |
| dance-1 / 10s | 16:23:07 |
| romance-1 / 5s | 17:01:48 |
| romance-1 / 10s | 17:15:13 |

After 16:10, refresh the first work: no new playback link/download after expiry,
no false coin-refund claim, and not-yet-expired works remain usable. Subsequent
read-only database/object checks must verify natural cleanup without changing
expiry or rerunning generation. An MP4 already saved on the phone is not revoked.
`prelaunch-media-retention-check.json` records deadlines; actual expiry/cleanup
acceptance remains open.

Production read-only audit at **14:46 Beijing** found **zero active/unknown tasks,
zero unfinished approved/pending/review payments, zero paid-but-unfulfilled orders
and zero open payment cases**. All six historical tasks are expired; five have no
coin debit and the existing real test has one debit/no expiry refund. No balance
was adjusted. All four opening flags and five financial-table fingerprints are
unchanged against the restore-verified PR #20 backup.
`prelaunch-production-exception-check.json` records this snapshot, not Live
acceptance or a promise of future zero backlog.

Production still exposes only dance/romance, both 5/10s with managed media.
Staging's 18 effects are its documented legacy QA arrangement under the controlled
Clerk allowlist, not a new production defect or a public promotional endpoint.
No extra catalogue/account mutation was inferred from this request.

The owner authorized only excluding `codex/h5-public-first-load` from automatic
Pages previews, pushing it and creating a PR. Preserve existing exclusions,
production `main`, build settings and CI. No merge, deployment or public opening
is authorized. Remaining gates are consolidated in the existing evidence ledger
below, not a separate operation manual.

Before pushing, read-only Railway trigger inspection confirmed PR deployments
are off and all four API/worker targets follow `main`. The staging Pages project
`vireal-h5-staging` now excludes exactly the three existing/new authorized branches:
`codex/paypal-public-registration`, `codex/paypal-wallet-lifecycle`, and
`codex/h5-public-first-load`. The complete source config, `main` production branch
and build config were verified unchanged except that one appended exclusion.
Production Pages remains direct-upload; no unrelated draft was applied.

PR [#21](https://github.com/houdzaiw/vireal/pull/21) is open for this branch and
attached to the current chat. Use its exact head's check results in the PR card;
do not mistake skipped unchanged-admin checks for new admin E2E evidence. This
records review preparation, not merge, closed rollout or public-opening approval.

## Wallet lifecycle closed release — 2026-10-14

The owner explicitly authorized PR [#20](https://github.com/houdzaiw/vireal/pull/20)
to merge after fresh backup/restore verification, with public registration and
recharge still closed. It merged at **02:19:26 UTC** to
`a1c42cbfd7cd9adf8bec209e033ff5b9c4bcdaf3`. This is the latest deployed source;
the earlier release/version tables below remain historical checkpoints.
No backend/schema migration was introduced. The clean merged H5 source is
identical to the reviewed PR head `d6e8010`.

Before the merge, `production-20261014-101812-pre-pr20-wallet.dump` in
`/Users/huili/Documents/vireal-backups/` restored successfully in an isolated,
socket-only PostgreSQL instance; **all 25 table fingerprints matched**.
SHA-256: `8117c1203304681591c43ce0bd64440e8cf966bfeec29288c19ad97123d8286f`.
The verification JSON is alongside the dump, both 0600. The restore server was
stopped. `APP_LIVE_ACCEPTANCE_ENABLED` is absent in both production services and
the deployed Settings default is **false**; this was recorded explicitly rather
than changing configuration. PayPal, public registration and terms approval are
explicitly false on both services. The region policy, UTC 30/5/1 limits, 10-second
maximum and old cumulative submission lock/count **1/1** were preserved.

| Target | Successful PR #20 deployment/version |
| --- | --- |
| Production API / bundled admin | `ce2c7732-c195-4d1a-b10f-e0daea8894da` |
| Production existing worker | `bbeb087c-22fd-4042-bfda-b98d3e0d3074` |
| Production H5 Pages | `4de6caca-3fe6-4b98-ab79-c7bbe9fc92e3` |
| Staging API / bundled admin | `0ee6b19f-b7f6-4edc-9916-f2495f4e967f` |
| Staging existing worker | `e9cd4d07-26f4-4b9a-bd19-8cb16bad5213` |
| Staging H5 Pages | `0e064494-15a3-46c1-af7c-43bdc5390b48` |

All six targets use the exact merge commit. Signed-region Worker code/configuration
was unchanged. Production H5 was rebuilt with its actual public Clerk key and API,
not the local mock build. `verify-production.sh` passed the closed observable
contract on the custom domains. Production wallet UI shows recharge unavailable,
three disabled packages and no PayPal button. Five financial tables match the
fresh verified backup; total tasks remain **6**, counted submissions remain **1**.
No new Live/Sandbox payment, refund, financial adjustment or paid prediction was
performed. Runtime/financial JSON records are under the backup directory.

Both reviewed-head and merged-main CI passed. Main H5 run `38500426842` passed
**41 Chromium / 41 macOS WebKit cases**; backend run `38500426989` passed
**396 tests with 91% aggregate coverage**. Existing admin Playwright path filters
skip unchanged admin tests; their aggregate success is not a fresh admin E2E run.

Real signed-in staging Chrome exercised **7 wallet refreshes, 3 package changes
and 4 home/wallet round trips** without starting checkout. Across **20 DOM
samples**, every wallet sample had one checkout root/button, two SDK scripts and
two PayPal iframes; leaving removed the root/button and session iframe, retaining
only one shared SDK iframe. PayPal accessibility containers remained six on the
wallet and zero after leaving, rather than growing. Balance stayed **666**;
read-only provider/ledger verification confirmed the existing USD 5.99 capture
still has one +100 credit and four existing video tasks. These are real SDK
lifecycle observations, not a heap profile, a phone benchmark or a new payment.

The existing romance 5-second work still loaded without a player error and its
authenticated MP4 download completed in Chrome. The downloaded 3,627,473-byte
file matched the archived provider output SHA-256
`f5d56e70feb495c9a311c500f38c9cc582dec8b877751f1e92a54be360f3d52e`, decoded
fully and contained 720x1280 H.264 video plus AAC audio. The browser automation's
download event timed out; completion was verified independently through the
native Chrome download UI and actual file, not inferred from the click.
On **2026-10-14**, after the PR #20 closed rollout, the owner reported that all
four requested real **iPhone/Safari** staging checks succeeded: playback,
**Download MP4**, **system save/share**, and **offline/online recovery**. This is
owner-assisted physical-device acceptance, not an agent-instrumented recording.
The report does not establish measured startup latency or its root cause, Android
behavior, or recovery after actual media expiry. No further payment/generation or
production gate change was performed for recording this result.
At that delivery checkpoint, actual Sandbox PENDING and provider capture-response
loss still lacked real evidence. The subsequently authorized checks are recorded
below, with their online-versus-isolated scope kept explicit. Public opening and
controlled Live acceptance remain blocked by the
missing eligible independent buyer and their separate readiness/authorization gates.

## Sandbox payment fault acceptance — 2026-10-14

The owner authorized **at most two USD 5.99 Sandbox virtual payments**, temporary
Payment Review on the matching virtual merchant, and its restoration afterward.
The owner separately accepted the existing site terms **only for these Sandbox
checks**, not public trading or Live payment. Two orders were created; no third
payment, refund, prediction, new account or production gate change is authorized
by this acceptance. All backend source matches deployed `a1c42cb`.

### Genuine PENDING capture, no premature credit, H5 recovery

The matching Sandbox **Business** merchant's Payment Review was originally off.
It was enabled and full-reload verified; Negative Testing and the virtual buyer's
review setting remained off. After the normal H5 checkout, order
`652ecf22-d25a-4ff5-9b37-149826d590b9` / PayPal `4G189190CR137044V` had capture
`1BD94467D9865150B` with actual **PENDING / PENDING_REVIEW**. The provider's overall
order status is COMPLETED; this does **not** make the pending capture fulfilled.
The [Orders v2 capture-state definition](https://developer.paypal.com/api/orders/v2/definitions/purchase_unit)
identifies this reason as manual review. Local status remained `capture_pending`,
`fulfilled_at` remained null, credit count remained zero and wallet remained
**666**. Verified event `WH-2YK58627L2029435H-3K295475JM191015A` was processed as
`PAYMENT.CAPTURE.PENDING`. Manual wallet refresh and a full page reload retained
the pending label and unchanged balance; existing video-task count remained four.

The merchant's Payment Review was subsequently restored **off** and persistence
verified by another full reload; Negative Testing remained off. The captured
payment still required provider review as of **03:21:43 UTC**. Turning the switch
off is not proof of releasing an existing transaction. The real pending/no-credit/
refresh checks pass; **PENDING -> COMPLETED -> unique 100-credit recovery remains
open until the provider genuinely releases this transaction**. Do not recapture,
change database payment state/balance or fabricate a webhook. The owner signed
in to the existing virtual merchant and the exact capture/invoice were
matched on its transaction-detail page. The status is pending, the displayed
release date is **October 15 (Beijing)** and the page warns review may take up to
three business days. Its More actions menu offers tracking and print operations,
not an approve/release action. No shipping/tracking information, refund or denial
was submitted to force an outcome; the displayed date is not a release guarantee.
`sandbox-pending-review-evidence.json` retains the provider/ledger/UI
checkpoint and webhook identity.

The owner authorized an **hourly, read-only follow-up in the current chat**.
Heartbeat `sandbox` is active and checks only this order, its real Sandbox capture
and its associated coin ledger. The durable `sandbox-pending-readonly-check.py`
uses a READ ONLY database transaction and provider GET (OAuth POST only for
authentication), never a capture/refund or other financial mutation. Unchanged
pending state is quiet; meaningful changes, completion, anomalies or required
owner action are reported. Genuine completion plus exactly one +100 credit is
required to pass. The follow-up stops after completion or a noncontinuable terminal
outcome; it cannot open production or replace the outstanding Live acceptance.
Local scheduled checks require the Mac and desktop app to remain running.

An initial click reused a prior fulfilled order's recovery key, causing checkout
to close and clear that key without creating or paying a new order. Database
inspection confirmed no new order or credit; only after following the UI refresh
instruction was the new pending-test order created. No old capture was replayed.

### Real capture response discarded, isolated backend recovers exactly once

The second order used the same reviewed backend code and real Sandbox API, with
a freshly migrated, **socket-only private local PostgreSQL ledger**. No online
wallet/region configuration, Clerk access or production service was changed.
The isolated order `54e23370-7460-41f2-a05d-3b23bce016be` / PayPal
`0VF69465D1120113K` was genuinely approved by the same US virtual buyer. At
**03:08:27 UTC** the backend sent exactly one idempotency-keyed capture POST.
PayPal returned **HTTP 201 / COMPLETED**, capture `9CV71315VW073932U` for USD 5.99.
Only after validating that real response, ownership/merchant/price and the still-
empty local ledger did the test transport discard the response and raise an
`httpx.ReadTimeout`. The real PayPal client mapped it to `PayPalError`; unchanged
`confirm_order` queried the provider rather than replaying capture and recovered
`paid`, one +100 ledger entry, a 100 balance and the same capture ID.

Four further concurrent query-only confirmations left **one** credit, balance
100 and the same capture ID; they sent no capture POST. The local server was
stopped after verification, retaining its private test data and sanitized evidence.
`sandbox-real-capture-response-loss-evidence.json` records the real HTTP/capture
boundary and result. This passes **real-provider/isolated-backend response-loss
integration**; it is not an on-Railway fault injection, an H5 outage or a mock
provider response. The online staging wallet was not credited for this isolated
order. Its genuine Sandbox callbacks may remain unassociated online because the
business order exists only in the local test ledger; preserve and identify these
test events rather than modifying the online wallet to hide them. The two
observed unassociated event IDs are `WH-3HN92418AG2274701-18468457Y60935135`
(approval) and `WH-3C778979K41526020-7X1396859S376212S` (completed capture).
Online staging balance still remained **666** at the final read-only checkpoint.

Production API/worker gates and all five financial-table fingerprints were
rechecked against the verified PR #20 backup and remain unchanged. No app source,
production deployment, Live payment, cash refund or video generation was changed
by this acceptance. The tools remain outside the repository at
`/tmp/vireal-sandbox-acceptance.xcbsfi`; evidence JSONs (0600) are under
`/Users/huili/project/new-chat/output/imagegen/vireal-launch-20261013/`.

## Delivery-recovery follow-up — 2026-10-13

### Closed recovery deployment completed at `ad329d1`

The owner explicitly authorized the PR #19 merge and closed update. PR
[#19](https://github.com/houdzaiw/vireal/pull/19) merged at **11:49:39 UTC** to
`ad329d184bf1280ed98a61a434989e643140e2ae`. Head and merged-main H5/backend/
admin/Playwright checks passed. Main H5 run `38392913906` and backend run
`38392914012` are successful. The production backup
`production-20261013-194226-pre-pr19-h5.dump` restored into an isolated local
database; all **25 tables** matched its exported snapshot. SHA-256:
`a7c717dc4e84c4aadc1b6e6e19d5d7611f4bb60e2ac14a3e690c1c98533d811d`.
The ephemeral restore server was stopped. No migration was introduced by PR #19.

| Target | Successful PR #19 deployment/version |
| --- | --- |
| Production API / bundled admin | `343992cf-e669-4adb-96f7-bdd6fdc678ea` |
| Production existing worker | `93e4b078-220d-44c7-b620-1bb74b9d960e` |
| Production H5 Pages | `f55846e7.vireal-h5-houdzaiw.pages.dev` |
| Staging API / bundled admin | `8050e9ce-727b-41f4-b04a-b04213c8f1df` |
| Staging existing worker | `25e14829-ecbd-4c1c-b805-8c6e6f08a387` |
| Staging H5 | Served release marker is the same `ad329d1` commit |

Railway auto-deployments and the production H5 build use this reviewed merge
commit. The unchanged signed-region Workers retain their prior versions.
`verify-production.sh` passed the **closed** observable contract on the production
custom domains; runtime checks found all four opening flags still false, old
submission lock/count **1/1**, and no database/reconciliation errors in sampled
logs. Do not publish the locally generated dummy-key/API browser-test build.

At this PR #19 checkpoint, the owner reported real iPhone/Safari **playback and
saving passed**, but physical offline/online recovery was still unreported. The
later PR #20 section records the owner's successful report for all four checks.
The browser MP4 download and system
save/share retrieve the same authenticated MP4: the latter uses supported file
sharing and otherwise falls back to browser download. Both wait for the file to
download first. One Mac-route sample measured production HTML at 1.42s and the
catalog API at 2.08s; this is not a phone measurement or an overseas comparison,
and does not prove mainland routing is the cause of slow loading.

### One Sandbox browser-capture interruption recovered

The owner authorized one virtual USD 5.99 payment and temporarily enabling the
existing US virtual buyer's Payment Review setting. The existing order
`d738ab18-932a-406c-800c-c366059395e7` / PayPal `7P10083839205330T` was reused.
Chrome blocked **only** its browser capture POST (`blocked:devtools`, one affected
request). At 12:05:23 UTC the order was APPROVED, with no capture or credit and
balance **566**. Normal verified callbacks/existing-worker reconciliation issued
exactly one capture `5A068862TA1628948`, completing at 12:06:22 UTC, and exactly
one **+100** ledger entry. H5 reached **666**, including after page reload;
generation task count stayed **4**. The temporary rule was removed, Keep log
restored off, No throttling retained and DevTools closed. No Live payment,
refund, manual financial database update or paid prediction was involved.
`sandbox-blocked-capture-recovery-evidence.json` records the scoped result.

Although Payment Review was enabled and reload-verified beforehand, PayPal
returned **COMPLETED**, not an actual PENDING capture. That gate remains open;
do not relabel the APPROVED period as PENDING. This test proves a blocked browser
capture-request recovery, not loss of a server capture response after provider
completion. On **2026-10-14**, the owner reauthenticated with the real merchant.
The same virtual buyer remained **Verified**. Payment Review was set off and its
persisted off state was confirmed after a full page reload. The owner's failed
virtual-buyer login was on the real `www.paypal.com` sign-in page, not Sandbox;
it did not establish test-account expiry. No account was regenerated and no
password, Live configuration or payment was changed during this cleanup.

### Wallet SDK lifecycle implementation checkpoint (before PR #20 release)

Real staging Chrome accumulated over 1,400 PayPal container nodes and reported
about 804 MB tab memory after repeated wallet polling. Source inspection found
each wallet redraw created a new SDK instance/payment session without releasing
the previous session. This is a concrete lifecycle defect, not proof that it
caused all reported phone latency. The follow-up caches SDK initialization for
the same public client/environment, preserves a same-identity/package checkout
during balance/order redraws, and calls session `destroy()` when changing
package, leaving, freezing or invalidating the wallet. It guards late async
mounts and retries failed initialization without retrying a payment. This uses
the [PayPal v6 session lifecycle API](https://github.com/paypal/paypal-js/blob/main/packages/paypal-js/types/v6/components/base-component.d.ts).
Six new lifecycle cases passed on both engines. Full local acceptance passed
**82 Chromium/WebKit cases**, 40 H5 contracts, a mock-config build and targeted
pre-commit checks. These regressions are isolated mocks, not an additional Sandbox
payment. At this checkpoint the follow-up still required review/CI and separate
deployment authorization; the subsequently authorized PR #20 release is above.
On **2026-10-14**, the owner authorized pushing only
`codex/paypal-wallet-lifecycle` and creating its review PR after excluding that
exact branch from automatic public previews. The staging Pages exclusion list
was verified as `codex/paypal-public-registration` plus
`codex/paypal-wallet-lifecycle`; other source settings, build configuration,
`main` production branch and the `*` preview inclusion were preserved. Production
H5 remains a direct-upload project. That branch-push authorization did not permit merging,
deploying, paying or enabling public commerce. No unrelated draft was applied.
An additional Mac-route compressed transfer sample measured the public Clerk
auth bundle at **1,199,802 transferred bytes / 4.89s**, versus the app bundle at
15,903 bytes / 0.98s. This identifies an initial-load cost worth profiling; it
does not measure physical-phone bandwidth, CPU parse time or overseas performance.

The owner still has no eligible independent overseas Live buyer. Do not manufacture
an overseas account, misstate residence, bypass region checks, or use merchant
self-payment. Recruit the first real overseas customer for an explicitly disclosed,
restricted first-order acceptance instead of requiring the owner to own a foreign
PayPal account. This does **not** waive the genuine receipt/unique credit/debit/
delivery gate or authorize general paid opening. A buyer may see card guest
checkout without a PayPal account, but availability is determined by PayPal's
region/risk decisions and is not guaranteed; see
[PayPal's guest-checkout explanation](https://www.paypal.com/c2/cshelp/article/how-do-i-accept-cards-with-checkout-using-the-guest-checkout-option--help307?locale.x=en_C2).

A failing regression identified a specific recovery gap: a scheduled signed
playback-address GET failure displayed a toast but scheduled no subsequent query
after terminal-task polling had stopped. The follow-up retries **only authenticated
GETs**, using 2/4/8-second backoff capped at 30 seconds, guards the current identity,
task and polling version, ignores invalid expiry timestamps, and re-arms player-
error recovery only after successful media loading. It never resubmits generation
or payment. Four new mocked cases cover transient address refresh, re-arming,
leaving the page and canceled system sharing. Local acceptance passed **70 tests
across Chromium/WebKit**, 40 H5 contracts, and targeted pre-commit checks. These
are browser-engine/synthetic tests, not physical iPhone save certification. The
fix's reviewed PR #19 and closed deployment are recorded above; the earlier base
checkpoint below remains historical `9afed5b` evidence.

The first follow-up CI run `38383181453` passed 64/70 checks but stalled on six
Linux WebKit cases (click stability and query/timer progress), unlike the full
macOS local pass. Its traces are preserved as GitHub artifacts and in
`/tmp/vireal-pr19-browser.30S4yc`; a specific compositor root cause is **not**
claimed. CI now runs every Chromium case on Ubuntu and every WebKit case on macOS,
without forced clicks, skips, extra retries or disabled animations. This follows
[Playwright's platform guidance](https://playwright.dev/docs/browsers#webkit)
for the closest Safari/media experience, not a claim that Linux WebKit was fixed.
The original stable `test-h5` check fails unless both host jobs succeed. Physical
iPhone acceptance remains necessary even after that cross-platform CI passes.

Real signed-in staging Chrome was put into DevTools **Offline**: five task GETs
failed with `net::ERR_INTERNET_DISCONNECTED`, and H5 displayed interrupted-status
retry without another generation. Restoring **No throttling** cleared the warning,
restored completed state and real 5-second player playback, with balance **566**.
DevTools was closed and normal network restored. This is actual staged transport
failure, not a physical phone radio-network test or proof of the new fix online.
`browser-network-recovery-evidence.json` records the scoped desktop result. The
earlier phone report covered playback/saving but not offline recovery or separate
save entries. The dated PR #20 section records the subsequent physical-device
report covering playback, both save entries and offline recovery.

At 10:22:05 UTC, an official Sandbox
[negative-testing header](https://developer.paypal.com/negative-testing/request-headers/)
returned `INTERNAL_SERVER_ERROR` / HTTP 500 for one scoped request on the existing
unapproved/canceled-window order `d738ab18-932a-406c-800c-c366059395e7`.
The actual payment client mapped it to 502. Merchant, local order, USD 5.99 and
unapproved-state guards were verified before the request. No buyer approved it,
no capture/credit occurred, and the financial snapshot remained unchanged at
566 coins. `paypal-official-negative-evidence.json` records it. This does **not**
certify an actual pending capture or browser loss of an approved payment response;
actual pending capture remains separate. The subsequently approved browser-
capture interruption test is recorded above and is not a server-response-loss
test. No Live request or additional paid prediction was sent.

## Closed selected release checkpoint — 2026-10-13

PR [#17](https://github.com/houdzaiw/vireal/pull/17) passed review/CI and merged at
08:01:59 UTC. Published source is `main` commit
`9afed5b700652f0d1c62bbafced3b636cfa870c9`; the clean local tree was synchronized
to that commit before every build/deployment. Main CI passed: **396 backend tests,
91% coverage**, H5, admin task UI, Playwright and Smokeshow. Local checks additionally
passed 40 H5 contract, 31 mocked Chromium H5 and 3 edge tests, pre-commit and H5 build.

| Target | Successful deployment/version |
| --- | --- |
| Production API / bundled admin | `6ca4f91d-a16c-42fa-89e4-10e044a3ba6a` |
| Production existing video/payment worker | `1ca20296-fb9c-45d3-bfae-71fcac725088` |
| Production signed-region Worker | `a8763b6d-2d36-407a-830e-d3a5460e2910` |
| Production H5 Pages | `cf62b703.vireal-h5-houdzaiw.pages.dev` |
| Staging API / bundled admin | `53249ad6-aae1-4fce-8198-353609958a0b` |
| Staging existing video/payment worker | `ad8c13c8-2f2a-458b-8f10-eaf0f549bf39` |
| Staging signed-region Worker | `4262b51f-2fb6-4a2d-92d0-a48ec290a2b8` |
| Staging H5 Pages | `17039902.vireal-h5-staging.pages.dev` |

Use custom domains for authenticated acceptance, not the Pages preview URLs.
Staging Railway sources and the staging H5 production branch now use `main`;
the existing feature-branch preview exclusion remains unchanged. No new service
or unrelated configuration draft was applied.

The first production API rollout failed before migration with PostgreSQL
`InvalidSchemaName` / no schema selected. Its predecessor remained serving.
The pooled Neon URL was replaced **only on the production API and worker** with
the same database's SSL direct URL, consistent with the existing initial-release
runbook. Read-only checks matched all 25 tables between endpoints and verified
SQLAlchemy's schema across transactions before this change. The exact source
commit was redeployed; do not use `PGOPTIONS search_path` with the pooled endpoint,
which rejected that startup option. This evidence supports the successful repair,
not a proven root-cause diagnosis of the pooler's session state.

Production and staging are at `b4c5d6e7f8a9`. Production post-migration verification
matched every pre-existing row/column in all 24 non-version tables. The fresh dump,
restore verification, migration rehearsal, direct-connection comparison,
deployed-migration verification and runtime evidence are in
`/Users/huili/Documents/vireal-backups/` with 0600 permissions. Both temporary
local restore servers were stopped; production was never used as the test DB.

`verify-production.sh` passed against `app.usevireal.com` / `api.usevireal.com`
with the expected commit and `RELEASE_CHECK_MODE=closed`: correct H5 recovery/
download/payment code, two effects with only 5/10s, exact three USD packages,
daily 30 cap, closed registration/recharge, anonymous wallet/download denial,
blocked docs and unsigned callback rejection. Runtime configuration separately
confirmed public registration, payments, acceptance and commerce-terms approval
remain closed; signed geography is on, daily/user/concurrency caps remain
30/5/1, demo/legacy/admin public signup are off. The cumulative generation lock
is still **1**, with one counted production prediction; it was **not unlocked**.
These checks did not exercise a Live payment or new production prediction.

Real staging evidence this run, using only newly generated fictional adult imagery:

| Combination | Task | Verified state / single debit |
| --- | --- | --- |
| dance-1 / 5s | `ac12ee92-4226-4085-9c7a-e1971cb6b279` | succeeded, private result saved, 28 coins |
| dance-1 / 10s | `d633ffca-bbbc-4f55-85e8-c2698865688c` | succeeded, private result saved, 47 coins |
| romance-1 / 5s | `1aaea428-5ca6-42f4-aed3-e49689443d64` | succeeded, private result saved, 22 coins |
| romance-1 / 10s | `7b3ae163-fedd-4233-ab13-044d1f29a248` | succeeded, private result saved, 38 coins |

All four use actual `wan-video/wan-2.7-r2v`, 720p, configured v1 prompts. Dance
prompt hash is `fa16aa887182aa88c0a26375da66a561` with one reference; romance is
`c26c90ee59bf50cc176498ff8f47eff9` with two. Supplier GET corroborated durations,
completion, reference counts and prompt match. Four of the five authorized
predictions were submitted, **estimated USD 3.00** using the provider's verified
[USD 0.10/s rate](https://replicate.com/wan-video/wan-2.7-r2v#pricing), not a final
provider invoice. No blind resubmission or production prediction occurred. Each
task has exactly one debit and no generation refund; wallet 720 -> 692 -> 645 ->
623 -> 585. The fifth prediction remains reserved for production acceptance.

All four outputs were played in the real H5 browser and downloaded through the
authenticated MP4 endpoint to `/Users/huili/Downloads/vireal-<task-id>.mp4`.
Downloaded SHA-256 hashes match the independently archived private results.
Refreshing dance 10s recovered its completed state, wallet and exact retention
timestamp. Romance 10s was revisited after its old player could not load media;
manual task refresh obtained a working link and real playback reached the end
of the 10.031s container, including while the account was payment-frozen. Existing
records/works remained accessible. Actual expiry-driven automatic recovery,
physical offline/online transitions and iOS/Android system-save are **not**
certified by this desktop run; mocked recovery coverage is recorded separately.

Built-in image generation produced `dance-concept.png`, `romance-concept.png`
and `romance-male-reference.png`, with full prompts and classification in
`/Users/huili/project/new-chat/output/imagegen/vireal-launch-20261013/asset-manifest.json`.
They are original synthetic adult concepts/inputs, **not actual previews**.
The public catalogue uses actual video frames `dance-actual-poster.png` (5s
sample, 0.5s frame) and `romance-actual-poster.png` (10s sample, 8s frame), with
their corresponding unmodified real MP4 samples. Internal real-person material
was not used or published. `generation-evidence.json` records safe supplier/task/
ledger observations without private object URLs or credentials.

The four synthetic outputs were archived read-only from their exact private
staging R2 keys under `real-video-evidence/` in that asset directory. `ffprobe`
confirmed 720x1280 H.264 video streams of exactly 5.000 / 10.000 seconds; AAC
padding makes the MP4 containers 5.038 / 10.031 seconds. All fully decoded with
FFmpeg. Sampled-frame QA confirms single-adult dance and romantic close-ups,
turns and approach; the romance clips do not substantiate the old rain promise.
`video-verification.json` records hashes and actual website expiry timestamps.
Local archives do not change private user works' 24-hour retention or grant
public bucket access. The separately uploaded managed catalogue samples are
intentionally public marketing media, not exposure of user works.

Actual production and staging admin sessions saved both covers, previews and
accurate bilingual descriptions. Dance is `Solo Dance` / 节拍律动; romance is
`Gentle Approach` / 温柔靠近, without guaranteed rain, gestures or exact identity.
Models, prices, durations and prompts were not modified. Production exposes only
these two effects, 5/10s; staging retains its 18 historical test effects under its
existing controlled Clerk email allowlist, not a public registration rollout.
`catalog-media-evidence.json` confirms each of eight managed media routes returns
206 with PNG/MP4 content, and all four production opening flags remain false.
Production browser QA confirmed the sample card, matching description and 5/10s
options. `production-immutability-evidence.json` checks finance, tasks, variants,
configs and uploads against the post-migration baseline; catalogue/media/audit
changes are intentional and separately recorded.

Real Sandbox cancel/window-close/refresh passed after action-time Sandbox terms
approval. The popup used `sandbox.paypal.com`; it was closed before payment.
Order `d738ab18-932a-406c-800c-c366059395e7` remains created/unpaid, with no capture,
fulfilment or recharge ledger credit. Reload preserved the 585-coin balance and
showed waiting for payment, not a false success.

An official **Sandbox-only virtual USD 1.00 partial refund** of the existing
220-coin USD 11.99 order `e24f5606-8344-4b0b-ad59-acf021228b19` completed as
`8U746287CW894423W`. Verified refund webhook
`WH-74537774K6344772U-05732634BH657203C` froze the account. The actual H5 disabled
new recharge while retaining records and working existing playback. Its refund
case required ceil(220 * 100 / 1199) = **19 coins**. A real authenticated staging
administrator supplied evidence/reason and completed audited recovery at
09:38:42 UTC: one `recharge_recovery` debit of 19, original recharge credit still
unique, correlated review resolved with zero additional recovery, wallet
**585 -> 566**, payment hold cleared. Real H5 refresh showed 566 and restored
the recharge options. `sandbox-partial-refund.json`,
`sandbox-acceptance-evidence.json` and `browser-acceptance-evidence.json` preserve
scoped evidence. No Live refund, manual wallet override or duplicate debit occurred.

**Still outstanding:** actual PayPal pending capture and transport-failure
recovery are not certified by mocked tests. Dispute/reversal and insufficient-
balance cases have isolated automated coverage, not manufactured Live events.
Live remains blocked by the owner's confirmed lack of an eligible independent
overseas buyer: USD 5.99 genuine payment, unique 100-coin receipt, the reserved
production 5s generation/debit/playback/download, final public terms approval
and separately authorized public opening remain gates;
**this successful closed deployment is not readiness to promote publicly**.

## Previous release checkpoint (historical)

Implementation was on `codex/paypal-public-registration`. As of **2026-10-12**,
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

### Follow-up remediation and review, 2026-10-13

Owner explicitly chose **finish remediation/review only; do not merge or deploy**.
PR #17 remains the feature delivery location. No production database, cloud
configuration, real payment/refund or new prediction is changed by this follow-up.

- Review found that `/app/media-assets/{id}` could issue new signed URLs for any
  active admin upload, even when its effect was hidden or still a draft. It now
  requires attachment to a published/enabled effect in an enabled category, at
  least one enabled duration within the release limit, and membership in the
  production launch selection. Soft-deleted media is excluded. Admin uploads still
  return their authorized preview URLs; only public access is restricted. Redirects
  are `private, no-store`; already-issued R2 URLs expire under their existing TTL,
  not instantly. This is not proof of display/portrait authorization.
- H5 builds embed `vireal-release-commit`, derived from the Git checkout or an
  explicit 40-character `VIREAL_RELEASE_COMMIT`. This is a source marker, not a
  cryptographic build attestation. Build only from a clean reviewed commit for a
  later deployment, and independently match Railway API/worker and Worker versions.
- `scripts/verify-production.sh` now requires the reviewed commit and checks the
  PayPal/task-recovery/download frontend, exactly the two 5/10s effects, approved
  USD packages/site capacity, protected wallet/download and the malformed-input
  rejection at the PayPal receiver. It no longer POSTs a valid device-login request
  that could create a business account on a misconfigured old backend. A production
  read-only run on this date correctly stopped at the missing release-commit marker;
  the existing online H5 is not the new candidate. No rollout was performed.
- Verification has **closed** (default) and **public** observation modes. Closed
  mode tolerates not-yet-supplied cover/preview URLs. Public mode requires both
  managed media references, a genuinely eligible edge country, open registration/
  recharge and remaining capacity. A CN/unknown response cannot certify worldwide
  closure; confirm the global Railway/Clerk switches separately. Neither mode
  certifies merchant readiness, rights, cash receipt, generation or mobile saving.
  JSON diagnostics never echo payloads, private fields or tokens.
- Local full regression: **396 backend tests passed; 91% application coverage**,
  including 18 new poster/preview visibility cases. Testing used a fresh disposable
  local PostgreSQL cluster with no repository `.env` or production backup. **39 H5
  contract, 31 mocked Chromium browser and 3 edge checks passed**; H5 build and
  ruff/mypy/ty passed. CI evidence for this follow-up must be recorded in the PR's latest checks,
  not inferred from the previous revision's green CI.
- CI report review reproduced `Z_BUF_ERROR` in the download action's streaming
  inflater for one digest-valid outer ZIP, even when downloaded serially; the
  GitHub CLI extracted all four report blobs successfully. Local reconstruction
  with stored outer ZIPs passed the same parser for every shard. Playwright blob
  uploads now use `compression-level: 0` (the blobs are already ZIP-compressed),
  with missing reports and digest mismatches remaining fatal. The aggregate
  green check also requires HTML report merge/upload success. This is a report
  packaging fix, not a skipped test or a relaxed integrity check; fresh CI is
  still required on the updated head.

After an independently approved closed deployment, run from its reviewed checkout:

```bash
H5_URL=https://app.usevireal.com \
API_URL=https://api.usevireal.com \
EXPECTED_RELEASE_COMMIT="$(git rev-parse HEAD)" \
RELEASE_CHECK_MODE=closed \
bash scripts/verify-production.sh
```

Use `public` mode only after separately authorized opening, from a genuine eligible
region; do not spoof geography or pass a fabricated signing header. The check does
not toggle any feature. Its success is observable technical evidence, never the
approval to open commerce or promote the product.

Promotion preparation remains **draft/not published**. Prepare brand accounts and
use “Vireal is preparing a small public beta. Follow for launch updates” for textual
prelaunch updates; do not claim current payment availability or free generation.
Once the later release/rights/Live gates pass, prepare three authorized demonstrations
(dance, romance, full mobile workflow) for Instagram Reels/YouTube Shorts. Clearly
label realistic AI output, verify music and portrait/social-advertising rights, and
show 5/10s duration, credits from $5.99, limits and 24-hour result retention. First
72 hours use organic posts only, target roughly 3–5 generating users/day within
actual remaining site capacity, keep the same public registration policy, and
record paid/credited/generated/downloaded outcomes without publishing user media.
No account creation, social posting, advertising purchase, attribution collection
or future monitor is authorized or implemented by this preparation note.

### Remaining gates and evidence ledger

1. **Public material: completed for the two selected effects.** Original synthetic
   adult inputs, true model output previews and matching actual-frame covers are
   installed through real admin sessions in staging and closed production. Titles,
   descriptions, prompt/model evidence and eight managed media routes were
   verified. Old internal real-person inputs/results remain unpublished.
2. **Reviewed source: PR #20 closed wallet-lifecycle release completed.**
   The latest reviewed closed deployment is `a1c42cb`; historical version tables
   and fresh database restore evidence are retained above. Real SDK component
   counts stayed stable across refresh/package/navigation checks. Railway/staging
   Pages follow `main`. Preserve CI and exact preview exclusions; exclude any
   newly named branch with scoped authorization before pushing. Do not publish
   previews, apply unrelated drafts or infer permission for another deployment.
   The additional startup/failure-state correction is local on
   `codex/h5-public-first-load`: local checks pass and PR #21 is open; validate its
   current head's CI/review before separately authorizing merge and closed rollout.
3. **Sandbox exceptions: partial.** Three packages, full refund, actual window
   cancellation/refresh, partial refund/freeze/audited 19-coin recovery and official
   500 client handling and approved-payment browser-capture request interruption
   with unique 100-coin recovery have dated evidence. October 14 additionally
   verified real PENDING capture/no premature credit/H5 reload and real-provider
   capture-response-loss recovery in an isolated same-source local ledger, with
   concurrent confirmations producing one credit. Provider release of the pending
   payment and its PENDING-to-paid unique credit remain open. Preserve the scoped
   distinction from on-Railway faults; mock coverage alone is not the evidence.
   Dispute/reversal/insufficient balance remain isolated tests; never manufacture
   a Live dispute or chargeback.
4. **Four effect-duration combinations: completed.** Dance/romance each 5/10s
   have genuine Wan 2.7 task/prompt/input-count evidence, one debit each, saved
   private outputs, real authenticated downloads with matching hashes, and decoded
   MP4 validation. Four authorized predictions are consumed (estimated USD 3),
   with only the production 5s prediction reserved inside the total USD 10 cap.
5. **Real phone delivery: all four iPhone/Safari checks passed by owner report.**
   On October 14 after the closed PR #20 rollout, the owner explicitly confirmed
   playback, Download MP4, system save/share and physical offline/online recovery.
   This closes those owner-assisted delivery checks, not actual-expiry recovery,
   Android certification or a latency benchmark. Existing staging outputs retain
   their recorded October 14 expiry times; no extension or new generation was
   performed. The owner now reports iPhone 16 Pro / iOS 26.5 and approximately
   2s Wi-Fi / 3s cellular to a usable staging catalog, a pre-fix estimate rather
   than a root-cause diagnosis. Natural expiry checks remain open at the precise
   deadlines above; instrumented device/network measurements remain separate;
   the reviewed wallet lifecycle fix's real SDK component counts are verified,
   not phone startup latency. Public and controlled Live gates remain closed.
6. **Public notices/support confirmed; controlled Live acceptance: pending.**
   On October 14 the owner approved the current public notices for a small public
   trial and reported successful external support-email receipt. Runtime terms
   approval and public opening still require their separately authorized stage;
   no gate was changed by recording consent. No eligible independent overseas buyer
   is available. Recruit a genuine first customer for restricted acceptance, verify
   USD 5.99 receipt, unique 100 coins, one production 5s debit/play/save, then decide
   public opening. `REPLICATE_POC_MAX_SUBMISSIONS=1` and all production opening
   flags remain unchanged. Removing the cumulative test lock happens only at the
   authorized production acceptance stage, not to bypass the missing buyer.

### Next actionable acceptance gates

| Gate | Current state | Next action / owner |
| --- | --- | --- |
| Sandbox review recovery | PENDING/no early credit/reload passed; final release-to-credit pending | Existing hourly read-only heartbeat waits for real PayPal completion and exactly one +100 credit; no third virtual payment. |
| Natural 24h expiry | Clock/config/fixture checks passed; actual cleanup and expired-phone view pending | Owner checks the first work after 16:10 Beijing; agent subsequently inspects cleanup and no new URL/false refund, read-only. No new generation. |
| H5 correction release | Local checks passed, PR #21 open, not deployed | Validate PR #21's exact current-head review/green CI first, then request separate merge/closed-deployment approval and fresh backup verification. |
| Public notices and support | Owner approved unchanged public-trial notices and verified external email receipt on October 14 | Keep the runtime terms flag off until the separately authorized acceptance/opening stage. Preserve the manual-support schedule and PayPal profile-contact follow-up; email receipt is not proof of 24/7 support or legal clearance. Renew review if copy/rules change. |
| Restricted real Live journey | No eligible independent overseas buyer; not passed | Owner recruits a real non-mainland buyer and confirms actual country/independence/email; agent verifies the exact Clerk subject and prepares only the approved restricted flow. Buyer manually pays $5.99; verify merchant receipt and one +100 credit, then action-time-authorized 5s generation, one debit and play/save. Preserve the five-prediction/$10 model cap; four are consumed. |
| Public opening / first 72h | Not authorized | After all gates, request explicit opening approval; open H5 registration/recharge together, never admin signup. Owner checks 09:00/15:00/21:00 Beijing and preserves callbacks/ledger during pauses. |

Completed public materials, four real combinations and normal iPhone delivery do
not need new paid tests. Full alert/notification acceptance, Android real-device
certification, instrumented overseas cold/warm timing and hashed-asset caching are
**before expansion** quality/operations work. The Sandbox heartbeat does not
monitor production. Eighteen public effects, 15s, extra models and automatic cash
refunds remain deferred.

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
