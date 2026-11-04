from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET

from scripts.prepare_3d_contribution import (
    ASSET_NAME,
    prepare,
    publish,
    readme_alt,
    replace_readme_alt,
    validate_snapshot,
    validate_svg,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/3d/profile-night-view.svg"


class ThreeDRefreshTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.artifact = self.root / "artifact"
        self.repo = self.root / "repo"
        (self.repo / "assets/3d").mkdir(parents=True)
        shutil.copy2(SOURCE, self.repo / "assets/3d" / ASSET_NAME)
        shutil.copy2(ROOT / "README.md", self.repo / "README.md")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_artifact(self, source: Path = SOURCE, end: date = date(2026, 11, 4)) -> None:
        prepare(source, self.artifact, end)

    def test_prepares_exact_integrity_checked_365_day_artifact(self) -> None:
        self.make_artifact()
        start, end, raw = validate_snapshot(self.artifact)
        self.assertEqual((start, end), (date(2025, 11, 5), date(2026, 11, 4)))
        self.assertEqual({path.name for path in self.artifact.iterdir()}, {ASSET_NAME, "snapshot.json"})
        self.assertEqual(hashlib.sha256(raw).hexdigest(), json.loads((self.artifact / "snapshot.json").read_text())["sha256"])
        self.assertEqual(len([n for n in ET.fromstring(raw).iter() if n.tag.endswith("rect") and n.get("class", "").startswith("cont-top-")]), 365)

    def test_rejects_malformed_svg_and_missing_inactive_day_cell(self) -> None:
        malformed = self.root / "malformed.svg"
        malformed.write_text("<svg><broken>", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid 3D contribution SVG"):
            validate_svg(malformed)

        root = ET.parse(SOURCE).getroot()
        first_cell = next(n for n in root.iter() if n.tag.endswith("rect") and n.get("class") == "cont-top-0")
        parent = next(p for p in root.iter() if first_cell in list(p))
        parent.remove(first_cell)
        missing = self.root / "missing-day.svg"
        ET.ElementTree(root).write(missing, encoding="utf-8", xml_declaration=True)
        with self.assertRaisesRegex(ValueError, "including inactive days"):
            validate_svg(missing)

    def test_rejects_corrupt_artifact_hash_or_unexpected_file(self) -> None:
        self.make_artifact()
        (self.artifact / "snapshot.json").write_text('{"bad": true}\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unexpected schema"):
            validate_snapshot(self.artifact)
        shutil.rmtree(self.artifact)
        self.make_artifact()
        (self.artifact / "extra.txt").write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "exactly"):
            validate_snapshot(self.artifact)

    def test_formats_accurate_utc_range_and_changes_only_target_image_alt(self) -> None:
        self.assertEqual(
            readme_alt(date(2025, 11, 5), date(2026, 11, 4)),
            "Neon Ember three-dimensional Night View of dxnnystyles public GitHub contributions for the trailing 365 days from November 5, 2025 through November 4, 2026 UTC. Snapshot updated November 4, 2026 UTC; inactive days are retained; not real time.",
        )
        original = (ROOT / "README.md").read_text(encoding="utf-8")
        updated = replace_readme_alt(original, readme_alt(date(2025, 11, 5), date(2026, 11, 4)))
        self.assertEqual(updated.count("src=\"assets/3d/profile-night-view.svg\""), 1)
        normalize = lambda text: re.sub(r'(<img\s+src="assets/3d/profile-night-view\.svg"\s+width="640"\s+alt=")[^"]*(">)', r'\1\2', text)
        self.assertEqual(normalize(updated), normalize(original))

    def test_changed_asset_and_date_are_prepared_together_and_repeat_is_noop(self) -> None:
        raw = SOURCE.read_bytes() + b"\n"
        changed = self.root / ASSET_NAME
        changed.write_bytes(raw)
        self.make_artifact(changed)
        self.assertTrue(publish(self.artifact, self.repo))
        published_asset = (self.repo / "assets/3d" / ASSET_NAME).read_bytes()
        published_readme = (self.repo / "README.md").read_text(encoding="utf-8")
        self.assertEqual(published_asset, raw)
        self.assertIn("November 5, 2025 through November 4, 2026 UTC", published_readme)
        self.assertFalse(publish(self.artifact, self.repo))
        self.assertEqual((self.repo / "assets/3d" / ASSET_NAME).read_bytes(), published_asset)
        self.assertEqual((self.repo / "README.md").read_text(encoding="utf-8"), published_readme)

    def test_invalid_artifact_leaves_existing_asset_and_readme_untouched(self) -> None:
        self.make_artifact()
        before_asset = (self.repo / "assets/3d" / ASSET_NAME).read_bytes()
        before_readme = (self.repo / "README.md").read_bytes()
        (self.artifact / ASSET_NAME).write_text("<svg>", encoding="utf-8")
        with self.assertRaises(ValueError):
            publish(self.artifact, self.repo)
        self.assertEqual((self.repo / "assets/3d" / ASSET_NAME).read_bytes(), before_asset)
        self.assertEqual((self.repo / "README.md").read_bytes(), before_readme)

    def test_workflow_is_daily_manual_read_only_generation_and_separate_publication(self) -> None:
        workflow = (ROOT / ".github/workflows/update-3d-contributions.yml").read_text(encoding="utf-8")
        generate, publish_job = workflow.split("  publish:", 1)
        self.assertIn("cron: '45 6 * * *'", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("permissions: {}", workflow)
        self.assertIn("contents: read", generate)
        self.assertNotIn("contents: write", generate)
        self.assertIn("contents: write", publish_job)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", generate)
        self.assertNotIn("GITHUB_TOKEN:", publish_job.split("      - name: Push the prepared 3D graph update", 1)[0])
        self.assertIn("yoshi389111/github-profile-3d-contrib@e235d118909be71eb7edb05482a3de4e76156df3", generate)
        self.assertIn("actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f", generate)
        self.assertIn("actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333", publish_job)
        self.assertIn("digest-mismatch: error", publish_job)
        self.assertIn("git add -- README.md assets/3d/profile-night-view.svg", publish_job)
        self.assertIn("git push", publish_job)


if __name__ == "__main__":
    unittest.main()
