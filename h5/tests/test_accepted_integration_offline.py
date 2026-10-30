"""Offline provenance/guard checks. Never import application settings or DB fixtures."""

import ast
import json
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
BASE = "7fce8165de7658eee31ed2e6e7e42c0a47e0f790"


def accepted(path):
    return subprocess.check_output(
        ["git", "show", f"{BASE}:{path}"], cwd=ROOT, text=True
    )


def current(path):
    return (ROOT / path).read_text()


def js_function(text, name):
    start = re.search(rf"^  (?:async )?function {name}\(", text, re.M)
    if start is None:
        raise AssertionError(f"Missing protected function: {name}")
    end = text.index("\n  }\n", start.start()) + 5
    return text[start.start() : end]


class AcceptedIntegrationOfflineTests(unittest.TestCase):
    def test_backend_only_adds_public_config_hints(self):
        path = "backend/app/api/routes/app_paypal.py"
        old, new = ast.parse(accepted(path)), ast.parse(current(path))
        for tree in (old, new):
            tree.body = [
                node
                for node in tree.body
                if not (
                    isinstance(node, ast.FunctionDef) and node.name == "payment_config"
                )
                and not (
                    isinstance(node, ast.ImportFrom)
                    and node.module == "app.services.staging_login_acceptance"
                    and [alias.name for alias in node.names]
                    == ["staging_sign_in_enabled"]
                )
            ]
        self.assertEqual(ast.dump(old), ast.dump(new))

    def test_accepted_config_only_adds_explicit_staging_configuration(self):
        path = "backend/app/core/config.py"
        old, new = ast.parse(accepted(path)), ast.parse(current(path))
        additions = {
            "STAGING_LOGIN_ACCEPTANCE_ISSUER",
            "STAGING_LOGIN_ACCEPTANCE_ORIGIN",
        }
        new.body = [
            node
            for node in new.body
            if not (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id in additions
                    for target in node.targets
                )
            )
        ]
        settings = next(
            node
            for node in new.body
            if isinstance(node, ast.ClassDef) and node.name == "Settings"
        )
        settings.body = [
            node
            for node in settings.body
            if not (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id.startswith("APP_STAGING_LOGIN_ACCEPTANCE_")
            )
            and not (
                isinstance(node, ast.FunctionDef)
                and node.name == "staging_login_acceptance_configuration_safe"
            )
        ]
        validator = next(
            node
            for node in settings.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_validate_commerce_configuration"
        )
        self.assertIn(
            "APP_STAGING_LOGIN_ACCEPTANCE_ENABLED", ast.unparse(validator.body[0].test)
        )
        validator.body.pop(0)
        self.assertEqual(ast.dump(old), ast.dump(new))

    def test_accepted_session_logic_is_preserved_around_staging_guards(self):
        path = "backend/app/api/routes/app_auth.py"
        old, new = ast.parse(accepted(path)), ast.parse(current(path))
        new.body = [
            node
            for node in new.body
            if not (
                isinstance(node, ast.ImportFrom)
                and node.module == "app.services.staging_login_acceptance"
            )
        ]
        session = next(
            node
            for node in new.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "initialize_clerk_session"
        )

        def added_guard(node):
            if isinstance(node, ast.Assign):
                return any(
                    isinstance(target, ast.Name) and target.id == "staging_request"
                    for target in node.targets
                )
            if isinstance(node, ast.AnnAssign):
                return isinstance(node.target, ast.Name) and node.target.id in {
                    "staging_identity",
                    "staging_user",
                }
            return isinstance(node, ast.If) and (
                isinstance(node.test, ast.Name)
                and node.test.id == "staging_request"
                or isinstance(node.test, ast.BoolOp)
                and isinstance(node.test.values[0], ast.Name)
                and node.test.values[0].id == "staging_request"
            )

        session.body = [node for node in session.body if not added_guard(node)]
        guard = next(
            node
            for node in session.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "require_current_setup_authorization"
        )
        self.assertTrue(added_guard(guard.body[0]))
        guard.body.pop(0)
        self.assertEqual(ast.dump(old), ast.dump(new))

    def test_existing_payment_and_special_mode_functions_are_verbatim(self):
        path = "h5/src/vireal-app.js"
        old, new = accepted(path), current(path)
        protected = (
            "generationAcceptanceAllowed",
            "originalPaymentOrder",
            "paymentCheckout",
            "refreshPayments",
            "recoveryText",
            "inspectPayment",
            "rechargeOrderRow",
            "paymentContext",
            "releasePayPal",
            "paymentInstance",
            "paypalSdk",
            "mountPayPal",
            "selectedVariant",
            "internalAcceptanceNotice",
            "signInRegionAllowed",
            "controlledAccountSetupAllowed",
            "signupAvailable",
            "taskVisual",
            "taskDelivery",
            "generationPage",
            "worksPage",
            "walletPage",
            "startPolling",
            "refreshPlayback",
            "saveTask",
            "deleteTask",
        )
        for name in protected:
            with self.subTest(function=name):
                candidate = js_function(new, name)
                if name == "signInRegionAllowed":
                    candidate = candidate.replace(
                        "    if (stagingLoginView()) return stagingSignInAllowed()\n",
                        "",
                        1,
                    )
                self.assertEqual(js_function(old, name), candidate)

    def test_no_other_accepted_tracked_paths_changed(self):
        changed = set(
            subprocess.check_output(
                ["git", "diff", "--name-only", BASE], cwd=ROOT, text=True
            ).splitlines()
        )
        self.assertLessEqual(
            changed,
            {
                ".env.example",
                "backend/app/api/routes/app_paypal.py",
                "backend/app/api/routes/app_auth.py",
                "backend/app/core/config.py",
                "backend/app/services/staging_login_acceptance.py",
                "backend/tests/api/routes/test_staging_login_acceptance.py",
                "h5/src/vireal-app.js",
                "h5/outputs/vireal-wan-video-h5/prototype/vireal-auth.js",
                "h5/package.json",
                "h5/tests/browser/vireal-v1.2.spec.ts",
                "h5/tests/browser/staging-login-acceptance.spec.ts",
                "h5/playwright.staging-login.config.ts",
                "h5/tests/unit/login-closure.test.mjs",
                "h5/tests/test_vireal_h5_prototype.py",
                "h5/tests/test_public_availability_offline.py",
                "h5/tests/test_accepted_integration_offline.py",
            },
        )
        for path in (
            "h5/bun.lock",
            "backend/app/core/db.py",
            "h5/src/vireal-production.css",
            "h5/src/vireal-v1.2.html",
        ):
            with self.subTest(path=path):
                self.assertEqual(accepted(path), current(path))

    def test_all_accepted_browser_cases_remain_and_prelaunch_script_is_unchanged(self):
        path = "h5/tests/browser/vireal-v1.2.spec.ts"
        # Case bodies and fixture changes are separately reviewed. No original
        # test or dynamically generated scenario may disappear in this package.
        case = r"^\s*(?:test\(|for \(const scenario of).*"
        self.assertEqual(
            re.findall(case, accepted(path), re.M),
            re.findall(case, current(path), re.M),
        )
        old, new = (
            json.loads(accepted("h5/package.json")),
            json.loads(current("h5/package.json")),
        )
        self.assertEqual(old["dependencies"], new["dependencies"])
        self.assertEqual(old["devDependencies"], new["devDependencies"])
        for name, value in old["scripts"].items():
            self.assertEqual(new["scripts"][name], value)


if __name__ == "__main__":
    unittest.main()
