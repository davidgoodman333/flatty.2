"""Feature extraction shared by training and prediction."""

import json
import re
from statistics import median

from ..config import MODEL_DIR
from ..rules import REPLY, RISK, require
from ..kinds import is_room
from ..text import detect_language, mentions_students, red_flags
from ..wishes import assess as assess_wishes, profile_languages

# Fallback market values for Bern (CHF per month) used until enough listings are scraped.
DEFAULT_MARKET = {"per_sqm": 24.0, "shared_room": 720.0, "by_rooms": {1: 1050, 2: 1400, 3: 1750, 4: 2150, 5: 2600}}

# The text model only sees text: TF-IDF plus these red flags found in the text. The order is
# fixed by the trained model, so rules.toml has to list exactly these (new ones go at the end).
TEXT_FLAGS = ["deposit_before_viewing", "no_viewing", "off_platform_contact", "payment_service", "urgency"]
if [flag["key"] for flag in RISK["red_flags"]][:len(TEXT_FLAGS)] != TEXT_FLAGS:
    raise RuntimeError(f"rules.toml: [[risk.red_flags]] must start with {', '.join(TEXT_FLAGS)}, in this order")

# Sources where photos and street addresses are normally present, so their absence means something.
PHOTO_SOURCES = set(RISK["photo_sources"])
ADDRESS_SOURCES = set(RISK["address_sources"])
TRUSTED_PROVIDERS = set(RISK["trusted_providers"])  # known non-profit housing organisations

# Listing signals, their thresholds and log-odds weights (positive = raises risk): rules.toml
# [risk.signals]. Weights learned from expert-rated listings (train.py: fit_signal_weights,
# models/signal_weights.json) replace the ones in the file.
SIGNALS = RISK["signals"]
require(SIGNALS, [
    "price_far_below_market", "price_below_market", "no_description", "short_description", "detailed_description",
    "no_photos", "one_photo", "many_photos", "no_address", "trusted_provider", "agency", "private_landlord",
    "duplicate_text",
], "risk.signals")
SIGNAL_WEIGHTS = {key: rule["weight"] for key, rule in SIGNALS.items()}
SIGNAL_WEIGHTS_PATH = MODEL_DIR / "signal_weights.json"
if SIGNAL_WEIGHTS_PATH.exists():
    SIGNAL_WEIGHTS.update(json.loads(SIGNAL_WEIGHTS_PATH.read_text()))


def is_shared(listing: dict) -> bool:
    """A room (in a shared flat or residence), as decided by app/kinds.py."""
    return is_room(listing)


def market_stats(listings: list[dict]) -> dict:
    homes = [l for l in listings if not is_shared(l) and l.get("price")]
    per_sqm = [l["price"] / l["surface"] for l in homes if l.get("surface") and l["surface"] >= 15]
    shared = [l["price"] for l in listings if is_shared(l) and l.get("price")]
    by_rooms: dict[int, list[float]] = {}
    for l in homes:
        if l.get("rooms"):
            by_rooms.setdefault(min(5, max(1, int(l["rooms"]))), []).append(l["price"])
    return {
        "per_sqm": median(per_sqm) if len(per_sqm) >= 20 else DEFAULT_MARKET["per_sqm"],
        "shared_room": median(shared) if len(shared) >= 10 else DEFAULT_MARKET["shared_room"],
        "by_rooms": {
            rooms: (median(by_rooms[rooms]) if len(by_rooms.get(rooms, [])) >= 8 else default)
            for rooms, default in DEFAULT_MARKET["by_rooms"].items()
        },
        "sample_size": len(listings),
    }


def expected_price(listing: dict, market: dict) -> float | None:
    if is_shared(listing):
        return market["shared_room"]
    if listing.get("surface") and listing["surface"] >= 15:
        return market["per_sqm"] * listing["surface"]
    if listing.get("rooms"):
        return market["by_rooms"][min(5, max(1, int(listing["rooms"])))]
    return None


def price_ratio(listing: dict, market: dict) -> float:
    expected = expected_price(listing, market)
    if not expected or not listing.get("price"):
        return 1.0
    return max(0.1, min(3.0, listing["price"] / expected))


def listing_text(listing: dict) -> str:
    return f"{listing.get('title') or ''}\n{listing.get('description') or ''}"


def description_length(listing: dict) -> int:
    return len((listing.get("description") or "").strip())


def text_flag_vector(listing: dict) -> list[float]:
    flags = set(red_flags(listing_text(listing)))
    return [float(flag in flags) for flag in TEXT_FLAGS]


def has_street_address(listing: dict) -> bool:
    # "Mösliweg 5, 3098 Köniz" has a street; "3008 Bern" only names the area.
    return bool(re.search(r"[^\d\s,]{3,}.*\d.*,", listing.get("address") or ""))


def text_key(listing: dict) -> str:
    return re.sub(r"\s+", " ", (listing.get("description") or "").lower()).strip()


