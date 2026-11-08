"""Synthetic-only regression: no real grant, credentials, database or HTTP."""

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
        self.assertIn("if: github.event_name == 'pull_request' &&", precommit)
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


if __name__ == "__main__":
    unittest.main()
