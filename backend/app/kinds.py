"""What kind of home a listing is: Room, Studio, Apartment or House.

Listing platforms are unreliable here: Flatfox marks some WG rooms as 1-room "furnished
flats", and some providers call a room with a shared kitchen a "studio". So the source's
category is only one piece of evidence:

Room       not self-contained: a room in a shared flat (WG) or a residence. Any one of:
           the source says so, the title names a room, the description starts like a WG ad,
           or the kitchen is shared.
Studio     self-contained (own kitchen and bathroom), at most 1.5 rooms and at most 50 m².
Apartment  self-contained with 2+ rooms, or a spacious 1-1.5-room flat (over 50 m²).
House      the source lists a house.
"""

import re

ROOM, STUDIO, APARTMENT, HOUSE = "Room", "Studio", "Apartment", "House"
STUDIO_MAX_SURFACE = 50

SHARED_CATEGORIES = {"SHARED"}
SHARED_TYPES = {"SHARED_FLAT", "SINGLE_ROOM"}
HOUSE_CATEGORIES = {"HOUSE"}

# "Zimmer"/"room" right after a number is a room count ("3.5-Zimmer zu vermieten" is a flat).
_NOT_COUNTED = r"(?<![\d½]-)(?<![\d½] )(?<![\d½])"
# A single room in the title. "WG-tauglich" (suitable for a flatshare) describes an apartment.
ROOM_TITLE = re.compile(
    rf"\b(wg(?![- ]?(tauglich|geeignet|fähig))|wg-zimmer|wohngemeinschaft|{_NOT_COUNTED}zimmer in|{_NOT_COUNTED}zimmer im|"
    rf"{_NOT_COUNTED}zimmer zu vermieten|einzelzimmer|möbliertes zimmer|grosses zimmer|helles zimmer|schönes zimmer|"
    rf"gemütliches zimmer|freies zimmer|zimmer frei|{_NOT_COUNTED}rooms? in|room for rent|furnished room|single room|"
    r"private room|room available|flat ?share|shared (flat|apartment|house)|flatmates?|mitbewohner\w*|colocation|coloc|"
    r"chambre|stanza|camera in)\b",
    re.IGNORECASE,
)
# Titles that unmistakably offer a whole 2+ room apartment (possibly "for a WG").
WHOLE_APARTMENT_TITLE = re.compile(
    r"\b([2-9]([.,]5)?|[2-9] ?½|[2-9] 1/2)\s*-?\s*(zimmer|zi|room)\.?\s*-?\s*(wohnung|whg|apartment|flat)",
    re.IGNORECASE,
)
# Unambiguous single-room wording; beats a whole-apartment title ("Zimmer in 4-Zimmer-Wohnung").
STRONG_ROOM_TITLE = re.compile(
    rf"({_NOT_COUNTED}zimmer in|{_NOT_COUNTED}rooms? in|einzelzimmer|möbliertes zimmer|wg-zimmer|chambre|stanza|room for rent)",
    re.IGNORECASE,
)
# The first lines of a WG ad.
ROOM_INTRO = re.compile(
    r"(zimmer in (einer|unserer|der|meiner) (\w+ )?(wg|wohngemeinschaft)|wg-zimmer|wir sind eine \w*\s?wg|"
    r"(neue[nr]?|eine[nr]?) mitbewohner|new flatmate|looking for a flatmate|room in our (flat|apartment)|"
    r"chambre dans (une|notre) colocation)",
    re.IGNORECASE,
)
# The kitchen (or kitchen and bathroom) is shared, so the unit is not self-contained.
SHARED_KITCHEN = re.compile(
    r"(küche (und (bad|dusche) )?(auf dem stockwerk|auf der etage|wird geteilt|werden geteilt)|gemeinschaftsküche|"
    r"gemeinsame küche|geteilte küche|küche teilen|shared kitchen|kitchen (is |are )?shared|share the kitchen|"
    r"cuisine (commune|partagée))",
    re.IGNORECASE,
)
OWN_KITCHEN = re.compile(r"(kochnische|küchenzeile|kitchenette|own kitchen|private kitchen|eigene küche|cuisine privée)", re.IGNORECASE)
ONE_ROOM_WORDS = re.compile(
    r"\b(studio|einzimmer|eineinhalbzimmer|single[- ]?wohnung|1[- ]?(zimmer|zi|zw|room)\b|"
    r"1[.,]5[- ]?(zimmer|zi|room)|1 ?½|1 1/2)",
    re.IGNORECASE,
)


def classify(listing: dict) -> str:
    cached = listing.get("_kind")
    if cached:
        return cached
    kind = _classify(listing)
    listing["_kind"] = kind
    return kind


def _classify(listing: dict) -> str:
    title = listing.get("title") or ""
    description = listing.get("description") or ""
    rooms = listing.get("rooms")
    surface = listing.get("surface")

    if listing.get("category") in HOUSE_CATEGORIES:
        return HOUSE
    if listing.get("category") in SHARED_CATEGORIES or listing.get("object_type") in SHARED_TYPES:
        return ROOM
    whole_apartment = WHOLE_APARTMENT_TITLE.search(title) and not STRONG_ROOM_TITLE.search(title)
    if not whole_apartment and (ROOM_TITLE.search(title) or ROOM_INTRO.search(description[:400])):
        return ROOM
    text = f"{title}\n{description}"
    if (rooms is None or rooms <= 2) and SHARED_KITCHEN.search(text) and not OWN_KITCHEN.search(text):
        return ROOM

    one_room = (rooms is not None and rooms <= 1.5) or listing.get("object_type") == "STUDIO" or (
        rooms is None and ONE_ROOM_WORDS.search(title)
    )
    if one_room or (rooms is None and surface and surface <= 35):
        return APARTMENT if surface and surface > STUDIO_MAX_SURFACE else STUDIO
    return APARTMENT


def is_room(listing: dict) -> bool:
    return classify(listing) == ROOM
