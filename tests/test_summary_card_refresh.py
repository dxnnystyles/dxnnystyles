from pathlib import Path
from datetime import datetime, timedelta, timezone
import sys
import os
import shutil
import subprocess
import tempfile
import unittest


FILES = [
    "0-profile-details.svg",
    "1-repos-per-language.svg",
    "2-most-commit-language.svg",
    "3-stats.svg",
    "4-productive-time.svg",
]
ASSETS = [f"assets/summary-cards/{name}" for name in FILES]
REPO = Path(__file__).resolve().parents[1]
PUBLISHER = REPO / "scripts/publish_summary_cards.py"
VALIDATOR = REPO / "scripts/verify_summary_cards.py"
WORKFLOW = REPO / ".github/workflows/update-summary-cards.yml"
HOOPS_WORKFLOW = REPO / ".github/workflows/update-hoops.yml"
sys.path.insert(0, str(REPO / "scripts"))
from summary_card_date import extract_date_line, update_readme_date, utc_publication_timestamp

PROFILE_DETAILS_LINE = '<p align="center"><img src="assets/summary-cards/0-profile-details.svg" width="700" alt="test"></p>'
PRESERVED_README = "# private test fixture\n\n[approved destination](https://example.invalid)\n\n"


def run_git(directory: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=directory, check=check, capture_output=True, text=True)
    return result.stdout.strip()


