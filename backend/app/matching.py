"""Rank listings for one student profile and explain each one.

reply    how likely the landlord replies to this particular student (quality model). Shown as
         a level (likely or unlikely), never as a number: the weights behind it are
         assumptions, and a percentage would look more exact than it is. This is the headline
         and the default sort order.
risk %   shown separately; it never removes a listing, the UI warns instead.

There is no "match" score: budget, type and the other preferences are filters, and how a
listing compares with them is reported as plain notes, not as a number.
"""

import re
from datetime import datetime

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


def in_wanted_area(area: str, city: str, wanted: list[str]) -> bool | None:
    """None if the student didn't choose an area."""
    if not wanted or "Anywhere" in wanted:
        return None
    return any(item.lower() in {area.lower(), (city or "").lower()} for item in wanted)


# What each reply-likelihood feature means for the student: (icon, title, detail).
# Whether it helps or hurts comes from the sign of the model's weight for that feature.
REPLY_FACTORS = {
    "private_landlord": ("home", "Private landlord", "Private landlords reply to students more often than agencies"),
    "mentions_students": ("work", "Student-friendly", "The listing mentions students"),
    "shared_flat": ("home", "Room in a shared flat", "Shared flats are often let to students"),
    "furnished_or_temporary": ("home", "Furnished or temporary", "Aimed at people who are new in town"),
    "cheap_for_market": ("search", "Cheap for the area", "Expect many other applicants"),
    "expensive_for_market": ("search", "Rent above the usual level", "Fewer people apply for expensive listings"),
    "language_barrier": ("mail", "Listing in a language you don't speak", "Your reply chances improve if you answer in the listing's language"),
    "has_permit": ("check", "You have a residence permit", "Landlords often ask for one"),
    "has_swiss_phone": ("check", "You have a Swiss phone number", "Landlords can reach you easily"),
    "has_swiss_bank": ("check", "You have a Swiss bank account", "Rent and deposit are simple to arrange"),
    "has_guarantor": ("check", "You have a guarantor in Switzerland", "This lowers the landlord's risk"),
    "has_viewing_person": ("check", "Someone can attend viewings for you", "You can react to viewing dates quickly"),
}


# Reply likelihood shown to the student: "likely" means more likely than not.
LIKELY_FROM = 0.5


def reply_level(probability: float) -> tuple[str, str]:
    return ("likely", "Likely") if probability >= LIKELY_FROM else ("unlikely", "Unlikely")


def shares(weights: list[float]) -> list[int]:
    """Each weight's share of the total absolute weight, in whole percent that add up to 100."""
    total = sum(abs(w) for w in weights)
    if not total:
        return [0] * len(weights)
    exact = [100 * abs(w) / total for w in weights]
    result = [int(x) for x in exact]
    # Largest remainder: hand out the missing points to the largest fractions.
    for i in sorted(range(len(exact)), key=lambda i: result[i] - exact[i])[:100 - sum(result)]:
        result[i] += 1
    return result


