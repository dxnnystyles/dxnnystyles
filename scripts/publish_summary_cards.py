#!/usr/bin/env python3
"""Publish a complete validated five-card set as one main-branch commit."""

from pathlib import Path
import hashlib
import os
import subprocess

from summary_card_date import extract_date_line, update_readme_date, utc_publication_timestamp


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


def remote_readme(commit: str) -> str:
    result = git("show", f"{commit}:README.md", check=False)
    if result.returncode != 0:
        raise SystemExit("Could not verify the README snapshot date at the publication baseline.")
    return result.stdout


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
    baseline_readme = remote_readme(baseline)
    checked_out_readme = Path("README.md").read_text(encoding="utf-8")
    if checked_out_readme != baseline_readme:
        raise SystemExit("Checked-out README differs from the verified baseline; refusing publication.")
    try:
        baseline_date = extract_date_line(baseline_readme)
    except ValueError as error:
        raise SystemExit(f"README refresh-date validation refused: {error}") from error

    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    source = Path(os.environ["VERIFIED_CARDS_DIR"]).resolve()
    if runner_temp not in source.parents:
        raise SystemExit("Verified cards must be downloaded inside RUNNER_TEMP.")
    new_hashes = hashes(source)
    if baseline_hashes == new_hashes and baseline_date is not None:
        print("PASS: generated cards are unchanged; existing cards and refresh date were preserved without a commit or push.")
        return

    # Capture the UTC publication-commit time only after the complete generated
    # set has been validated and the date/card state has been compared.
    publication_time = utc_publication_timestamp()
    publication_date = publication_time.date().isoformat()
    try:
        updated_readme = update_readme_date(checked_out_readme, publication_date)
    except ValueError as error:
        raise SystemExit(f"README refresh-date update refused: {error}") from error

    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        (ASSET_DIR / name).write_bytes((source / name).read_bytes())
    Path("README.md").write_text(updated_readme, encoding="utf-8", newline="")

    allowed_assets = {f"{ASSET_DIR.as_posix()}/{name}" for name in FILES}
    allowed = allowed_assets | {"README.md"}
    git("add", "--", *sorted(allowed))
    staged = set(git("diff", "--cached", "--name-only").stdout.splitlines())
    if staged - allowed:
        raise SystemExit(f"Unexpected staged paths: {sorted(staged - allowed)}")
    if baseline_hashes != new_hashes and not (staged & allowed_assets):
        raise SystemExit("Card hashes changed, but no card asset was staged; refusing a date-only publication.")
    git("diff", "--cached", "--check")
    if not staged:
        raise SystemExit("Card output changed but no publication files were staged.")

    # Recheck the target immediately before commit/push; concurrency serializes
    # refresh runs, while this also detects unrelated external main movement.
    if remote_head() != baseline:
        raise SystemExit("Remote main moved before commit; refusing publication.")

    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    commit_env = os.environ.copy()
    commit_env["GIT_AUTHOR_DATE"] = publication_time.isoformat()
    commit_env["GIT_COMMITTER_DATE"] = publication_time.isoformat()
    subprocess.run(
        ["git", "commit", "-m", "Refresh public summary cards"],
        check=True,
        capture_output=True,
        text=True,
        env=commit_env,
    )
    commit = git("rev-parse", "HEAD").stdout.strip()
    parent = git("rev-parse", f"{commit}^1").stdout.strip()
    changed = set(git("diff-tree", "--no-commit-id", "--name-only", "-r", commit).stdout.splitlines())
    committed_assets = changed & allowed_assets
    date_only_initialization = baseline_hashes == new_hashes and baseline_date is None
    if parent != baseline or (not committed_assets and not date_only_initialization) or changed - allowed:
        raise SystemExit("Publication commit is not based on the verified baseline or contains an unexpected path.")
    committed_readme = git("show", f"{commit}:README.md").stdout
    if extract_date_line(committed_readme) is None or extract_date_line(committed_readme)[0] != publication_date:
        raise SystemExit("Publication commit does not include the matching complete-set refresh date.")

    if remote_head() != baseline:
        raise SystemExit("Remote main moved before push; no candidate commit was pushed.")
    pushed = git("push", "origin", f"HEAD:refs/heads/{BRANCH}", check=False)
    observed_remote = remote_head()
    if observed_remote != baseline and observed_remote != commit:
        # A concurrent external update may not exist in this checkout yet.
        # Fetch it read-only before comparing the prior and current card sets.
        git("fetch", "origin", BRANCH, check=False)
    published_hashes = remote_asset_hashes(observed_remote)
    published_readme = remote_readme(observed_remote)
    published_date = extract_date_line(published_readme)
    if observed_remote == commit and published_hashes == new_hashes and published_date is not None and published_date[0] == publication_date:
        print(f"PASS: published complete validated card set and matching UTC date in one commit: {commit}; changed {len(committed_assets)} card file(s).")
        if pushed.returncode != 0:
            print("NOTICE: push reported an error after GitHub accepted the complete commit; remote ref and hashes verified.")
        return
    baseline_date = extract_date_line(baseline_readme)
    if pushed.returncode != 0 and baseline_hashes is not None and published_hashes == baseline_hashes and published_readme == baseline_readme and published_date == baseline_date:
        raise SystemExit("Push failed or was rejected; remote last-good five-card hashes and refresh date are unchanged. Rerun after resolving the push issue.")
    if pushed.returncode != 0 and observed_remote == baseline:
        raise SystemExit("Push failed; remote main remains at the last-good cards and refresh date. Rerun after resolving the push issue.")
    if observed_remote != commit:
        raise SystemExit("Remote main does not point to the complete publication commit; inspect remote state before recovery.")
    if published_hashes != new_hashes or published_date is None or published_date[0] != publication_date:
        raise SystemExit("Remote cards or refresh date do not match the complete validated publication.")


if __name__ == "__main__":
    main()
