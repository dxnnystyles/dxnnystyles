#!/usr/bin/env python3
"""Prepare, derive, and validate all public Hoops SVGs before publication."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import os
import tempfile
import xml.etree.ElementTree as ET


NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)
FILES = ("hoops.svg", "hoops-dark.svg", "hoops-profile-dark-panel.svg")
ATTRIBUTION = "dxnnystyles · public contributions"
DESCRIPTION = (
    "Public GitHub contribution activity for dxnnystyles, animated as a basketball shootaround. "
    "The cells, dates, scores and animation use public dxnnystyles activity only."
)
PANEL_DESCRIPTION = (
    "Public GitHub contribution activity for dxnnystyles, animated as a basketball shootaround "
    "on a fixed charcoal panel. The cells, dates, scores and animation use public dxnnystyles activity only."
)


def _tag(name: str) -> str:
    return f"{{{NS}}}{name}"


def _remove_updated_labels(root: ET.Element) -> None:
    for parent in root.iter():
        for child in list(parent):
            if child.get("id") == "hoops-updated-at" or (
                child.tag == _tag("text") and (child.text or "").startswith("Updated ")
            ):
                parent.remove(child)


def _set_description(root: ET.Element, text: str) -> None:
    desc = root.find(_tag("desc"))
    if desc is None:
        desc = ET.Element(_tag("desc"))
        title = root.find(_tag("title"))
        root.insert(list(root).index(title) + 1 if title is not None else 0, desc)
    desc.text = text


def _insert_panel(root: ET.Element, panel: ET.Element) -> None:
    for child in list(root):
        if child.get("id") in ("widget-dark-panel", "hoops-theme-independent-panel"):
            root.remove(child)
    style = next((node for node in list(root) if node.tag == _tag("style")), None)
    index = list(root).index(style) + 1 if style is not None else 0
    root.insert(index, deepcopy(panel))


def _set_date(root: ET.Element, date_label: str, color: str) -> None:
    _remove_updated_labels(root)
    label = ET.Element(_tag("text"), {
        "id": "hoops-updated-at", "x": "884", "y": "215", "text-anchor": "end",
        "font-size": "10", "fill": color,
    })
    label.text = date_label
    root.append(label)


def _validate_source(path: Path) -> ET.Element:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as error:
        raise ValueError(f"invalid Hoops input {path.name}: {error}") from error
    if root.tag != _tag("svg") or (root.get("width"), root.get("height"), root.get("viewBox")) != (
        "900", "218", "0 0 900 218"
    ):
        raise ValueError(f"unexpected Hoops SVG dimensions: {path.name}")
    title = root.find(_tag("title"))
    if title is None or "dxnnystyles" not in (title.text or "").casefold():
        raise ValueError(f"missing dxnnystyles title: {path.name}")
    raw = path.read_text(encoding="utf-8")
    if "aaronsanchez2000" in raw.casefold():
        raise ValueError(f"unexpected second-account content: {path.name}")
    visible_text = " ".join(node.text or "" for node in root.findall(f".//{_tag('text')}"))
    if ATTRIBUTION not in visible_text:
        raise ValueError(f"missing public-data attribution: {path.name}")
    style = root.find(_tag("style"))
    if style is None or "@keyframes" not in (style.text or ""):
        raise ValueError(f"missing upstream Hoops animation: {path.name}")
    return root


def _validate_panel_template(path: Path) -> ET.Element:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as error:
        raise ValueError(f"invalid Hoops panel template: {error}") from error
    panel = next((node for node in root.iter(_tag("rect")) if node.get("id") == "widget-dark-panel"), None)
    if panel is None or panel.get("fill") != "#161b22" or panel.get("rx") is None:
        raise ValueError("panel template must contain the approved rounded charcoal background")
    return panel


def _validate_output(path: Path, expect_panel: bool) -> None:
    root = _validate_source(path)
    title = root.find(_tag("title"))
    desc = root.find(_tag("desc"))
    if title is None or desc is None or not (desc.text or "").strip():
        raise ValueError(f"missing accessible title or description: {path.name}")
    labels = [node for node in root.findall(f".//{_tag('text')}") if node.get("id") == "hoops-updated-at"]
    if len(labels) != 1 or not (labels[0].text or "").startswith("Updated "):
        raise ValueError(f"missing unique UTC update label: {path.name}")
    panels = [node for node in root.iter(_tag("rect")) if node.get("id") == "widget-dark-panel"]
    if len(panels) != (1 if expect_panel else 0):
        raise ValueError(f"unexpected dark-panel count: {path.name}")
    if path.name == "hoops.svg":
        white_panels = [node for node in root.iter(_tag("rect")) if node.get("id") == "hoops-theme-independent-panel"]
        if len(white_panels) != 1 or white_panels[0].get("fill") != "#ffffff":
            raise ValueError("light Hoops asset is missing its opaque white panel")


def validate_asset_directory(directory: Path) -> None:
    """Validate the exact transferred three-file set before any publication."""
    try:
        actual = {path.name for path in directory.iterdir()}
    except OSError as error:
        raise ValueError(f"cannot inspect Hoops artifact directory: {error}") from error
    if actual != set(FILES) or any(not (directory / name).is_file() for name in FILES):
        raise ValueError(f"Hoops artifact must contain exactly {', '.join(FILES)}")
    roots = {name: _validate_source(directory / name) for name in FILES}
    for name in FILES:
        _validate_output(directory / name, expect_panel=name == "hoops-profile-dark-panel.svg")
    dates = {
        name: next(node.text for node in roots[name].iter(_tag("text")) if node.get("id") == "hoops-updated-at")
        for name in FILES
    }
    if len(set(dates.values())) != 1:
        raise ValueError("Hoops artifact files have mismatched update dates")
    date_label = next(iter(dates.values()))
    try:
        parsed_date = datetime.strptime(date_label, "Updated %Y-%m-%d UTC")
    except ValueError as error:
        raise ValueError("Hoops artifact has an invalid UTC update date") from error
    if date_label != parsed_date.strftime("Updated %Y-%m-%d UTC"):
        raise ValueError("Hoops artifact has a noncanonical UTC update date")
    if [node.text for node in _validate_output_style(directory / "hoops-dark.svg")] != [
        node.text for node in _validate_output_style(directory / "hoops-profile-dark-panel.svg")
    ]:
        raise ValueError("derived dark panel does not preserve the generated animation")


def prepare_assets(generated_dir: Path, output_dir: Path, panel_template: Path, date: str | None = None) -> None:
    """Build all three assets in temporary storage, then expose only a validated set."""
    date_label = f"Updated {date or datetime.now(timezone.utc).strftime('%Y-%m-%d')} UTC"
    try:
        datetime.strptime(date_label, "Updated %Y-%m-%d UTC")
    except ValueError as error:
        raise ValueError("date must use YYYY-MM-DD") from error

    light = _validate_source(generated_dir / "hoops.svg")
    dark = _validate_source(generated_dir / "hoops-dark.svg")
    panel_background = _validate_panel_template(panel_template)

    _set_description(light, DESCRIPTION)
    _insert_panel(light, ET.Element(_tag("rect"), {
        "id": "hoops-theme-independent-panel", "x": "1", "y": "1", "width": "898",
        "height": "216", "rx": "8", "fill": "#ffffff", "stroke": "#d0d7de",
        "stroke-width": "1", "pointer-events": "none",
    }))
    _set_date(light, date_label, "#57606a")

    _set_description(dark, DESCRIPTION)
    _set_date(dark, date_label, "#7d8590")
    panel = deepcopy(dark)
    _set_description(panel, PANEL_DESCRIPTION)
    _insert_panel(panel, panel_background)
    _set_date(panel, date_label, "#7d8590")

    staged_roots = {
        "hoops.svg": light,
        "hoops-dark.svg": dark,
        "hoops-profile-dark-panel.svg": panel,
    }
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hoops-validated-", dir=output_dir.parent) as stage_name:
        stage_dir = Path(stage_name)
        for filename, root in staged_roots.items():
            ET.ElementTree(root).write(stage_dir / filename, encoding="utf-8", xml_declaration=False)
        validate_asset_directory(stage_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for filename in FILES:
            replacement = output_dir / f".{filename}.new"
            replacement.write_bytes((stage_dir / filename).read_bytes())
            os.replace(replacement, output_dir / filename)


def _validate_output_style(path: Path) -> list[ET.Element]:
    root = ET.parse(path).getroot()
    styles = root.findall(_tag("style"))
    if not styles or "@keyframes" not in (styles[0].text or ""):
        raise ValueError(f"missing CSS animation: {path.name}")
    return styles


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True, help="prepared output directory or transferred artifact directory")
    parser.add_argument("--panel-template", type=Path)
    parser.add_argument("--validate-only", action="store_true", help="validate an exact transferred three-file set")
    parser.add_argument("--date", help="UTC YYYY-MM-DD override for deterministic tests")
    args = parser.parse_args()
    try:
        if args.validate_only:
            validate_asset_directory(args.output_dir)
        else:
            if args.generated_dir is None or args.panel_template is None:
                parser.error("--generated-dir and --panel-template are required unless --validate-only is used")
            prepare_assets(args.generated_dir, args.output_dir, args.panel_template, args.date)
    except (OSError, ValueError) as error:
        parser.exit(1, f"FAIL: {error}\n")
    print("PASS: validated the exact three-file public Hoops asset set" if args.validate_only else
          "PASS: validated and prepared the complete three-file public Hoops asset set")


if __name__ == "__main__":
    main()