def duplicate_texts(listings: list[dict]) -> set[str]:
    """IDs of private listings whose text also appears in another listing with a different
    town or a clearly different rent (copy-paste scams). Agencies reuse texts legitimately."""
    groups: dict[str, list[dict]] = {}
    for listing in listings:
        if listing.get("is_private") and len(text_key(listing)) >= SIGNALS["duplicate_text"]["min_length"]:
            groups.setdefault(text_key(listing), []).append(listing)
    duplicates = set()
    for group in groups.values():
        for a in group:
            for b in group:
                towns = ((a.get("city") or "").lower(), (b.get("city") or "").lower())
                if a["id"] != b["id"] and (
                    (all(towns) and towns[0] != towns[1])
                    or abs((a.get("price") or 0) - (b.get("price") or 0)) > SIGNALS["duplicate_text"]["price_difference"] * max(a.get("price") or 1, 1)
                ):
                    duplicates.add(a["id"])
    return duplicates


def risk_signals(listing: dict, market: dict, duplicates: set[str] = frozenset()) -> list[tuple[str, str, float]]:
    """Evidence outside the text, as (key, explanation, log-odds weight).

    Positive weights raise the risk, negative weights lower it. The weights are an expert prior
    (pitch slide 4, Swiss police and consumer warnings) and are re-fitted once expert-rated
    listings exist (see train.py: fit_signal_weights).
    """
    W = SIGNAL_WEIGHTS
    signals = []
    source = listing.get("source")
    ratio = price_ratio(listing, market)
    expected = expected_price(listing, market)
    if expected and listing.get("price") and ratio < SIGNALS["price_below_market"]["below_ratio"]:
        below = round(100 * (1 - ratio))
        far = ratio < SIGNALS["price_far_below_market"]["below_ratio"]
        key, weight = ("price_far_below_market", W["price_far_below_market"]) if far else ("price_below_market", W["price_below_market"])
        signals.append((key, f"Rent is {below}% below similar listings (about CHF {expected:,.0f})".replace(",", "’"), weight))

    length = description_length(listing)
    if length < SIGNALS["no_description"]["shorter_than"]:
        signals.append(("no_description", "No or almost no description", W["no_description"]))
    elif length < SIGNALS["short_description"]["shorter_than"]:
        signals.append(("short_description", "Very short description", W["short_description"]))
    elif length >= SIGNALS["detailed_description"]["at_least"]:
        signals.append(("detailed_description", "Detailed description", W["detailed_description"]))

    if source in PHOTO_SOURCES:
        photos = len(listing.get("images") or [])
        if photos == 0:
            signals.append(("no_photos", "No photos", W["no_photos"]))
        elif photos == 1:
            signals.append(("one_photo", "Only one photo", W["one_photo"]))
        elif photos >= SIGNALS["many_photos"]["at_least"]:
            signals.append(("many_photos", f"{photos} photos", W["many_photos"]))

    if source in ADDRESS_SOURCES and not has_street_address(listing):
        signals.append(("no_address", "No street address, only the area", W["no_address"]))

    if source in TRUSTED_PROVIDERS:
        signals.append(("trusted_provider", "Known non-profit housing provider", W["trusted_provider"]))
    elif listing.get("agency"):
        signals.append(("agency", f"Listed by a company ({listing['agency']})", W["agency"]))
    elif listing.get("is_private"):
        signals.append(("private_landlord", "Private landlord (scams are almost always posted privately)", W["private_landlord"]))

    if listing.get("id") in duplicates:
        signals.append(("duplicate_text", "Same text as another listing elsewhere or at another price", W["duplicate_text"]))
    return signals


# --- Quality / reply likelihood -------------------------------------------------------

QUALITY_FEATURES = [
    "private_landlord", "mentions_students", "shared_flat", "furnished_or_temporary", "cheap_for_market",
    "expensive_for_market", "language_barrier", "has_permit", "has_swiss_phone", "has_swiss_bank",
    "has_guarantor", "has_viewing_person",
    # From the wishes the local LLM read in the listing (app/wishes.py): 1 if required, 0.6 if preferred.
    "language_wish_unmet", "language_wish_met", "not_for_students",
]
require(REPLY["factors"], QUALITY_FEATURES, "reply.factors")


def yes(value) -> float:
    return float(value in (True, "yes"))


def quality_features(listing: dict, profile: dict, market: dict) -> dict[str, float]:
    ratio = price_ratio(listing, market)
    language = detect_language(listing_text(listing))
    speaks = profile_languages(profile)  # Swiss German counts as German (rules.toml)
    wished = assess_wishes(listing.get("wishes"), profile)["features"]
    # "Keine Studenten" mentions students too: a wish read by the LLM overrides the keyword.
    students = 0.0 if wished["not_for_students"] else float(
        mentions_students(listing_text(listing)) or wished["students_welcome"] > 0)
    return {
        "private_landlord": float(bool(listing.get("is_private"))),
        "mentions_students": students,
        "shared_flat": float(is_shared(listing)),
        "furnished_or_temporary": float(bool(listing.get("is_furnished") or listing.get("is_temporary"))),
        "cheap_for_market": float(ratio < REPLY["cheap_below"]),
        "expensive_for_market": float(ratio > REPLY["expensive_above"]),
        "language_barrier": float(language not in ("Unknown", "English") and language not in speaks),
        "has_permit": yes(profile.get("hasResidencePermit")),
        "has_swiss_phone": yes(profile.get("hasSwissNumber")),
        "has_swiss_bank": yes(profile.get("hasSwissBank")),
        "has_guarantor": yes(profile.get("hasGuarantor")),
        "has_viewing_person": yes(profile.get("hasViewingPerson")),
        "language_wish_unmet": wished["language_wish_unmet"],
        "language_wish_met": wished["language_wish_met"],
        "not_for_students": wished["not_for_students"],
    }
