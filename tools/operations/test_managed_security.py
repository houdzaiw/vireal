"""Adversarial policy tests; synthetic files only, no credentials or network."""

import copy
from datetime import UTC, datetime, timedelta
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "owner_tool_fixtures", Path(__file__).with_name("test_local_tools.py")
)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
backup, fake_db = fixtures.backup, fixtures.fake_db
TARGET = fixtures.SYNTHETIC_TARGET


class ManagedSecurity(unittest.TestCase):
    def setUp(self):
        target = patch.object(
            backup,
            "PRODUCTION_TARGET_SHA256",
            backup.sha(json.dumps(TARGET, sort_keys=True).encode()),
        )
        target.start()
        self.addCleanup(target.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = datetime(2026, 11, 12, 6, tzinfo=UTC)
        self.profile = {
            "security_mode": "neon-managed",
            "target": copy.deepcopy(TARGET),
        }
        self.evidence = {
            "schema": 1,
            "target": copy.deepcopy(TARGET),
            "vendor_control_acceptance": "accepted-managed-trust-boundary",
            "known_public_exclusions": [],
            "independently_verified_internal_hops": False,
            "project_specific_confirmation": "not_obtained",
            "reviewed_at": self.now.isoformat(),
            "sources": {},
        }
        for name, url in backup.VENDOR_SOURCES.items():
            raw = b"Synthetic public statement, not live vendor evidence."
            (self.root / name).write_bytes(raw)
            self.evidence["sources"][name] = {
                "url": url,
                "retrieved_at": self.now.isoformat(),
                "sha256": backup.sha(raw),
            }
        self.grant = {
            "starts_at": self.now.isoformat(),
            "security_mode": "neon-managed",
            "target": copy.deepcopy(TARGET),
            "vendor_evidence_path": str(self.root / "evidence.json"),
        }
        self.seal()

    def seal(self):
        raw = json.dumps(self.evidence).encode()
        Path(self.grant["vendor_evidence_path"]).write_bytes(raw)
        self.grant["vendor_evidence_sha256"] = backup.sha(raw)

    def check(self):
        return backup.security_policy(self.grant, self.profile, self.now)

    def test_valid_policy_does_not_claim_internal_measurement(self):
        self.assertEqual(self.check()["security_mode"], "neon-managed")
        out = backup.backend_tls(fake_db(), security_mode="neon-managed", target=TARGET)
        self.assertEqual(out["pg_stat_ssl"], {"ssl": False, "version": None})
        self.assertEqual(
            out["internal_path_assurance"],
            "vendor-assertion-not-independently-verified",
        )

    def test_native_failure_never_changes_to_managed(self):
        with self.assertRaisesRegex(ValueError, "BACKEND_TLS"):
            backup.backend_tls(fake_db())
        for mode in (None, "auto", "ignore-backend"):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                backup.backend_tls(fake_db(), security_mode=mode)

    def test_managed_still_requires_every_client_control(self):
        cases = [fake_db(client=False), fake_db(protocol=b"TLSv1.1")]
        for key, value in (
            ("sslmode", "require"),
            ("channel_binding", "prefer"),
            ("ssl_min_protocol_version", "TLSv1.1"),
            ("sslrootcert", ""),
        ):
            cases.append(fake_db(params={key: value}))
        for db in cases:
            with self.assertRaises(ValueError):
                backup.backend_tls(db, security_mode="neon-managed", target=TARGET)

    def test_wrong_live_host_database_or_role_stops(self):
        for key in ("host", "database", "role"):
            target = TARGET | {key: "other"}
            with (
                self.subTest(key=key),
                self.assertRaisesRegex(ValueError, "SECURITY_TARGET"),
            ):
                backup.backend_tls(
                    fake_db(target=target),
                    security_mode="neon-managed",
                    target=TARGET,
                )
        with self.assertRaises(ValueError):
            backup.backend_tls(fake_db(), security_mode="neon-managed")

    def test_missing_or_mixed_modes_and_native_evidence_refuse(self):
        for mode in (None, "native-postgres-tls", "auto"):
            self.grant["security_mode"] = mode
            with self.assertRaises(ValueError):
                self.check()
        self.grant["security_mode"] = self.profile["security_mode"] = (
            "native-postgres-tls"
        )
        with self.assertRaises(ValueError):
            self.check()
        self.grant["vendor_evidence_sha256"] = self.grant["vendor_evidence_path"] = None
        self.check()

    def test_rehashed_wrong_project_plan_or_region_refuse(self):
        for key in ("project", "host", "database", "plan", "region"):
            old = copy.deepcopy(self.evidence)
            self.evidence["target"][key] = "other"
            self.seal()
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check()
            self.evidence = old
        self.seal()
        self.profile["target"]["database"] = "vireal_staging"
        self.grant["target"] = self.profile["target"]
        with self.assertRaises(ValueError):
            self.check()

    def test_evidence_bytes_snapshot_and_duplicate_keys_refuse(self):
        path = Path(self.grant["vendor_evidence_path"])
        path.write_text("{}")
        with self.assertRaises(ValueError):
            self.check()
        self.seal()
        (self.root / "security.html").write_text("changed")
        with self.assertRaises(ValueError):
            self.check()
        with self.assertRaises(ValueError):
            backup.unique_json(b'{"a":1,"a":2}')

    def test_review_window_boundaries_and_future_refuse(self):
        for delta, allowed in (
            (timedelta(minutes=-30), True),
            (timedelta(minutes=-30, microseconds=-1), False),
            (timedelta(seconds=1), False),
        ):
            instant = self.now + delta
            self.evidence["reviewed_at"] = instant.isoformat()
            for item in self.evidence["sources"].values():
                item["retrieved_at"] = instant.isoformat()
            self.seal()
            if allowed:
                self.check()
            else:
                with self.assertRaises(ValueError):
                    self.check()

    def test_public_exclusion_unknown_source_or_false_measurement_refuse(self):
        original = copy.deepcopy(self.evidence)
        for key, value in (
            ("known_public_exclusions", ["Free"]),
            ("independently_verified_internal_hops", True),
            ("vendor_control_acceptance", "pending"),
        ):
            self.evidence = copy.deepcopy(original)
            self.evidence[key] = value
            self.seal()
            with self.assertRaises(ValueError):
                self.check()
        self.evidence = original
        self.evidence["sources"]["security.html"]["url"] = "https://example.invalid"
        self.seal()
        with self.assertRaises(ValueError):
            self.check()

    def test_missing_backend_observation_is_not_fabricated(self):
        for row in (None, (False,), ("false", None)):
            with self.assertRaises(ValueError):
                backup.backend_tls(
                    fake_db(backend=row),
                    security_mode="neon-managed",
                    target=TARGET,
                )

    def test_positive_obsolete_backend_tls_observation_requires_review(self):
        with self.assertRaisesRegex(ValueError, "BACKEND_TLS"):
            backup.backend_tls(
                fake_db(backend=(True, "TLSv1.1")),
                security_mode="neon-managed",
                target=TARGET,
            )


if __name__ == "__main__":
    unittest.main()
