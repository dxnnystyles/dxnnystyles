#!/usr/bin/env python3
"""Fail closed unless all five candidate SVGs are public-only and complete."""

from argparse import ArgumentParser
from pathlib import Path
import os
import re
import shutil
import xml.etree.ElementTree as ET


EXPECTED = {
    "0-profile-details.svg": (
        700,
        200,
        ("All-time", "contributions", "Public repos", "non-fork", "GitHub account age"),
    ),
    "1-repos-per-language.svg": (340, 200, ("Top Languages by Repo",)),
    "2-most-commit-language.svg": (340, 200, ("Top Languages by Commit",)),
    "3-stats.svg": (340, 200, ("Total Stars:", "Total Commits:", "Total PRs:", "Total Issues:", "Contributed to:")),
    "4-productive-time.svg": (340, 200, ("Commits by Hour", "America/Los_Angeles", "trailing year")),
}
CONTACT_MARKERS = ("@", "email", "company", "location", "website", "twitter")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def validate_card_set(directory: Path) -> tuple[list[tuple[str, ET.Element, str, str]], list[str]]:
    if not directory.is_dir():
        raise SystemExit(f"Expected generator output folder is missing: {directory}")

    actual = {path.name for path in directory.iterdir() if path.is_file() and path.suffix == ".svg"}
    if actual != set(EXPECTED):
        raise SystemExit(f"Expected exactly five card SVGs; found: {sorted(actual)}")

    validated = []
    manifest_lines = []
    for name, (expected_width, expected_height, expected_text) in EXPECTED.items():
        source = directory / name
        if source.stat().st_size < 1000:
            raise SystemExit(f"SVG is unexpectedly small: {name} ({source.stat().st_size} bytes)")
        try:
            root = ET.parse(source).getroot()
        except ET.ParseError as error:
            raise SystemExit(f"Invalid SVG XML in {name}: {error}") from error
        if local_name(root.tag) != "svg":
            raise SystemExit(f"Root is not SVG: {name}")

        try:
            width = float(root.attrib["width"].removesuffix("px"))
            height = float(root.attrib["height"].removesuffix("px"))
            view_box = [float(value) for value in re.split(r"[ ,]+", root.attrib["viewBox"].strip())]
        except (KeyError, ValueError) as error:
            raise SystemExit(f"Missing or invalid SVG dimensions in {name}: {error}") from error
        if width != expected_width or height != expected_height or view_box != [0.0, 0.0, expected_width, expected_height]:
            raise SystemExit(f"Unexpected dimensions in {name}: width={width}, height={height}, viewBox={view_box}")

        title = next((node for node in root if local_name(node.tag) == "title"), None)
        description = next((node for node in root if local_name(node.tag) == "desc"), None)
        if root.attrib.get("role") != "img" or not (title is not None and (title.text or "").strip()):
            raise SystemExit(f"Missing accessible SVG image role/title in {name}.")
        if not (description is not None and (description.text or "").strip()):
            raise SystemExit(f"Missing accessible SVG description in {name}.")
        labelled_by = set(root.attrib.get("aria-labelledby", "").split())
        if title.attrib.get("id") not in labelled_by or description.attrib.get("id") not in labelled_by:
            raise SystemExit(f"aria-labelledby does not reference the title and description in {name}.")

        nodes = list(root.iter())
        if any(local_name(node.tag).casefold() in {"script", "foreignobject"} for node in nodes):
            raise SystemExit(f"Unsupported executable/HTML content in {name}.")
        for node in nodes:
            for attribute, value in node.attrib.items():
                if local_name(attribute).casefold() in {"href", "src"} and re.match(r"https?://", value, re.I):
                    raise SystemExit(f"External resource reference found in {name}.")

        if not any(
            local_name(node.tag) == "rect"
            and node.attrib.get("fill", "").casefold() == "#161b22"
            and node.attrib.get("stroke", "").casefold() == "#30363d"
            for node in nodes
        ):
            raise SystemExit(f"Missing approved charcoal surface and border in {name}.")

        text = " ".join(node.text or "" for node in nodes)
        attributes = " ".join(value for node in nodes for value in node.attrib.values())
        lowered = f"{text} {attributes}".casefold()
        if not text.strip():
            raise SystemExit(f"Card contains no readable text: {name}")
        missing = [phrase for phrase in expected_text if phrase.casefold() not in lowered]
        if missing:
            raise SystemExit(f"Card {name} is missing expected labels/content: {missing}")
        if "error" in lowered or "there are no" in lowered:
            raise SystemExit(f"Card {name} contains an upstream error/empty-data placeholder.")
        if name == "0-profile-details.svg":
            if "dxnnystyles" not in lowered:
                raise SystemExit("Profile Details does not identify the requested account.")
            if any(marker in lowered for marker in CONTACT_MARKERS):
                raise SystemExit("Profile Details contains contact/personal metadata markers.")
            if any(marker in lowered for marker in ("contribution graph", "contributions in the last year", "monthly totals", "contributioncalendar")):
                raise SystemExit("Profile Details must omit its contribution chart and rolling-calendar labels.")
            if "contact fields and the contribution chart are omitted" not in lowered:
                raise SystemExit("Profile Details description must identify omitted contact fields and chart.")
        if name == "4-productive-time.svg":
            bars = [node for node in nodes if local_name(node.tag) == "rect" and node.attrib.get("class") == "bar"]
            if len(bars) != 24:
                raise SystemExit(f"Productive Time should contain 24 hourly bars; found {len(bars)}.")

        visible_text = " ".join((node.text or "").strip() for node in nodes if (node.text or "").strip())
        validated.append((name, root, title.text.strip(), description.text.strip()))
        manifest_lines.append(f"{name}: width={width:g}, height={height:g}, bytes={source.stat().st_size}")
        manifest_lines.append(f"  title={title.text.strip()}; description={description.text.strip()}")
        print(f"PASS {name}: {source.stat().st_size} bytes, {width:g}x{height:g}, labels validated")
        print(f"  content: {visible_text}")
    return validated, manifest_lines


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path(os.environ.get("SUMMARY_CARDS_OUTPUT_PATH", "")) / "dxnnystyles",
    )
    parser.add_argument("--copy-to", type=Path, default=None)
    parser.add_argument("--no-copy", action="store_true", help="Validate only; never copy or create artifacts.")
    args = parser.parse_args()

    if args.no_copy and args.copy_to is not None:
        parser.error("--no-copy cannot be combined with --copy-to")

    validated, manifest_lines = validate_card_set(args.directory)
    if args.copy_to is None:
        allowed = set(EXPECTED) | {"verification.txt"}
        files = {path.name for path in args.directory.iterdir() if path.is_file()}
        if files - allowed or not set(EXPECTED).issubset(files):
            raise SystemExit(f"Verified artifact contains unexpected files: {sorted(files - allowed)}")
        manifest = args.directory / "verification.txt"
        if manifest.exists():
            contents = manifest.read_text(encoding="utf-8")
            manifest_values = dict(line.split("=", 1) for line in contents.splitlines() if "=" in line)
            if manifest_values.get("candidate_sha") != os.environ.get("SUMMARY_CARDS_CANDIDATE_SHA"):
                raise SystemExit("Verification artifact does not identify the exact pinned generator candidate.")
            if manifest_values.get("source_account") != "dxnnystyles" or manifest_values.get("private_contribution_scope") != "none":
                raise SystemExit("Verification artifact has incomplete provenance.")
        elif os.environ.get("SUMMARY_CARDS_CANDIDATE_SHA"):
            raise SystemExit("The transferred generator artifact is missing its provenance manifest.")
        print("PASS complete five-card set revalidated without modifying it.")
        return

    if args.copy_to.exists() and any(args.copy_to.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty verification destination: {args.copy_to}")
    candidate_sha = os.environ.get("SUMMARY_CARDS_CANDIDATE_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", candidate_sha):
        raise SystemExit("Candidate SHA is missing or malformed.")
    args.copy_to.mkdir(parents=True, exist_ok=True)
    for name, _, _, _ in validated:
        shutil.copy2(args.directory / name, args.copy_to / name)
    manifest_lines = [
        f"candidate_sha={candidate_sha}",
        "source_account=dxnnystyles",
        "token=repository-scoped GITHUB_TOKEN; contents:read",
        f"output_path={args.directory}",
        "private_contribution_scope=none",
        *manifest_lines,
    ]
    (args.copy_to / "verification.txt").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    copied = {path.name for path in args.copy_to.glob("*.svg")}
    if copied != set(EXPECTED):
        raise SystemExit(f"Verified-artifact folder is incomplete: {sorted(copied)}")
    print("PASS all five cards validated; complete set copied to the private artifact folder.")


if __name__ == "__main__":
    main()
