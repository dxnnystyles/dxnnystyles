#!/usr/bin/env python3
"""Check the centered expanded public profile candidate and its asset allowlist."""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
import argparse
from html.parser import HTMLParser
from pathlib import Path

from summary_card_date import extract_date_line

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_URLS = {
    "https://dxnnystyles.github.io/browser-chess/",
    "https://github.com/dxnnystyles/browser-chess",
    "https://open.spotify.com/album/0aLqVmlz4ytvJRcGKW8q4D",
}
TECH = ("swift", "python", "shell", "javascript", "html", "css", "typescript", "nodejs", "vite", "react", "nextjs", "astro", "supabase")
TECH_LABELS = ("Swift", "Python", "Shell", "JavaScript", "HTML", "CSS", "TypeScript", "Node.js", "Vite", "React", "Next.js", "Astro", "Supabase")
TECH_BACKGROUNDS = {
    "swift": "#B23C1F", "python": "#1E5B82", "shell": "#A44800", "javascript": "#5D5310",
    "html": "#A63E00", "css": "#1150A0", "typescript": "#175A9A", "nodejs": "#25652C",
    "vite": "#4936A5", "react": "#065D73", "nextjs": "#3B3B3B", "astro": "#762AA5", "supabase": "#126B4E",
}
SVG_NS = "{http://www.w3.org/2000/svg}"
GRID_ASSETS = {
    f"assets/tech/technology-grid-{layout}-{theme}.svg"
    for layout in ("desktop", "mobile")
    for theme in ("dark", "light")
}
ASSETS = {
    "assets/browser-chess-launcher.svg", "assets/music/slappywax-cover.jpg",
    "assets/hoops/hoops-profile-dark-panel.svg", "assets/hoops/hoops.svg",
    "assets/hoops/hoops-dark.svg", "assets/3d/profile-night-view.svg",
    *(f"assets/summary-cards/{name}.svg" for name in (
        "0-profile-details", "1-repos-per-language", "2-most-commit-language",
        "3-stats", "4-productive-time",
    )),
    *(f"assets/tech/{name}.svg" for name in TECH),
}
ALLOWED = {".gitignore", "README.md", "scripts/check_readme.py", "scripts/summary_card_date.py", "scripts/verify_summary_cards.py", "scripts/publish_summary_cards.py", "scripts/prepare_hoops_assets.py", ".github/workflows/update-hoops.yml", ".github/workflows/update-summary-cards.yml", "tests/test_summary_card_refresh.py", "tests/test_hoops_refresh.py", *ASSETS}

class Markup(HTMLParser):
    def __init__(self) -> None:
        super().__init__(); self.images: list[dict[str, str | None]] = []; self.sources: list[dict[str, str | None]] = []; self.urls: set[str] = set(); self.paragraph_images: list[list[str]] = []; self._current_p: list[str] | None = None
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        item = dict(attrs)
        if tag == "p": self._current_p = []
        if tag == "source": self.sources.append(item)
        if tag == "img":
            self.images.append(item)
            if self._current_p is not None: self._current_p.append(item.get("src", "") or "")
        if tag == "a" and item.get("href"): self.urls.add(item["href"] or "")
    def handle_endtag(self, tag: str) -> None:
        if tag == "p" and self._current_p is not None:
            self.paragraph_images.append(self._current_p); self._current_p = None

class VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(); self.parts: list[str] = []
    def handle_data(self, data: str) -> None:
        self.parts.append(data)

def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr); raise SystemExit(1)

