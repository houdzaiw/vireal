from pathlib import Path
import copy
import json
import os
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "vireal-v1.2.html"
APP = ROOT / "src" / "vireal-app.js"
PRODUCTION_CSS = ROOT / "src" / "vireal-production.css"
PROTOTYPE = (
    ROOT / "outputs" / "vireal-wan-video-h5" / "prototype" / "prototype_v1.2.html"
)
BUILD_SCRIPT = ROOT / "scripts" / "build-vireal-pages.sh"
AUTH_ENTRY = PROTOTYPE.parent / "vireal-auth.js"
VERIFY_SCRIPT = ROOT.parent / "scripts" / "verify-production.sh"
CONTRACT_SCRIPT = ROOT.parent / "scripts" / "verify-release-contract.py"
REVIEWED_COMMIT = "a" * 40


def launch_catalog():
    return {
        "categories": [
            {
                "effects": [
                    {
                        "slug": slug,
                        "title_en": slug,
                        "input_image_count": inputs,
                        "poster_url": "/api/v1/app/media-assets/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "preview_video_url": "/api/v1/app/media-assets/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                        "variants": [
                            {"duration_seconds": duration, "coin_cost": 12}
                            for duration in [5, 10]
                        ],
                    }
                    for slug, inputs in [("dance-1", 1), ("romance-1", 2)]
                ]
            }
        ]
    }


def launch_commerce():
    return {
        "environment": "live",
        "country": "US",
        "region_allowed": True,
        "registration_enabled": False,
        "recharge_enabled": False,
        "global_real_limit": 30,
        "global_real_remaining": 30,
        "resets_at": "2026-10-14T00:00:00Z",
        "support_email": "li522903183@gmail.com",
        "products": [
            {"product_id": product, "coins": coins, "amount": cents, "currency": "USD"}
            for product, coins, cents in [
                ("coins_100", 100, 599),
                ("coins_220", 220, 1199),
                ("coins_500", 500, 2499),
            ]
        ],
    }


class ProductionEdgeCheckTests(unittest.TestCase):
    def run_edge_check(
        self,
        *,
        docs_status: int,
        private_status: int = 403,
        commit: str = REVIEWED_COMMIT,
        features: str | None = None,
        catalog=None,
        commerce=None,
        paypal_status="422 ",
        protected_status=401,
    ):
        # Export a shell curl stub so no real service or credential is used.
        curl_stub = r"""
curl() {
  case "${@: -1}" in
    https://h5.example.com/)
      printf '%s' "$TEST_H5_HTML" ;;
    https://h5.example.com/assets/vireal-app.js)
      printf '%s' "$TEST_H5_JS" ;;
    https://api.example.com/api/v1/utils/health-check/)
      printf '%s' 'true' ;;
    https://api.example.com/api/v1/app/effect-catalog)
      printf '%s' "$TEST_CATALOG" ;;
    https://api.example.com/api/v1/app/paypal/config)
      printf '%s' "$TEST_COMMERCE" ;;
    https://api.example.com/api/v1/app/wallet|https://api.example.com/api/v1/app/video-tasks/00000000-0000-0000-0000-000000000000/download)
      printf '%s' "$TEST_PROTECTED_STATUS" ;;
    https://api.example.com/docs)
      printf '%s' "$TEST_DOCS_STATUS" ;;
    https://api.example.com/api/v1/webhooks/replicate)
      printf '%s' '401 ' ;;
    https://api.example.com/api/v1/webhooks/payments/paypal)
      printf '%s' "$TEST_PAYPAL_STATUS" ;;
    https://r2.example.com/private.mp4)
      printf '%s' "$TEST_PRIVATE_STATUS" ;;
    *) return 9 ;;
  esac
}
export -f curl
bash "$1"
"""
        return subprocess.run(
            ["bash", "-c", curl_stub, "edge-check-test", str(VERIFY_SCRIPT)],
            env={
                **os.environ,
                "H5_URL": "https://h5.example.com",
                "API_URL": "https://api.example.com",
                "R2_PRIVATE_OBJECT_URL": "https://r2.example.com/private.mp4",
                "TEST_DOCS_STATUS": str(docs_status),
                "TEST_PRIVATE_STATUS": str(private_status),
                "RELEASE_CHECK_MODE": "closed",
                "EXPECTED_RELEASE_COMMIT": REVIEWED_COMMIT,
                "PYTHON_BIN": sys.executable,
                "TEST_H5_HTML": '<meta name="vireal-api-base-url" content="https://api.example.com"><meta name="vireal-backend-mode" content="1"><meta name="vireal-release" content="v1.2-production"><meta name="clerk-publishable-key" content="pk_live_test">'
                + f'<meta name="vireal-release-commit" content="{commit}">',
                "TEST_H5_JS": features
                if features is not None
                else "/api/v1/app/effect-catalog /api/v1/app/paypal/orders data-refresh-task data-download-task playback_url_expires_at",
                "TEST_CATALOG": json.dumps(
                    catalog if catalog is not None else launch_catalog()
                ),
                "TEST_COMMERCE": json.dumps(
                    commerce if commerce is not None else launch_commerce()
                ),
                "TEST_PAYPAL_STATUS": paypal_status,
                "TEST_PROTECTED_STATUS": str(protected_status),
            },
            capture_output=True,
            text=True,
            timeout=5,
        )

    def test_docs_must_be_inaccessible_at_edge_or_origin(self):
        for status in [403, 404, 200, 302, 500]:
            with self.subTest(status=status):
                result = self.run_edge_check(docs_status=status)
                self.assertEqual(result.returncode == 0, status in {403, 404})

    def test_unsigned_r2_must_deny_access(self):
        for status in [400, 401, 403, 404, 200, 302, 500]:
            with self.subTest(status=status):
                result = self.run_edge_check(docs_status=403, private_status=status)
                self.assertEqual(result.returncode == 0, status in {400, 401, 403, 404})

    def test_old_source_and_missing_payment_recovery_are_rejected(self):
        self.assertNotEqual(
            self.run_edge_check(docs_status=403, commit="b" * 40).returncode, 0
        )
        self.assertNotEqual(
            self.run_edge_check(
                docs_status=403, features="/api/v1/app/effect-catalog"
            ).returncode,
            0,
        )

    def test_old_catalog_and_missing_paypal_receiver_are_rejected(self):
        self.assertNotEqual(
            self.run_edge_check(docs_status=403, catalog={"categories": []}).returncode,
            0,
        )
        for status in ["200 ", "204 ", "404 ", "503 ", "302 https://example.com/"]:
            with self.subTest(status=status):
                self.assertNotEqual(
                    self.run_edge_check(
                        docs_status=403, paypal_status=status
                    ).returncode,
                    0,
                )

    def test_anonymous_wallet_and_download_must_remain_protected(self):
        for status in [200, 302, 404, 500]:
            with self.subTest(status=status):
                self.assertNotEqual(
                    self.run_edge_check(
                        docs_status=403, protected_status=status
                    ).returncode,
                    0,
                )

    def test_checks_never_claim_real_acceptance_or_create_device_accounts(self):
        result = self.run_edge_check(docs_status=403)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no payment or generation was exercised", result.stdout)
        self.assertIn(
            "Region-scoped checks do not prove global switches", result.stdout
        )
        self.assertNotIn("/app/auth/device-login", VERIFY_SCRIPT.read_text())


