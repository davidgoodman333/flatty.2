"""Offline geography for Bern: neighbourhoods, common destinations and commute estimates.

No geocoding API is used. Coordinates are approximate centroids, good enough to
assign a neighbourhood and estimate a public-transport commute.
"""

import re
from math import asin, cos, radians, sin, sqrt

BERN_NEIGHBOURHOODS = {
    "Old Town": (46.9480, 7.4474),
    "Länggasse": (46.9560, 7.4290),
    "Lorraine": (46.9560, 7.4450),
    "Breitenrain": (46.9590, 7.4530),
    "Wankdorf": (46.9640, 7.4660),
    "Felsenau": (46.9650, 7.4380),
    "Mattenhof": (46.9425, 7.4290),
    "Monbijou": (46.9420, 7.4400),
    "Weissenbühl": (46.9360, 7.4260),
    "Holligen": (46.9440, 7.4140),
    "Bümpliz": (46.9430, 7.3900),
    "Bethlehem": (46.9470, 7.3730),
    "Kirchenfeld": (46.9420, 7.4520),
    "Schosshalde": (46.9500, 7.4700),
    "Elfenau": (46.9330, 7.4690),
}

# For sources that publish no coordinates (approximate centres).
BERN_CENTRE = (46.9480, 7.4474)
# Places inside the City of Bern, in addition to BERN_NEIGHBOURHOODS.
BERN_SPOTS = {
    "Tscharnergut": (46.9446, 7.3826), "Bümpliz Nord": (46.9490, 7.3930), "WankdorfCity": (46.9620, 7.4700),
    "Brünnen": (46.9440, 7.3740), "Altenberg": (46.9530, 7.4520), "Sandrain": (46.9410, 7.4410),
    "Obstberg": (46.9480, 7.4600), "Old town": (46.9480, 7.4474), "Altstadt": (46.9480, 7.4474),
    "Engehalde": (46.9620, 7.4400), "Spitalacker": (46.9560, 7.4560), "Murifeld": (46.9420, 7.4680),
}
TOWNS = {
    "Köniz": (46.9240, 7.4140), "Wabern": (46.9290, 7.4510), "Liebefeld": (46.9300, 7.4180),
    "Ostermundigen": (46.9560, 7.4870), "Ittigen": (46.9760, 7.4810), "Zollikofen": (46.9990, 7.4580),
    "Bolligen": (46.9735, 7.4960), "Muri bei Bern": (46.9310, 7.4870), "Gümligen": (46.9330, 7.5080),
    "Bremgarten bei Bern": (46.9780, 7.4380), "Worb": (46.9300, 7.5630), "Belp": (46.8910, 7.4980),
    "Münsingen": (46.8730, 7.5610), "Kehrsatz": (46.9100, 7.4710), "Niederwangen": (46.9250, 7.3800),
    "Hinterkappelen": (46.9640, 7.3800), "Lyss": (47.0740, 7.3060), "Burgdorf": (47.0590, 7.6280),
    "Thun": (46.7580, 7.6280), "Biel": (47.1370, 7.2470), "Fribourg": (46.8060, 7.1610),
    "Laupen": (46.9020, 7.2400), "Utzenstorf": (47.1300, 7.5560), "Schliern": (46.9050, 7.4170),
    "Niederscherli": (46.8870, 7.3920), "Rüfenacht": (46.9300, 7.5370), "Spiegel bei Bern": (46.9240, 7.4330),
    "Wahlendorf": (46.9930, 7.3650), "Toffen": (46.8600, 7.4920), "Studen": (47.1110, 7.3030),
    "Sigriswil": (46.7170, 7.7150), "Wohlen bei Bern": (46.9720, 7.3570), "Uettligen": (46.9890, 7.3870),
    "Kirchlindach": (46.9990, 7.4170), "Stettlen": (46.9580, 7.5250), "Allmendingen": (46.9180, 7.5250),
}


def _find(places: dict, text: str) -> tuple[str, tuple[float, float]] | None:
    for name, coords in sorted(places.items(), key=lambda item: -len(item[0])):
        # Whole words only: "Thunstrasse" must not match "Thun".
        if re.search(rf"(?<!\w){re.escape(name.lower())}(?!\w)", text):
            return name, coords
    return None


def locate(*texts: str | None) -> tuple[str | None, tuple[float, float] | None]:
    """(town, coordinates) from free text. Places inside Bern resolve to town "Bern"."""
    joined = " ".join(text for text in texts if text).lower()
    if town := _find(TOWNS, joined):
        return town
    if spot := _find({**BERN_NEIGHBOURHOODS, **BERN_SPOTS}, joined):
        return "Bern", spot[1]
    return ("Bern", BERN_CENTRE) if "bern" in joined else (None, None)


def place_coordinates(*texts: str | None) -> tuple[float, float] | None:
    return locate(*texts)[1]


DESTINATIONS = [
    (("university of bern", "uni bern", "unibe", "unitobler", "vonroll", "hochschulstrasse"), "University of Bern", (46.9505, 7.4381)),
    (("bfh", "berner fachhochschule", "fachhochschule"), "BFH Bern", (46.9614, 7.4655)),
    (("ph bern", "phbern", "pädagogische"), "PH Bern", (46.9532, 7.4318)),
    (("insel", "inselspital"), "Inselspital", (46.9471, 7.4245)),
    (("wankdorf",), "Wankdorf", (46.9630, 7.4650)),
    (("bahnhof", "hauptbahnhof", "bern hb", "station", "bern"), "Bern station", (46.9490, 7.4391)),
]
DEFAULT_DESTINATION = ("Bern station", (46.9490, 7.4391))


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1, lat2, lng2 = map(radians, (*a, *b))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(h))


def neighbourhood(city: str | None, lat: float | None, lng: float | None) -> str:
    city = (city or "").strip()
    if city.lower() == "bern" and lat and lng:
        return min(BERN_NEIGHBOURHOODS, key=lambda name: distance_km((lat, lng), BERN_NEIGHBOURHOODS[name]))
    return city.title() if city.islower() else city or "Bern region"


def resolve_destination(text: str | None) -> tuple[str, tuple[float, float], bool]:
    """Return (name, coordinates, is_exact). Unknown places fall back to Bern station."""
    query = (text or "").lower()
    for keywords, name, coords in DESTINATIONS:
        if any(keyword in query for keyword in keywords):
            return name, coords, True
    return DEFAULT_DESTINATION[0], DEFAULT_DESTINATION[1], False


def commute_minutes(origin: tuple[float, float], destination: tuple[float, float]) -> int:
    """Rough door-to-door public-transport estimate: tram/bus in town, train further out."""
    km = distance_km(origin, destination)
    return round(5 + km * 3.5) if km <= 6 else round(15 + km * 1.4)
