"""Exercise the actual GET function with synthetic dependencies, no app imports.

Do not load backend conftest/settings/.env or connect to a database. The AST
is used only to remove decorators/type annotations, not to replace the body.
"""

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import unittest


class PublicAvailabilityOfflineTests(unittest.TestCase):
    def config(
        self,
        *,
        enabled=False,
        region=True,
        acceptance=False,
        identity=False,
        signup=False,
        recharge=False,
        generation_mode=False,
        payment_mode=False,
        setup_mode=False,
        window_open=False,
        country=None,
    ):
        path = (
            Path(__file__).resolve().parents[2] / "backend/app/api/routes/app_paypal.py"
        )
        function = next(
            n
            for n in ast.parse(path.read_text()).body
            if isinstance(n, ast.FunctionDef) and n.name == "payment_config"
        )
        function.decorator_list = []
        function.returns = None
        for arg in function.args.args:
            arg.annotation = None
        settings = SimpleNamespace(
            APP_GLOBAL_DAILY_REAL_SUBMISSIONS=30,
            APP_VIDEO_SUBMISSIONS_ENABLED=enabled,
            APP_LIVE_ACCEPTANCE_ENABLED=acceptance,
            PAYPAL_ENVIRONMENT="sandbox",
            PAYPAL_CLIENT_ID="synthetic-public-id",
            APP_PUBLIC_REGISTRATION_ENABLED=signup,
            PAYPAL_ENABLED=recharge,
            APP_SUPPORT_EMAIL="support@example.invalid",
            APP_GENERATION_ACCEPTANCE_ENABLED=generation_mode,
            APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED=payment_mode,
            APP_CONTROLLED_CN_ACCOUNT_SETUP_ENABLED=setup_mode,
            APP_GENERATION_ACCEPTANCE_EXPIRES_AT=None,
            APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT=None,
            APP_CONTROLLED_CN_ACCOUNT_SETUP_EXPIRES_AT=None,
        )
        response = SimpleNamespace(headers={})
        namespace = {
            "datetime": datetime,
            "UTC": UTC,
            "settings": settings,
            "global_real_count": lambda **_: 0,
            "region_allowed": lambda _: region,
            "acceptance_request_allowed": lambda _: identity,
            "edge_country": lambda _: country or ("US" if region else None),
            "controlled_cn_account_setup_enabled": lambda: window_open,
            "generation_acceptance_user": lambda *_: None,
            "generation_acceptance_task": lambda *_: None,
            "generation_acceptance_window_open": lambda: window_open,
            "generation_acceptance_mode_safe": lambda: window_open,
            "payment_only_user": lambda *_: None,
            "payment_only_order_created": lambda *_: False,
            "grant_for_user": lambda *_: None,
            "valid_grant": lambda *_, **__: False,
            "payment_only_acceptance_enabled": lambda: window_open,
            "internal_acceptance_enabled": lambda: False,
            "PAYMENT_ONLY_COUNTRIES": {"CN", "HK"},
            "controlled_registration_enabled": lambda: False,
            "paypal_configured": lambda: True,
            "utc_day_bounds": lambda now: (now, now + timedelta(days=1)),
            "PRODUCTS": {},
        }
        exec(
            compile(
                ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])),
                str(path),
                "exec",
            ),
            namespace,
        )
        result = namespace["payment_config"](object(), response, object())
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        return result

    def test_disabled_submission_gate_remains_false_even_with_signup_and_recharge(self):
        data = self.config(signup=True, recharge=True)
        self.assertIs(data["uploads_enabled"], False)
        self.assertIs(data["generation_enabled"], False)

    def test_enabled_submission_gate_is_independent_of_signup_and_recharge(self):
        data = self.config(enabled=True)
        self.assertIs(data["uploads_enabled"], True)
        self.assertIs(data["generation_enabled"], True)
        self.assertIs(data["registration_enabled"], False)
        self.assertIs(data["recharge_enabled"], False)

    def test_region_and_live_identity_cannot_be_bypassed(self):
        for kwargs in [dict(region=False), dict(acceptance=True, identity=False)]:
            with self.subTest(**kwargs):
                data = self.config(enabled=True, **kwargs)
                self.assertIs(data["uploads_enabled"], False)
                self.assertIs(data["generation_enabled"], False)

    def test_an_identity_cannot_override_the_submission_kill_switch(self):
        data = self.config(enabled=False, acceptance=True, identity=True)
        self.assertIs(data["uploads_enabled"], False)
        self.assertIs(data["generation_enabled"], False)

    def test_only_two_non_sensitive_boolean_fields_added(self):
        data = self.config()
        self.assertIs(type(data["uploads_enabled"]), bool)
        self.assertIs(type(data["generation_enabled"]), bool)
        self.assertFalse(
            any("secret" in key or "password" in key or "token" in key for key in data)
        )

    def test_raw_private_modes_block_ordinary_hints_even_if_expired_or_invalid(self):
        for flag in ("generation_mode", "payment_mode", "setup_mode"):
            for window_open in (False, True):
                with self.subTest(flag=flag, window_open=window_open):
                    data = self.config(
                        enabled=True,
                        signup=True,
                        recharge=True,
                        window_open=window_open,
                        **{flag: True},
                    )
                    self.assertIs(data["uploads_enabled"], False)
                    self.assertIs(data["generation_enabled"], False)
                    self.assertIs(data["registration_enabled"], False)

    def test_private_sign_in_hint_is_not_a_generation_entitlement(self):
        data = self.config(
            enabled=True,
            region=False,
            country="CN",
            generation_mode=True,
            window_open=True,
        )
        self.assertIs(data["generation_acceptance_sign_in_enabled"], True)
        self.assertIs(data["generation_acceptance_allowed"], False)
        self.assertIs(data["uploads_enabled"], False)
        self.assertIs(data["generation_enabled"], False)


if __name__ == "__main__":
    unittest.main()
