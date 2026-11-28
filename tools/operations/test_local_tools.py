"""Synthetic-only regression: no real grant, credentials, database or HTTP."""

import copy
import importlib.util
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import subprocess
import sys
import unittest

import httpx

HERE = Path(__file__).parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backup, email = load("backup_once"), load("test_email_once")
repair = load("restore_candidate_checks")
SYNTHETIC_TARGET = {
    "project": "synthetic-project",
    "host": "synthetic.invalid",
    "database": "synthetic_database",
    "role": "synthetic_reader",
    "plan": "Free",
    "region": "synthetic-region",
}


def fake_db(
    *, backend=(False, None), client=True, protocol=b"TLSv1.3", params=None, target=None
):
    target = target or SYNTHETIC_TARGET
    policy = {
        "sslmode": "verify-full",
        "channel_binding": "require",
        "ssl_min_protocol_version": "TLSv1.2",
        "sslrootcert": "/synthetic/ca.crt",
    } | (params or {})
    return SimpleNamespace(
        pgconn=SimpleNamespace(
            ssl_in_use=client,
            ssl_attribute=lambda _: protocol,
            info=[
                SimpleNamespace(keyword=k.encode(), val=v.encode())
                for k, v in policy.items()
            ],
        ),
        info=SimpleNamespace(
            host=target["host"],
            dbname=target["database"],
            user=target["role"],
            get_parameters=lambda: policy,
        ),
        execute=lambda _: SimpleNamespace(fetchone=lambda: backend),
    )


