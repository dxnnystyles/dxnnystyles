#!/usr/bin/env python3
"""Validate the centered profile and the theme-aware technology-grid markup."""
from __future__ import annotations

import base64
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
TECH = (
    "swift", "python", "shell", "javascript", "html", "css", "typescript",
    "nodejs", "vite", "react", "nextjs", "astro", "supabase",
)
TECH_LABELS = (
    "Swift", "Python", "Shell", "JavaScript", "HTML", "CSS", "TypeScript",
    "Node.js", "Vite", "React", "Next.js", "Astro", "Supabase",
)
BASE_BADGES = {
    "Swift": "swift", "Python": "python", "Shell": "shell",
    "JavaScript": "javascript", "HTML": "html", "CSS": "css",
    "Node.js": "nodejs", "Vite": "vite",
}
GRID_FILES = {
    f"assets/tech/technology-grid-{layout}-{theme}.svg"
    for layout in ("desktop", "mobile")
    for theme in ("dark", "light")
}
LEGACY_BADGES = {f"assets/tech/{name}.svg" for name in BASE_BADGES.values()}
ASSETS = {
    "assets/browser-chess-launcher.svg", "assets/music/slappywax-cover.jpg",
    "assets/hoops/hoops.svg", "assets/hoops/hoops-dark.svg",
    *LEGACY_BADGES, *GRID_FILES,
}
ALLOWED = {
    ".gitignore", "README.md", "scripts/check_readme.py",
    ".github/workflows/update-hoops.yml", *ASSETS,
}
NS = "{http://www.w3.org/2000/svg}"
HEADINGS = {
    "Apps & Scripting", "Web", "Languages", "Runtime & Tooling",
    "Frameworks", "Platform",
}


