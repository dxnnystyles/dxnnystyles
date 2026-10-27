#!/usr/bin/env python3
"""Shared parsing and formatting for the five-card refresh date."""

from datetime import date, datetime, timezone
import re


DATE_MARKER = "Profile snapshot · Updated"
DATE_LINE_PATTERN = re.compile(
    r"<p align=\"center\"><sub>Profile snapshot · Updated "
    r"<strong>(\d{4}-\d{2}-\d{2})</strong></sub></p>"
)
PROFILE_DETAILS_ANCHOR = '<p align="center"><img src="assets/summary-cards/0-profile-details.svg"'


def utc_publication_timestamp(now: datetime | None = None) -> datetime:
    """Return an aware UTC timestamp suitable for the publication commit."""
    value = now if now is not None else datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Publication time must include a timezone.")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def format_date_line(updated_date: str) -> str:
    """Render a theme-adaptive, centered native GitHub Markdown date line."""
    try:
        parsed = date.fromisoformat(updated_date)
    except ValueError as error:
        raise ValueError("Refresh date must be a valid YYYY-MM-DD date.") from error
    if parsed.isoformat() != updated_date:
        raise ValueError("Refresh date must use canonical YYYY-MM-DD format.")
    return (
        '<p align="center"><sub>Profile snapshot · Updated '
        f"<strong>{updated_date}</strong></sub></p>"
    )


def extract_date_line(readme: str) -> tuple[str, int, int] | None:
    """Return the date and source range, rejecting malformed or misplaced markers."""
    marker_count = readme.count(DATE_MARKER)
    if marker_count == 0:
        return None
    if marker_count != 1:
        raise ValueError("README must contain at most one Profile snapshot date line.")

    anchor_count = readme.count(PROFILE_DETAILS_ANCHOR)
    if anchor_count != 1:
        raise ValueError("README must contain exactly one Profile Details card anchor.")
    anchor_index = readme.index(PROFILE_DETAILS_ANCHOR)
    prefix = readme[:anchor_index]
    nonempty_lines = [(line, start, end) for line, start, end in _line_ranges(prefix) if line.strip()]
    if not nonempty_lines:
        raise ValueError("Profile snapshot date must immediately precede the Profile Details card.")
    line, start, end = nonempty_lines[-1]
    match = DATE_LINE_PATTERN.fullmatch(line.strip())
    if not match:
        raise ValueError("Profile snapshot date line has unexpected markup or placement.")
    try:
        parsed = date.fromisoformat(match.group(1))
    except ValueError as error:
        raise ValueError("Profile snapshot date is not a valid calendar date.") from error
    if parsed.isoformat() != match.group(1):
        raise ValueError("Profile snapshot date must use canonical YYYY-MM-DD format.")
    return match.group(1), start, end


def _line_ranges(value: str):
    start = 0
    for line in value.splitlines(keepends=True):
        end = start + len(line)
        yield line.rstrip("\r\n"), start, end
        start = end
    if start < len(value):
        yield value[start:].rstrip("\r\n"), start, len(value)


def update_readme_date(readme: str, updated_date: str) -> str:
    """Insert or update only the shared date immediately above Profile Details."""
    new_line = format_date_line(updated_date)
    existing = extract_date_line(readme)
    if existing is not None:
        old_date, start, end = existing
        if old_date == updated_date:
            return readme
        old_text = readme[start:end]
        newline = "\r\n" if old_text.endswith("\r\n") else "\n"
        return readme[:start] + new_line + newline + readme[end:]

    if readme.count(PROFILE_DETAILS_ANCHOR) != 1:
        raise ValueError("README must contain exactly one Profile Details card anchor.")
    anchor_index = readme.index(PROFILE_DETAILS_ANCHOR)
    return readme[:anchor_index] + new_line + "\n\n" + readme[anchor_index:]
