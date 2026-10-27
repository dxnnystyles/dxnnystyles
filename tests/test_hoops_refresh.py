from pathlib import Path
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
ASSETS = REPO / "assets/hoops"
SCRIPTS = REPO / "scripts"
import sys
sys.path.insert(0, str(SCRIPTS))
from prepare_hoops_assets import FILES, NS, prepare_assets, validate_asset_directory


class HoopsRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hoops-refresh-test-")
        self.root = Path(self.temp.name)
        self.generated = self.root / "generated"
        self.output = self.root / "publish-ready"
        self.generated.mkdir()
        shutil.copy2(ASSETS / "hoops.svg", self.generated / "hoops.svg")
        shutil.copy2(ASSETS / "hoops-dark.svg", self.generated / "hoops-dark.svg")
        self.panel_template = ASSETS / "hoops-profile-dark-panel.svg"

    def tearDown(self):
        self.temp.cleanup()

    def run_prepare(self):
        prepare_assets(self.generated, self.output, self.panel_template, "2026-10-27")

    def test_derives_and_validates_all_three_assets_from_same_generated_data(self):
        self.run_prepare()
        self.assertEqual({path.name for path in self.output.iterdir()}, set(FILES))
        roots = {name: ET.parse(self.output / name).getroot() for name in FILES}
        for name, root in roots.items():
            self.assertEqual(root.tag, f"{{{NS}}}svg")
            self.assertEqual((root.get("width"), root.get("height"), root.get("viewBox")), ("900", "218", "0 0 900 218"))
            self.assertIsNotNone(root.find(f"{{{NS}}}title"))
            self.assertIsNotNone(root.find(f"{{{NS}}}desc"))
            self.assertEqual(len([node for node in root.iter(f"{{{NS}}}text") if node.get("id") == "hoops-updated-at"]), 1)
            self.assertIn("Updated 2026-10-27 UTC", " ".join(node.text or "" for node in root.iter(f"{{{NS}}}text")))
            self.assertIn("@keyframes", root.find(f"{{{NS}}}style").text)
        panel = roots["hoops-profile-dark-panel.svg"]
        backgrounds = [node for node in panel.iter(f"{{{NS}}}rect") if node.get("id") == "widget-dark-panel"]
        self.assertEqual(len(backgrounds), 1)
        self.assertEqual(backgrounds[0].get("fill"), "#161b22")
        dark_backgrounds = [node for node in roots["hoops-dark.svg"].iter(f"{{{NS}}}rect") if node.get("id") == "widget-dark-panel"]
        self.assertEqual(dark_backgrounds, [])
        light_background = next(node for node in roots["hoops.svg"].iter(f"{{{NS}}}rect") if node.get("id") == "hoops-theme-independent-panel")
        self.assertEqual(light_background.get("fill"), "#ffffff")
        self.assertEqual(
            [node.text for node in roots["hoops-dark.svg"].findall(f"{{{NS}}}style")],
            [node.text for node in panel.findall(f"{{{NS}}}style")],
        )
        self.assertIn("public dxnnystyles activity only", roots["hoops.svg"].find(f"{{{NS}}}desc").text)
        self.assertIn("fixed charcoal panel", panel.find(f"{{{NS}}}desc").text)

    def test_panel_tracks_changed_generated_source_and_repeat_is_byte_stable(self):
        self.run_prepare()
        first = {name: (self.output / name).read_bytes() for name in FILES}
        self.run_prepare()
        self.assertEqual(first, {name: (self.output / name).read_bytes() for name in FILES})

        path = self.generated / "hoops-dark.svg"
        root = ET.parse(path).getroot()
        score = next(node for node in root.iter(f"{{{NS}}}text") if node.get("class") == "score0")
        score.text = "999"
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=False)
        self.run_prepare()
        panel = ET.parse(self.output / "hoops-profile-dark-panel.svg").getroot()
        panel_score = next(node for node in panel.iter(f"{{{NS}}}text") if node.get("class") == "score0")
        self.assertEqual(panel_score.text, "999")
        self.assertNotEqual(first["hoops-profile-dark-panel.svg"], (self.output / "hoops-profile-dark-panel.svg").read_bytes())

    def test_invalid_partial_generation_preserves_last_prepared_set(self):
        self.run_prepare()
        last_good = {name: (self.output / name).read_bytes() for name in FILES}
        (self.generated / "hoops-dark.svg").write_text("<svg><broken>", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid Hoops input"):
            self.run_prepare()
        self.assertEqual(last_good, {name: (self.output / name).read_bytes() for name in FILES})
        shutil.copy2(ASSETS / "hoops-dark.svg", self.generated / "hoops-dark.svg")
        self.run_prepare()
        self.assertEqual(last_good, {name: (self.output / name).read_bytes() for name in FILES})

    def test_transferred_artifact_requires_exact_files_and_matching_date(self):
        self.run_prepare()
        validate_asset_directory(self.output)
        (self.output / "unexpected.txt").write_text("not an SVG", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "exactly"):
            validate_asset_directory(self.output)
        (self.output / "unexpected.txt").unlink()

        path = self.output / "hoops-dark.svg"
        root = ET.parse(path).getroot()
        label = next(node for node in root.iter(f"{{{NS}}}text") if node.get("id") == "hoops-updated-at")
        label.text = "Updated 2026-10-28 UTC"
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=False)
        with self.assertRaisesRegex(ValueError, "mismatched update dates"):
            validate_asset_directory(self.output)

    def test_workflow_promotes_only_the_complete_trio_and_noops_when_unchanged(self):
        workflow = (REPO / ".github/workflows/update-hoops.yml").read_text(encoding="utf-8")
        self.assertIn("permissions: {}", workflow)
        generate, publish = workflow.split("  publish:", 1)
        self.assertIn("permissions:\n      contents: read", generate)
        self.assertIn("contents: write", publish)
        self.assertNotIn("GITHUB_TOKEN:", generate)
        push_step = publish.split("      - name: Push the prepared Hoops commit", 1)[1]
        self.assertNotIn("GITHUB_TOKEN:", publish.split("      - name: Push the prepared Hoops commit", 1)[0])
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", push_step)
        self.assertIn("HarrisJDCampbell/hoops@c90b483d3f7e61544afaee4c105a51d410346cb2", generate)
        self.assertIn("actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f", generate)
        self.assertIn("actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333", publish)
        self.assertIn("digest-mismatch: error", publish)
        self.assertIn("--validate-only", publish)
        publisher_script = publish.split("      - name: Prepare one atomic three-asset commit without credentials", 1)[1]
        self.assertLess(publisher_script.index("git clone"), publisher_script.index("python3 scripts/prepare_hoops_assets.py --validate-only"))
        self.assertIn('out_dir: ${{ runner.temp }}/hoops-generated', workflow)
        for name in FILES:
            self.assertIn(name, workflow)
        self.assertIn("git diff --cached --quiet", workflow)
        self.assertIn('git push', workflow)


if __name__ == "__main__":
    unittest.main()
