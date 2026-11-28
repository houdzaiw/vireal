"""Local, single-host backup admission. No provider, database or secret access.

The journal is append-only. Its separately fsynced anchor makes interrupted
appends and truncation fail closed. Reservations are never reclaimed here.
Operator evidence digests are review references, not vendor attestations.
"""

import fcntl
import hashlib
import json
import os
import re
import stat
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

MAX_CIPHER = 4 * 1024**2
MAX_SIDECAR = 4096
MAX_ATTEMPTS = 4096
MAX_JOURNAL = 32 * 1024**2
MAGIC = b"VIREAL_BACKUP_CAPACITY_1\n"
ZERO = "0" * 64
POLICY_KEYS = {
    "schema",
    "target_sha256",
    "profile_sha256",
    "host_sha256",
    "starts_at",
    "ends_at",
    "streams",
    "max_captures",
    "max_attempts_per_capture",
    "max_attempts",
    "cipher_bytes",
    "sidecar_bytes",
    "local_extra_bytes",
    "wire_bytes_per_attempt",
    "cloud_allocation_bytes",
    "local_allocation_bytes",
    "wire_allocation_bytes",
    "maximum_cu_milli",
    "closing_micros",
}
PROOFS = {
    "space",
    "other_consumers",
    "wire",
    "backend_exit",
    "closing",
    "fulfillment",
    "single_host",
}


def need(value, code):
    if not value:
        raise ValueError("CAPACITY_" + code)


