from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = (
    ROOT
    / "outputs"
    / "vireal-wan-video-h5"
    / "prototype"
    / "prototype_v1.1.html"
)
BUILD_SCRIPT = ROOT / "scripts" / "build-vireal-pages.sh"
AUTH_ENTRY = PROTOTYPE.parent / "vireal-auth.js"
README = ROOT / "outputs" / "vireal-wan-video-h5" / "README.md"


class VirealH5PrototypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = PROTOTYPE.read_text(encoding="utf-8") if PROTOTYPE.exists() else ""
        cls.build_script = BUILD_SCRIPT.read_text(encoding="utf-8")
        cls.auth_entry = AUTH_ENTRY.read_text(encoding="utf-8")
        cls.readme = README.read_text(encoding="utf-8")

    def test_v11_prototype_exists(self) -> None:
        self.assertTrue(PROTOTYPE.exists())

    def test_pages_build_uses_v11(self) -> None:
        self.assertIn("prototype_v1.1.html", self.build_script)

    def test_production_auth_uses_bundled_clerk(self) -> None:
        self.assertIn('name="clerk-publishable-key"', self.html)
        self.assertIn('/assets/vireal-auth.js', self.html)
        self.assertIn("initializeClerkSession", self.html)
        self.assertIn("clerk.session.getToken()", self.html)
        self.assertNotIn("device-login", self.html)
        self.assertNotIn("123456", self.html)
        self.assertNotIn("virealAppAccessToken", self.html)
        self.assertIn("/api/v1/app/auth/logout", self.html)
        self.assertIn('import { ui } from "@clerk/ui"', self.auth_entry)
        self.assertIn("await clerk.load({ ui })", self.auth_entry)
        logout_handler = self.html[
            self.html.index("document.getElementById('logoutButton')") :
        ]
        self.assertLess(
            logout_handler.index("await revokeBackendSession()"),
            logout_handler.index("await window.VirealClerk.signOut()"),
        )

    def test_pages_build_requires_clerk_publishable_key(self) -> None:
        self.assertIn("VITE_CLERK_PUBLISHABLE_KEY is required", self.build_script)
        self.assertIn("vireal-auth.js", self.build_script)

    def test_production_styles_are_built_locally(self) -> None:
        self.assertIn('/assets/vireal.css', self.html)
        self.assertNotIn('cdn.tailwindcss.com', self.html)
        self.assertIn('bunx tailwindcss', self.build_script)

    def test_compact_generation_mode_switch_exists(self) -> None:
        self.assertIn('id="generationModeSwitch"', self.html)
        self.assertIn('data-mode="standard"', self.html)
        self.assertIn('data-mode="advanced"', self.html)

    def test_standard_mode_is_the_default(self) -> None:
        self.assertIn("mode: 'standard'", self.html)

    def test_standard_mode_forces_five_seconds(self) -> None:
        self.assertIn("state.mode === 'standard'", self.html)
        self.assertIn("state.duration = 5", self.html)
        self.assertIn("duration10Button.disabled = isStandard", self.html)

    def test_upload_disclosure_is_non_blocking_and_complete(self) -> None:
        self.assertIn("上传即表示你拥有图片使用权", self.html)
        self.assertIn("第三方 AI 服务处理", self.html)
        self.assertIn("24 小时后清理", self.html)
        self.assertNotIn("if (!state.consent)", self.html)

    def test_generation_does_not_spend_or_refund_demo_coins(self) -> None:
        self.assertNotIn("state.balance -= state.cost", self.html)
        self.assertNotIn("refundDemoCoins(task)", self.html)

    def test_free_experience_summary_exists(self) -> None:
        self.assertIn('id="freeExperienceSummary"', self.html)

    def test_idempotency_fingerprint_includes_mode(self) -> None:
        self.assertIn("dance:${state.mode}:${uploadId}:${state.duration}", self.html)

    def test_video_task_request_sends_mode(self) -> None:
        self.assertIn("mode: state.mode", self.html)

    def test_video_task_request_uses_upload_ids_array_contract(self) -> None:
        self.assertIn("upload_ids: [upload.uploadId]", self.html)
        self.assertNotIn("upload_id: upload.uploadId", self.html)

    def test_task_persists_execution_metadata(self) -> None:
        self.assertIn("executionType: payload.execution_type", self.html)
        self.assertIn("isDemo: Boolean(payload.is_demo)", self.html)
        self.assertIn("const quota = payload.quota || payload", self.html)

    def test_demo_rendering_state_and_badge_exist(self) -> None:
        self.assertIn("rendering_demo", self.html)
        self.assertIn("payload.is_demo", self.html)
        self.assertIn('id="demoResultBadge"', self.html)

    def test_bilingual_mode_and_demo_labels_exist(self) -> None:
        for label in (
            "普通模式",
            "高级模式",
            "Standard",
            "Advanced",
            "演示结果",
            "Demo result",
        ):
            self.assertIn(label, self.html)

    def test_progress_copy_is_not_hard_coded_to_wan(self) -> None:
        self.assertNotIn("已提交到 Wan 视频生成队列", self.html)

    def test_execution_label_helper_exists(self) -> None:
        self.assertIn("function executionLabel(task)", self.html)
        self.assertIn("local_demo", self.html)

    def test_v11_title_and_mode_review_route_exist(self) -> None:
        self.assertIn("Vireal · 双模式视频生成 v1.1", self.html)
        self.assertIn("mode: 'create'", self.html)

    def test_readme_names_v11_as_current_prototype(self) -> None:
        self.assertIn("prototype_v1.1.html", self.readme)

    def test_create_renderer_does_not_shadow_translation_helper(self) -> None:
        self.assertNotIn("const t = selectedTemplate()", self.html)
        self.assertNotIn("available.map(t =>", self.html)
        self.assertNotIn("selectable.map(t =>", self.html)

    def test_single_person_dance_is_the_only_creation_template(self) -> None:
        self.assertIn("template: 'dance'", self.html)
        self.assertIn("const available = templates.filter(t => t.id === 'dance')", self.html)
        self.assertIn("const selectable = templates.filter(t => t.id === 'dance')", self.html)
        self.assertNotIn("HUG · WAN VIDEO", self.html)
        self.assertNotIn("<b>牵手 · 10 秒</b>", self.html)

    def test_creation_flow_is_always_silent(self) -> None:
        self.assertIn("document.getElementById('audioSpec').textContent = t('silentSpec')", self.html)
        self.assertNotIn("AI audio", self.html)
        self.assertNotIn("模型环境声", self.html)
        self.assertNotIn("带声音的私人短视频", self.html)
        self.assertNotIn("声音方案", self.html)
        self.assertNotIn("声音与合成", self.html)
        self.assertNotIn("生成环境声并封装 MP4", self.html)


if __name__ == "__main__":
    unittest.main()
