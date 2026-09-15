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


if __name__ == "__main__":
    unittest.main()
