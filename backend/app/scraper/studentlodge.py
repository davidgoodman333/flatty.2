"""studentlodge.ch: non-profit student housing in and around Bern (since 1962).

All room and studio types are on one overview page, so a run needs a single request.
These are room *types* with a starting rent; availability is checked when booking.
"""

import re

from ..geo import place_coordinates
from . import html
from .compliance import PoliteClient

BASE = "https://www.studentlodge.ch"
OVERVIEW = f"{BASE}/Mietobjekte-302"
HOUSES = ("Tscharnergut", "Bümpliz Nord", "WankdorfCity", "Bolligen", "Bümplizstrasse")


def parse_cards(page: str) -> list[dict]:
    listings = []
    for card in re.split(r'<div class="card h-100">', page)[1:]:
        title_match = re.search(r'class="card-title">(.*?)</h3>', card, re.DOTALL)
        link_match = re.search(r'href="(/[^"]+-(\d+))"[^>]*><strong>Details', card)
        price = html.chf(r'class="big"><strong>([\d.,\'’]+)</strong>', card)
        if not (title_match and link_match and price):
            continue
        title = " ".join(html.text(title_match.group(1)).split())
        text_match = re.search(r'class="card-text">(.*?)</p>', card, re.DOTALL)
        details = html.text(text_match.group(1)) if text_match else ""
        lowered = f"{title} {details}".lower()
        if "platz" in lowered:  # parking spaces
            continue

        studio = "studio" in lowered or "apartment" in lowered
        flat_rooms = html.number(r"(\d)-zimmer", lowered)
        shared = not studio and not flat_rooms
        location = next((house for house in HOUSES if house.lower() in details.lower()), "")
        coords = place_coordinates(location or "Bern")
        images = [BASE + src for src in re.findall(r'data-lazy="([^"]+)"', card)][:8]

        listings.append({
            "id": f"studentlodge:{link_match.group(2)}",
            "source": "studentlodge",
            "source_id": link_match.group(2),
            "url": BASE + link_match.group(1),
            "title": f"{title.split('/')[0].strip()} – studentlodge {location}".strip(" –"),
            "description": f"{title}. {details} Non-profit student housing (studentlodge.ch) for students and apprentices. Rent from CHF {price:.0f} per month.",
            "price": price,
            "rooms": flat_rooms or (2.0 if "business" in lowered else 1.0),
            "surface": html.number(r"([\d.]+)\s*m", title),
            "category": "SHARED" if shared else "APARTMENT",
            "object_type": "SINGLE_ROOM" if shared else "APARTMENT",
            "zipcode": "",
            "city": "Bolligen" if location == "Bolligen" else "Bern",
            "address": None,
            "lat": coords[0] if coords else None,
            "lng": coords[1] if coords else None,
            "is_private": False,
            "is_furnished": "möbliert" in lowered and "unmöbliert" not in lowered,
            "is_temporary": False,
            "moving_date": None,
            "available_text": "Check availability when booking",
            "agency": "studentlodge.ch (non-profit)",
            "published": None,
            "attributes": [label for word, label in (("balkon", "Balcony or garden"), ("rollstuhl", "Wheelchair accessible"), ("hindernisfrei", "Wheelchair accessible"), ("wlan", "Internet")) if word in lowered],
            "images": [{"thumb": src, "full": src} for src in images],
        })
    return listings


def collect(client: PoliteClient, bbox, max_listings: int, on_listing) -> bool:
    cards = parse_cards(client.get(OVERVIEW).text)
    for listing in cards[:max_listings]:
        on_listing(listing)
    return bool(cards) and len(cards) <= max_listings
