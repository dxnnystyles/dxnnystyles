#!/usr/bin/env python3
"""Check the profile README's approved structure, links, assets, and public file set."""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SECTIONS = [
    "Danny Styles",
    "About",
    "Currently",
    "Selected work",
    "GitHub activity",
    "Featured project: slappywax",
    "Chess",
    "Beyond code",
    "Contact / links",
]
APPROVED_URLS = {
    "https://github.com/dxnnystyles",
    "https://github.com/dxnnystyles/browser-chess",
    "https://dxnnystyles.github.io/browser-chess/",
    "https://open.spotify.com/album/0aLqVmlz4ytvJRcGKW8q4D",
}
ALLOWED_PUBLIC_FILES = {
    ".gitignore",
    "README.md",
    "assets/dxnnystyles-retro-computer.svg",
    "assets/browser-chess-preview.svg",
    "scripts/check_readme.py",
}


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    readme_path = ROOT / "README.md"
    if not readme_path.is_file():
        fail("README.md is missing")
    readme = readme_path.read_text(encoding="utf-8")

    sections = re.findall(r"^##\s+(.+?)\s*$", readme, flags=re.MULTILINE)
    if sections != EXPECTED_SECTIONS:
        fail(f"expected the nine approved sections in order; found {sections!r}")
    beyond_code = re.search(
        r"^##\s+Beyond code\s*$\n(.*?)(?=^##\s+|\Z)",
        readme,
        flags=re.MULTILINE | re.DOTALL,
    )
    if beyond_code is None or "#featured-project-slappywax" not in beyond_code.group(1):
        fail("Beyond code must link only to the approved slappywax section")

    markdown_links = re.findall(r"!\[[^\]]*\]\([^)]+\)|(?<!!)\[[^\]]+\]\([^)]+\)", readme)
    if len(markdown_links) != readme.count("]("):
        fail("README contains a malformed Markdown image or link")
    if readme.count("`") % 2:
        fail("README contains an unmatched inline-code marker")
    if readme.count("[Danny Styles - slappywax](https://open.spotify.com/album/0aLqVmlz4ytvJRcGKW8q4D)") != 1:
        fail("README must show the exact approved slappywax text and Spotify album link once")
    forbidden_claims = ("@aaronsanchez2000", "spotify.com/embed", "iframe", "trophy", "custom amber")
    if any(claim in readme.casefold() for claim in forbidden_claims):
        fail("README includes unapproved attribution, embed, trophy, or external accent content")

    links = re.findall(r"!\[[^\]]*\]\(([^)]+)\)|\[[^\]]+\]\(([^)]+)\)", readme)
    local_assets: set[str] = set()
    urls: set[str] = set()
    for image_url, link_url in links:
        target = image_url or link_url
        if target.startswith("#"):
            continue
        elif target.startswith("https://"):
            urls.add(target)
        elif target.startswith("http://") or target.startswith(("//", "data:")):
            fail(f"non-HTTPS or embedded destination is not allowed: {target}")
        else:
            local_assets.add(target)
            if not (ROOT / target).is_file():
                fail(f"local README asset is missing: {target}")
    if urls != APPROVED_URLS:
        fail(f"README contains unapproved destinations: {sorted(urls ^ APPROVED_URLS)!r}")

    actual_files = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file() and ".git" not in path.parts and "__pycache__" not in path.parts
    }
    if actual_files != ALLOWED_PUBLIC_FILES:
        fail(f"public files differ from the reviewed minimal set: {sorted(actual_files ^ ALLOWED_PUBLIC_FILES)!r}")
    expected_assets = {
        "assets/dxnnystyles-retro-computer.svg",
        "assets/browser-chess-preview.svg",
    }
    if local_assets != expected_assets:
        fail(f"unexpected README assets: {sorted(local_assets ^ expected_assets)!r}")

    ns = "{http://www.w3.org/2000/svg}"
    expected_views = {
        "assets/dxnnystyles-retro-computer.svg": "0 0 1200 430",
        "assets/browser-chess-preview.svg": "0 0 1000 260",
    }
    for asset, view_box in expected_views.items():
        try:
            svg = ET.parse(ROOT / asset).getroot()
        except ET.ParseError as exc:
            fail(f"{asset} is invalid XML: {exc}")
        if svg.tag != f"{ns}svg" or svg.get("viewBox") != view_box:
            fail(f"{asset} has an unexpected SVG root or viewBox")
        if svg.find(f"{ns}title") is None or svg.find(f"{ns}desc") is None:
            fail(f"{asset} needs an accessible title and description")
        for element in svg.iter():
            for key, value in element.attrib.items():
                if key.endswith("href") and value.startswith(("http:", "https:")):
                    fail(f"{asset} must not depend on remote assets")

    print(
        f"PASS: {len(sections)} ordered sections, {len(urls)} approved destinations including the exact slappywax album link, "
        f"{len(local_assets)} local images, reviewed public file allowlist, and accessible self-contained SVGs."
    )


if __name__ == "__main__":
    main()
