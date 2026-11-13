"""Rank listings for one student profile and explain each match.

match % = 60 % preference fit (budget, area, type, commute) + 40 % quality model
          (how likely the landlord replies to this particular student).
The risk score is shown separately and never removes a listing; the UI warns instead.
"""

import re
from datetime import datetime

from . import llm
from .geo import commute_minutes, distance_km, neighbourhood, resolve_destination
from .kinds import APARTMENT, HOUSE, ROOM, STUDIO, classify
from .ml.features import is_shared
from .ml.models import QualityModel
from .scraper.sources import SOURCES
from .text import FLAG_LABELS, detect_language

SOURCE_NAMES = {source.key: source.name for source in SOURCES}

BUDGET_TOLERANCE = 1.15  # show listings up to 15 % over budget, with a warning


# Onboarding / filter choices → kinds from app/kinds.py (plus a room-count condition for flats).
TYPE_CHOICES = {
    "Shared apartment": lambda kind, rooms: kind == ROOM,
    "Studio": lambda kind, rooms: kind == STUDIO,
    "Proper flat": lambda kind, rooms: kind in (APARTMENT, HOUSE),
    "2-person flat": lambda kind, rooms: kind in (APARTMENT, HOUSE) and (rooms is None or 2 <= rooms <= 3.5),
    "3-person flat": lambda kind, rooms: kind in (APARTMENT, HOUSE) and (rooms is None or rooms >= 3.5),
}


def matches_type(listing: dict, wanted: list[str]) -> bool:
    kind, rooms = classify(listing), listing.get("rooms")
    return not wanted or any(TYPE_CHOICES[item](kind, rooms) for item in wanted if item in TYPE_CHOICES)


def budget_fit(price: float, budget: float) -> float:
    if price <= budget:
        return 1.0
    return max(0.0, 1 - (price / budget - 1) / (BUDGET_TOLERANCE - 1))


def commute_fit(minutes: int) -> float:
    return 1.0 if minutes <= 12 else max(0.2, 1 - (minutes - 12) / 35)


def area_fit(area: str, city: str, wanted: list[str]) -> float:
    if not wanted or "Anywhere" in wanted:
        return 1.0
    names = {area.lower(), (city or "").lower()}
    return 1.0 if any(item.lower() in names for item in wanted) else 0.45


