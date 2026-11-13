"""Collect Bern rental listings from Flatfox's public listing API.

Two endpoints are used, both allowed by flatfox.ch/robots.txt:
  /api/v1/pin/             map pins (id, coordinates, price) inside a bounding box
  /api/v1/public-listing/  listing details, requested in batches by id
"""

import re

from .compliance import PoliteClient

BASE = "https://flatfox.ch"
CATEGORIES = ("APARTMENT", "SHARED", "HOUSE")
PIN_LIMIT = 1000  # maximum the API returns per request
BATCH_SIZE = 50


def fetch_pins(client: PoliteClient, bbox: tuple[float, float, float, float], depth: int = 0) -> tuple[list[dict], bool]:
    """Monthly-rent pins in the area, and whether that list is complete."""
    west, south, east, north = bbox
    params = [("west", west), ("south", south), ("east", east), ("north", north), ("max_count", PIN_LIMIT), ("offer_type", "RENT")]
    params += [("object_category", category) for category in CATEGORIES]
    pins = client.get(f"{BASE}/api/v1/pin/", params=params).json()
    if len(pins) >= PIN_LIMIT and depth < 2:
        # Too many results for one request: split the area into four tiles.
        mid_lng, mid_lat = (west + east) / 2, (south + north) / 2
        tiles = [(west, south, mid_lng, mid_lat), (mid_lng, south, east, mid_lat), (west, mid_lat, mid_lng, north), (mid_lng, mid_lat, east, north)]
        results = [fetch_pins(client, tile, depth + 1) for tile in tiles]
        unique = {pin["pk"]: pin for tile_pins, _ in results for pin in tile_pins}
        return list(unique.values()), all(complete for _, complete in results)
    complete = len(pins) < PIN_LIMIT  # still capped after splitting twice: some listings are missing
    return [pin for pin in pins if pin.get("price_unit") == "monthly"], complete


def fetch_details(client: PoliteClient, pks: list[int]) -> list[dict]:
    if not pks:
        return []  # An empty filter would return every listing in Switzerland.
    params = [("pk", pk) for pk in pks] + [("limit", len(pks)), ("expand", "images")]
    return client.get(f"{BASE}/api/v1/public-listing/", params=params).json().get("results", [])


def fetch_one(client: PoliteClient, pk: int) -> dict | None:
    """One listing, or None if Flatfox no longer has it at all."""
    response = client.get(f"{BASE}/api/v1/public-listing/{pk}/", params={"expand": "images"}, missing_ok=True)
    return None if response.status_code in (404, 410) else response.json()


def is_active(raw: dict | None) -> bool:
    """Flatfox marks live listings "act"; rented or withdrawn ones become e.g. "dis"."""
    return bool(raw) and raw.get("status") == "act"


# Flatfox attribute codes → labels shown in Flatty (and used by the feature filters).
ATTRIBUTES = {
    "balconygarden": "Balcony or garden", "petsallowed": "Pets allowed", "dishwasher": "Dishwasher",
    "washingmachine": "Washing machine", "tumbler": "Tumble dryer", "lift": "Lift",
    "parkingspace": "Parking", "garage": "Garage", "accessiblewithwheelchair": "Wheelchair accessible",
    "broadbandinternet": "Internet", "cable": "Cable TV", "view": "View", "fireplace": "Fireplace",
    "parquetflooring": "Parquet floor", "minergie": "Minergie", "childfriendly": "Child-friendly",
    "newbuilding": "New building", "oldbuilding": "Old building", "ramp": "Ramp",
}


def _images(raw: dict) -> list[dict]:
    """Photo URLs on Flatfox's own servers. Flatty links to them; it never downloads or re-hosts them."""
    def absolute(url: str) -> str:
        return url if url.startswith("http") else BASE + url  # some photos already live on cdn.flatfox.ch

    images = []
    for image in raw.get("images") or []:
        if isinstance(image, dict) and image.get("url_listing_search"):
            images.append({"thumb": absolute(image["url_listing_search"]), "full": absolute(image.get("url") or image["url_listing_search"])})
    return images[:12]


def pk_from_url(url: str) -> int | None:
    match = re.search(r"/(\d{4,})/?(?:[?#].*)?$", url)
    return int(match.group(1)) if match else None


def _number(value) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def normalise(raw: dict) -> dict:
    """Map a Flatfox record to Flatty's schema. Contact data and images are dropped on purpose."""
    agency = (raw.get("agency") or {}).get("name") or None
    surface = _number(raw.get("surface_living")) or _number(raw.get("space_display"))
    if surface is not None and not 5 <= surface <= 600:
        surface = None  # obvious data-entry errors (e.g. plot size typed into living space)
    return {
        "id": f"flatfox:{raw['pk']}",
        "source": "flatfox",
        "source_id": str(raw["pk"]),
        "url": BASE + (raw.get("url") or f"/{raw['pk']}/"),
        "title": raw.get("description_title") or raw.get("short_title") or raw.get("public_title"),
        "description": raw.get("description") or "",
        "price": _number(raw.get("rent_gross")) or _number(raw.get("price_display")),
        "rooms": _number(raw.get("number_of_rooms")),
        "surface": surface,
        "category": raw.get("object_category"),
        "object_type": raw.get("object_type"),
        "zipcode": str(raw.get("zipcode") or ""),
        "city": raw.get("city"),
        "address": raw.get("public_address"),
        "lat": _number(raw.get("latitude")),
        "lng": _number(raw.get("longitude")),
        "is_private": agency is None,
        "is_furnished": bool(raw.get("is_furnished")),
        "is_temporary": bool(raw.get("is_temporary")),
        "moving_date": raw.get("moving_date"),
        "agency": agency,
        "published": raw.get("published"),
        "status": raw.get("status"),
        "rent_net": _number(raw.get("rent_net")),
        "rent_charges": _number(raw.get("rent_charges")),
        "floor": raw.get("floor"),
        "year_built": raw.get("year_built"),
        "year_renovated": raw.get("year_renovated"),
        "available_text": "Immediately" if raw.get("moving_date_type") == "imm" else ("By arrangement" if raw.get("moving_date_type") == "agr" else None),
        "attributes": [ATTRIBUTES[a["name"]] for a in raw.get("attributes") or [] if a.get("name") in ATTRIBUTES],
        "images": _images(raw),
    }


def is_relevant(listing: dict) -> bool:
    """Keep homes a student could live in; drop parking, offices and listings without a price."""
    return (
        listing.get("status") == "act"
        and listing["category"] in CATEGORIES
        and bool(listing["price"])
        and 150 <= listing["price"] <= 6000
    )


def collect(client: PoliteClient, bbox: tuple[float, float, float, float], max_listings: int, on_listing) -> bool:
    """Save every relevant listing; return True if the run saw all listings in the area."""
    pins, complete = fetch_pins(client, bbox)
    pks = [pin["pk"] for pin in pins][:max_listings]
    for start in range(0, len(pks), BATCH_SIZE):
        for raw in fetch_details(client, pks[start:start + BATCH_SIZE]):
            listing = normalise(raw)
            if is_relevant(listing):
                on_listing(listing)
    return complete and len(pins) <= max_listings
