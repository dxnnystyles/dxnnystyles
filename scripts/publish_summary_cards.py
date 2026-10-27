#!/usr/bin/env python3
"""Publish a complete validated five-card set as one main-branch commit."""

from pathlib import Path
import hashlib
import os
import subprocess


BRANCH = "main"
FILES = [
    "0-profile-details.svg",
    "1-repos-per-language.svg",
    "2-most-commit-language.svg",
    "3-stats.svg",
    "4-productive-time.svg",
]
ASSET_DIR = Path("assets/summary-cards")


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], check=check, capture_output=True, text=True)


def hashes(directory: Path) -> dict[str, str]:
    actual = {path.name for path in directory.glob("*.svg")}
    if actual != set(FILES):
        raise SystemExit(f"Expected exactly five SVGs in {directory}; found {sorted(actual)}")
    return {
        name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
        for name in FILES
    }


def remote_head() -> str:
    values = git("ls-remote", "origin", f"refs/heads/{BRANCH}").stdout.split()
    if len(values) != 2:
        raise SystemExit("Could not verify the remote profile branch before publication.")
    return values[0]


def remote_asset_hashes(commit: str) -> dict[str, str] | None:
    result = {}
    for name in FILES:
        show = git("show", f"{commit}:{ASSET_DIR.as_posix()}/{name}", check=False)
        if show.returncode != 0:
            return None
        contents = show.stdout.encode()
        result[name] = hashlib.sha256(contents).hexdigest()
    return result


def main() -> None:
    baseline = os.environ.get("BASELINE_SHA", "")
    if not baseline or git("rev-parse", "HEAD").stdout.strip() != baseline:
        raise SystemExit("Checked-out main differs from the generation baseline; refusing stale publication.")
    if git("branch", "--show-current").stdout.strip() != BRANCH:
        raise SystemExit("Publisher must run on main.")

    remote = remote_head()
    if remote != baseline:
        raise SystemExit("Remote main moved during generation; refusing publication and preserving current assets.")
    baseline_hashes = remote_asset_hashes(baseline)

    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    source = Path(os.environ["VERIFIED_CARDS_DIR"]).resolve()
    if runner_temp not in source.parents:
        raise SystemExit("Verified cards must be downloaded inside RUNNER_TEMP.")
    new_hashes = hashes(source)

    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        (ASSET_DIR / name).write_bytes((source / name).read_bytes())

    allowed = {f"{ASSET_DIR.as_posix()}/{name}" for name in FILES}
    git("add", "--", *sorted(allowed))
    staged = set(git("diff", "--cached", "--name-only").stdout.splitlines())
    if staged - allowed:
        raise SystemExit(f"Unexpected staged paths: {sorted(staged - allowed)}")
    git("diff", "--cached", "--check")
    if not staged:
        print("PASS: generated cards are unchanged; no commit or push was made.")
        return

    # Recheck the target immediately before commit/push; concurrency serializes
    # refresh runs, while this also detects unrelated external main movement.
    if remote_head() != baseline:
        raise SystemExit("Remote main moved before commit; refusing publication.")

    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    git("commit", "-m", "Refresh public summary cards")
    commit = git("rev-parse", "HEAD").stdout.strip()
    parent = git("rev-parse", f"{commit}^1").stdout.strip()
    changed = set(git("diff-tree", "--no-commit-id", "--name-only", "-r", commit).stdout.splitlines())
    if parent != baseline or not changed or changed - allowed:
        raise SystemExit("Publication commit is not based on the verified baseline or contains an unexpected path.")

    if remote_head() != baseline:
        raise SystemExit("Remote main moved before push; no candidate commit was pushed.")
    pushed = git("push", "origin", f"HEAD:refs/heads/{BRANCH}", check=False)
    observed_remote = remote_head()
    if observed_remote != baseline and observed_remote != commit:
        # A concurrent external update may not exist in this checkout yet.
        # Fetch it read-only before comparing the prior and current card sets.
        git("fetch", "origin", BRANCH, check=False)
    published_hashes = remote_asset_hashes(observed_remote)
    if observed_remote == commit and published_hashes == new_hashes:
        print(f"PASS: published complete validated set in one commit: {commit}; changed {len(changed)} card file(s).")
        if pushed.returncode != 0:
            print("NOTICE: push reported an error after GitHub accepted the complete commit; remote ref and hashes verified.")
        return
    if pushed.returncode != 0 and baseline_hashes is not None and published_hashes == baseline_hashes:
        raise SystemExit("Push failed or was rejected; remote last-good five-card hashes are unchanged. Rerun after resolving the push issue.")
    if pushed.returncode != 0 and observed_remote == baseline:
        raise SystemExit("Push failed; remote main remains at the last-good baseline. Rerun after resolving the push issue.")
    if observed_remote != commit:
        raise SystemExit("Remote main does not point to the complete publication commit; inspect remote state before recovery.")
    if published_hashes != new_hashes:
        raise SystemExit("Remote five-card asset hashes do not match the validated output set.")


if __name__ == "__main__":
    main()
