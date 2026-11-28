# Pilot cost-bound arithmetic

`tools/ci/pilot_cost_bound.py` performs offline Standard R2 and pilot budget
arithmetic. It does not query accounts, authenticate evidence, deploy limits or
open commerce. Current bills, account identifiers and operational observations
belong in the owner's separate private acceptance records.

## Account and period scope

Aggregate every bucket, environment and other account consumer before applying
free allowances and billing-unit rounding. Storage GB-month inputs must cover
daily peaks, initial objects, unfinished multipart uploads and retained outputs.
Use actual billing periods; a window can cross a renewal boundary.

The Standard calculation uses included monthly storage/Class A/Class B usage and
upward rounding. Compute business and closing costs as differences of cumulative
cycle costs, rather than rounding each bucket or phase independently. Infrequent
Access, additional bucket fees, Basin and migration products require separate
bounds; they are not silently covered by this Standard-only calculator.

Authenticated failed operations may be billable. Failed or unknown submissions
retain their reservations. Direct R2 egress pricing does not cover other metered
proxy, worker, hosting or network services.

## Budget and future liabilities

Each required service needs a verified business/closing upper bound and evidence.
Missing values are unknown, not zero. Include the next order's reservation before
admission, and include unsettled payments, unknown submissions, delivery, media
retention/cleanup and reporting delay. Avoid double counting only where the
invoice/reservation overlap is demonstrated; do not credit predicted revenue.

Non-expiring paid balances create future redemption and continuing-service
liabilities. A finite time window or prepaid hosting term alone does not establish
an unlimited-time funding bound. Preserve existing balances and accepted orders;
do not certify the budget by making balances expire or hard-stopping fulfillment.

Passing arithmetic never authorizes promotion. Runtime counters, all consumers,
security, capacity, fresh backup/restore, real payment/generation/alerts, fixed
release candidate and owner release acceptance remain separate requirements.

Run the synthetic cost regression suite from the repository root:

```sh
python3 -m unittest discover -s tools/ci -p test_pilot_cost_bound.py -v
```

Public rate/rounding reference: https://developers.cloudflare.com/r2/pricing/ .
Re-read the applicable account price and period before establishing a live bound.