class RefreshHardeningTests(unittest.TestCase):
    def test_utc_publication_date_and_readme_locality(self):
        local_time = datetime(2026, 10, 27, 0, 30, tzinfo=timezone(timedelta(hours=7)))
        utc_time = utc_publication_timestamp(local_time)
        self.assertEqual(utc_time.isoformat(), "2026-10-26T17:30:00+00:00")
        self.assertEqual(utc_time.date().isoformat(), "2026-10-26")
        with self.assertRaises(ValueError):
            utc_publication_timestamp(datetime(2026, 10, 27, 0, 30))

        original = PRESERVED_README + PROFILE_DETAILS_LINE + "\n"
        first = update_readme_date(original, "2000-01-01")
        second = update_readme_date(first, "2026-10-26")
        old_line = "<!-- profile-snapshot-date: 2000-01-01 -->"
        new_line = "<!-- profile-snapshot-date: 2026-10-26 -->"
        self.assertEqual(second, first.replace(old_line, new_line, 1))
        self.assertTrue(second.index(new_line) < second.index(PROFILE_DETAILS_LINE))
        self.assertEqual(extract_date_line(second)[0], "2026-10-26")
        self.assertEqual(second.count("profile-snapshot-date:"), 1)
        self.assertNotIn("Profile snapshot · Updated", second)

    def test_malformed_or_partial_generated_set_is_rejected_before_publisher(self):
        self.assertEqual(run_git(self.work, "rev-parse", "HEAD"), self.baseline)
        baseline_readme = run_git(self.work, "show", f"{self.baseline}:README.md")
        malformed_dir = self.root / "malformed-cards"
        malformed_dir.mkdir()
        for name in FILES:
            shutil.copy2(REPO / "assets/summary-cards" / name, malformed_dir / name)
        (malformed_dir / FILES[0]).write_text("<svg><broken>", encoding="utf-8")
        malformed = subprocess.run(
            ["python3", str(VALIDATOR), "--directory", str(malformed_dir), "--no-copy"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(malformed.returncode, 0)

        (malformed_dir / FILES[0]).write_text("valid-fixture", encoding="utf-8")
        (malformed_dir / FILES[-1]).unlink()
        partial = subprocess.run(
            ["python3", str(VALIDATOR), "--directory", str(malformed_dir), "--no-copy"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(partial.returncode, 0)
        self.assertEqual(run_git(self.work, "rev-parse", "HEAD"), self.baseline)
        self.assertEqual(run_git(self.work, "show", f"{self.baseline}:README.md"), baseline_readme)
        self.assertEqual(run_git(self.work, "ls-remote", "origin", "refs/heads/main").split()[0], self.baseline)

    def test_workflow_serializes_refreshes_and_pins_reviewed_node24_actions(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("cron: '31 7 * * *'", workflow)
        self.assertEqual(workflow.count("cron:"), 1)
        hoops_workflow = HOOPS_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", hoops_workflow)
        self.assertIn("cron: '17 6 * * *'", hoops_workflow)
        self.assertEqual(hoops_workflow.count("cron:"), 1)
        self.assertIn("group: summary-cards-refresh-${{ github.repository }}", workflow)
        self.assertIn("queue: max", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8", workflow)
        self.assertIn("git clone --no-tags --single-branch --branch main", workflow)
        self.assertIn("git push \"https://github.com/$GITHUB_REPOSITORY.git\" HEAD:main", workflow)
        self.assertIn("name: Push the prepared complete card update", workflow)
        self.assertIn("name: Verify the prepared commit is now the remote baseline", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("report_change_state", PUBLISHER.read_text(encoding="utf-8"))
        self.assertNotIn('git("push"', PUBLISHER.read_text(encoding="utf-8"))
        self.assertIn("actions/setup-node@a0853c24544627f65ddf259abe73b1d18a591444", workflow)
        self.assertIn("actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f", workflow)
        self.assertIn("path: ${{ runner.temp }}/summary-cards-verified/", workflow)
        self.assertIn("actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333", workflow)
        self.assertIn("digest-mismatch: error", workflow)
        self.assertIn("uses: dxnnystyles/github-profile-summary-cards@179a08d62b489701d4e902495386d64367ea8003", workflow)
        self.assertIn("SUMMARY_CARDS_CANDIDATE_SHA: 179a08d62b489701d4e902495386d64367ea8003", workflow)
        self.assertIn("if: github.ref == 'refs/heads/main'", workflow)
        self.assertIn("needs.generate.result == 'success' && github.ref == 'refs/heads/main'", workflow)
        self.assertIn("AUTO_PUSH: false", workflow)
        self.assertIn("permissions: {}", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("contents: write", workflow)

    def test_transferred_artifact_requires_exact_generator_and_public_account_provenance(self):
        artifact = self.root / "artifact-with-manifest"
        artifact.mkdir()
        for name in FILES:
            shutil.copy2(REPO / "assets/summary-cards" / name, artifact / name)
        candidate = "179a08d62b489701d4e902495386d64367ea8003"
        (artifact / "verification.txt").write_text(
            f"candidate_sha={candidate}\nsource_account=dxnnystyles\nprivate_contribution_scope=none\n",
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["SUMMARY_CARDS_CANDIDATE_SHA"] = candidate
        verified = subprocess.run(
            ["python3", str(VALIDATOR), "--directory", str(artifact), "--no-copy"],
            env=env, capture_output=True, text=True,
        )
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)

        (artifact / "verification.txt").write_text(
            "candidate_sha=0000000000000000000000000000000000000000\nsource_account=dxnnystyles\nprivate_contribution_scope=none\n",
            encoding="utf-8",
        )
        wrong_revision = subprocess.run(
            ["python3", str(VALIDATOR), "--directory", str(artifact), "--no-copy"],
            env=env, capture_output=True, text=True,
        )
        self.assertNotEqual(wrong_revision.returncode, 0)
        self.assertIn("exact pinned generator candidate", wrong_revision.stderr)

    def test_current_visual_branch_cards_pass_profile_verification(self):
        result = subprocess.run(
            ["python3", str(VALIDATOR), "--directory", str(REPO / "assets/summary-cards"), "--no-copy"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("0-profile-details.svg", result.stdout)
        self.assertIn("700x200", result.stdout)
        self.assertIn("PASS complete five-card set", result.stdout)

    def test_validator_refuses_conflicting_copy_options(self):
        result = subprocess.run(
            ["python3", str(VALIDATOR), "--no-copy", "--copy-to", str(self.root / "unexpected-copy")],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--no-copy cannot be combined with --copy-to", result.stderr)
        self.assertFalse((self.root / "unexpected-copy").exists())

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="summary-card-publish-test-")
        self.root = Path(self.tmp.name)
        self.remote = self.root / "origin.git"
        self.work = self.root / "work"
        self.racer = self.root / "racer"
        self.runner_temp = self.root / "runner-temp"
        self.output = self.runner_temp / "verified-cards"
        self.github_output = self.runner_temp / "github-output.txt"
        self.runner_temp.mkdir()
        subprocess.run(["git", "init", "--bare", str(self.remote)], check=True, capture_output=True)
        subprocess.run(["git", "init", str(self.work)], check=True, capture_output=True)
        run_git(self.work, "switch", "-c", "main")
        run_git(self.work, "config", "user.name", "Test Publisher")
        run_git(self.work, "config", "user.email", "test-publisher@example.invalid")
        run_git(self.work, "remote", "add", "origin", str(self.remote))
        for name in FILES:
            path = self.work / "assets/summary-cards" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"last-good:{name}\n", encoding="utf-8")
        (self.work / "README.md").write_text(
            update_readme_date(PRESERVED_README + PROFILE_DETAILS_LINE + "\n", "2000-01-01"),
            encoding="utf-8",
        )
        run_git(self.work, "add", "--", *ASSETS, "README.md")
        run_git(self.work, "commit", "-m", "seed last-good cards")
        run_git(self.work, "push", "-u", "origin", "main")
        self.baseline = run_git(self.work, "rev-parse", "HEAD")
        (self.work / "scripts").mkdir()
        shutil.copy2(PUBLISHER, self.work / "scripts/publish_summary_cards.py")
        shutil.copy2(REPO / "scripts/summary_card_date.py", self.work / "scripts/summary_card_date.py")
        self.output.mkdir()
        for name in FILES:
            (self.output / name).write_text(f"candidate:{name}\n", encoding="utf-8")
        self.env = os.environ.copy()
        self.env.update({
            "BASELINE_SHA": self.baseline,
            "RUNNER_TEMP": str(self.runner_temp),
            "VERIFIED_CARDS_DIR": str(self.output),
            "GITHUB_OUTPUT": str(self.github_output),
        })

    def tearDown(self):
        self.tmp.cleanup()

    def prepare(self, expect_success: bool = True):
        self.github_output.write_text("", encoding="utf-8")
        result = subprocess.run(
            ["python3", "scripts/publish_summary_cards.py"],
            cwd=self.work,
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode == 0, expect_success, result.stdout + result.stderr)
        return result

    def push_prepared(self, expect_success: bool = True):
        result = subprocess.run(
            ["git", "push", "origin", "HEAD:refs/heads/main"],
            cwd=self.work,
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode == 0, expect_success, result.stdout + result.stderr)
        return result

    def publish(self, expect_success: bool = True):
        result = self.prepare(expect_success)
        if expect_success and "has_changes=true" in self.github_output.read_text(encoding="utf-8"):
            self.push_prepared()
        return result

    def test_atomic_success_and_unchanged_noop(self):
        baseline_readme = run_git(self.work, "show", f"{self.baseline}:README.md")
        result = self.publish(expect_success=True)
        self.assertIn("prepared complete five-card publication commit", result.stdout)
        first = run_git(self.work, "rev-parse", "HEAD")
        self.assertEqual(run_git(self.work, "rev-parse", f"{first}^1"), self.baseline)
        changed = set(run_git(self.work, "diff-tree", "--no-commit-id", "--name-only", "-r", first).splitlines())
        self.assertEqual(changed, set(ASSETS) | {"README.md"})
        self.assertEqual(run_git(self.work, "ls-remote", "origin", "refs/heads/main").split()[0], first)
        first_readme = run_git(self.work, "show", f"{first}:README.md")
        date_from_readme = extract_date_line(first_readme)[0]
        commit_time = datetime.fromisoformat(run_git(self.work, "show", "-s", "--format=%cI", first))
        self.assertEqual(commit_time.astimezone(timezone.utc).date().isoformat(), date_from_readme)
        self.assertEqual(first_readme, update_readme_date(baseline_readme, date_from_readme))
        self.assertEqual(extract_date_line(baseline_readme)[0], "2000-01-01")

        self.env["BASELINE_SHA"] = first
        result = self.publish(expect_success=True)
        self.assertIn("existing cards and refresh date were preserved", result.stdout)
        self.assertEqual(run_git(self.work, "rev-parse", "HEAD"), first)
        self.assertEqual(run_git(self.work, "ls-remote", "origin", "refs/heads/main").split()[0], first)
        self.assertEqual(run_git(self.work, "show", f"{first}:README.md"), first_readme)

    def test_first_success_adds_date_when_no_prior_refresh_date_exists(self):
        original_readme = PRESERVED_README + PROFILE_DETAILS_LINE + "\n"
        (self.work / "README.md").write_text(original_readme, encoding="utf-8")
        run_git(self.work, "add", "README.md")
        run_git(self.work, "commit", "--amend", "--no-edit")
        run_git(self.work, "push", "--force", "origin", "main")
        self.baseline = run_git(self.work, "rev-parse", "HEAD")
        self.env["BASELINE_SHA"] = self.baseline

        result = self.publish(expect_success=True)
        self.assertIn("prepared complete five-card publication commit", result.stdout)
        published = run_git(self.work, "rev-parse", "HEAD")
        readme = subprocess.run(
            ["git", "show", f"{published}:README.md"],
            cwd=self.work,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        date_line = extract_date_line(readme)
        self.assertIsNotNone(date_line)
        self.assertEqual(readme, update_readme_date(original_readme, date_line[0]))
        self.assertEqual(run_git(self.work, "ls-remote", "origin", "refs/heads/main").split()[0], published)

    def test_first_success_adds_date_when_cards_are_already_current(self):
        original_readme = PRESERVED_README + PROFILE_DETAILS_LINE
        (self.work / "README.md").write_text(original_readme, encoding="utf-8")
        run_git(self.work, "add", "README.md")
        run_git(self.work, "commit", "--amend", "--no-edit")
        run_git(self.work, "push", "--force", "origin", "main")
        self.baseline = run_git(self.work, "rev-parse", "HEAD")
        self.env["BASELINE_SHA"] = self.baseline
        for name in FILES:
            (self.output / name).write_text(f"last-good:{name}\n", encoding="utf-8")

        result = self.publish(expect_success=True)
        self.assertIn("prepared complete five-card publication commit", result.stdout)
        initialized = run_git(self.work, "rev-parse", "HEAD")
        changed = set(run_git(self.work, "diff-tree", "--no-commit-id", "--name-only", "-r", initialized).splitlines())
        self.assertEqual(changed, {"README.md"})
        initialized_readme = run_git(self.work, "show", f"{initialized}:README.md")
        initialized_date = extract_date_line(initialized_readme)
        self.assertIsNotNone(initialized_date)
        self.assertEqual(initialized_readme, update_readme_date(original_readme, initialized_date[0]))
        for name in FILES:
            self.assertEqual(
                run_git(self.work, "show", f"{initialized}:{ASSETS[FILES.index(name)]}"),
                f"last-good:{name}",
            )
        self.assertEqual(run_git(self.work, "ls-remote", "origin", "refs/heads/main").split()[0], initialized)

        self.env["BASELINE_SHA"] = initialized
        result = self.publish(expect_success=True)
        self.assertIn("existing cards and refresh date were preserved", result.stdout)
        self.assertEqual(run_git(self.work, "rev-parse", "HEAD"), initialized)
        self.assertEqual(run_git(self.work, "ls-remote", "origin", "refs/heads/main").split()[0], initialized)

    def test_failed_initial_date_only_publication_preserves_remote(self):
        original_readme = PRESERVED_README + PROFILE_DETAILS_LINE
        (self.work / "README.md").write_text(original_readme, encoding="utf-8")
        run_git(self.work, "add", "README.md")
        run_git(self.work, "commit", "--amend", "--no-edit")
        run_git(self.work, "push", "--force", "origin", "main")
        self.baseline = run_git(self.work, "rev-parse", "HEAD")
        self.env["BASELINE_SHA"] = self.baseline
        for name in FILES:
            (self.output / name).write_text(f"last-good:{name}\n", encoding="utf-8")
        hook = self.work / ".git/hooks/pre-push"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)

        result = self.prepare(expect_success=True)
        self.assertIn("has_changes=true", self.github_output.read_text(encoding="utf-8"))
        self.push_prepared(expect_success=False)
        self.assertEqual(run_git(self.work, "ls-remote", "origin", "refs/heads/main").split()[0], self.baseline)
        self.assertEqual(run_git(self.work, "show", f"{self.baseline}:README.md"), original_readme)
        self.assertIsNone(extract_date_line(run_git(self.work, "show", f"{self.baseline}:README.md")))
        for name in FILES:
            self.assertEqual(
                run_git(self.work, "show", f"{self.baseline}:{ASSETS[FILES.index(name)]}"),
                f"last-good:{name}",
            )

    def test_incomplete_input_and_rejected_push_preserve_then_recover(self):
        missing = self.output / FILES[-1]
        missing.unlink()
        result = self.prepare(expect_success=False)
        self.assertIn("Expected exactly five SVGs", result.stderr)
        self.assertEqual(run_git(self.work, "rev-parse", "HEAD"), self.baseline)
        self.assertEqual(run_git(self.work, "ls-remote", "origin", "refs/heads/main").split()[0], self.baseline)
        baseline_readme = run_git(self.work, "show", f"{self.baseline}:README.md")
        self.assertEqual(run_git(self.work, "show", f"{self.baseline}:README.md"), baseline_readme)
        missing.write_text(f"candidate:{FILES[-1]}\n", encoding="utf-8")

        subprocess.run(["git", "clone", "--branch", "main", str(self.remote), str(self.racer)], check=True, capture_output=True)
        run_git(self.racer, "config", "user.name", "Race Probe")
        run_git(self.racer, "config", "user.email", "race-probe@example.invalid")
        (self.racer / "race-marker.txt").write_text("synthetic branch race\n", encoding="utf-8")
        run_git(self.racer, "add", "race-marker.txt")
        run_git(self.racer, "commit", "-m", "advance branch before candidate push")

        hook = self.work / ".git/hooks/pre-push"
        hook.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "git -C \"$RACE_REPO\" push origin main\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)
        self.env["RACE_REPO"] = str(self.racer)
        result = self.prepare(expect_success=True)
        remote_after_race = run_git(self.racer, "rev-parse", "HEAD")
        self.push_prepared(expect_success=False)
        self.assertEqual(run_git(self.racer, "ls-remote", "origin", "refs/heads/main").split()[0], remote_after_race)
        self.assertEqual(run_git(self.racer, "show", f"{remote_after_race}:README.md"), baseline_readme)
        for name in FILES:
            self.assertEqual(
                run_git(self.racer, "show", f"{remote_after_race}:assets/summary-cards/{name}"),
                f"last-good:{name}",
            )

        hook.unlink()
        run_git(self.work, "fetch", "origin", "main")
        run_git(self.work, "reset", "--hard", "origin/main")
        self.env["BASELINE_SHA"] = remote_after_race
        result = self.publish(expect_success=True)
        self.assertIn("prepared complete five-card publication commit", result.stdout)
        recovered = run_git(self.work, "rev-parse", "HEAD")
        self.assertEqual(run_git(self.work, "rev-parse", f"{recovered}^1"), remote_after_race)
        recovered_paths = set(run_git(self.work, "diff-tree", "--no-commit-id", "--name-only", "-r", recovered).splitlines())
        self.assertEqual(recovered_paths, set(ASSETS) | {"README.md"})
        recovered_commit_time = datetime.fromisoformat(run_git(self.work, "show", "-s", "--format=%cI", recovered))
        recovered_utc_date = recovered_commit_time.astimezone(timezone.utc).date().isoformat()
        self.assertEqual(
            extract_date_line(run_git(self.work, "show", f"{recovered}:README.md"))[0],
            recovered_utc_date,
        )


if __name__ == "__main__":
    unittest.main()
