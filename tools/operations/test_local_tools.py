"""Synthetic-only regression: no real grant, credentials, database or HTTP."""

import copy
import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
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


class Tools(unittest.TestCase):
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
            db = SimpleNamespace(
                pgconn=SimpleNamespace(
                    ssl_in_use=client, ssl_attribute=lambda _: protocol
                ),
                execute=lambda _: SimpleNamespace(
                    fetchone=lambda: (backend_ok, backend_version)
                ),
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


if __name__ == "__main__":
    unittest.main()