def encoded(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "DUPLICATE_KEY")
            result[key] = value
        return result

    try:
        return json.loads(
            raw, object_pairs_hook=pairs, parse_constant=lambda _: need(False, "NUMBER")
        )
    except (TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("CAPACITY_JSON") from exc


def count(value, minimum=0, maximum=2**63 - 1):
    need(type(value) is int and minimum <= value <= maximum, "COUNT")
    return value


def sha(value):
    need(
        type(value) is str and re.fullmatch("[a-f0-9]{64}", value) and value != ZERO,
        "DIGEST",
    )
    return value


def instant(value):
    need(type(value) is str, "TIME")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("CAPACITY_TIME") from exc
    need(result.tzinfo is not None, "TIME")
    return result.astimezone(UTC)


def host_identity():
    # Operational single-host binding, not hardware attestation or a cloud lock.
    return hashlib.sha256(os.uname().nodename.encode()).hexdigest()


def policy_limits(policy):
    need(type(policy) is dict and policy.keys() == POLICY_KEYS, "POLICY")
    need(type(policy["schema"]) is int and policy["schema"] == 1, "VERSION")
    for key in ("target_sha256", "profile_sha256", "host_sha256"):
        sha(policy[key])
    start, end = instant(policy["starts_at"]), instant(policy["ends_at"])
    need(start < end, "HORIZON")
    streams = policy["streams"]
    need(type(streams) is list and 1 <= len(streams) <= 4, "STREAMS")
    need(
        all(type(s) is str and re.fullmatch("[a-z0-9_-]{1,32}", s) for s in streams),
        "STREAMS",
    )
    need(len(streams) == len(set(streams)), "STREAMS")
    captures = count(policy["max_captures"], 1, MAX_ATTEMPTS)
    per_capture = count(policy["max_attempts_per_capture"], 1, MAX_ATTEMPTS)
    attempts = count(policy["max_attempts"], 1, MAX_ATTEMPTS)
    need(attempts <= captures * per_capture, "ATTEMPTS")
    cloud = count(policy["cipher_bytes"], 1, MAX_CIPHER) + count(
        policy["sidecar_bytes"], 1, MAX_SIDECAR
    )
    local = 2 * cloud + count(policy["local_extra_bytes"])
    wire = count(policy["wire_bytes_per_attempt"], 1)
    for field, required in (
        ("cloud_allocation_bytes", attempts * cloud),
        ("local_allocation_bytes", attempts * local),
        ("wire_allocation_bytes", attempts * wire),
    ):
        need(count(policy[field]) >= required, "ALLOCATION")
    count(policy["maximum_cu_milli"], 1, 56000)
    count(policy["closing_micros"], 0, 30_000_000)
    return {"cloud": cloud, "local": local, "wire": wire}


def validate(policy, evidence, *, at, target_sha256, profile_sha256, host_sha256):
    """Check explicit reviewed inputs; unknown bounds are never replaced by zero."""
    policy_limits(policy)
    need(at.tzinfo is not None, "TIME")
    need(instant(policy["starts_at"]) <= at < instant(policy["ends_at"]), "HORIZON")
    for key, expected in (
        ("target_sha256", target_sha256),
        ("profile_sha256", profile_sha256),
        ("host_sha256", host_sha256),
    ):
        need(policy[key] == sha(expected), "BINDING")
    need(
        type(evidence) is dict and evidence.get("policy_sha256") == digest(policy),
        "EVIDENCE",
    )
    observed, expires = (
        instant(evidence.get("observed_at")),
        instant(evidence.get("expires_at")),
    )
    need(observed <= at < expires <= observed + timedelta(minutes=30), "STALE")
    proofs = evidence.get("proofs")
    need(type(proofs) is dict and proofs.keys() == PROOFS, "PROOFS")
    for proof in proofs.values():
        sha(proof)
    for medium in ("cloud", "local", "wire"):
        available = count(evidence.get(medium + "_available_bytes"))
        other = count(evidence.get(medium + "_other_bytes"))
        reserve = count(evidence.get(medium + "_reserve_bytes"))
        need(
            available >= other + reserve + policy[medium + "_allocation_bytes"], "SPACE"
        )
    duration = instant(policy["ends_at"]) - instant(policy["starts_at"])
    # Compare exact integer microseconds; no float or assumed scale-to-zero.
    micros = (
        duration.days * 86400 + duration.seconds
    ) * 1_000_000 + duration.microseconds
    required = (
        micros * policy["maximum_cu_milli"] + 3_600_000_000 - 1
    ) // 3_600_000_000
    available = count(evidence.get("compute_available_mcu_hours"))
    committed = count(evidence.get("compute_other_mcu_hours"))
    need(available >= required + committed, "COMPUTE")
    admission = count(evidence.get("admission_micros"))
    need(
        admission < 120_000_000 and admission + policy["closing_micros"] <= 150_000_000,
        "COST",
    )
    need(
        count(evidence.get("closing_required_micros")) <= policy["closing_micros"],
        "CLOSING",
    )
    return digest(policy)


def check_cipher(value, policy):
    need(
        type(value) is bytes and 0 < len(value) <= policy["cipher_bytes"],
        "CIPHER_LIMIT",
    )


def check_sidecar(value, policy):
    need(
        type(value) is bytes and 0 < len(value) <= policy["sidecar_bytes"],
        "SIDECAR_LIMIT",
    )


class Ledger:
    """One fixed private directory per execution host, shared by all run IDs.

    Locks are local only. Missing files, inconsistent anchors and unknown
    attempts require separate reconciliation; no automatic repair or refund.
    """

    def __init__(self, root, policy):
        policy_limits(policy)
        self.root = Path(root)
        self.policy = decode(encoded(policy))
        self.policy_sha = digest(self.policy)
        self.amounts = policy_limits(self.policy)

    def safe_fd(self, fd, directory=False):
        s = os.fstat(fd)
        need(s.st_uid == os.getuid(), "OWNER")
        need(stat.S_IMODE(s.st_mode) == (0o700 if directory else 0o600), "PERMISSIONS")
        need(
            stat.S_ISDIR(s.st_mode)
            if directory
            else stat.S_ISREG(s.st_mode) and s.st_nlink == 1,
            "FILE",
        )

    @contextmanager
    def transaction(self, initialize=False):
        need(type(initialize) is bool, "INITIALIZE")
        directory = lock = journal = None
        try:
            if initialize:
                # A second initialization is never an alternative to resuming.
                self.root.mkdir(mode=0o700)
            directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.safe_fd(directory, True)
            flags = os.O_RDWR | os.O_NOFOLLOW
            if initialize:
                flags |= os.O_CREAT | os.O_EXCL
            lock = os.open("anchor.lock", flags, 0o600, dir_fd=directory)
            self.safe_fd(lock)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if initialize:
                self.write_all(lock, MAGIC + ZERO.encode())
                os.fsync(lock)
            need(os.fstat(lock).st_size == len(MAGIC) + 64, "ANCHOR")
            anchor = os.pread(lock, len(MAGIC) + 64, 0)
            need(anchor.startswith(MAGIC), "ANCHOR")
            flags = os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW
            if initialize:
                flags |= os.O_CREAT | os.O_EXCL
            journal = os.open("journal.jsonl", flags, 0o600, dir_fd=directory)
            self.safe_fd(journal)
            if initialize:
                self.append(
                    journal,
                    lock,
                    {"kind": "header", "policy_sha256": self.policy_sha},
                    ZERO,
                )
                os.fsync(directory)
            records, last = self.read(journal)
            need(os.pread(lock, 64, len(MAGIC)).decode() == last, "ANCHOR")
            yield records, last, journal, lock
        except (OSError, UnicodeError) as exc:
            raise ValueError("CAPACITY_LEDGER_IO") from exc
        finally:
            for fd in (journal, lock, directory):
                if fd is not None:
                    os.close(fd)

    @staticmethod
    def write_all(fd, data):
        while data:
            wrote = os.write(fd, data)
            need(wrote > 0, "WRITE")
            data = data[wrote:]

    def append(self, journal, lock, event, previous):
        body = {"event": event, "previous": previous}
        row = body | {"sha256": digest(body)}
        raw = encoded(row) + b"\n"
        need(
            len(raw) <= 2048 and os.fstat(journal).st_size + len(raw) <= MAX_JOURNAL,
            "JOURNAL_LIMIT",
        )
        self.write_all(journal, raw)
        os.fsync(journal)
        need(os.pwrite(lock, row["sha256"].encode(), len(MAGIC)) == 64, "ANCHOR")
        os.fsync(lock)

    def read(self, journal):
        size = os.fstat(journal).st_size
        need(0 < size <= MAX_JOURNAL, "JOURNAL_LIMIT")
        raw = os.pread(journal, size, 0)
        need(len(raw) == size and raw.endswith(b"\n"), "JOURNAL")
        records, previous = {}, ZERO
        for index, line in enumerate(raw.splitlines()):
            need(0 < len(line) < 2048, "JOURNAL")
            row = decode(line)
            need(
                type(row) is dict and row.keys() == {"event", "previous", "sha256"},
                "JOURNAL",
            )
            need(
                row["previous"] == previous
                and row["sha256"]
                == digest({"event": row["event"], "previous": previous}),
                "CHAIN",
            )
            previous = row["sha256"]
            event = row["event"]
            need(type(event) is dict, "JOURNAL")
            if index == 0:
                need(
                    event == {"kind": "header", "policy_sha256": self.policy_sha},
                    "POLICY_CHANGED",
                )
                continue
            run_id = event.get("run_id")
            need(type(run_id) is str and re.fullmatch("[a-f0-9]{12}", run_id), "RUN_ID")
            if event.get("kind") == "reserve":
                need(run_id not in records, "REPLAY")
                self.check_capture(
                    event["capture_id"], event["stream"], event["capture_kind"]
                )
                need(
                    event.keys()
                    == {"kind", "run_id", "capture_id", "stream", "capture_kind", "at"},
                    "JOURNAL",
                )
                at = instant(event["at"])
                need(
                    instant(self.policy["starts_at"])
                    <= at
                    < instant(self.policy["ends_at"]),
                    "HORIZON",
                )
                records[run_id] = event | {"outcome": "reserved"}
            else:
                need(
                    run_id in records and records[run_id]["outcome"] == "reserved",
                    "OUTCOME",
                )
                self.check_outcome(event)
                records[run_id] = records[run_id] | {"outcome": event["outcome"]}
        need(len(records) <= self.policy["max_attempts"], "ATTEMPTS")
        return records, previous

    def check_capture(self, capture_id, stream, kind):
        need(
            type(capture_id) is str and re.fullmatch("[a-z0-9_-]{1,48}", capture_id),
            "CAPTURE_ID",
        )
        need(stream in self.policy["streams"], "STREAM")
        need(kind in {"opening", "scheduled", "closing", "maintenance"}, "KIND")

    @staticmethod
    def check_outcome(event):
        need(
            event.keys()
            == {
                "kind",
                "run_id",
                "outcome",
                "snapshot_at",
                "retain_until",
                "receipt_sha256",
            }
            and event["kind"] == "finish",
            "OUTCOME",
        )
        need(event["outcome"] in {"confirmed", "unknown"}, "OUTCOME")
        if event["outcome"] == "confirmed":
            snapshot = instant(event["snapshot_at"])
            need(
                instant(event["retain_until"]) >= snapshot + timedelta(days=14),
                "RETENTION",
            )
            sha(event["receipt_sha256"])
        else:
            need(
                all(
                    event[k] is None
                    for k in ("snapshot_at", "retain_until", "receipt_sha256")
                ),
                "OUTCOME",
            )

    def reserve(self, run_id, capture_id, stream, kind, *, at, initialize=False):
        need(type(run_id) is str and re.fullmatch("[a-f0-9]{12}", run_id), "RUN_ID")
        self.check_capture(capture_id, stream, kind)
        need(
            at.tzinfo is not None
            and instant(self.policy["starts_at"])
            <= at
            < instant(self.policy["ends_at"]),
            "HORIZON",
        )
        with self.transaction(initialize) as (records, last, journal, lock):
            need(run_id not in records, "REPLAY")
            need(
                all(r["outcome"] == "confirmed" for r in records.values()), "UNRESOLVED"
            )
            need(len(records) < self.policy["max_attempts"], "ATTEMPTS")
            same = [
                r
                for r in records.values()
                if (r["capture_id"], r["stream"]) == (capture_id, stream)
            ]
            need(not same or all(r["capture_kind"] == kind for r in same), "KIND")
            captures = {(r["capture_id"], r["stream"]) for r in records.values()} | {
                (capture_id, stream)
            }
            need(
                len(captures) <= self.policy["max_captures"]
                and len(same) < self.policy["max_attempts_per_capture"],
                "CAPTURES",
            )
            event = {
                "kind": "reserve",
                "run_id": run_id,
                "capture_id": capture_id,
                "stream": stream,
                "capture_kind": kind,
                "at": at.isoformat(),
            }
            self.append(journal, lock, event, last)
        return {
            "policy_sha256": self.policy_sha,
            "run_id": run_id,
            "reserved_bytes": dict(self.amounts),
        }

    def finish(
        self,
        run_id,
        *,
        outcome="unknown",
        snapshot_at=None,
        retain_until=None,
        receipt_sha256=None,
    ):
        event = {
            "kind": "finish",
            "run_id": run_id,
            "outcome": outcome,
            "snapshot_at": snapshot_at,
            "retain_until": retain_until,
            "receipt_sha256": receipt_sha256,
        }
        self.check_outcome(event)
        with self.transaction() as (records, last, journal, lock):
            need(
                run_id in records and records[run_id]["outcome"] == "reserved",
                "OUTCOME",
            )
            if outcome == "confirmed":
                snapshot = instant(snapshot_at)
                need(
                    instant(records[run_id]["at"])
                    <= snapshot
                    < instant(self.policy["ends_at"]),
                    "SNAPSHOT",
                )
            self.append(journal, lock, event, last)

    def summary(self):
        with self.transaction() as (records, _last, _journal, _lock):
            return {
                "attempts": len(records),
                "reserved_bytes": {
                    k: len(records) * v for k, v in self.amounts.items()
                },
                "outcomes": {k: r["outcome"] for k, r in records.items()},
                "deletion_credit_bytes": 0,
                "live_capacity_accepted": False,
            }
