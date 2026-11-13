"""University of Bern Welcome Center accommodation board.

Offers from private hosts for students and visiting researchers. Each offer has its own
page with a small table (city, location, rooms, rent, availability) and a description.
The contact box (names, e-mail, phone) is cut off and never stored.
"""

import re
from datetime import datetime

from ..geo import locate
from . import html
from .compliance import PoliteClient

BASE = "https://www.unibe.ch/university/organization/welcome_center/accommodation/accommodation_offers"
CATEGORIES = ("1___25_zimmer", "3___45_rooms", "5_rooms")

SHARED_PATTERN = re.compile(
    r"\brooms? (in|at)\b|\b(furnished|free|big|bright|single|one) rooms?\b(?![- ]?(apartment|flat))|"
    r"\b(zimmer in|shared|flatshare|wg|sublet (a|1) (furnished )?room)\b",
    re.IGNORECASE,
)


def listing_urls(client: PoliteClient) -> list[str]:
    urls: list[str] = []
    for category in CATEGORIES:
        page = client.get(f"{BASE}/{category}/index_eng.html").text
        pattern = rf'href="({re.escape(BASE)}/{category}/[^"/]+/index_eng\.html)"'
        urls += [url for url in dict.fromkeys(re.findall(pattern, page)) if url not in urls]
    return urls


def parse(url: str, page: str) -> dict | None:
    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.DOTALL)
    cells = [html.text(cell) for cell in re.findall(r"<td[^>]*>(.*?)</td>", page, re.DOTALL)]
    if not title_match or len(cells) < 5:
        return None
    city_cell, location, rooms_text, rent_text, availability = cells[:5]

    # Description: the text blocks before the contact box (which holds personal data).
    body = page.split('class="hint-box"', 1)[0]
    blocks = [part.split("zmsrow-", 1)[0] for part in body.split('zmsrow-ZMSTextarea">')[1:]]
    description = "\n".join(html.text("<" + block) for block in blocks)[:4000]

    title = re.sub(r"^[A-Z]\.\d+\s*", "", html.text(title_match.group(1))).strip()
    code = url.rstrip("/").split("/")[-2]
    raw_city = city_cell.split(",")[-1].strip()  # the street part before the comma is dropped
    town, coords = locate(raw_city, location, title)
    city = town or re.sub(r"^\d{4}\s*|\s*\(.*\)$", "", raw_city) or "Bern region"

    monthly = html.chf(r"CHF\s*([\d'’.,]+-?)[^/\n]*?/\s*(?:month|monat|mt)", rent_text)
    weekly_only = monthly is None and "week" in rent_text.lower()
    first = html.chf(r"CHF\s*([\d'’.,]+-?)", rent_text) or html.chf(r"([\d'’.,]{3,}-?)\s*(?:CHF|Fr)", rent_text)
    price = (first or 0) * 4.33 if weekly_only else (monthly or first)
    shared = bool(SHARED_PATTERN.search(title)) or "room in" in rooms_text.lower()
    rooms = 1.0 if shared else html.number(r"(\d+(?:[.,]5)?)", rooms_text)
    surface = html.number(r"(\d{2,3})\s*(?:m2|m²|sqm|square met)", f"{rooms_text} {description}")
    published = re.search(r"published:\s*(\d{2})\.(\d{2})\.(\d{4})", page)
    lowered = f"{title} {rooms_text} {description}".lower()

    return {
        "id": f"unibe:{code}",
        "source": "unibe",
        "source_id": code,
        "url": url,
        "title": title,
        "description": f"{rooms_text}\n{location}\n{description}",
        "price": round(price) if price else None,
        "rooms": rooms,
        "surface": surface if surface and 5 <= surface <= 400 else None,
        "category": "SHARED" if shared else "APARTMENT",
        "object_type": "SHARED_FLAT" if shared else "APARTMENT",
        "zipcode": "",
        "city": city,
        "address": None,  # street addresses of private hosts are not stored
        "lat": coords[0] if coords else None,
        "lng": coords[1] if coords else None,
        "is_private": True,
        "is_furnished": "furnished" in lowered and "unfurnished" not in lowered or "möbliert" in lowered,
        "is_temporary": bool(re.search(r"\b(to|until|bis)\b\s+\w*\s*\d", availability, re.IGNORECASE)),
        "moving_date": None,
        "available_text": availability[:120],
        "agency": None,
        "published": datetime(int(published[3]), int(published[2]), int(published[1])).isoformat() if published else None,
        "attributes": ["Pets allowed"] if re.search(r"pets (are )?(allowed|welcome)", lowered) else [],
        "images": [],
    }


def collect(client: PoliteClient, bbox, max_listings: int, on_listing) -> bool:
    urls = listing_urls(client)
    for url in urls[:max_listings]:
        listing = parse(url, client.get(url).text)
        if listing and listing["price"] and 150 <= listing["price"] <= 6000:
            on_listing(listing)
    return len(urls) <= max_listings


def check(client: PoliteClient, url: str) -> tuple[bool, dict | None]:
    """Re-read one offer page: (still online?, fresh data or None if it could not be parsed)."""
    response = client.get(url, missing_ok=True)
    if response.status_code in (404, 410) or "/accommodation_offers/" not in str(response.url):
        return False, None
    return True, parse(url, response.text)