class ReleaseContractTests(unittest.TestCase):
    def check(self, contract, data, mode="closed"):
        return subprocess.run(
            [sys.executable, str(CONTRACT_SCRIPT), contract, mode],
            input=json.dumps(data),
            capture_output=True,
            text=True,
            timeout=5,
        )

    def test_selected_catalog_accepts_only_complete_5_10_combinations(self):
        self.assertEqual(self.check("catalog", launch_catalog()).returncode, 0)
        for change in [
            "extra",
            "empty",
            "slug",
            "duration",
            "cost",
            "inputs",
            "private",
        ]:
            data = copy.deepcopy(launch_catalog())
            effects = data["categories"][0]["effects"]
            if change == "extra":
                effects.append(copy.deepcopy(effects[0]))
            elif change == "empty":
                effects.clear()
            elif change == "slug":
                effects[0]["slug"] = "hidden-1"
            elif change == "duration":
                effects[0]["variants"][1]["duration_seconds"] = 15
            elif change == "cost":
                effects[0]["variants"][0]["coin_cost"] = 0
            elif change == "inputs":
                effects[1]["input_image_count"] = 1
            elif change == "private":
                effects[0]["variants"][0]["prompt"] = "private-canary-token"
            with self.subTest(change=change):
                result = self.check("catalog", data)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("private-canary-token", result.stdout + result.stderr)

    def test_public_checks_require_real_managed_media_references(self):
        self.assertEqual(
            self.check("catalog", launch_catalog(), "public").returncode, 0
        )
        for field in ["poster_url", "preview_video_url"]:
            for value in [None, "https://example.com/placeholder.png", ""]:
                data = launch_catalog()
                data["categories"][0]["effects"][0][field] = value
                self.assertNotEqual(self.check("catalog", data, "public").returncode, 0)
                self.assertEqual(self.check("catalog", data).returncode, 0)

    def test_prices_capacity_and_observed_closed_flags_are_verified(self):
        self.assertEqual(self.check("commerce", launch_commerce()).returncode, 0)
        for field, value in [
            ("environment", "sandbox"),
            ("global_real_limit", 3),
            ("global_real_remaining", -1),
            ("global_real_remaining", True),
            ("registration_enabled", True),
            ("recharge_enabled", True),
            ("support_email", "wrong@example.com"),
        ]:
            data = launch_commerce()
            data[field] = value
            self.assertNotEqual(self.check("commerce", data).returncode, 0)
        for field, value in [("coins", 999), ("amount", 599.0), ("currency", "CNY")]:
            data = launch_commerce()
            data["products"][0][field] = value
            self.assertNotEqual(self.check("commerce", data).returncode, 0)

    def test_public_mode_does_not_bypass_region_or_closed_payment_state(self):
        data = launch_commerce()
        data.update(
            registration_enabled=True,
            recharge_enabled=True,
            client_id="public-client-id",
        )
        self.assertEqual(self.check("commerce", data, "public").returncode, 0)
        for field, value in [
            ("country", "CN"),
            ("country", None),
            ("country", "XX"),
            ("region_allowed", False),
            ("registration_enabled", False),
            ("recharge_enabled", False),
            ("client_id", None),
            ("global_real_remaining", 0),
        ]:
            invalid = {**data, field: value}
            self.assertNotEqual(self.check("commerce", invalid, "public").returncode, 0)

    def test_malformed_responses_fail_without_echoing_payloads(self):
        for contract in ["catalog", "commerce"]:
            for data in [
                None,
                [],
                "private-canary-token",
                {"categories": [None]},
                {"products": [None]},
            ]:
                result = self.check(contract, data)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("private-canary-token", result.stdout + result.stderr)