def main() -> None:
    parser_args = argparse.ArgumentParser(description=__doc__)
    parser_args.add_argument(
        "--require-refresh-date",
        action="store_true",
        help="Fail if the first successful complete refresh has not populated the hidden provenance marker yet.",
    )
    args = parser_args.parse_args()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    try:
        refresh_date = extract_date_line(readme)
    except ValueError as error:
        fail(str(error))
    if refresh_date is None and args.require_refresh_date:
        fail("the internal snapshot marker is not initialized; it is added after a successful complete refresh")
    if "Profile snapshot · Updated" in readme:
        fail("the internal refresh date must not be displayed as a README caption")
    visible=VisibleText(); visible.feed(readme)
    if "profile-snapshot-date:" in "".join(visible.parts):
        fail("the internal snapshot marker must remain an HTML comment, not visible profile text")
    if '<h1 align="center">dxnnystyles</h1>\n<p align="center">Software · Chess · Music</p>' not in readme:
        fail("centered H1 identity and directly following subtitle are required")
    if re.search(r"^#{1,6}\s", readme, flags=re.MULTILINE) or "Beyond code" in readme.casefold():
        fail("Markdown section headings or the removed Beyond Code section remain")
    headings = re.findall(r"<(h[2-6]) align=\"center\">(.*?)</\1>", readme, flags=re.IGNORECASE)
    expected_headings = [
        ("h2", "Apps &amp; Scripting"),
        ("h2", "Web"),
        ("h2", "GitHub Activity"),
        ("h2", "Stats"),
        ("h2", "Projects"),
        ("h2", "Music / Other"),
    ]
    if headings != expected_headings or len(re.findall(r"<h[2-6]\b", readme, flags=re.IGNORECASE)) != 6:
        fail("the six approved centered section headings, in order and with consistent markup, are required")
    if readme.count("assets/hoops/hoops-profile-dark-panel.svg") != 1: fail("fixed dark Hoops panel is not the single displayed Hoops asset")
    if "Danny Styles - slappywax" not in readme or readme.count("https://open.spotify.com/album/0aLqVmlz4ytvJRcGKW8q4D") != 1:
        fail("exact slappywax wording/link is missing or duplicated")
    if "Browser Chess Source" not in readme or "Open the live game" not in readme: fail("approved game links are missing")
    if any(term in readme.casefold() for term in ("@aaronsanchez2000", "spotify.com/embed", "<iframe", "chess.com", "trophy", "linktree", "ds-site", "lowlighter")):
        fail("README contains an unapproved identity, integration, or destination")
    parser=Markup(); parser.feed(readme)
    paired={"assets/summary-cards/3-stats.svg", "assets/summary-cards/1-repos-per-language.svg"}
    if not any(paired.issubset(set(group)) for group in parser.paragraph_images): fail("Stats and Repositories per Language must share one inline responsive paragraph")
    second_pair={"assets/summary-cards/2-most-commit-language.svg", "assets/summary-cards/4-productive-time.svg"}
    if not any(second_pair.issubset(set(group)) for group in parser.paragraph_images): fail("Most Commit Language and Productive Time must share one inline responsive paragraph")
    if len(parser.images) != 22: fail(f"expected 13 technology badges and nine other images; found {len(parser.images)}")
    if any(not (image.get("alt") or "").strip() for image in parser.images): fail("an image is missing alternative text")
    image_paths={image.get("src", "").split("#",1)[0] for image in parser.images}
    source_paths={source.get("srcset", "").split("#",1)[0] for source in parser.sources}
    references=image_paths|source_paths
    expected_references=ASSETS-{"assets/hoops/hoops.svg", "assets/hoops/hoops-dark.svg"}
    if references != expected_references: fail(f"README asset references differ: {sorted(references ^ expected_references)}")
    if parser.sources or "<picture" in readme.casefold(): fail("technology badges must not use responsive picture selection")
    if any(path in readme for path in GRID_ASSETS): fail("superseded technology-grid assets must not be referenced by the README")
    tech_images=[image for image in parser.images if image.get("src", "").startswith("assets/tech/")]
    if [image.get("src") for image in tech_images] != [f"assets/tech/{name}.svg" for name in TECH]:
        fail("all 13 technology badges must appear in the approved order")
    if [image.get("alt") for image in tech_images] != list(TECH_LABELS):
        fail("technology badges must retain their accessible names")
    if any(image.get("height")!="30" for image in tech_images): fail("technology badge height must remain 30px")
    ordered_labels=("Apps &amp; Scripting", "Web", "Languages", "Runtime &amp; Tooling", "Frameworks", "Platform", "🇺🇸 English", "🇫🇷 Français · Learning")
    positions=[readme.find(label) for label in ordered_labels]
    if any(position<0 for position in positions) or positions!=sorted(positions):
        fail("technology categories, subgroups, and spoken-language labels are missing or out of order")
    if readme.count('align="center"') < 8: fail("identity, technology labels, and widget rows must remain centered")
    anchors=("assets/summary-cards/0-profile-details.svg","assets/hoops/hoops-profile-dark-panel.svg","assets/3d/profile-night-view.svg","assets/summary-cards/3-stats.svg","assets/summary-cards/2-most-commit-language.svg","assets/browser-chess-launcher.svg","assets/music/slappywax-cover.jpg")
    positions=[readme.find(anchor) for anchor in anchors]
    if any(position<0 for position in positions) or positions!=sorted(positions):
        fail("Profile Details must precede Hoops, with the five-card set after Hoops and Neon Ember")
    if parser.urls != EXPECTED_URLS: fail(f"destinations differ: {sorted(parser.urls ^ EXPECTED_URLS)}")
    for target in references:
        if not (ROOT / target).is_file(): fail(f"missing image {target}")
    paired_charts=[ET.parse(ROOT/path).getroot() for path in sorted(paired)]
    dimensions=[(chart.get("width"), chart.get("height"), chart.get("viewBox")) for chart in paired_charts]
    if dimensions[0] != dimensions[1]: fail("Public GitHub Stats and Repository Languages SVG canvases must have identical dimensions and aspect ratios")
    for name in TECH:
        path=ROOT/f"assets/tech/{name}.svg"
        root=ET.parse(path).getroot()
        title=root.find("{http://www.w3.org/2000/svg}title")
        desc=root.find("{http://www.w3.org/2000/svg}desc")
        label=root.find("{http://www.w3.org/2000/svg}text")
        rect=root.find("{http://www.w3.org/2000/svg}rect")
        if root.get("role")!="img" or title is None or title.text!=TECH_LABELS[TECH.index(name)] or desc is None:
            fail(f"technology badge lacks its accessible name/description: {name}")
        if (root.get("height"), root.get("viewBox", "").split()[-1]) != ("32", "32") or rect is None or rect.get("fill")!=TECH_BACKGROUNDS[name]:
            fail(f"technology badge is not a consistent solid brand-color chip: {name}")
        if label is None or label.text!=TECH_LABELS[TECH.index(name)] or label.get("fill")!="#FFFFFF":
            fail(f"technology badge lacks readable white label text: {name}")
        if root.find(f"{SVG_NS}svg") is None:
            fail(f"technology badge must retain its vector logo: {name}")
        if any(node.tag.endswith(("linearGradient", "radialGradient", "filter")) for node in root.iter()):
            fail(f"technology badge must not use mixed gradient/filter styling: {name}")
        background=TECH_BACKGROUNDS[name]
        def luminance(color: str) -> float:
            channels=[int(color[index:index+2],16)/255 for index in (1,3,5)]
            linear=[value/12.92 if value<=0.04045 else ((value+0.055)/1.055)**2.4 for value in channels]
            return .2126*linear[0]+.7152*linear[1]+.0722*linear[2]
        contrast=1.05/(luminance(background)+.05)
        if contrast<5:
            fail(f"technology badge label contrast is below 5:1: {name} ({contrast:.2f}:1)")
    ns=SVG_NS
    for path in sorted((ROOT/"assets").rglob("*.svg")):
        try: root=ET.parse(path).getroot()
        except ET.ParseError as exc: fail(f"invalid SVG {path.relative_to(ROOT)}: {exc}")
        if root.tag != f"{ns}svg": fail(f"invalid SVG root: {path.relative_to(ROOT)}")
        for node in root.iter():
            if any(k.endswith("href") and v.startswith(("http:", "https:")) for k,v in node.attrib.items()): fail(f"remote embedded image in {path.relative_to(ROOT)}")
    cover=(ROOT/"assets/music/slappywax-cover.jpg").read_bytes()
    if cover[:2] != b"\xff\xd8": fail("slappywax source image is not JPEG")
    card_paths=sorted((ROOT/"assets/summary-cards").glob("*.svg"))
    if len(card_paths)!=5: fail(f"expected five summary-card assets; found {len(card_paths)}")
    for chart_path in card_paths:
        chart=ET.parse(chart_path).getroot()
        if not any(node.tag.endswith("rect") and node.get("fill")=="#161b22" for node in chart.iter()): fail(f"chart must use the shared dark surface: {chart_path.relative_to(ROOT)}")
        if chart.get("role")!="img" or chart.find(f"{ns}title") is None or chart.find(f"{ns}desc") is None:
            fail(f"summary card needs intrinsic accessible naming: {chart_path.relative_to(ROOT)}")
    details=ET.parse(ROOT/"assets/summary-cards/0-profile-details.svg").getroot()
    details_text=" ".join(node.text or "" for node in details.iter())
    if re.search(r"\b(?:email|company|location|website|twitter)\b|[\w.+-]+@[\w.-]+\.[a-z]{2,}",details_text,re.I):
        fail("Profile Details contains contact metadata")
    if (details.get("width"), details.get("height"), details.get("viewBox")) != ("700", "200", "0 0 700 200"):
        fail("Profile Details must use the compact responsive 700x200 layout")
    details_desc = details.find(f"{ns}desc")
    if details_desc is None or "all-time contributions" not in (details_desc.text or "") or "contribution chart are omitted" not in (details_desc.text or ""):
        fail("Profile Details must describe public totals and omitted chart/contact fields")
    if not all(label in details_text for label in ("All-time", "contributions", "Public repos", "non-fork", "GitHub account age")):
        fail("Profile Details is missing its approved public statistics labels")
    if re.search(r"contribution graph|contributions in the last year|monthly totals|\b\d{2}/(?:0[1-9]|1[0-2])\b",details_text,re.I):
        fail("Profile Details must not render a contribution chart or rolling-calendar labels")
    for filename in ("1-repos-per-language.svg","2-most-commit-language.svg","3-stats.svg","4-productive-time.svg"):
        card=ET.parse(ROOT/"assets/summary-cards"/filename).getroot()
        if (card.get("width"),card.get("height"),card.get("viewBox"))!=("340","200","0 0 340 200"):
            fail(f"supporting card must use matching 340x200 dimensions: {filename}")
    if "America/Los_Angeles" not in (ROOT/"assets/summary-cards/4-productive-time.svg").read_text(encoding="utf-8"):
        fail("Productive Time must retain the verified local time zone")
    panel=ET.parse(ROOT/"assets/hoops/hoops-profile-dark-panel.svg").getroot()
    dark=ET.parse(ROOT/"assets/hoops/hoops-dark.svg").getroot()
    panel_rect=next((node for node in panel.iter() if node.get("id")=="widget-dark-panel"),None)
    style_text=lambda tree:[node.text for node in tree.iter() if node.tag.endswith("style")]
    if panel_rect is None or panel_rect.get("fill")!="#161b22" or style_text(panel)!=style_text(dark):
        fail("dark Hoops panel must be opaque and preserve the upstream dark artwork animation")
    workflow=(ROOT/".github/workflows/update-hoops.yml").read_text()
    if "HarrisJDCampbell/hoops@c90b483d3f7e61544afaee4c105a51d410346cb2" not in workflow or "github_user_name: dxnnystyles" not in workflow or "read:user" in workflow:
        fail("existing pinned public-only Hoops workflow changed unexpectedly")
    if "out_dir: ${{ runner.temp }}/hoops-generated" not in workflow or "scripts/prepare_hoops_assets.py" not in workflow:
        fail("Hoops must generate and validate outside tracked assets before promotion")
    if any(name not in workflow for name in ("hoops.svg", "hoops-dark.svg", "hoops-profile-dark-panel.svg")):
        fail("Hoops publication must include both generator outputs and the README-displayed panel")
    chess=ET.parse(ROOT/"assets/browser-chess-launcher.svg").getroot()
    chess_bg=next((node.get("fill") for node in chess if node.tag.endswith("rect") and node.get("width")=="900"),None)
    if chess_bg!="#161b22" or "#66DEAD" not in " ".join(node.attrib.get("stroke","")+node.attrib.get("fill","") for node in chess.iter()):
        fail("Browser Chess launcher must retain the approved charcoal and mint palette")
    if "Dead Pixel Club" not in (chess.find(f"{ns}desc").text or "") or "DEAD PIXEL CLUB" not in " ".join(node.text or "" for node in chess.iter()):
        fail("Browser Chess launcher must retain its restrained Dead Pixel Club identity")
    actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts}
    if actual != ALLOWED: fail(f"public allowlist differs: {sorted(actual ^ ALLOWED)}")
    for old in ("assets/stats/github-public-stats.svg", "assets/stats/repository-languages.svg", "assets/activity/public-events-sample.svg"):
        if (ROOT/old).exists(): fail(f"replaced legacy widget asset remains: {old}")
    date_status = f"refresh date {refresh_date[0]}" if refresh_date else "refresh date awaits first successful publication"
    print(f"PASS: centered composition; vertical text-and-badge technology groups; {len(TECH)} labeled technologies; five unified public-data cards; {date_status}; chess/music destinations; {len(parser.images)} accessible images; {len(actual)} allowed files.")

if __name__ == "__main__": main()
