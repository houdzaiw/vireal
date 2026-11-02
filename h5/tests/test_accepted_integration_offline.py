"""Offline provenance/guard checks. Never import application settings or DB fixtures."""

import ast
import json
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
BASE = "b017fccf2373b40508aec9bcafa4cac5adfd5830"
INTEGRATED_BASE = "9e30a0fc98202a9cc0e3e967e089fa02adb68df9"


def accepted(path, ref=BASE):
    return subprocess.check_output(
        ["git", "show", f"{ref}:{path}"], cwd=ROOT, text=True
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
        # The accepted local integration now also authorizes pilot admission at
        # customer order/capture boundaries. Undo only those explicit additions;
        # reconciliation, fulfillment, recovery and all other code stay exact.
        path = "backend/app/api/routes/app_paypal.py"
        old, new = ast.parse(accepted(path)), ast.parse(current(path))

        class UndoPilot(ast.NodeTransformer):
            def visit_ImportFrom(self, node):
                return None if node.module == "app.services.pilot_access" else node

            def visit_Expr(self, node):
                if (
                    isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id == "require_pilot_commerce"
                ):
                    return None
                return self.generic_visit(node)

            def visit_Call(self, node):
                if (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "require_new_commerce_user"
                ):
                    self_outer.assertEqual(
                        {kw.arg for kw in node.keywords},
                        {"session", "user", "verify_profile"},
                    )
                    node.keywords = []
                return node

            def visit_FunctionDef(self, node):
                if node.name == "payment_config":
                    return None
                if node.name == "capture_paypal_order":
                    node.args.args = [
                        arg for arg in node.args.args if arg.arg != "request"
                    ]
                return self.generic_visit(node)

        self_outer = self
        old.body = [
            n
            for n in old.body
            if not isinstance(n, ast.FunctionDef) or n.name != "payment_config"
        ]
        new = UndoPilot().visit(new)
        self.assertEqual(ast.dump(old), ast.dump(new))

    def test_accepted_config_only_adds_explicit_staging_configuration(self):
        # Preserve the already accepted staging login guards, adding only the
        # default-off pilot and positive global cap, and rejecting mixed modes.
        path = "backend/app/core/config.py"
        old, new = ast.parse(accepted(path)), ast.parse(current(path))

        class UndoPilot(ast.NodeTransformer):
            def visit_AnnAssign(self, node):
                if isinstance(node.target, ast.Name) and node.target.id in {
                    "APP_PILOT_ENABLED",
                    "APP_PILOT_INVITED_EMAILS",
                    "APP_GLOBAL_MAX_CONCURRENT_VIDEO_TASKS",
                }:
                    return None
                return node

            def visit_FunctionDef(self, node):
                if node.name in {"_validate_pilot_emails", "pilot_configuration_safe"}:
                    return None
                return self.generic_visit(node)

            def visit_If(self, node):
                test = ast.unparse(node.test)
                if test in {
                    "self.APP_PILOT_ENABLED and (not self.pilot_configuration_safe())",
                    "self.APP_PILOT_ENABLED and not self.pilot_configuration_safe()",
                    "self.APP_GLOBAL_MAX_CONCURRENT_VIDEO_TASKS < 1",
                }:
                    return None
                return self.generic_visit(node)

            def visit_BoolOp(self, node):
                node.values = [
                    v
                    for v in node.values
                    if ast.unparse(v) != "not self.APP_PILOT_ENABLED"
                ]
                return self.generic_visit(node)

        new = UndoPilot().visit(new)
        self.assertEqual(ast.dump(old), ast.dump(new))
        source = current(path)
        self.assertIn("APP_PILOT_ENABLED: bool = False", source)
        self.assertIn("APP_PILOT_INVITED_EMAILS: list[EmailStr] = []", source)
        self.assertIn("APP_GLOBAL_MAX_CONCURRENT_VIDEO_TASKS: int = 1", source)

    def test_accepted_session_logic_is_preserved_around_staging_guards(self):
        path = "backend/app/api/routes/app_auth.py"
        old, new = ast.parse(accepted(path)), ast.parse(current(path))

        class UndoPilot(ast.NodeTransformer):
            def visit_ImportFrom(self, node):
                return None if node.module == "app.services.pilot_access" else node

            def visit_Assign(self, node):
                if any(
                    isinstance(t, ast.Name)
                    and t.id in {"pilot_requested", "pilot_admission"}
                    for t in node.targets
                ):
                    return None
                return node

            def visit_If(self, node):
                if (
                    isinstance(node.test, ast.BoolOp)
                    and isinstance(node.test.values[0], ast.Name)
                    and node.test.values[0].id == "pilot_admission"
                ):
                    return None
                if (
                    isinstance(node.test, ast.BoolOp)
                    and isinstance(node.test.op, ast.Or)
                    and "pilot_requested" in ast.unparse(node.test)
                ):
                    return None
                return self.generic_visit(node)

            def visit_BoolOp(self, node):
                node.values = [
                    v for v in node.values if ast.unparse(v) != "not pilot_admission"
                ]
                return self.generic_visit(node)

        self.assertEqual(ast.dump(old), ast.dump(UndoPilot().visit(new)))

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
                if name == "paymentCheckout":
                    candidate = candidate.replace(
                        "    if (!pilotCommerceAllowed()) return null\n", "", 1
                    )
                elif name == "signupAvailable":
                    candidate = candidate.replace(
                        "    if (state.commerce?.pilot_mode === true) return Boolean(!controlled && pilotLanding\n"
                        "      && !accountSetupRestricted() && state.commerce?.region_allowed === true\n"
                        "      && state.commerce.pilot_registration_enabled === true)\n",
                        "",
                        1,
                    )
                elif name == "walletPage":
                    candidate = candidate.replace(
                        "const available = pilotCommerceAllowed() && ",
                        "const available = ",
                        1,
                    )
                self.assertEqual(js_function(old, name), candidate)

    def test_legacy_order_route_only_adds_the_hosted_write_rejection(self):
        path = "backend/app/api/routes/app_orders.py"
        old, new = ast.parse(accepted(path)), ast.parse(current(path))
        function = next(
            node
            for node in new.body
            if isinstance(node, ast.FunctionDef) and node.name == "create_order"
        )
        guard = ast.parse(
            'if settings.ENVIRONMENT != "local":\n'
            '    raise HTTPException(403, "Legacy mobile payment orders are unavailable")'
        ).body[0]
        self.assertEqual(ast.dump(function.body[-2]), ast.dump(guard))
        self.assertEqual(
            ast.dump(function.body[-1].value.func),
            ast.dump(ast.parse("crud.create_app_order", mode="eval").body),
        )
        del function.body[-2]
        # Retain every historical read and special-mode branch verbatim in AST.
        self.assertEqual(ast.dump(old), ast.dump(new))

    def test_previously_accepted_pilot_additions_remain_exact(self):
        # These additions were untracked in the original local-only check.
        # Pin them to the reviewed integration instead of broadly allowing edits.
        for path in (
            "backend/app/services/pilot_access.py",
            "backend/tests/api/routes/test_global_video_concurrency.py",
            "backend/tests/api/routes/test_pilot_admission.py",
            "h5/tests/browser/pilot-admission.spec.ts",
        ):
            with self.subTest(path=path):
                self.assertEqual(accepted(path, INTEGRATED_BASE), current(path))

    def test_h5_workflow_only_adds_history_and_complete_offline_regression(self):
        path = ".github/workflows/test-h5.yml"
        old, new = accepted(path), current(path)
        additions = (
            "          # Offline provenance checks compare against accepted historical commits.\n"
            "          fetch-depth: 0\n",
            "      - name: Run H5 offline regression tests\n"
            "        run: bun run test:offline\n",
        )
        self.assertLess(new.index("run: bun ci"), new.index(additions[1]))
        self.assertLess(new.index(additions[1]), new.index("run: bun run test\n"))
        for addition in additions:
            self.assertEqual(new.count(addition), 1)
            new = new.replace(addition, "", 1)
        self.assertEqual(old, new)

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
                ".github/workflows/test-h5.yml",
                "README.md",
                "backend/app/api/routes/app_orders.py",
                "backend/app/api/routes/app_paypal.py",
                "backend/app/api/routes/app_auth.py",
                "backend/app/core/config.py",
                "backend/app/api/routes/app_video_tasks.py",
                "backend/app/services/video_quota.py",
                "backend/app/services/commercial_access.py",
                "backend/app/services/generation_acceptance.py",
                "backend/app/services/pilot_access.py",
                "backend/tests/api/routes/test_global_video_concurrency.py",
                "backend/tests/api/routes/test_pilot_admission.py",
                "backend/tests/api/routes/test_legacy_order_gate.py",
                "backend/tests/core/test_config_v12.py",
                "backend/tests/api/routes/test_app_video_tasks.py",
                "backend/app/services/staging_login_acceptance.py",
                "backend/tests/api/routes/test_staging_login_acceptance.py",
                "h5/src/vireal-app.js",
                "h5/outputs/vireal-wan-video-h5/prototype/vireal-auth.js",
                "h5/package.json",
                "h5/tests/browser/vireal-v1.2.spec.ts",
                "h5/tests/browser/staging-login-acceptance.spec.ts",
                "h5/tests/browser/pilot-admission.spec.ts",
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