class VirealH5ProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = SOURCE.read_text(encoding="utf-8")
        cls.app = APP.read_text(encoding="utf-8")
        cls.css = PRODUCTION_CSS.read_text(encoding="utf-8")
        cls.build_script = BUILD_SCRIPT.read_text(encoding="utf-8")
        cls.auth_entry = AUTH_ENTRY.read_text(encoding="utf-8")

    def test_v12_visual_reference_is_preserved(self) -> None:
        self.assertTrue(PROTOTYPE.exists())
        self.assertNotEqual(SOURCE, PROTOTYPE)

    def test_production_has_separate_v12_source(self) -> None:
        self.assertTrue(SOURCE.exists())
        self.assertIn('content="v1.2-production"', self.html)
        self.assertIn("vireal-v1.2.html", self.build_script)

    def test_build_stamps_a_reviewed_commit_and_rejects_invalid_values(self) -> None:
        self.assertIn('name="vireal-release-commit"', self.html)
        self.assertIn("__VIREAL_RELEASE_COMMIT__", self.build_script)
        result = subprocess.run(
            ["bash", str(BUILD_SCRIPT)],
            env={**os.environ, "VIREAL_RELEASE_COMMIT": "invalid-commit"},
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("40-character Git commit", result.stderr)

    def test_v11_fallback_is_built(self) -> None:
        self.assertIn("fallback/v1.1", self.build_script)
        self.assertIn("prototype_v1.1.html", self.build_script)

    def test_production_assets_are_local(self) -> None:
        self.assertNotIn("cdn.tailwindcss.com", self.html)
        self.assertIn("/assets/vireal-v1.2.css", self.html)
        self.assertIn("/assets/vireal-production.css", self.html)
        self.assertIn("/assets/vireal-app.js", self.html)

    def test_build_requires_clerk_and_api(self) -> None:
        self.assertIn("VIREAL_API_BASE_URL is required", self.build_script)
        self.assertIn("VITE_CLERK_PUBLISHABLE_KEY is required", self.build_script)
        self.assertIn("VIREAL_API_BASE_URL must be an HTTPS origin", self.build_script)

    def test_clerk_is_bundled(self) -> None:
        self.assertIn('name="clerk-publishable-key"', self.html)
        self.assertIn('import { Clerk } from "@clerk/clerk-js"', self.auth_entry)
        self.assertIn("await clerk.load({ ui })", self.auth_entry)

    def test_catalog_is_dynamic(self) -> None:
        self.assertIn("/api/v1/app/effect-catalog", self.app)
        self.assertIn("state.catalog.categories", self.app)
        self.assertNotIn("API_SNAPSHOT", self.app)

    def test_catalog_supports_dynamic_category_and_effect_counts(self) -> None:
        self.assertIn("categories().map", self.app)
        self.assertIn("category?.effects || []", self.app)
        self.assertNotIn("slice(0, 3)", self.app)

    def test_missing_media_uses_numbered_gradient(self) -> None:
        self.assertIn("surface-number", self.app)
        self.assertIn("category?.tones", self.app)
        self.assertIn("has-media", self.css)

    def test_public_catalog_never_embeds_model_or_prompt_fields(self) -> None:
        catalog_render = self.app[
            self.app.index("function homePage") : self.app.index(
                "function generatePage"
            )
        ]
        self.assertNotIn("prompt", catalog_render)
        self.assertNotIn("model", catalog_render)

    def test_generate_flow_uses_server_effect_contract(self) -> None:
        self.assertIn("effect_id: effect.id", self.app)
        self.assertIn("variant_id: variant.id", self.app)
        self.assertIn("upload_ids: uploadIds", self.app)
        self.assertIn('"Idempotency-Key": attempt.key', self.app)
        self.assertIn("key: crypto.randomUUID()", self.app)

    def test_upload_count_is_effect_driven(self) -> None:
        self.assertIn("effect.input_image_count", self.app)
        self.assertIn('effect.input_image_count === 2 ? " two"', self.app)

    def test_price_and_duration_are_variant_driven(self) -> None:
        self.assertIn("variant.duration_seconds", self.app)
        self.assertIn("variant.coin_cost", self.app)
        self.assertNotIn("state.balance -=", self.app)

    def test_wallet_uses_real_server_priced_paypal_orders(self) -> None:
        self.assertIn("/api/v1/app/wallet", self.app)
        self.assertIn("wallet?.ledger", self.app)
        self.assertIn("/api/v1/app/paypal/orders", self.app)
        self.assertIn("/api/v1/app/paypal/config", self.app)
        self.assertIn("coin_quantity", self.app)
        self.assertIn("order.fulfilled_at", self.app)
        self.assertNotIn("data-pack", self.app)
        self.assertNotIn("确认充值", self.app)

    def test_bottom_navigation_has_only_three_entries(self) -> None:
        nav = self.app[
            self.app.index("function nav(active)") : self.app.index("function homePage")
        ]
        self.assertEqual(nav.count("<button"), 3)
        self.assertIn("发现", nav)
        self.assertIn("作品", nav)
        self.assertIn("我的", nav)
        self.assertNotIn("金币", nav)

    def test_wallet_entry_is_top_balance(self) -> None:
        self.assertIn('class="energy-pill" data-route="wallet"', self.app)

    def test_works_are_loaded_from_backend(self) -> None:
        self.assertIn("/api/v1/app/video-tasks?skip=0&limit=50", self.app)
        self.assertIn("data-delete-task", self.app)
        self.assertIn('method: "DELETE"', self.app)

    def test_task_polling_and_restore_routes_exist(self) -> None:
        self.assertIn("function startPolling", self.app)
        self.assertIn("/api/v1/app/video-tasks/${taskId}", self.app)
        self.assertIn("generation", self.app)

    def test_submission_unknown_copy_does_not_promise_refund(self) -> None:
        self.assertIn("submission_unknown", self.app)
        self.assertIn("确认前不会自动退款", self.app)

    def test_failure_copy_mentions_server_refund(self) -> None:
        self.assertIn("task.coin_refunded_at", self.app)
        self.assertIn("金币已退回钱包", self.app)
        self.assertIn("这不代表发生退款", self.app)
        self.assertNotIn("若产生扣币，系统已自动退款", self.app)

    def test_client_does_not_send_model_price_or_prompt(self) -> None:
        create_task = self.app[
            self.app.index("async function createTask") : self.app.index(
                "function startPolling"
            )
        ]
        self.assertNotIn("coin_cost", create_task)
        self.assertNotIn("model:", create_task)
        self.assertNotIn("prompt:", create_task)

    def test_adult_authorization_ui_is_absent(self) -> None:
        self.assertNotIn("成人授权", self.app)
        self.assertNotIn("adult_authorization", self.app)

    def test_real_quota_is_displayed(self) -> None:
        self.assertIn("daily_remaining", self.app)
        self.assertIn("concurrent_remaining", self.app)

    def test_r2_upload_endpoint_is_used(self) -> None:
        self.assertIn("/api/v1/app/uploads/images", self.app)
        self.assertIn("FormData", self.app)

    def test_auth_session_is_initialized(self) -> None:
        self.assertIn("/api/v1/app/auth/session", self.app)
        self.assertIn("clerk.session.id", self.app)
        self.assertNotIn("device-login", self.app)

    def test_logout_revokes_backend_before_clerk(self) -> None:
        logout = self.app[
            self.app.index('if (event.target.closest("[data-logout]"))') :
        ]
        self.assertLess(
            logout.index("/api/v1/app/auth/logout"),
            logout.index("VirealClerk?.signOut"),
        )

    def test_mobile_shell_has_no_horizontal_overflow(self) -> None:
        self.assertIn("overflow-x: hidden", PROTOTYPE.read_text(encoding="utf-8"))
        self.assertIn("width: 100%", self.css)


if __name__ == "__main__":
    unittest.main()