def card(listing: dict, profile: dict, market: dict, quality_model: QualityModel, enforce_budget: bool = True) -> dict | None:
    budget = float(profile.get("budget") or 1800)
    price = listing.get("price") or 0
    if enforce_budget and price > budget * BUDGET_TOLERANCE:
        return None

    area = neighbourhood(listing.get("city"), listing.get("lat"), listing.get("lng"))
    destination_name, destination, exact = resolve_destination(profile.get("destination"))
    minutes = commute_minutes((listing["lat"], listing["lng"]), destination) if listing.get("lat") else None
    type_ok = matches_type(listing, profile.get("apartmentTypes") or [])
    language = detect_language(f"{listing.get('title')} {listing.get('description')}")

    preference = (
        0.35 * budget_fit(price, budget)
        + 0.25 * area_fit(area, listing.get("city"), profile.get("areas") or [])
        + 0.20 * (1.0 if type_ok else 0.3)
        + 0.20 * (commute_fit(minutes) if minutes is not None else 0.6)
    )
    quality, quality_features = quality_model.predict(listing, profile, market)
    match = round(100 * (0.6 * preference + 0.4 * quality))
    risk = round(100 * (listing.get("risk_score") or 0))

    reasons = []
    if price <= budget:
        reasons.append({"tone": "yes", "icon": "check", "title": "Within your budget", "detail": f"CHF {budget - price:,.0f} below your maximum".replace(",", "’")})
    else:
        reasons.append({"tone": "warn", "icon": "check", "title": "Slightly over budget", "detail": f"CHF {price - budget:,.0f} above your maximum".replace(",", "’")})
    if minutes is not None:
        place = destination_name if exact else f"{destination_name} (we couldn't place “{profile.get('destination')}”)"
        reasons.append({
            "tone": "yes" if minutes <= 20 else "warn", "icon": "train",
            "title": "Easy commute" if minutes <= 20 else "Longer commute",
            "detail": f"About {minutes} min to {place} by public transport (estimate)",
        })
    if not type_ok:
        chosen = ", ".join(t.lower() for t in profile.get("apartmentTypes") or [])
        reasons.append({"tone": "warn", "icon": "home", "title": "Different type than you chose", "detail": f"This is a {_type_label(listing).lower()}; you chose {chosen}"})
    if classify(listing) == ROOM and re.search(r"studio", listing.get("title") or "", re.IGNORECASE):
        reasons.append({"tone": "warn", "icon": "home", "title": "Called a studio, but the kitchen is shared", "detail": "Flatty counts it as a room: a studio has its own kitchen and bathroom"})
    if quality_features["private_landlord"]:
        reasons.append({"tone": "yes", "icon": "home", "title": "Private landlord", "detail": "Private landlords reply to students more often than agencies"})
    if quality_features["mentions_students"]:
        reasons.append({"tone": "yes", "icon": "work", "title": "Student-friendly", "detail": "The listing mentions students"})
    if quality_features["language_barrier"]:
        reasons.append({"tone": "warn", "icon": "mail", "title": f"Listing written in {language}", "detail": "Your reply chances improve if you answer in the listing's language"})
    if listing.get("surface") and price and not is_shared(listing):
        typical = price / market["per_sqm"]  # m² that this rent usually buys in Bern
        if listing["surface"] < typical * 0.9:
            reasons.append({"tone": "warn", "icon": "home", "title": "Smaller than average", "detail": f"{typical - listing['surface']:.0f} m² below similar listings for this price"})
    if quality_features["cheap_for_market"]:
        reasons.append({"tone": "warn", "icon": "search", "title": "Cheap for the area", "detail": "Expect many other applicants"})

    tags = [f"{minutes} min to {destination_name.split(' (')[0]}"] if minutes is not None else []
    tags += [label for flag, label in (("is_furnished", "Furnished"), ("is_temporary", "Temporary")) if listing.get(flag)]
    tags.append("Private landlord" if listing.get("is_private") else (listing.get("agency") or "Agency"))

    original_title = listing.get("title") or _type_label(listing)
    title_en = listing.get("title_en")
    if not title_en and original_title:
        title_en = llm.translate_title(original_title)
        listing["title_en"] = title_en

    features = list(listing.get("attributes") or [])
    if listing.get("is_furnished"):
        features.insert(0, "Furnished")

    return {
        "id": listing["id"],
        "source": listing["source"],
        "sourceName": SOURCE_NAMES.get(listing["source"], "Pasted listing"),
        "url": listing["url"],
        "kind": _type_label(listing),
        "rooms": listing.get("rooms"),
        "surface": listing.get("surface"),
        "rentNet": listing.get("rent_net"),
        "rentCharges": listing.get("rent_charges"),
        "floor": listing.get("floor"),
        "yearBuilt": listing.get("year_built"),
        "availableText": listing.get("available_text"),
        "published": listing.get("published"),
        "isTemporary": bool(listing.get("is_temporary")),
        "features": features,
        "images": listing.get("images") or [],
        "lat": listing.get("lat"),
        "lng": listing.get("lng"),
        "area": area,
        "city": listing.get("city"),
        "title": title_en or original_title,
        "originalTitle": original_title,
        "price": price,
        "rent": f"CHF {price:,.0f}".replace(",", "’"),
        "meta": " · ".join(part for part in (_surface_label(listing), _rooms_label(listing)) if part),
        "match": max(1, min(99, match)),
        "risk": max(1, min(99, risk)),
        "quality": round(100 * quality),
        "commuteMinutes": minutes,
        "language": language,
        "movingDate": listing.get("moving_date"),
        "tags": tags[:3],
        "reasons": reasons[:5],
        **risk_explanation(listing),
        "modelVersion": {"risk": listing.get("model_version"), "quality": quality_model.version},
    }


def risk_explanation(listing: dict) -> dict:
    """What raised and what lowered the risk score, for the result page."""
    details = listing.get("risk_details") or {}
    signals = details.get("signals", [])
    return {
        "riskFlags": [FLAG_LABELS.get(flag, flag) for flag in details.get("text_flags", [])]
        + [s["label"] for s in sorted(signals, key=lambda s: -s["weight"]) if s["weight"] > 0],
        "riskPositives": [s["label"] for s in sorted(signals, key=lambda s: s["weight"]) if s["weight"] < 0],
        "riskText": round(100 * details["text_probability"]) if "text_probability" in details else None,
        "riskTextEvidence": details.get("text_evidence"),
    }


