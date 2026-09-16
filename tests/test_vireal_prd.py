from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
PRD = (
    ROOT
    / "outputs"
    / "vireal-wan-video-h5"
    / "prd"
    / "prd_v1.1.html"
)


class VirealFinalPrdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = PRD.read_text(encoding="utf-8") if PRD.exists() else ""

    def test_final_prd_exists(self) -> None:
        self.assertTrue(PRD.exists())

    def test_required_sections_are_present(self) -> None:
        for section_id in (
            "meta",
            "background",
            "goals",
            "users",
            "features",
            "solution",
            "flowcharts",
            "exceptions",
            "analytics",
            "roadmap",
            "annex",
        ):
            self.assertIn(f'id="{section_id}"', self.html)

    def test_version_switcher_links_v10_and_v11(self) -> None:
        self.assertIn('value="prd_v1.0.html"', self.html)
        self.assertIn('value="prd_v1.1.html" selected', self.html)

    def test_user_journey_is_complete(self) -> None:
        for heading in ("阶段", "用户触点", "用户行为", "痛点 / 情绪", "产品机会点"):
            self.assertIn(heading, self.html)

    def test_all_prototype_slices_use_v11_and_sandbox(self) -> None:
        iframe_tags = re.findall(r"<iframe\b[^>]*>", self.html)
        self.assertGreaterEqual(len(iframe_tags), 4)
        self.assertTrue(
            all('../prototype/prototype_v1.1.html' in tag for tag in iframe_tags)
        )
        self.assertEqual(
            len(iframe_tags),
            self.html.count('sandbox="allow-scripts allow-same-origin"'),
        )

    def test_all_v11_flowcharts_are_linked(self) -> None:
        for index in range(1, 7):
            self.assertIn(f"{index:02d}_", self.html)
            self.assertIn("_v1.1.mmd", self.html)

    def test_backend_contract_and_statuses_are_documented(self) -> None:
        for term in (
            "upload_ids",
            "mode",
            "minimax/video-01",
            "wan-video/wan-2.7-r2v",
            "rendering_demo",
            "submission_unknown",
            "execution_type",
            "fallback_reason",
        ):
            self.assertIn(term, self.html)

    def test_final_prd_has_no_pending_placeholders(self) -> None:
        self.assertNotIn("待补充", self.html)


if __name__ == "__main__":
    unittest.main()
