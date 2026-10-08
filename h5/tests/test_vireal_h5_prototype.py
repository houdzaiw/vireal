from pathlib import Path
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

    def test_wallet_is_real_and_has_no_payment_packages(self) -> None:
        self.assertIn("/api/v1/app/wallet", self.app)
        self.assertIn("wallet?.ledger", self.app)
        self.assertIn("本期不开放 H5 充值", self.app)
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
        self.assertIn("失败已退款", self.app)
        self.assertIn("系统已自动退款", self.app)

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
