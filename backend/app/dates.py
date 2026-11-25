"""When a listing is available: start and end date, read from the listing's data.

Flatfox gives a start date; the Uni Bern board gives free text such as "from 22.12.2026 to
28.02.2027" or "as of now, to the end of January 2027". Anything that can't be read stays
None ("unknown"), and an unknown date never hides a listing.
"""

import re
from calendar import monthrange
from datetime import date

MONTHS = {
    name: number
    for number, names in enumerate([
        ("january", "januar", "jan"), ("february", "februar", "feb"), ("march", "märz", "mar"), ("april", "apr"),
        ("may", "mai"), ("june", "juni", "jun"), ("july", "juli", "jul"), ("august", "aug"),
        ("september", "sep", "sept"), ("october", "oktober", "oct", "okt"), ("november", "nov"),
        ("december", "dezember", "dec", "dez"),
    ], start=1)
    for name in names
}
MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
DAY = r"(\d{1,2})(?:st|nd|rd|th|\.)?"

# One date expression. Groups: numeric d, m, y | day-first d, month, y | month-first month, d, y
# | part of month ("end of"), month, y | day only, y ("31st 2026", month taken from the start).
DATE = re.compile(
    rf"(\d{{1,2}})\.(\d{{1,2}})\.(\d{{4}})"
    rf"|{DAY}\s+({MONTH})\b(?:\s+(\d{{4}}))?"
    rf"|\b({MONTH})\s+{DAY}(?!\d)(?:\s+(\d{{4}}))?"
    rf"|(?:\b(beginning|start|middle|mid|end)\s+(?:of\s+)?)?\b({MONTH})\b(?:\s+(\d{{4}}))?"
    rf"|{DAY}\s+(\d{{4}})",
    re.IGNORECASE,
)
SPLIT = re.compile(r"\s(?:to|until|till|bis)\s|\s[-–]\s", re.IGNORECASE)
NOW = re.compile(r"\b(as of now|immediately|per sofort|ab sofort|now)\b", re.IGNORECASE)


def _parse(text: str, end: bool, other: dict | None = None) -> dict | None:
    """First date in `text` as {year, month, day}; missing parts are None."""
    match = DATE.search(text)
    if not match:
        return None
    g = match.groups()
    if g[0]:
        return {"day": int(g[0]), "month": int(g[1]), "year": int(g[2])}
    if g[4]:
        return {"day": int(g[3]), "month": MONTHS[g[4].lower()], "year": int(g[5]) if g[5] else None}
    if g[6] and g[7]:
        return {"day": int(g[7]), "month": MONTHS[g[6].lower()], "year": int(g[8]) if g[8] else None}
    if g[10]:
        part = (g[9] or "").lower()
        day = {"beginning": 1, "start": 1, "middle": 15, "mid": 15}.get(part)
        if day is None and (part == "end" or end):
            day = 0  # last day of the month, filled in once the year is known
        return {"day": 1 if day is None else day, "month": MONTHS[g[10].lower()], "year": int(g[11]) if g[11] else None}
    if g[12]:
        return {"day": int(g[12]), "month": (other or {}).get("month"), "year": int(g[13])}
    return None


def _date(parts: dict | None) -> str | None:
    if not parts or not parts["year"] or not parts["month"]:
        return None
    try:
        day = parts["day"] or monthrange(parts["year"], parts["month"])[1]
        return date(parts["year"], parts["month"], day).isoformat()
    except ValueError:
        return None


def rental_period(moving_date: str | None, available_text: str | None) -> tuple[str | None, str | None]:
    """(available from, available until) as ISO dates. None means unknown or open-ended."""
    text = (available_text or "").strip()
    pieces = SPLIT.split(text, maxsplit=1)
    start = _parse(pieces[0], end=False)
    finish = _parse(pieces[1], end=True, other=start) if len(pieces) == 2 else None
    if start and finish:
        # "January 1st to February 28th 2027": the year is written only once.
        start["year"] = start["year"] or finish["year"]
        finish["month"] = finish["month"] or start["month"]
    available_from = moving_date or (None if NOW.search(pieces[0]) else _date(start))
    return available_from, _date(finish)


def fits_period(moving_date: str | None, available_text: str | None, needed_from: str | None, needed_until: str | None) -> bool:
    """False only if the listing's known dates rule the student's period out."""
    available_from, available_until = rental_period(moving_date, available_text)
    if needed_from and available_from and available_from > needed_from:
        return False  # free only after the student needs to move in
    if available_until and (needed_until or needed_from) and available_until < (needed_until or needed_from):
        return False  # the rental ends before the student's stay does
    return True
