# Owner-operated local tools

These are local preparation, not authorization to run against a provider. There is no live grant in this directory. Invoking either CLI without its fresh grant exits before input or network I/O. Never rerun a consumed attempt. Do not put credentials into arguments, files, screenshots or chat.

## Operating backup

`backup_once.py` reuses the pinned R3 engine, sealed crypto, strict target parser, hardened terminal reader and bounded child-process runner in the existing owner workspace. The R3 files/receipts are never edited or consumed. These owner tools deliberately depend on `/Users/huili/project/new-chat/output`; they are not Railway or CI deployment executors.

Each separately authorized run needs a new twelve-hex run ID, an at-most-30-minute grant, exact tool/profile SHA-256, current deployment metadata review and one profile: production-26 (`6d3804e2`, `c5d6e7f8a9b0`) or candidate-30 (accepted base `cb40c1c`, `d6e7f8a9b0c1`, plus exact new local source-file hashes). Future post-migration grants must bind the eventual CI-approved commit; `cb40c1c` is an ancestry marker, not a claim that the uncommitted local changes have shipped.

Opening sequence 0 runs once immediately. Later sequence N is due at the actual opening snapshot + N×45 minutes; input opens four minutes early and the snapshot must occur less than two minutes late. Grants pin the prior receipt bytes and matching profile/sequence; upload confirmation must arrive before the actual previous snapshot reaches 60 minutes. Validity is snapshot+60 minutes, never upload+60 minutes. A fresh opening backup is required after changing profiles. Closing and pre-maintenance backups use independently authorized opening-style runs; they do not reset the existing business budget or operating evidence.

Only two source connections are permitted: strict TLS/READ ONLY snapshot and matching pg_dump. Client TLS must be verified with channel binding and minimum TLS1.2; the backend must independently report ssl=true and TLS1.2/1.3. The current unresolved Neon result remains a blocker. Pending orders/tasks are counted, not required to be zero. Tables/extensions/full schema and encrypted row fingerprints must match the chosen profile, with no dynamic acceptance of arbitrary tables. The 30-table profile recognizes only the frozen uq_budget_current partial-unique-index definition; changed or additional partial indexes are rejected. A transaction-consistent export is encrypted in memory, decoded in memory for verification, then only ciphertext and sanitized manifest go to the approved iCloud directory. Local directories are 0700 and files 0600, with at least 14-day retention, no deletion, no upload of plaintext. Source password is passed only in the single pg_dump child's memory environment. Source/schema/hash/disk/CA/TLS/window/cloud errors stop without retry.

A receipt is preparation/evidence for a future authorized operator update, not an API call that activates business or refreshes other facts. Preserve the original expiry of staff, sender, worker and cost evidence. Operator checks remain every10 minutes while staffed09:00–23:00 Beijing; backup every45 minutes does not substitute for presence. No restore is run by this CLI and no new full-service recovery time objective claim is made.

## One test email

`test_email_once.py` is fixed to ops@alerts.usevireal.com → li522903183@gmail.com, one recipient, fixed nontransactional subject/body and one POST to the official Resend endpoint. Fresh authorization must record current whole-team remaining daily/monthly allowance and sending-only domain restriction. The owner enters only that key in the hidden terminal. The claim is durable before input/I/O; timeout, crash or uncertain result never causes a resend. Provider acceptance is not human receipt; a separate owner receipt confirmation is required. Neither tool is authorized by these docs to execute now.


## Prepared resource-accounting profile

The local `candidate-33` mode adds exactly `app_resource_policy`,
`app_resource_attempt`, and `app_media_read_grant` to the 30-table profile and
pins migration head `e7f8a9b0c1d2`, ancestry marker `d0728f3`, plus exact source
file hashes and the new tool hash. It is not a live grant or deployed commit.
The sealed engine and old 26/30 profiles remain unchanged. Unknown tables,
changed partial indexes, more than 50,000 rows per table, 100,000 total row
fingerprints or a 4 MiB manifest still stop. The ledger allocation must fit the
remaining record budget across all retained scopes. Full 33-table encrypted
backup/restore and deployment-platform validation remain pending. Do not remove
the unresolved backend security gate to make this profile run on Neon.


## Prepared exact candidate restore repair

`restore_candidate_checks.py` is a pure plan builder, not an operating CLI. It
opens no connections and has no grant or acceptance override. It is restricted
to candidate-33 / e7f8a9b0c1d2, the exact 33-table inventory, four fixed CHECK
identities/definitions and column types. All row fingerprints, extensions,
locale and other schema categories must match before it returns eight fixed
statements. No statement is taken from manifest SQL. Other profiles reject.

The proposed operator procedure is only for an isolated restored copy: verify
the authenticated archive and catalog first; if the raw manifests already match,
repair nothing. For the exact recognized rendering difference, apply all eight
statements in one transaction, with immediate CHECK validation, then recapture
and require **raw full-manifest equality**, including after commit. Any failure
rolls back; no NOT VALID, disabled triggers, cast normalization or new equality
exception is permitted. This is not connected to the sealed live executor.

The synthetic 33-table PostgreSQL 18 drill passed exact equality after repair,
post-commit equality, interrupted-repair rollback and invalid-state rejection.
The pure owner-tool suite has 20 passing tests. Production source permissions,
Neon complete-path security, independent cloud retrieval and operating RTO are
still unaccepted. A future operator grant must pin this new helper's SHA as well
as the selected schema, source, tool and process plan before any real use.
