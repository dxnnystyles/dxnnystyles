#!/usr/bin/env python3
"""Check the centered profile widgets, sources, links, and public file allowlist."""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_URLS = {
    "https://dxnnystyles.github.io/browser-chess/",
    "https://github.com/dxnnystyles/browser-chess",
    "https://open.spotify.com/album/0aLqVmlz4ytvJRcGKW8q4D",
}
BADGES = {
    "swift": "Swift", "python": "Python", "shell": "Shell",
    "javascript": "JavaScript", "html": "HTML", "css": "CSS",
    "nodejs": "Node.js", "vite": "Vite",
}
ASSETS = {
    "assets/browser-chess-launcher.svg", "assets/music/slappywax-cover.jpg",
    "assets/hoops/hoops.svg", "assets/hoops/hoops-dark.svg",
    *(f"assets/tech/{name}.svg" for name in BADGES),
}
ALLOWED = {
    ".gitignore", "README.md", "scripts/check_readme.py",
    ".github/workflows/update-hoops.yml", *ASSETS,
}

class Markup(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[dict[str, str | None]] = []
        self.sources: list[dict[str, str | None]] = []
        self.anchors: list[dict[str, str | None]] = []
        self.centered_groups = 0
        self.h1 = False
        self.forbidden_sections: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        item = dict(attrs)
        if tag == "h1":
            self.h1 = item.get("align", "").casefold() == "center"
        if tag == "p" and item.get("align", "").casefold() == "center":
            self.centered_groups += 1
        if tag == "img":
            self.images.append(item)
        if tag == "source":
            self.sources.append(item)
        if tag == "a":
            self.anchors.append(item)
        if tag == "h2":
            self.forbidden_sections.append("h2")


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if not re.search(r"<h1\s+align=\"center\">dxnnystyles</h1>", readme):
        fail("centered dxnnystyles identity is missing")
    if "Software · Chess · Music" not in readme:
        fail("approved centered identity line is missing")
    if re.search(r"^#{1,6}\s", readme, flags=re.MULTILINE):
        fail("traditional Markdown section headings remain")
    removed = ("Beyond code", "Currently", "Selected work", "About")
    if any(label.casefold() in readme.casefold() for label in removed):
        fail("superseded prose sections remain")
    if "Danny Styles - slappywax" not in readme or readme.count("https://open.spotify.com/album/0aLqVmlz4ytvJRcGKW8q4D") != 1:
        fail("exact slappywax title/link is missing or duplicated")
    forbidden = ("@aaronsanchez2000", "spotify.com/embed", "<iframe", "chess.com", "3d-contrib", "trophy", "linktree", "ds-site")
    if any(term in readme.casefold() for term in forbidden):
        fail("README contains unapproved attribution, integration, or destination")

    parser = Markup()
    parser.feed(readme)
    if not parser.h1 or parser.centered_groups == 0:
        fail("README identity and visible widget groups must use centered alignment")
    if any(not image.get("alt", "").strip() for image in parser.images):
        fail("all images need non-empty alternative text")
    targets = {image.get("src", "") for image in parser.images}
    targets.update(source.get("srcset", "").split()[0] for source in parser.sources)
    if targets != ASSETS:
        fail(f"image inventory differs: {sorted(targets ^ ASSETS)!r}")
    if any(not (ROOT / target).is_file() for target in targets):
        fail("README refers to a missing local image")
    image_by_src = {image.get("src", ""): image for image in parser.images}
    for badge in BADGES:
        if image_by_src[f"assets/tech/{badge}.svg"].get("height") != "30":
            fail(f"{BADGES[badge]} badge must use the approved larger 30px size")
    if image_by_src["assets/music/slappywax-cover.jpg"].get("width") != "320":
        fail("slappywax cover prominence must remain at 320px")
    heading_end = readme.index("</p>", readme.index("<strong>Stack</strong>")) + len("</p>")
    badge_start = readme.index('<p align="center">', heading_end)
    badge_source = readme[badge_start:readme.index("</p>", badge_start)]
    if badge_source.count('<br>') != 5:
        fail("technology groups must remain compact within one centered block")
    urls = {match.rstrip(".,") for match in re.findall(r"https://[^\s\"<>]+", readme)}
    if urls != EXPECTED_URLS:
        fail(f"unapproved or missing URLs: {sorted(urls ^ EXPECTED_URLS)!r}")
    link_text = re.sub(r"<[^>]+>", " ", readme)
    if "Open the live game" not in readme or "Source" not in link_text:
        fail("game launcher alt text and source destination need readable labels")

    for name, label in BADGES.items():
        svg = (ROOT / f"assets/tech/{name}.svg").read_text(encoding="utf-8")
        if f'aria-label="{label}"' not in svg or f"<title>{label}</title>" not in svg:
            fail(f"{label} badge is missing its accessible name")
    ns = "{http://www.w3.org/2000/svg}"
    for path in sorted((ROOT / "assets").rglob("*.svg")):
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            fail(f"invalid SVG {path.relative_to(ROOT)}: {exc}")
        if root.tag != f"{ns}svg":
            fail(f"invalid SVG root: {path.relative_to(ROOT)}")
        for element in root.iter():
            if any(key.endswith("href") and value.startswith(("http:", "https:")) for key, value in element.attrib.items()):
                fail(f"remote embedded asset in {path.relative_to(ROOT)}")
    if (ROOT / "assets/music/slappywax-cover.jpg").read_bytes()[:2] != b"\xff\xd8":
        fail("album artwork is not a JPEG")

    workflow = (ROOT / ".github/workflows/update-hoops.yml").read_text(encoding="utf-8")
    if "HarrisJDCampbell/hoops@c90b483d3f7e61544afaee4c105a51d410346cb2" not in workflow:
        fail("Hoops action is not pinned to the reviewed upstream revision")
    if "github_user_name: dxnnystyles" not in workflow or "read:user" in workflow:
        fail("Hoops must use only the verified account and avoid private-data scope")
    if "git add assets/hoops/hoops.svg assets/hoops/hoops-dark.svg" not in workflow:
        fail("Hoops refresh must stage only the two last-good image files")

    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts}
    if actual != ALLOWED:
        fail(f"public file allowlist differs: {sorted(actual ^ ALLOWED)!r}")
    print(f"PASS: centered identity, {len(BADGES)} labeled badges, Hoops, album and chess widgets, {len(urls)} approved destinations, alt text, and {len(actual)} allowed public files.")

if __name__ == "__main__":
    main()
