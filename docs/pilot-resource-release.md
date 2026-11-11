# Bounded pilot resources: implementation and release requirements

This is an implementation candidate, not promotion approval. Current account
configuration, bills, security findings and acceptance receipts are retained in
separate owner-controlled review materials. No allocation is activated by migration.

## Durable limits

The candidate adds `app_resource_policy`, `app_resource_attempt` and
`app_media_read_grant`. Before an external resource operation, an independent
transaction locks the allocation row, checks all relevant counters and durably
reserves the attempt. Caller rollback, restart, failure and unknown outcomes do
not release possibly consumed costs. A repeated business key reuses its task.

Upload count/bytes, conservative stored bytes, generation count/model/duration,
Class A writes and Class B reads are bounded explicitly. User reads/link issuance
and delivery operations have separate finite allowances; exhausting user replay
allowance must not consume delivery reserve. New admissions and old-order
fulfillment remain separate. Missing, expired or insufficient delivery coverage
is a failure to be reviewed, not a guarantee of fulfillment under all faults.

Generated video writes use one bounded PUT and one SDK attempt. Each explicit
Worker retry consumes another allowance. Stored bytes cover initial data plus
cumulative writes, including overwrites/retries; logical deletion or intended
cleanup does not reduce the bound. No scope replacement or counter reset may
bypass outstanding tokens, tasks, uncertain requests or billing obligations.

## Counted media access

Managed links use `GET /api/v1/app/media/read?token=...`. Short-lived tokens contain
an unpredictable grant ID, purpose/audience and expiry; the object identity and
delivery class stay in the database. Each read rechecks availability and allowance.
Single Range reads are counted; malformed or multiple ranges are rejected. HEAD
does not issue an R2 request. Link parameters cannot upgrade user allowances.

Protected generation requires managed input, avoiding an arbitrary absolute URL
bypass. The new entry point cannot revoke existing direct signed URLs: prove their
expiry or revocation before activation. Token redaction applies to application
logs and telemetry; independently verify upstream hosted logs and other consumers.

## Database and backup preparation

Each process uses finite pool settings: `DATABASE_POOL_SIZE` (default 5),
`DATABASE_POOL_MAX_OVERFLOW` (default 0), and
`DATABASE_POOL_TIMEOUT_SECONDS` (default 10). Zero-sized/unlimited pools and
nonfinite waiting are rejected. Pool exhaustion times out; it does not replay an
in-flight transaction. Include every process, deployment overlap, management and
backup connection in capacity planning. Source defaults do not prove live limits.

The fixed 33-table backup candidate is distinct from historical smaller profiles.
A pure repair-plan helper generates eight fixed statements for four reviewed CHECK
definition round-trip differences in an isolated restored copy. Immediately demand
full original-manifest equality, validate constraints and verify persisted state.
Unknown schemas/differences stop; do not disable constraints, weaken acceptance
or execute arbitrary archive-provided repair SQL. Live capture, independent
retrieval, privileges, platform security and restore time remain separate gates.

## Release and rollback requirements

1. Fix a candidate commit and reviewed source hashes; verify all automatic build
   and deployment paths and CI allowance before any remote write.
2. Establish provider security, identity/grants, fresh encrypted backup and
   independent restore, actual capacity and complete account-wide cost bounds.
3. Review exact migration/configuration/commands, fees, old-task fulfillment and
   a compatible rollback. Separate migration credentials from runtime credentials.
4. Validate synthetic limits/faults first, then a specifically bounded staged
   exercise. Real payment/generation/messages, resource changes and production
   release require their explicit owner handoffs.
5. Re-read effective deployment, bills/quotas and evidence before final opening.

Retain new tables, reservations and balances on rollback. An old binary that
ignores new limits or uses broad credentials is not an accepted business rollback.
Free-tier or low idle usage does not establish sustained load or complete closing
capacity. Media retention and cleanup polling intervals are not completion bounds.