class Tools(unittest.TestCase):
    def setUp(self):
        target = patch.object(
            backup,
            "PRODUCTION_TARGET_SHA256",
            backup.sha(json.dumps(SYNTHETIC_TARGET, sort_keys=True).encode()),
        )
        target.start()
        self.addCleanup(target.stop)

    def test_minimum_tls_is_injected_at_native_boundary(self):
        seen = []

        class Base:
            def __init__(self, native, check, resolver):
                self.native = native

        connection = backup.strict_connector(Base)(
            lambda **kw: seen.append(kw), lambda: None
        )
        connection.native(
            host="public-synthetic.invalid",
            sslmode="verify-full",
            channel_binding="require",
        )
        self.assertEqual(
            seen,
            [
                {
                    "host": "public-synthetic.invalid",
                    "sslmode": "verify-full",
                    "channel_binding": "require",
                    "ssl_min_protocol_version": "TLSv1.2",
                }
            ],
        )

    def test_mail_grant_binds_scope_expiry_allowance_and_reader(self):
        now = datetime(2026, 11, 8, 2, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as tmp:
            reader = Path(tmp) / "reader.py"
            reader.write_text("# public synthetic reader\n")
            with patch.object(email, "READER", reader):
                grant = dict(
                    authorized=True,
                    operation="single-resend-test-email",
                    run_id="abcdef123456",
                    starts_at=now.isoformat(),
                    expires_at=(now + timedelta(minutes=30)).isoformat(),
                    tool_sha256=backup.sha(Path(email.__file__).read_bytes()),
                    reader_sha256=backup.sha(reader.read_bytes()),
                    sender=email.SENDER,
                    recipient=email.RECIPIENT,
                    remaining_daily=1,
                    remaining_monthly=1,
                    sending_only_domain_restricted=True,
                    quota_verified_until=(now + timedelta(minutes=20)).isoformat(),
                )
                self.assertEqual(
                    email.validate(grant, now), now + timedelta(minutes=30)
                )
                for changed in (
                    {"recipient": "other@example.invalid"},
                    {"remaining_daily": 0},
                    {"remaining_monthly": 0},
                    {"sending_only_domain_restricted": False},
                    {"quota_verified_until": now.isoformat()},
                    {"reader_sha256": "bad"},
                    {"expires_at": now.isoformat()},
                ):
                    with self.assertRaises(ValueError):
                        email.validate(grant | changed, now)

    def test_required_ci_checks_cover_pr_and_main_without_path_skips(self):
        root = HERE.parents[1]
        for name in (
            "test-backend.yml",
            "test-h5.yml",
            "test-docker-compose.yml",
            "playwright.yml",
            "zizmor.yml",
            "pre-commit.yml",
        ):
            workflow = (root / ".github/workflows" / name).read_text()
            trigger = workflow.split("permissions:", 1)[0]
            self.assertIn("pull_request:", trigger)
            self.assertIn("push:", trigger)
            self.assertIn("main", trigger)
            self.assertNotIn("paths:", trigger)
            self.assertNotIn("paths-ignore:", trigger)
        playwright = (root / ".github/workflows/playwright.yml").read_text()
        self.assertNotIn("allowed-skips:", playwright)
        self.assertNotIn("needs.changes", playwright)
        self.assertNotIn("dorny/paths-filter", playwright)
        precommit = (root / ".github/workflows/pre-commit.yml").read_text()
        self.assertIn("github.event.pull_request.head.sha || github.sha", precommit)
        self.assertIn("--all-files", precommit)
        self.assertNotIn("git push", precommit)
        self.assertNotIn("tiangolo/pr-push", precommit)
        self.assertNotIn("id-token: write", precommit)
        self.assertIn("Reject generated or formatter changes", precommit)
        self.assertIn("pre-commit-alls-green:", precommit)

    def test_cadence_uses_actual_opening_snapshot(self):
        first = datetime(2026, 11, 8, 1, 0, 33, tzinfo=UTC)
        for index in (1, 2, 10):
            due = first + timedelta(minutes=45 * index)
            self.assertEqual(
                backup.due_time(first, index, due - timedelta(minutes=4)), due
            )
            self.assertEqual(
                backup.due_time(first, index, due + timedelta(seconds=119)), due
            )
            for bad in (
                due - timedelta(minutes=4, seconds=1),
                due + timedelta(minutes=2),
            ):
                with self.assertRaises(ValueError):
                    backup.due_time(first, index, bad)

    def test_client_and_backend_tls_separately_required(self):
        for client, protocol, backend_ok, backend_version, allowed in (
            (True, b"TLSv1.3", True, "TLSv1.3", True),
            (True, b"TLSv1.2", True, "TLSv1.2", True),
            (True, b"TLSv1.3", False, None, False),
            (False, b"TLSv1.3", True, "TLSv1.3", False),
            (True, b"TLSv1", True, "TLSv1.3", False),
            (True, b"TLSv1.3", True, "TLSv1", False),
        ):
            db = fake_db(
                client=client, protocol=protocol, backend=(backend_ok, backend_version)
            )
            if allowed:
                backup.backend_tls(db)
            else:
                with self.assertRaises(ValueError):
                    backup.backend_tls(db)

    def test_grant_expiry_source_and_profile_tampering(self):
        now = datetime(2026, 11, 8, 2, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "backend/app").mkdir(parents=True)
            p = source / "backend/app/synthetic.py"
            p.write_text("# public synthetic\n")
            base, head, count = backup.PROFILE_HEADS["production-26"]
            profile = dict(
                mode="production-26",
                security_mode="native-postgres-tls",
                target=SYNTHETIC_TARGET,
                accepted_base=base,
                migration_head=head,
                table_count=count,
                source_root=str(source),
                source_files={"backend/app/synthetic.py": backup.sha(p.read_bytes())},
            )
            grant = dict(
                authorized=True,
                operation="single-production-operating-backup",
                run_id="abcdef123456",
                starts_at=now.isoformat(),
                expires_at=(now + timedelta(minutes=30)).isoformat(),
                profile_sha256=backup.sha(json.dumps(profile, sort_keys=True).encode()),
                tool_sha256=backup.sha(Path(backup.__file__).read_bytes()),
                security_mode="native-postgres-tls",
                target=SYNTHETIC_TARGET,
                vendor_evidence_sha256=None,
            )
            self.assertEqual(
                backup.validate_grant(grant, profile, now), now + timedelta(minutes=30)
            )
            for changed in (
                {"authorized": False},
                {"expires_at": now.isoformat()},
                {"tool_sha256": "bad"},
                {"profile_sha256": "bad"},
            ):
                with self.assertRaises(ValueError):
                    backup.validate_grant(grant | changed, profile, now)
            p.write_text("# changed\n")
            with self.assertRaises(ValueError):
                backup.validate_grant(grant, profile, now)

    def test_email_payload_is_fixed_and_has_no_key_or_response(self):
        calls = []

        def handler(request):
            calls.append(request)
            body = json.loads(request.content)
            self.assertEqual(str(request.url), email.URL)
            self.assertEqual(body["to"], [email.RECIPIENT])
            self.assertEqual(body["from"], email.SENDER)
            self.assertNotIn("synthetic-secret", request.content.decode())
            return httpx.Response(
                202, json={"never_export": "synthetic private response"}
            )

        self.assertTrue(
            email.send("synthetic-secret", "abcdef123456", httpx.MockTransport(handler))
        )
        self.assertEqual(len(calls), 1)

    def test_unknown_email_never_retries(self):
        calls = []

        def handler(request):
            calls.append(request)
            raise httpx.ReadTimeout("synthetic timeout")

        with self.assertRaises(httpx.ReadTimeout):
            email.send("synthetic-secret", "abcdef123456", httpx.MockTransport(handler))
        self.assertEqual(len(calls), 1)

    def test_unapproved_mail_and_backup_refuse_before_input(self):
        with self.assertRaises(ValueError):
            email.validate({}, datetime.now(UTC))
        with self.assertRaises(ValueError):
            backup.validate_grant({}, {}, datetime.now(UTC))

    def test_profile_counts_are_explicit_not_dynamic(self):
        self.assertEqual(backup.PROFILE_HEADS["production-26"][2], 26)
        self.assertEqual(backup.PROFILE_HEADS["candidate-30"][2], 30)
        self.assertEqual(len(backup.EXTRA_TABLES), 4)
        self.assertEqual(len(set(backup.EXTRA_TABLES)), 4)


class ResourceProfileTests(unittest.TestCase):
    def test_exact_additive_scope_preserves_old_profiles(self):
        self.assertEqual(backup.profile_extra_tables("production-26"), ())
        self.assertEqual(
            backup.profile_extra_tables("candidate-30"), backup.EXTRA_TABLES
        )
        additions = backup.profile_extra_tables("candidate-33")
        self.assertEqual(len(additions), 7)
        self.assertEqual(len(set(additions)), 7)
        self.assertEqual(
            set(additions) - set(backup.EXTRA_TABLES),
            {"app_resource_policy", "app_resource_attempt", "app_media_read_grant"},
        )
        self.assertEqual(backup.PROFILE_HEADS["candidate-33"][1:], ("e7f8a9b0c1d2", 33))

    def test_unknown_profile_is_not_an_escape_hatch(self):
        with self.assertRaises(ValueError):
            backup.profile_extra_tables("accept-all-tables")

    def test_new_profile_still_whitelists_only_exact_budget_partial_index(self):
        module = SimpleNamespace(
            C=SimpleNamespace(TABLES=tuple(str(i) for i in range(33))),
            HAZARD_SQL="SELECT x.indpred IS NOT NULL",
        )
        sql = backup.hazard_sql(module)
        self.assertIn(backup.BUDGET_INDEX, sql)
        self.assertIn("c.relname='app_budget_window'", sql)
        self.assertNotIn("app_resource_policy", sql)

    def test_unknown_driver_stops_without_opening_connection(self):
        with self.assertRaises(ValueError):
            backup.negotiated_tls_protocol(SimpleNamespace(ssl_in_use=True))


class CandidateRestorePlanTests(unittest.TestCase):
    def fixture(self):
        source = {
            "schema": {
                "database_locale": [["synthetic-local"]],
                "relations": [
                    [t, "r", "p", False, False] for t in sorted(repair.TABLES)
                ],
                "columns": [],
                "constraints": [],
                "indexes": [],
                "collations": [],
            },
            "rows": {t: [] for t in repair.TABLES},
            "extensions": [["plpgsql", "1.0"], ["uuid-ossp", "1.1"]],
        }
        for table, name, types, _, definition in repair.SPECS:
            source["schema"]["constraints"].append([table, name, "c", True, definition])
            for index, (column, kind) in enumerate(types.items(), 1):
                source["schema"]["columns"].append(
                    [table, index, column, kind, True, "", "", None]
                )
        target = copy.deepcopy(source)
        for row in target["schema"]["constraints"]:
            row[4] = repair.restored_definition(row[4])
        return source, target

    def plan(self, source, target, **kw):
        return repair.repair_plan(
            source, target, **({"profile": "candidate-33", "head": "e7f8a9b0c1d2"} | kw)
        )

    def test_fixed_statements_only_and_no_input_mutation(self):
        source, target = self.fixture()
        original = copy.deepcopy((source, target))
        plan = self.plan(source, target)
        self.assertEqual(len(plan), 8)
        self.assertTrue(all("public." in statement for statement in plan))
        self.assertFalse(
            any(
                "NOT VALID" in statement or "DISABLE" in statement for statement in plan
            )
        )
        self.assertEqual((source, target), original)

    def test_old_or_unknown_profile_and_head_refuse(self):
        source, target = self.fixture()
        for changed in (
            {"profile": "production-26"},
            {"profile": "candidate-30"},
            {"profile": "unknown"},
            {"head": "other"},
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.plan(source, target, **changed)

    def test_any_unrelated_manifest_difference_refuses(self):
        source, target = self.fixture()

        def change_row(m):
            m["rows"]["app_resource_attempt"] = [["synthetic-different-hash"]]

        def change_type(m):
            m["schema"]["columns"][0][3] = "text"

        def change_locale(m):
            m["schema"]["database_locale"] = []

        def add_table(m):
            m["rows"]["unreviewed"] = []

        def change_index(m):
            m["schema"]["indexes"] = [["different"]]

        def change_extension(m):
            m["extensions"] = []

        for mutate in (
            change_row,
            change_type,
            change_locale,
            add_table,
            change_index,
            change_extension,
        ):
            item = copy.deepcopy(target)
            mutate(item)
            with self.subTest(mutation=mutate.__name__), self.assertRaises(ValueError):
                self.plan(source, item)

    def test_constraint_tampering_and_incomplete_diff_refuse(self):
        source, target = self.fixture()
        for field, value in (
            (1, "changed_name"),
            (2, "f"),
            (3, False),
            (3, 1),
            (4, "CHECK (true)"),
        ):
            item = copy.deepcopy(target)
            item["schema"]["constraints"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.plan(source, item)
        for action in ("duplicate", "missing", "already_equal"):
            item = copy.deepcopy(target)
            if action == "duplicate":
                item["schema"]["constraints"].append(
                    copy.deepcopy(item["schema"]["constraints"][0])
                )
            elif action == "missing":
                item["schema"]["constraints"].pop()
            else:
                item["schema"]["constraints"][0] = copy.deepcopy(
                    source["schema"]["constraints"][0]
                )
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.plan(source, item)

    def test_changed_source_rule_and_both_changed_types_refuse(self):
        source, target = self.fixture()
        source["schema"]["constraints"][0][4] = "CHECK (true)"
        with self.assertRaises(ValueError):
            self.plan(source, target)
        source, target = self.fixture()
        for item in (source, target):
            item["schema"]["columns"][0][3] = "text"
        with self.assertRaises(ValueError):
            self.plan(source, target)

    def test_malformed_input_refuses(self):
        source, target = self.fixture()
        for item in ({}, None, {"schema": None}, {"schema": {"constraints": [None]}}):
            with self.subTest(item=item), self.assertRaises(ValueError):
                self.plan(source, item)


capacity = load("backup_capacity")


class BackupCapacityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "ledger"
        self.now = datetime.now(UTC)
        self.profile = dict(
            mode="production-26",
            security_mode="native-postgres-tls",
            target=SYNTHETIC_TARGET,
            migration_head=backup.PROFILE_HEADS["production-26"][1],
            table_count=26,
        )
        self.profile_sha = backup.sha(json.dumps(self.profile, sort_keys=True).encode())
        target_sha = backup.sha(json.dumps(SYNTHETIC_TARGET, sort_keys=True).encode())
        self.policy = dict(
            schema=1,
            target_sha256=target_sha,
            profile_sha256=self.profile_sha,
            host_sha256=capacity.host_identity(),
            starts_at=(self.now - timedelta(minutes=1)).isoformat(),
            ends_at=(self.now + timedelta(hours=84)).isoformat(),
            streams=["production"],
            max_captures=3,
            max_attempts_per_capture=2,
            max_attempts=3,
            cipher_bytes=capacity.MAX_CIPHER,
            sidecar_bytes=capacity.MAX_SIDECAR,
            local_extra_bytes=65536,
            wire_bytes_per_attempt=1024**2,
            cloud_allocation_bytes=3 * (capacity.MAX_CIPHER + capacity.MAX_SIDECAR),
            local_allocation_bytes=3
            * (2 * (capacity.MAX_CIPHER + capacity.MAX_SIDECAR) + 65536),
            wire_allocation_bytes=3 * 1024**2,
            maximum_cu_milli=1000,
            closing_micros=20_000_000,
        )
        self.evidence = dict(
            policy_sha256=capacity.digest(self.policy),
            observed_at=self.now.isoformat(),
            expires_at=(self.now + timedelta(minutes=30)).isoformat(),
            proofs={
                key: capacity.digest("public synthetic " + key)
                for key in capacity.PROOFS
            },
            compute_available_mcu_hours=100_000,
            compute_other_mcu_hours=1000,
            admission_micros=100_000_000,
            closing_required_micros=15_000_000,
        )
        for medium in ("cloud", "local", "wire"):
            self.evidence.update(
                {
                    medium + "_available_bytes": self.policy[
                        medium + "_allocation_bytes"
                    ]
                    + 1024,
                    medium + "_other_bytes": 512,
                    medium + "_reserve_bytes": 512,
                }
            )
        self.grant = dict(
            capacity_schema=1,
            capacity_helper_sha256=backup.sha(Path(capacity.__file__).read_bytes()),
            capacity_policy=self.policy,
            capacity_evidence=self.evidence,
            initialize_capacity_ledger=True,
            profile_sha256=self.profile_sha,
            tool_sha256=backup.sha(Path(backup.__file__).read_bytes()),
            run_id="000000000001",
            target=SYNTHETIC_TARGET,
            security_mode="native-postgres-tls",
            vendor_evidence_sha256=None,
            capture_id="opening",
            capacity_stream="production",
            capture_kind="opening",
            expires_at=(self.now + timedelta(minutes=30)).isoformat(),
        )

    def validate(self, policy=None, evidence=None):
        return capacity.validate(
            policy if policy is not None else self.policy,
            evidence if evidence is not None else self.evidence,
            at=self.now,
            target_sha256=self.policy["target_sha256"],
            profile_sha256=self.profile_sha,
            host_sha256=capacity.host_identity(),
        )

    def ledger(self, policy=None):
        return capacity.Ledger(self.root, policy if policy is not None else self.policy)

    def reserve(self, n=1, **kw):
        return self.ledger().reserve(
            f"{n:012x}",
            kw.pop("capture_id", f"slot{n}"),
            kw.pop("stream", "production"),
            kw.pop("kind", "scheduled"),
            at=kw.pop("at", self.now),
            initialize=kw.pop("initialize", n == 1),
            **kw,
        )

    def confirm(self, n=1):
        self.ledger().finish(
            f"{n:012x}",
            outcome="confirmed",
            snapshot_at=self.now.isoformat(),
            retain_until=(self.now + timedelta(days=14)).isoformat(),
            receipt_sha256=capacity.digest("public receipt"),
        )

    def test_explicit_finite_policy_and_space_compute_cost_boundaries(self):
        self.validate()
        for changes in (
            {"cloud_available_bytes": self.policy["cloud_allocation_bytes"] + 1023},
            {"compute_available_mcu_hours": 85016},
            {"closing_required_micros": 20_000_001},
            {"admission_micros": 120_000_000},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.validate(evidence=self.evidence | changes)

    def test_missing_or_unknown_proof_never_becomes_zero(self):
        for key in self.evidence:
            if key == "policy_sha256":
                continue
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate(
                    evidence={k: v for k, v in self.evidence.items() if k != key}
                )
        for proof in capacity.PROOFS:
            with self.subTest(proof=proof), self.assertRaises(ValueError):
                self.validate(
                    evidence=self.evidence
                    | {"proofs": self.evidence["proofs"] | {proof: None}}
                )

    def test_policy_rejects_boolean_nonfinite_and_negative_quantities(self):
        for key, value in (
            ("max_attempts", True),
            ("cipher_bytes", 0),
            ("wire_bytes_per_attempt", None),
            ("closing_micros", float("nan")),
            ("max_captures", -1),
            ("sidecar_bytes", 4097),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate(policy=self.policy | {key: value})
        with self.assertRaises(ValueError):
            capacity.decode(b'{"x":1,"x":2}')
        with self.assertRaises(ValueError):
            capacity.decode(b'{"x":NaN}')

    def test_stale_or_changed_source_target_host_refuses(self):
        for change in (
            {"expires_at": self.now.isoformat()},
            {"observed_at": (self.now + timedelta(seconds=1)).isoformat()},
            {"expires_at": (self.now + timedelta(minutes=31)).isoformat()},
        ):
            with self.assertRaises(ValueError):
                self.validate(evidence=self.evidence | change)
        for key in ("target_sha256", "profile_sha256", "host_sha256"):
            with self.assertRaises(ValueError):
                self.validate(policy=self.policy | {key: capacity.digest("different")})

    def test_full_envelope_and_sidecar_caps_include_all_overhead(self):
        capacity.check_cipher(b"x" * capacity.MAX_CIPHER, self.policy)
        capacity.check_sidecar(b"x" * capacity.MAX_SIDECAR, self.policy)
        for value in (b"", b"x" * (capacity.MAX_CIPHER + 1), bytearray(b"x")):
            with self.assertRaises(ValueError):
                capacity.check_cipher(value, self.policy)
        with self.assertRaises(ValueError):
            capacity.check_sidecar(b"x" * 4097, self.policy)

    def test_same_run_replay_and_changed_policy_cannot_reset_counts(self):
        self.reserve()
        self.confirm()
        with self.assertRaises(ValueError):
            self.reserve(initialize=False)
        with self.assertRaises(ValueError):
            self.reserve(2, initialize=True)
        changed = self.policy | {"max_captures": 4}
        with self.assertRaises(ValueError):
            self.ledger(changed).reserve(
                "000000000002", "opening2", "production", "opening", at=self.now
            )
        self.assertEqual(self.ledger().summary()["attempts"], 1)

    def test_global_aggregate_charges_opening_closing_and_maintenance(self):
        for n, kind in enumerate(("opening", "closing", "maintenance"), 1):
            self.reserve(n, kind=kind)
            self.confirm(n)
        with self.assertRaises(ValueError):
            self.reserve(4)
        s = self.ledger().summary()
        self.assertEqual(s["attempts"], 3)
        self.assertEqual(s["reserved_bytes"]["cloud"], 3 * (capacity.MAX_CIPHER + 4096))
        self.assertEqual(s["reserved_bytes"]["wire"], 3 * 1024**2)
        self.assertFalse(s["live_capacity_accepted"])

    def test_extra_capture_per_capture_limit_and_streams_are_checked(self):
        self.reserve(capture_id="same")
        self.confirm()
        self.reserve(2, capture_id="same")
        self.confirm(2)
        with self.assertRaises(ValueError):
            self.reserve(3, capture_id="same")
        with self.assertRaises(ValueError):
            self.reserve(3, stream="unreviewed")

    def test_unresolved_and_unknown_attempts_keep_reservations_and_block(self):
        self.reserve()
        with self.assertRaises(ValueError):
            self.reserve(2)
        self.ledger().finish("000000000001")
        with self.assertRaises(ValueError):
            self.reserve(2)
        with self.assertRaises(ValueError):
            self.confirm()
        self.assertEqual(
            self.ledger().summary()["outcomes"], {"000000000001": "unknown"}
        )

    def test_retention_expiry_does_not_delete_or_credit_anything(self):
        self.reserve()
        with self.assertRaises(ValueError):
            self.ledger().finish(
                "000000000001",
                outcome="confirmed",
                snapshot_at=self.now.isoformat(),
                retain_until=(self.now + timedelta(days=13)).isoformat(),
                receipt_sha256=capacity.digest("receipt"),
            )
        self.confirm()
        before = (self.root / "journal.jsonl").read_bytes()
        with self.assertRaises(ValueError):
            self.reserve(2, at=self.now + timedelta(days=15))
        self.assertEqual(self.ledger().summary()["deletion_credit_bytes"], 0)
        self.assertEqual((self.root / "journal.jsonl").read_bytes(), before)

    def test_missing_symlink_unsafe_permissions_and_corrupt_files_refuse(self):
        with self.assertRaises(ValueError):
            self.reserve(initialize=False)
        self.reserve()
        self.confirm()
        journal = self.root / "journal.jsonl"
        good = journal.read_bytes()
        journal.chmod(0o644)
        with self.assertRaises(ValueError):
            self.ledger().summary()
        journal.chmod(0o600)
        journal.unlink()
        journal.symlink_to(self.root / "outside")
        with self.assertRaises(ValueError):
            self.ledger().summary()
        journal.unlink()
        journal.write_bytes(good + b'{"partial":')
        journal.chmod(0o600)
        with self.assertRaises(ValueError):
            self.ledger().summary()

    def test_deleted_or_complete_record_truncated_journal_never_reinitializes(self):
        self.reserve()
        self.confirm()
        journal = self.root / "journal.jsonl"
        journal.write_bytes(journal.read_bytes().splitlines(keepends=True)[0])
        with self.assertRaises(ValueError):
            self.ledger().summary()
        journal.unlink()
        with self.assertRaises(ValueError):
            self.reserve(2)
        with self.assertRaises(ValueError):
            self.reserve(2, initialize=True)

    def test_interrupted_anchor_commit_retains_charge_and_fails_closed(self):
        self.reserve()
        self.confirm()
        with patch.object(
            capacity.os, "pwrite", side_effect=OSError("public simulated crash")
        ):
            with self.assertRaises(ValueError):
                self.reserve(2)
        self.assertIn(b"000000000002", (self.root / "journal.jsonl").read_bytes())
        with self.assertRaises(ValueError):
            self.ledger().summary()
        with self.assertRaises(ValueError):
            self.reserve(3)

    def test_private_root_and_hardlinked_journal_refuse(self):
        self.reserve()
        self.root.chmod(0o755)
        with self.assertRaises(ValueError):
            self.ledger().summary()
        self.root.chmod(0o700)
        os.link(self.root / "journal.jsonl", Path(self.tmp.name) / "duplicate")
        with self.assertRaises(ValueError):
            self.ledger().summary()

    def child(self, n, crash=False):
        script = """
import importlib.util,json,os,sys
from datetime import datetime
from pathlib import Path
s=importlib.util.spec_from_file_location('capacity',sys.argv[1])
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
try:
 m.Ledger(Path(sys.argv[2]),json.loads(sys.argv[3])).reserve(sys.argv[4],sys.argv[4],'production','scheduled',at=datetime.fromisoformat(sys.argv[5]))
 if sys.argv[6]=='crash':os._exit(23)
 print('CLAIM')
except ValueError:print('REFUSE')
"""
        return subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                script,
                capacity.__file__,
                str(self.root),
                json.dumps(self.policy),
                f"{n:012x}",
                self.now.isoformat(),
                "crash" if crash else "normal",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_two_processes_at_last_allowance_only_one_can_claim(self):
        self.policy["max_attempts"] = 2
        self.reserve()
        self.confirm()
        children = [self.child(2), self.child(3)]
        outcomes = [p.communicate(timeout=15) for p in children]
        self.assertTrue(all(p.returncode == 0 for p in children), outcomes)
        self.assertEqual(
            sorted(out for out, _err in outcomes), [b"CLAIM\n", b"REFUSE\n"]
        )
        self.assertEqual(self.ledger().summary()["attempts"], 2)

    def test_process_exit_after_reservation_preserves_unknown_charge(self):
        self.reserve()
        self.confirm()
        child = self.child(2, crash=True)
        child.communicate(timeout=15)
        self.assertEqual(child.returncode, 23)
        self.assertEqual(
            self.ledger().summary()["outcomes"]["000000000002"], "reserved"
        )
        with self.assertRaises(ValueError):
            self.reserve(3)

    def test_old_missing_helper_and_missing_proof_stop_before_engine_or_input(self):
        for changed in (
            {"capacity_schema": None},
            {"capacity_helper_sha256": "bad"},
            {"capacity_evidence": {}},
        ):
            with patch.object(backup, "load_engine") as engine:
                with self.assertRaises(ValueError):
                    backup.execute(self.grant | changed, self.profile)
                engine.assert_not_called()
        with self.assertRaises(ValueError):
            backup.capacity_admission(
                self.grant, self.profile | {"security_mode": "neon-managed"}, self.now
            )

    def fake_execute(
        self,
        *,
        large_cipher=False,
        large_sidecar=False,
        stale_after_input=False,
        partial=False,
    ):
        calls = []
        core = SimpleNamespace(
            TABLES=tuple(f"table{n}" for n in range(26)),
            source_env=lambda *_: {},
            seal_archive=lambda *_: (
                b"x" * (self.policy["cipher_bytes"] + 1 if large_cipher else 20)
            ),
        )

        class Connector:
            def __init__(self, native, check, resolver=None):
                self.native = native

            def __call__(self, params):
                calls.append("connection")
                return self.native(**params)

        module = SimpleNamespace(
            C=core,
            R=SimpleNamespace(Connector=Connector),
            private_dir=lambda _: None,
            private_comparison=lambda *_: None,
            read_safe=lambda p: p.read_bytes(),
            write_new=lambda p, b: p.write_bytes(b),
            safe_stop=lambda *_: "STOP",
        )
        engine = SimpleNamespace(
            safe_stop=lambda *_: "STOP",
            operating_snapshot=lambda *_: {},
            encoded=lambda v: (json.dumps(v, sort_keys=True) + "\n").encode(),
            native=lambda *_: None,
            ACTIVE_IO=SimpleNamespace(event=lambda *_: None),
        )

        def run(_args):
            # All writes below are public synthetic data under TemporaryDirectory.
            ledger_root = (
                Path(self.tmp.name)
                / "Documents/vireal-backups/production-operating-capacity"
            )
            self.assertEqual(
                capacity.Ledger(ledger_root, self.policy).summary()["attempts"], 1
            )
            calls.append("input")
            if stale_after_input:
                self.evidence["expires_at"] = datetime.now(UTC).isoformat()
            db = module.R.Connector(
                lambda **_: fake_db(backend=(True, "TLSv1.3")), lambda: None
            )({})
            engine.operating_snapshot(
                module, db, lambda: None, "public@example.invalid"
            )
            module.C.source_env({}, "public-synthetic.invalid")
            cipher = module.C.seal_archive(None)
            calls.append("archive_write")
            snapshot = datetime.now(UTC)
            manifest = dict(
                archive="x" * 5000 if large_sidecar else "public-synthetic.fernet",
                ciphertext_bytes=len(cipher),
                ciphertext_sha256=backup.sha(cipher),
                snapshot_at=snapshot.isoformat(),
                retain_at_least_until=(snapshot + timedelta(days=14)).isoformat(),
            )
            engine.encoded(manifest)
            calls.append("cloud_write")
            if partial:
                return 2
            report = manifest | dict(
                cadence_passed=True,
                icloud_uploaded=True,
                icloud_uploaded_observed_at=datetime.now(UTC).isoformat(),
                latest_upload_confirmation_at=(
                    snapshot + timedelta(minutes=15)
                ).isoformat(),
                manifest_sha256=capacity.digest(manifest),
            )
            (engine.ROOT / "slot-0.json").write_bytes(engine.encoded(report))
            return 0

        engine.run_cli = run
        home = Path(self.tmp.name)
        (home / "Documents/vireal-backups").mkdir(parents=True, mode=0o700)
        fake_sys = SimpleNamespace(
            flags=SimpleNamespace(isolated=1),
            dont_write_bytecode=True,
            stdin=SimpleNamespace(isatty=lambda: True),
            stdout=SimpleNamespace(isatty=lambda: True),
            stderr=SimpleNamespace(isatty=lambda: True),
        )
        with (
            patch.object(backup, "load_engine", return_value=(engine, module, {})),
            patch.object(
                backup, "validate_grant", return_value=self.now + timedelta(minutes=30)
            ),
            patch.object(backup, "sys", fake_sys),
            patch.object(backup.Path, "home", return_value=home),
        ):
            try:
                result = backup.execute(self.grant, self.profile)
            except ValueError:
                result = "refused"
        summary = capacity.Ledger(
            home / "Documents/vireal-backups/production-operating-capacity", self.policy
        ).summary()
        return result, calls, summary

    def test_synthetic_complete_wrapper_records_confirmed_without_freeing_bytes(self):
        result, calls, summary = self.fake_execute()
        self.assertEqual(result, 0)
        self.assertEqual(calls, ["input", "connection", "archive_write", "cloud_write"])
        self.assertEqual(summary["outcomes"], {self.grant["run_id"]: "confirmed"})
        self.assertEqual(
            summary["reserved_bytes"]["cloud"],
            self.policy["cipher_bytes"] + self.policy["sidecar_bytes"],
        )

    def test_wrapper_rejects_cipher_overflow_before_any_archive_or_cloud_write(self):
        result, calls, summary = self.fake_execute(large_cipher=True)
        self.assertEqual(result, "refused")
        self.assertNotIn("archive_write", calls)
        self.assertNotIn("cloud_write", calls)
        self.assertEqual(summary["outcomes"][self.grant["run_id"]], "unknown")

    def test_wrapper_rejects_sidecar_overflow_before_cloud_write(self):
        result, calls, summary = self.fake_execute(large_sidecar=True)
        self.assertEqual(result, "refused")
        self.assertNotIn("cloud_write", calls)
        self.assertEqual(summary["outcomes"][self.grant["run_id"]], "unknown")

    def test_evidence_expiring_during_input_refuses_before_connection(self):
        result, calls, summary = self.fake_execute(stale_after_input=True)
        self.assertEqual(result, "refused")
        self.assertEqual(calls, ["input"])
        self.assertEqual(summary["outcomes"][self.grant["run_id"]], "unknown")

    def test_unknown_cloud_result_never_frees_or_retries(self):
        result, calls, summary = self.fake_execute(partial=True)
        self.assertEqual(result, 2)
        self.assertEqual(calls.count("input"), 1)
        self.assertEqual(calls.count("cloud_write"), 1)
        self.assertEqual(summary["outcomes"][self.grant["run_id"]], "unknown")

    def valid_receipt(self):
        return dict(
            icloud_uploaded=True,
            cadence_passed=True,
            capture_run_id=self.grant["run_id"],
            capacity_policy_sha256=capacity.digest(self.policy),
            profile_sha256=self.profile_sha,
            tool_sha256=self.grant["tool_sha256"],
            target=SYNTHETIC_TARGET,
            ciphertext_bytes=20,
            ciphertext_sha256=capacity.digest("public ciphertext"),
            manifest_sha256=capacity.digest("public sidecar"),
            snapshot_at=self.now.isoformat(),
            icloud_uploaded_observed_at=(self.now + timedelta(seconds=1)).isoformat(),
            latest_upload_confirmation_at=(
                self.now + timedelta(minutes=15)
            ).isoformat(),
            retain_at_least_until=(self.now + timedelta(days=14)).isoformat(),
        )

    def test_receipt_replay_wrong_target_or_changed_binding_refuses(self):
        report = self.valid_receipt()
        at = self.now + timedelta(seconds=2)
        backup.capacity_receipt(capacity, self.policy, self.grant, report, at)
        for key, value in (
            ("capture_run_id", "000000000002"),
            ("capacity_policy_sha256", capacity.digest("different")),
            ("target", {}),
            ("tool_sha256", "different"),
            ("cadence_passed", False),
            ("icloud_uploaded", None),
            ("ciphertext_bytes", True),
            ("manifest_sha256", capacity.ZERO),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                backup.capacity_receipt(
                    capacity, self.policy, self.grant, report | {key: value}, at
                )

    def test_future_expired_or_extended_upload_and_retention_refuse(self):
        report = self.valid_receipt()
        at = self.now + timedelta(seconds=2)
        for change in (
            {"snapshot_at": (self.now + timedelta(seconds=3)).isoformat()},
            {
                "icloud_uploaded_observed_at": (
                    self.now - timedelta(seconds=1)
                ).isoformat()
            },
            {
                "latest_upload_confirmation_at": (
                    self.now + timedelta(minutes=16)
                ).isoformat()
            },
            {"retain_at_least_until": (self.now + timedelta(days=13)).isoformat()},
        ):
            with self.assertRaises(ValueError):
                backup.capacity_receipt(
                    capacity, self.policy, self.grant, report | change, at
                )
        with self.assertRaises(ValueError):
            backup.capacity_receipt(
                capacity,
                self.policy,
                self.grant,
                report,
                self.now + timedelta(minutes=30),
            )

    def test_fractional_compute_time_is_rounded_up_not_truncated(self):
        duration = capacity.instant(self.policy["ends_at"]) - capacity.instant(
            self.policy["starts_at"]
        )
        self.assertEqual(duration, timedelta(hours=84, minutes=1))
        self.validate(evidence=self.evidence | {"compute_available_mcu_hours": 85017})
        with self.assertRaises(ValueError):
            self.validate(
                evidence=self.evidence | {"compute_available_mcu_hours": 85016}
            )

    def test_aggregate_allocations_must_cover_every_attempt(self):
        for medium in ("cloud", "local", "wire"):
            key = medium + "_allocation_bytes"
            with self.assertRaises(ValueError):
                capacity.policy_limits(self.policy | {key: self.policy[key] - 1})

    def test_logical_capture_cap_cannot_be_bypassed_by_fresh_ids(self):
        self.policy["max_captures"] = 2
        self.reserve()
        self.confirm()
        self.reserve(2)
        self.confirm(2)
        with self.assertRaises(ValueError):
            self.reserve(3)

    def test_ledger_lock_contention_refuses_without_append(self):
        self.reserve()
        self.confirm()
        before = (self.root / "journal.jsonl").read_bytes()
        with self.ledger().transaction(), self.assertRaises(ValueError):
            self.reserve(2)
        self.assertEqual((self.root / "journal.jsonl").read_bytes(), before)

    def test_wrong_file_owner_refuses(self):
        self.reserve()
        actual = capacity.os.fstat

        def wrong_owner(fd):
            info = actual(fd)
            return SimpleNamespace(st_uid=info.st_uid + 1)

        with (
            patch.object(capacity.os, "fstat", side_effect=wrong_owner),
            self.assertRaises(ValueError),
        ):
            self.ledger().summary()

    def test_helpers_have_no_provider_or_process_execution_adapters(self):
        import ast

        tree = ast.parse(Path(capacity.__file__).read_text())
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertFalse(
            imports & {"httpx", "requests", "socket", "subprocess", "psycopg", "boto3"}
        )
        names = {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        self.assertFalse(names & {"system", "popen", "connect", "unlink", "rmdir"})


if __name__ == "__main__":
    unittest.main()