def reply_reasons(features: dict[str, float], weights: dict[str, float], language: str) -> list[dict]:
    """The facts behind the reply likelihood, strongest first.

    `share` is how much each fact counts towards the score, as a percentage of all facts that
    apply (they add up to 100); `tone` says whether it raises ("yes") or lowers ("warn") it.
    """
    active = [name for name in sorted(features, key=lambda name: -abs(weights.get(name, 0)))
              if features[name] and weights.get(name, 0)]
    reasons = []
    for name, share in zip(active, shares([weights[name] for name in active])):
        icon, title, detail = REPLY_FACTORS[name]
        if name == "language_barrier":
            title = f"Listing written in {language}"
        reasons.append({
            "tone": "yes" if weights[name] > 0 else "warn", "icon": icon, "title": title, "detail": detail,
            "share": share,
        })
    return reasons


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

    quality, quality_features = quality_model.predict(listing, profile, market)
    level, level_label = reply_level(quality)
    risk = round(100 * (listing.get("risk_score") or 0))

    # Why the reply likelihood is what it is.
    reasons = reply_reasons(quality_features, quality_model.weights(), language)

    # How the listing compares with what the student asked for. Not part of any score.
    notes = []
    if price <= budget:
        notes.append({"tone": "yes", "icon": "check", "title": "Within your budget", "detail": f"CHF {budget - price:,.0f} below your maximum".replace(",", "’")})
    else:
        notes.append({"tone": "warn", "icon": "check", "title": "Slightly over budget", "detail": f"CHF {price - budget:,.0f} above your maximum".replace(",", "’")})
    if minutes is not None:
        place = destination_name if exact else f"{destination_name} (we couldn't place “{profile.get('destination')}”)"
        notes.append({
            "tone": "yes" if minutes <= 20 else "warn", "icon": "train",
            "title": "Easy commute" if minutes <= 20 else "Longer commute",
            "detail": f"About {minutes} min to {place} by public transport (estimate)",
        })
    wanted_areas = [a for a in profile.get("areas") or [] if a]
    in_area = in_wanted_area(area, listing.get("city"), wanted_areas)
    if in_area is not None:
        notes.append({
            "tone": "yes" if in_area else "warn", "icon": "map",
            "title": "In an area you chose" if in_area else "Outside the areas you chose",
            "detail": f"{area}; you chose {', '.join(wanted_areas)}",
        })
    if not type_ok:
        chosen = ", ".join(t.lower() for t in profile.get("apartmentTypes") or [])
        notes.append({"tone": "warn", "icon": "home", "title": "Different type than you chose", "detail": f"This is a {_type_label(listing).lower()}; you chose {chosen}"})
    if classify(listing) == ROOM and re.search(r"studio", listing.get("title") or "", re.IGNORECASE):
        notes.append({"tone": "warn", "icon": "home", "title": "Called a studio, but the kitchen is shared", "detail": "Flatty counts it as a room: a studio has its own kitchen and bathroom"})
    if listing.get("surface") and price and not is_shared(listing):
        typical = price / market["per_sqm"]  # m² that this rent usually buys in Bern
        if listing["surface"] < typical * 0.9:
            notes.append({"tone": "warn", "icon": "home", "title": "Smaller than average", "detail": f"{typical - listing['surface']:.0f} m² below similar listings for this price"})

    tags = [f"{minutes} min to {destination_name.split(' (')[0]}"] if minutes is not None else []
    tags += [label for flag, label in (("is_furnished", "Furnished"), ("is_temporary", "Temporary")) if listing.get(flag)]
    tags.append("Private landlord" if listing.get("is_private") else (listing.get("agency") or "Agency"))

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
        "title": listing.get("title") or _type_label(listing),
        "price": price,
        "rent": f"CHF {price:,.0f}".replace(",", "’"),
        "meta": " · ".join(part for part in (_surface_label(listing), _rooms_label(listing)) if part),
        "replyLevel": level,
        "replyLabel": level_label,
        "replyScore": round(quality, 4),  # for ordering only; the app never shows it
        "risk": max(1, min(99, risk)),
        "commuteMinutes": minutes,
        "language": language,
        "movingDate": listing.get("moving_date"),
        "tags": tags[:3],
        "reasons": reasons,  # all of them, so the shares add up to 100
        "notes": notes[:5],
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
    "reply": lambda c: (-c["replyScore"], c["risk"]),
    "price_asc": lambda c: (c["price"], -c["replyScore"]),
    "price_desc": lambda c: (-c["price"], -c["replyScore"]),
    "newest": lambda c: (-(datetime.fromisoformat(c["published"]).timestamp() if c["published"] else 0), -c["replyScore"]),
    "risk": lambda c: (c["risk"], -c["replyScore"]),
    "commute": lambda c: (c["commuteMinutes"] if c["commuteMinutes"] is not None else 999, -c["replyScore"]),
    "size": lambda c: (-(c["surface"] or 0), -c["replyScore"]),
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
    selected = sorted((c for c in cards if passes(c, filters)), key=SORTS.get(sort, SORTS["reply"]))
    return {"total": len(selected), "listings": selected[offset:offset + limit], "sourceCounts": source_counts}


def rank(listings: list[dict], profile: dict, market: dict) -> list[dict]:
    return search(listings, profile, market, {}, "reply", 0, len(listings))["listings"]
