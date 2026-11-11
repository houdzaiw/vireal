# Managed PostgreSQL security acceptance

This document describes acceptance requirements. It does not certify a deployed
account or authorize a connection, permission change, migration or release.
Account observations and operational receipts are retained separately by the owner.

## Distinct trust boundaries

A managed PostgreSQL proxy may terminate client TLS. PostgreSQL backend statistics
then observe the proxy-to-compute connection, rather than the external client
session. Retain these as separate evidence fields; never infer complete protection
from a URL template, a successful query or a backend statistic alone.

External connections require certificate and hostname verification, required SCRAM
channel binding and TLS 1.2 or later. Verify the complete effective libpq parameters,
actual negotiated protocol, expected database and role, read-only transaction,
rollback and connection close from the same connection. Do not fall back to weaker
verification when a check fails. Exclude service/environment overrides and require
an explicitly reviewed trust store and connection timeouts.

Independently establish confidentiality, integrity and authenticated workload access
on the provider's internal path. Public implementation support for optional TLS is
not evidence that a particular managed deployment enables it. Unsupported fields
and missing provider confirmation remain unverified.

Use separate runtime and backup identities without administrative flags, role
memberships or object ownership. Review explicit object/column grants, migration
ownership, all consumers and safe credential handoff before any live change.
Runtime startup must check the reviewed schema and permissions without migrating
or initializing business data.

## Driver and backup compatibility

The compatibility helper prefers a supported driver protocol accessor. For a
qualified psycopg-binary layout, it can read the actual connection protocol from
that package's own libpq, checking the package, library version and PGconn pointer
type. Unknown platforms/layouts stop. A different system libpq must not be guessed.

Local real PostgreSQL tests cover correct TLS/binding and rejection of wrong
hostname, unknown CA, wrong credentials, expired certificate, old TLS, plaintext
and unavailable channel binding. Local success does not qualify every deployed
platform, consumer, existing connection or backup client.

The historical backup backend-TLS condition and sealed acceptance engine are not
bypassed by this architecture review. Any changed tool/profile requires new pins,
reviewed scope and independent capture/restore qualification. Do not treat a driver
mock or a restore diagnostic as live backup acceptance.

## Separate release gates

Client path, provider internal path, identity/least privilege and operational
coverage require independent evidence. Budget, bounded capacity, fresh encrypted
backup, independent retrieval/restore, alert delivery and paid delivery are
additional gates. A passing local suite never enables commerce or publishing.

References:

- https://neon.com/docs/connect/connect-securely
- https://neon.com/docs/security/security-overview
- https://www.postgresql.org/docs/18/libpq-connect.html
- https://www.postgresql.org/docs/18/monitoring-stats.html#MONITORING-PG-STAT-SSL-VIEW