KIND_LABELS = {ROOM: "Room", STUDIO: "Studio", APARTMENT: "Apartment", HOUSE: "House"}


def _type_label(listing: dict) -> str:
    return KIND_LABELS[classify(listing)]


def _rooms_label(listing: dict) -> str:
    rooms = listing.get("rooms")
    kind = classify(listing)
    if kind == ROOM:
        return "Room, shared kitchen or flat"
    if kind == STUDIO:
        return "Studio, own kitchen and bathroom"
    return f"{rooms:g} rooms" if rooms else ""


def _surface_label(listing: dict) -> str:
    # For shared flats Flatfox's m² is sometimes the room and sometimes the whole flat.
    return f"{listing['surface']:.0f} m²" if listing.get("surface") else ""


SORTS = {
    "match": lambda c: (-c["match"], c["risk"]),
    "price_asc": lambda c: (c["price"], -c["match"]),
    "price_desc": lambda c: (-c["price"], -c["match"]),
    "newest": lambda c: (-(datetime.fromisoformat(c["published"]).timestamp() if c["published"] else 0), -c["match"]),
    "risk": lambda c: (c["risk"], -c["match"]),
    "commute": lambda c: (c["commuteMinutes"] if c["commuteMinutes"] is not None else 999, -c["match"]),
    "size": lambda c: (-(c["surface"] or 0), -c["match"]),
}


def passes(c: dict, filters: dict, ignore_source: bool = False) -> bool:
    """True if the card matches every active filter (all filters are optional)."""
    if not ignore_source and filters.get("sources") and c["source"] not in filters["sources"]:
        return False
    if filters.get("priceMin") and c["price"] < filters["priceMin"]:
        return False
    if filters.get("priceMax") and c["price"] > filters["priceMax"]:
        return False
    if filters.get("roomsMin") and (c["rooms"] or 0) < filters["roomsMin"]:
        return False
    if filters.get("surfaceMin") and (c["surface"] or 0) < filters["surfaceMin"]:
        return False
    if filters.get("types") and not any(TYPE_CHOICES[t](c["kind"], c["rooms"]) for t in filters["types"] if t in TYPE_CHOICES):
        return False
    if filters.get("features") and not set(filters["features"]) <= set(c["features"]):
        return False
    if filters.get("maxRisk") is not None and c["risk"] > filters["maxRisk"]:
        return False
    if filters.get("rental") == "permanent" and c["isTemporary"] or filters.get("rental") == "temporary" and not c["isTemporary"]:
        return False
    if filters.get("withPhotos") and not c["images"]:
        return False
    if filters.get("availableBy") and c["movingDate"] and c["movingDate"] > filters["availableBy"]:
        return False
    if filters.get("areaLat") is not None and filters.get("areaLng") is not None:
        if c["lat"] is None or c["lng"] is None:
            return False  # location unknown, so it can't be shown as inside the area
        if distance_km((c["lat"], c["lng"]), (filters["areaLat"], filters["areaLng"])) > filters.get("radiusKm", 2.0):
            return False
    return True


def search(listings: list[dict], profile: dict, market: dict, filters: dict, sort: str, offset: int, limit: int) -> dict:
    model = QualityModel()
    # Without an explicit maximum price, hide listings far over the student's budget.
    enforce_budget = not filters.get("priceMax")
    cards = [c for c in (card(listing, profile, market, model, enforce_budget) for listing in listings) if c]
    source_counts: dict[str, int] = {}
    for c in cards:
        if passes(c, filters, ignore_source=True):
            source_counts[c["source"]] = source_counts.get(c["source"], 0) + 1
    selected = sorted((c for c in cards if passes(c, filters)), key=SORTS.get(sort, SORTS["match"]))
    return {"total": len(selected), "listings": selected[offset:offset + limit], "sourceCounts": source_counts}


def rank(listings: list[dict], profile: dict, market: dict) -> list[dict]:
    return search(listings, profile, market, {}, "match", 0, len(listings))["listings"]
