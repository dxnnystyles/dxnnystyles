#!/usr/bin/env python3
"""Validate and transactionally prepare the public 3D contribution SVG."""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

NS = "http://www.w3.org/2000/svg"
TAG = f"{{{NS}}}"
ASSET_NAME = "profile-night-view.svg"
README_MARKER = 'src="assets/3d/profile-night-view.svg"'
EXPECTED_VIEW = ("1280", "850", "0 0 1280 850")
EXPECTED_TOP_COLORS = (
    "rgb(45, 38, 39)",
    "rgb(122, 59, 44)",
    "rgb(181, 82, 49)",
    "rgb(240, 120, 61)",
    "rgb(255, 196, 94)",
)


def validate_svg(path: Path) -> bytes:
    try:
        raw = path.read_bytes()
        root = ET.fromstring(raw)
    except (OSError, ET.ParseError) as error:
        raise ValueError(f"invalid 3D contribution SVG: {error}") from error
    if root.tag != f"{TAG}svg" or (
        root.get("width"), root.get("height"), root.get("viewBox")
    ) != EXPECTED_VIEW:
        raise ValueError("3D SVG dimensions or root are not the approved 1280x850 canvas")
    if b"<!DOCTYPE" in raw.upper() or b"<script" in raw.lower() or b"foreignObject" in raw:
        raise ValueError("3D SVG contains prohibited active or embedded content")
    if any(
        key.endswith("href") and value.startswith(("http:", "https:"))
        for node in root.iter()
        for key, value in node.attrib.items()
    ):
        raise ValueError("3D SVG contains an external resource")
    styles = "\n".join(node.text or "" for node in root.iter(f"{TAG}style"))
    for expected in (
        ".fill-bg { fill: #161b22; }",
        ".fill-fg { fill: #e6edf3; }",
        ".fill-strong { fill: #FFB36A; }",
        ".fill-weak { fill: #8b949e; }",
    ):
        if expected not in styles:
            raise ValueError(f"3D SVG is missing the approved style: {expected}")
    if not all(f".cont-top-{index} {{ fill: {color}; }}" in styles for index, color in enumerate(EXPECTED_TOP_COLORS)):
        raise ValueError("3D SVG does not retain the approved Neon Ember contribution palette")
    day_faces = [
        node for node in root.iter(f"{TAG}rect")
        if re.fullmatch(r"cont-top-[0-4]", node.get("class", ""))
    ]
    if len(day_faces) != 365:
        raise ValueError(f"expected all 365 daily contribution cells, including inactive days; found {len(day_faces)}")
    if sum(1 for node in root.iter() if node.tag in (f"{TAG}animate", f"{TAG}animateTransform")) < 1:
        raise ValueError("3D SVG is missing the approved contribution animation")
    return raw


def format_day(value: date) -> str:
    return f"{value.strftime('%B')} {value.day}, {value.year}"


def readme_alt(start: date, end: date) -> str:
    return (
        "Neon Ember three-dimensional Night View of dxnnystyles public GitHub contributions "
        f"for the trailing 365 days from {format_day(start)} through {format_day(end)} UTC. "
        f"Snapshot updated {format_day(end)} UTC; inactive days are retained; not real time."
    )


def replace_readme_alt(readme: str, alt: str) -> str:
    pattern = re.compile(
        r'(<img\s+src="assets/3d/profile-night-view\.svg"\s+width="640"\s+alt=")[^"]*(">)'
    )
    updated, count = pattern.subn(lambda match: match.group(1) + alt + match.group(2), readme)
    if count != 1:
        raise ValueError("README must contain exactly one approved 3D graph reference")
    return updated


def validate_snapshot(directory: Path) -> tuple[date, date, bytes]:
    try:
        names = {item.name for item in directory.iterdir()}
        metadata = json.loads((directory / "snapshot.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid 3D refresh artifact: {error}") from error
    if names != {ASSET_NAME, "snapshot.json"}:
        raise ValueError("3D refresh artifact must contain exactly the SVG and snapshot metadata")
    if set(metadata) != {"version", "start_date", "end_date", "sha256"} or metadata["version"] != 1:
        raise ValueError("3D snapshot metadata has an unexpected schema")
    try:
        start = date.fromisoformat(metadata["start_date"])
        end = date.fromisoformat(metadata["end_date"])
    except (TypeError, ValueError) as error:
        raise ValueError("3D snapshot metadata contains invalid UTC dates") from error
    if (end - start).days != 364:
        raise ValueError("3D snapshot must describe an inclusive 365-day window")
    raw = validate_svg(directory / ASSET_NAME)
    if hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
        raise ValueError("3D SVG integrity hash does not match the transferred metadata")
    return start, end, raw


def prepare(source: Path, output: Path, end: date) -> None:
    raw = validate_svg(source)
    start = end - timedelta(days=364)
    output.mkdir(parents=True, exist_ok=False)
    (output / ASSET_NAME).write_bytes(raw)
    metadata = {
        "version": 1,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    (output / "snapshot.json").write_text(json.dumps(metadata, sort_keys=True) + "\n", encoding="utf-8")


def publish(directory: Path, repo: Path) -> bool:
    start, end, raw = validate_snapshot(directory)
    asset_path = repo / "assets/3d" / ASSET_NAME
    readme_path = repo / "README.md"
    previous = validate_svg(asset_path)
    if raw == previous:
        print("3D contribution SVG unchanged; preserving the last published snapshot date.")
        return False
    current_readme = readme_path.read_text(encoding="utf-8")
    updated_readme = replace_readme_alt(current_readme, readme_alt(start, end))
    # Prepare and validate both replacements before changing either working file.
    if updated_readme == current_readme:
        raise ValueError("new 3D SVG differs but its README snapshot description did not change")
    validate_svg(directory / ASSET_NAME)
    asset_path.write_bytes(raw)
    readme_path.write_text(updated_readme, encoding="utf-8")
    print("Prepared the validated 3D SVG and matching README snapshot description as one publication.")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--source", type=Path, required=True)
    prepare_parser.add_argument("--output", type=Path, required=True)
    prepare_parser.add_argument("--end-date", required=True)
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--directory", type=Path, required=True)
    publish_parser = sub.add_parser("publish")
    publish_parser.add_argument("--directory", type=Path, required=True)
    publish_parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.source, args.output, date.fromisoformat(args.end_date))
        validate_snapshot(args.output)
    elif args.command == "validate":
        validate_snapshot(args.directory)
    else:
        has_changes = publish(args.directory, args.repo)
        import os

        output_file = Path(os.environ.get("GITHUB_OUTPUT", "/dev/null"))
        with output_file.open("a", encoding="utf-8") as stream:
            stream.write(f"has_changes={'true' if has_changes else 'false'}\n")


if __name__ == "__main__":
    main()
