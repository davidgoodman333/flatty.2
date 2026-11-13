"""Tiny HTML helpers for the page-based sources (no third-party parser needed)."""

import html
import re


def text(fragment: str) -> str:
    fragment = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", fragment, flags=re.DOTALL | re.IGNORECASE)
    fragment = re.sub(r"<br\s*/?>|</(p|div|li|h\d|tr)>", "\n", fragment, flags=re.IGNORECASE)
    fragment = html.unescape(re.sub(r"<[^>]+>", "", fragment)).replace("\xa0", " ")
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in fragment.splitlines())
    return "\n".join(line for line in lines if line)


def chf(pattern: str, value: str) -> float | None:
    """Swiss price like 1'250.-, 1’250, 1,250 or 1.250 → 1250."""
    match = re.search(pattern, value, re.IGNORECASE)
    if not match:
        return None
    digits = re.sub(r"[.,]-+$|\.$", "", match.group(1).strip())
    digits = re.sub(r"['’]|[.,](?=\d{3}\b)", "", digits)
    try:
        return float(digits.replace(",", "."))
    except ValueError:
        return None


def number(pattern: str, value: str) -> float | None:
    match = re.search(pattern, value, re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1).replace("'", "").replace("’", "").replace(",", "."))
    except ValueError:
        return None