class Markup(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[dict[str, str | None]] = []
        self.sources: list[dict[str, str | None]] = []
        self.centered_groups = 0
        self.h1 = False

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


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def check_grid(path: Path, layout: str, theme: str) -> ET.Element:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        fail(f"invalid SVG {path.relative_to(ROOT)}: {exc}")
    if root.tag != f"{NS}svg" or root.get("role") != "img":
        fail(f"technology grid needs an SVG image root: {path.name}")
    if root.find(f"{NS}title") is None or root.find(f"{NS}desc") is None:
        fail(f"technology grid needs an accessible title and description: {path.name}")

    nested = [node for node in root.iter() if node.tag.endswith("image")]
    labels: list[str] = []
    for node in nested:
        try:
            source = base64.b64decode(node.get("href", "").split(",", 1)[1])
            badge = ET.fromstring(source)
        except Exception as exc:
            fail(f"invalid embedded badge in {path.name}: {exc}")
        title = badge.find(f"{NS}title")
        label = (title.text or "").strip() if title is not None else ""
        labels.append(label)
        if label not in TECH_LABELS:
            fail(f"unknown technology badge in {path.name}: {label!r}")
        if label in BASE_BADGES:
            expected = (ROOT / f"assets/tech/{BASE_BADGES[label]}.svg").read_bytes()
            if source != expected:
                fail(f"existing {label} badge artwork changed in {path.name}")
        if node.get("height") != "30":
            fail(f"technology badge height changed in {path.name}")
    if labels != list(TECH_LABELS):
        fail(f"technology badge names/order differ in {path.name}: {labels}")

    columns = sorted({float(node.get("x", "-1")) for node in nested})
    expected_columns = [20.0, 130.0, 330.0, 470.0] if layout == "desktop" else [44.0, 197.0]
    if columns != expected_columns:
        fail(f"unexpected {layout} badge columns in {path.name}: {columns}")

    texts = [node for node in root.iter() if node.tag.endswith("text")]
    heading_nodes = {node.text: node for node in texts if node.text in HEADINGS}
    if set(heading_nodes) != HEADINGS:
        fail(f"technology headings differ in {path.name}: {sorted(heading_nodes)}")
    color = "#FFFFFF" if theme == "dark" else "#1F2328"
    if any(
        node.get("fill") != color
        or any(attr in node.attrib for attr in ("stroke", "filter", "style"))
        for node in heading_nodes.values()
    ):
        fail(f"{theme} headings must be plain {color} text in {path.name}")
    if any(node.tag.endswith("rect") for node in root.iter()):
        fail(f"technology grid must remain transparent: {path.name}")

    positions = {node.text: (node.get("x"), node.get("y")) for node in texts}
    if layout == "desktop":
        if positions.get("Apps & Scripting") != ("120", "31") or positions.get("Web") != ("460", "31"):
            fail(f"desktop category headings are not aligned in {path.name}")
        rows = {"Languages": "72", "Runtime & Tooling": "171", "Frameworks": "240", "Platform": "347"}
        if any(positions.get(label) != ("460", y) for label, y in rows.items()):
            fail(f"desktop subgroup headings moved in {path.name}")
    elif positions.get("Apps & Scripting") != ("185", "28") or positions.get("Web") != ("185", "139"):
        fail(f"mobile categories are not vertically stacked in {path.name}")
    return root


def main() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if not re.search(r'<h1\s+align="center">dxnnystyles</h1>', readme):
        fail("centered dxnnystyles identity is missing")
    if "Software · Chess · Music" not in readme:
        fail("approved identity line is missing")
    if re.search(r"^#{1,6}\s", readme, flags=re.MULTILINE):
        fail("traditional Markdown section headings remain")
    if "English" not in readme or "Français · Learning" not in readme:
        fail("centered spoken-language row is missing")
    spotify_url = "https://open.spotify.com/album/0aLqVmlz4ytvJRcGKW8q4D"
    if readme.count("Danny Styles - slappywax") != 1 or readme.count(spotify_url) != 1:
        fail("approved slappywax wording or destination changed")
    if "<picture>" in readme and readme.count("<picture>") != 2:
        fail("only the two technology-grid pictures are permitted")
    if "prefers-color-scheme" in readme:
        fail("theme selection must not depend on system appearance")

    parser = Markup()
    parser.feed(readme)
    if not parser.h1 or not parser.centered_groups:
        fail("identity and widget groups must remain centered")
    if any(not (image.get("alt") or "").strip() for image in parser.images):
        fail("all images need accessible alternative text")

    pictures = re.findall(r"<picture>(.*?)</picture>", readme, flags=re.DOTALL)
    if len(pictures) != 2 or len(parser.sources) != 2:
        fail("expected two technology picture elements and mobile sources")
    expected_variants = {
        "dark": ("assets/tech/technology-grid-desktop-dark.svg#gh-dark-mode-only", "assets/tech/technology-grid-mobile-dark.svg"),
        "light": ("assets/tech/technology-grid-desktop-light.svg#gh-light-mode-only", "assets/tech/technology-grid-mobile-light.svg"),
    }
    for theme, (desktop_ref, mobile_ref) in expected_variants.items():
        matches = [block for block in pictures if desktop_ref in block]
        if len(matches) != 1 or f'srcset="{mobile_ref}"' not in matches[0]:
            fail(f"{theme} desktop/mobile assets must be paired inside one picture")
        if f'media="(max-width: 600px)"' not in matches[0]:
            fail(f"{theme} mobile grid needs the 600px source breakpoint")
    if any("#gh-" in (source.get("srcset") or "") for source in parser.sources):
        fail("theme suffixes must stay on img src, not rely on srcset suffix handling")

    tech_images = [image for image in parser.images if (image.get("src") or "").startswith("assets/tech/technology-grid-desktop-")]
    if len(tech_images) != 2 or tech_images[0].get("alt") != tech_images[1].get("alt"):
        fail("dark/light technology images need the same accessible description")
    alt = tech_images[0].get("alt") or ""
    if not all(label.casefold() in alt.casefold() for label in TECH_LABELS):
        fail("technology-grid alternative text must name all 13 technologies")

    targets = {(image.get("src") or "").split("#", 1)[0] for image in parser.images}
    targets.update((source.get("srcset") or "").split()[0].split("#", 1)[0] for source in parser.sources)
    expected_targets = ASSETS - {"assets/hoops/hoops-dark.svg", *LEGACY_BADGES}
    if targets != expected_targets:
        fail(f"README image inventory differs: {sorted(targets ^ expected_targets)}")
    if any(not (ROOT / target).is_file() for target in targets):
        fail("README refers to a missing asset")

    if sum((image.get("src") or "").startswith("assets/hoops/hoops.svg") for image in parser.images) != 1:
        fail("the original single Hoops asset must remain displayed")
    if "assets/hoops/hoops-dark.svg" in readme:
        fail("the unpublished dark Hoops asset must remain unused")
    if "Open the live game" not in readme or "Source" not in re.sub(r"<[^>]+>", " ", readme):
        fail("Browser Chess launcher and source label must remain present")
    urls = {match.rstrip(".,") for match in re.findall(r"https://[^\s\"<>]+", readme)}
    if urls != EXPECTED_URLS:
        fail(f"approved destinations changed: {sorted(urls ^ EXPECTED_URLS)}")

    for label, name in BASE_BADGES.items():
        svg = (ROOT / f"assets/tech/{name}.svg").read_text(encoding="utf-8")
        if f'aria-label="{label}"' not in svg or f"<title>{label}</title>" not in svg:
            fail(f"existing {label} badge is missing its accessible name")
    for path in sorted((ROOT / "assets").rglob("*.svg")):
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            fail(f"invalid SVG {path.relative_to(ROOT)}: {exc}")
        if root.tag != f"{NS}svg":
            fail(f"invalid SVG root: {path.relative_to(ROOT)}")
        for node in root.iter():
            if any(key.endswith("href") and value.startswith(("http:", "https:")) for key, value in node.attrib.items()):
                fail(f"remote embedded image in {path.relative_to(ROOT)}")

    for layout in ("desktop", "mobile"):
        dark = check_grid(ROOT / f"assets/tech/technology-grid-{layout}-dark.svg", layout, "dark")
        light = check_grid(ROOT / f"assets/tech/technology-grid-{layout}-light.svg", layout, "light")
        dark_nodes, light_nodes = list(dark.iter()), list(light.iter())
        if dark.attrib != light.attrib or len(dark_nodes) != len(light_nodes):
            fail(f"{layout} theme variants have different structure or dimensions")
        for left, right in zip(dark_nodes, light_nodes):
            if left.tag != right.tag or left.text != right.text:
                fail(f"{layout} theme variants have different content")
            if left.tag.endswith("text") and left.text in HEADINGS:
                if {key: value for key, value in left.attrib.items() if key != "fill"} != {key: value for key, value in right.attrib.items() if key != "fill"}:
                    fail(f"{layout} heading geometry differs between themes")
            elif left.attrib != right.attrib:
                fail(f"{layout} badges or geometry differ between themes")

    if (ROOT / "assets/music/slappywax-cover.jpg").read_bytes()[:2] != b"\xff\xd8":
        fail("album artwork is not a JPEG")
    workflow = (ROOT / ".github/workflows/update-hoops.yml").read_text(encoding="utf-8")
    if "HarrisJDCampbell/hoops@c90b483d3f7e61544afaee4c105a51d410346cb2" not in workflow:
        fail("Hoops action revision changed")
    if "github_user_name: dxnnystyles" not in workflow or "read:user" in workflow:
        fail("Hoops must remain public-data-only for dxnnystyles")
    if "git add assets/hoops/hoops.svg assets/hoops/hoops-dark.svg" not in workflow:
        fail("Hoops workflow staging behavior changed")

    actual = {path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*") if path.is_file() and ".git" not in path.parts and "__pycache__" not in path.parts}
    if actual != ALLOWED:
        fail(f"public file allowlist differs: {sorted(actual ^ ALLOWED)}")
    print(f"PASS: centered profile, 13 technology names, 4 theme/layout SVGs, existing Hoops/Chess/music checks, {len(urls)} approved links, {len(actual)} allowed files. Responsive source selection requires live GitHub verification.")


if __name__ == "__main__":
    main()
