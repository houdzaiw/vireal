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


class VirealH5PrototypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = PROTOTYPE.read_text(encoding="utf-8") if PROTOTYPE.exists() else ""
        cls.build_script = BUILD_SCRIPT.read_text(encoding="utf-8")

    def test_v11_prototype_exists(self) -> None:
        self.assertTrue(PROTOTYPE.exists())

    def test_pages_build_uses_v11(self) -> None:
        self.assertIn("prototype_v1.1.html", self.build_script)

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

    def test_task_persists_execution_metadata(self) -> None:
        self.assertIn("executionType: payload.execution_type", self.html)
        self.assertIn("isDemo: Boolean(payload.is_demo)", self.html)

    def test_demo_rendering_state_and_badge_exist(self) -> None:
        self.assertIn("rendering_demo", self.html)
        self.assertIn("payload.is_demo", self.html)
        self.assertIn('id="demoResultBadge"', self.html)


if __name__ == "__main__":
    unittest.main()
