from pathlib import Path
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


def run_git(directory: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=directory, check=check, capture_output=True, text=True)
    return result.stdout.strip()


class RefreshHardeningTests(unittest.TestCase):
    def test_workflow_serializes_refreshes_and_pins_reviewed_node24_actions(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("schedule:", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("group: summary-cards-refresh-${{ github.repository }}", workflow)
        self.assertIn("queue: max", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8", workflow)
        self.assertIn("actions/setup-node@a0853c24544627f65ddf259abe73b1d18a591444", workflow)
        self.assertIn("actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f", workflow)
        self.assertIn("actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333", workflow)
        self.assertIn("uses: dxnnystyles/github-profile-summary-cards@c4381200d1eabe72d08bbafd2911c26cb0cddf03", workflow)
        self.assertIn("SUMMARY_CARDS_CANDIDATE_SHA: c4381200d1eabe72d08bbafd2911c26cb0cddf03", workflow)
        self.assertIn("if: github.ref == 'refs/heads/main'", workflow)
        self.assertIn("needs.generate.result == 'success' && github.ref == 'refs/heads/main'", workflow)
        self.assertIn("AUTO_PUSH: false", workflow)
        self.assertIn("permissions: {}", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("contents: write", workflow)

    def test_current_visual_branch_cards_pass_profile_verification(self):
        result = subprocess.run(
            ["python3", str(VALIDATOR), "--directory", str(REPO / "assets/summary-cards"), "--no-copy"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("0-profile-details.svg", result.stdout)
        self.assertIn("700x380", result.stdout)
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
        run_git(self.work, "add", "--", *ASSETS)
        run_git(self.work, "commit", "-m", "seed last-good cards")
        run_git(self.work, "push", "-u", "origin", "main")
        self.baseline = run_git(self.work, "rev-parse", "HEAD")
        (self.work / "scripts").mkdir()
        shutil.copy2(PUBLISHER, self.work / "scripts/publish_summary_cards.py")
        self.output.mkdir()
        for name in FILES:
            (self.output / name).write_text(f"candidate:{name}\n", encoding="utf-8")
        self.env = os.environ.copy()
        self.env.update({
            "BASELINE_SHA": self.baseline,
            "RUNNER_TEMP": str(self.runner_temp),
            "VERIFIED_CARDS_DIR": str(self.output),
        })

    def tearDown(self):
        self.tmp.cleanup()

    def publish(self, expect_success: bool):
        result = subprocess.run(
            ["python3", "scripts/publish_summary_cards.py"],
            cwd=self.work,
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode == 0, expect_success, result.stdout + result.stderr)
        return result

    def test_atomic_success_and_unchanged_noop(self):
        result = self.publish(expect_success=True)
        self.assertIn("published complete validated set", result.stdout)
        first = run_git(self.work, "rev-parse", "HEAD")
        self.assertEqual(run_git(self.work, "rev-parse", f"{first}^1"), self.baseline)
        self.assertEqual(set(run_git(self.work, "diff-tree", "--no-commit-id", "--name-only", "-r", first).splitlines()), set(ASSETS))
        self.assertEqual(run_git(self.work, "ls-remote", "origin", "refs/heads/main").split()[0], first)

        self.env["BASELINE_SHA"] = first
        result = self.publish(expect_success=True)
        self.assertIn("unchanged; no commit or push", result.stdout)
        self.assertEqual(run_git(self.work, "rev-parse", "HEAD"), first)
        self.assertEqual(run_git(self.work, "ls-remote", "origin", "refs/heads/main").split()[0], first)

    def test_incomplete_input_and_rejected_push_preserve_then_recover(self):
        missing = self.output / FILES[-1]
        missing.unlink()
        result = self.publish(expect_success=False)
        self.assertIn("Expected exactly five SVGs", result.stderr)
        self.assertEqual(run_git(self.work, "rev-parse", "HEAD"), self.baseline)
        self.assertEqual(run_git(self.work, "ls-remote", "origin", "refs/heads/main").split()[0], self.baseline)
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
        result = self.publish(expect_success=False)
        self.assertIn("last-good five-card hashes are unchanged", result.stderr.casefold())
        remote_after_race = run_git(self.racer, "rev-parse", "HEAD")
        self.assertEqual(run_git(self.racer, "ls-remote", "origin", "refs/heads/main").split()[0], remote_after_race)
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
        self.assertIn("published complete validated set", result.stdout)
        recovered = run_git(self.work, "rev-parse", "HEAD")
        self.assertEqual(run_git(self.work, "rev-parse", f"{recovered}^1"), remote_after_race)
        self.assertEqual(set(run_git(self.work, "diff-tree", "--no-commit-id", "--name-only", "-r", recovered).splitlines()), set(ASSETS))


if __name__ == "__main__":
    unittest.main()
