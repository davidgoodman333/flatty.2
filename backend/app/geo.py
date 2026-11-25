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


# Where students study: name chosen in the app -> (short label, school in an English e-mail,
# school in a German e-mail, coordinates). The same list is in src/options.ts (CAMPUSES); keep
# both in sync. Coordinates come from OpenStreetMap (street address of each building).
CAMPUSES = {
    "University of Bern": ("Uni Bern", "the University of Bern", "an der Universität Bern", (46.9506, 7.4385)),
    "BFH (Bern University of Applied Sciences)": ("BFH", "the Bern University of Applied Sciences (BFH)", "an der Berner Fachhochschule (BFH)", (46.9513, 7.4352)),
    "Uni Bern: Main building (Hochschulstrasse 4)": ("Uni Bern main building", "the University of Bern", "an der Universität Bern", (46.9506, 7.4385)),
    "Uni Bern: UniS (Schanzeneckstrasse 1)": ("UniS", "the University of Bern", "an der Universität Bern", (46.9502, 7.4360)),
    "Uni Bern: ExWi, Exact Sciences (Sidlerstrasse 5)": ("ExWi", "the University of Bern", "an der Universität Bern", (46.9511, 7.4389)),
    "Uni Bern: Unitobler (Lerchenweg 36)": ("Unitobler", "the University of Bern", "an der Universität Bern", (46.9538, 7.4302)),
    "Uni Bern: vonRoll (Fabrikstrasse 8)": ("vonRoll", "the University of Bern", "an der Universität Bern", (46.9533, 7.4232)),
    "Uni Bern: Uni Mittelstrasse (Mittelstrasse 43)": ("Uni Mittelstrasse", "the University of Bern", "an der Universität Bern", (46.9558, 7.4356)),
    "Uni Bern: Uni Engehalde (Engehaldenstrasse 8)": ("Uni Engehalde", "the University of Bern", "an der Universität Bern", (46.9538, 7.4396)),
    "Uni Bern: Bühlplatz, Chemistry and Life Sciences (Baltzerstrasse 4)": ("Bühlplatz", "the University of Bern", "an der Universität Bern", (46.9518, 7.4285)),
    "Uni Bern: Insel campus, Medicine (Freiburgstrasse 18)": ("Insel campus", "the University of Bern", "an der Universität Bern", (46.9474, 7.4258)),
    "Uni Bern: Tierspital, Vetsuisse (Länggassstrasse 120)": ("Tierspital", "the University of Bern", "an der Universität Bern", (46.9564, 7.4268)),
    "Uni Bern: Sport Science, ZSSw (Bremgartenstrasse 145)": ("ZSSw", "the University of Bern", "an der Universität Bern", (46.9623, 7.4318)),
    "BFH: Business (Brückenstrasse 73)": ("BFH Business", "the Bern University of Applied Sciences (BFH)", "an der Berner Fachhochschule (BFH)", (46.9424, 7.4406)),
    "BFH: Health (Murtenstrasse 10)": ("BFH Health", "the Bern University of Applied Sciences (BFH)", "an der Berner Fachhochschule (BFH)", (46.9487, 7.4273)),
    "BFH: Health (Schwarztorstrasse 48)": ("BFH Health", "the Bern University of Applied Sciences (BFH)", "an der Berner Fachhochschule (BFH)", (46.9446, 7.4324)),
    "BFH: Social Work (Hallerstrasse 10)": ("BFH Social Work", "the Bern University of Applied Sciences (BFH)", "an der Berner Fachhochschule (BFH)", (46.9526, 7.4353)),
    "BFH: Engineering and Computer Science, Bern (Wankdorffeldstrasse 102)": ("BFH Wankdorf", "the Bern University of Applied Sciences (BFH)", "an der Berner Fachhochschule (BFH)", (46.9648, 7.4562)),
    "BFH: HKB Arts, Bümpliz (Fellerstrasse 11)": ("HKB Bümpliz", "the Bern Academy of the Arts (HKB)", "an der Hochschule der Künste Bern (HKB)", (46.9470, 7.3915)),
    "BFH: HKB Music (Papiermühlestrasse 13a)": ("HKB Music", "the Bern Academy of the Arts (HKB)", "an der Hochschule der Künste Bern (HKB)", (46.9554, 7.4605)),
    "BFH: HKB Music and Theatre (Ostermundigenstrasse 103)": ("HKB Ostermundigenstrasse", "the Bern Academy of the Arts (HKB)", "an der Hochschule der Künste Bern (HKB)", (46.9566, 7.4726)),
    "BFH: HAFL Agriculture, Forest and Food Sciences (Zollikofen)": ("BFH-HAFL Zollikofen", "the Bern University of Applied Sciences (BFH)", "an der Berner Fachhochschule (BFH)", (46.9918, 7.4680)),
    "BFH: Engineering and Computer Science, Biel/Bienne (Quellgasse 21)": ("BFH Biel", "the Bern University of Applied Sciences (BFH)", "an der Berner Fachhochschule (BFH)", (47.1422, 7.2448)),
    "BFH: Architecture, Wood and Civil Engineering, Biel/Bienne (Solothurnstrasse 102)": ("BFH Biel", "the Bern University of Applied Sciences (BFH)", "an der Berner Fachhochschule (BFH)", (47.1586, 7.2769)),
    "BFH: Burgdorf (Pestalozzistrasse 20)": ("BFH Burgdorf", "the Bern University of Applied Sciences (BFH)", "an der Berner Fachhochschule (BFH)", (47.0574, 7.6211)),
    "PHBern, University of Teacher Education (Fabrikstrasse 8)": ("PHBern", "PHBern, the University of Teacher Education", "an der PHBern", (46.9533, 7.4232)),
    "gibb Berufsfachschule Bern (Lorrainestrasse 1)": ("gibb", "gibb Berufsfachschule Bern", "an der gibb Berufsfachschule Bern", (46.9548, 7.4449)),
    "BFF Bern (Monbijoustrasse 21)": ("BFF Bern", "BFF Bern", "an der BFF Bern", (46.9445, 7.4365)),
    "WKS KV Bildung (Effingerstrasse 70)": ("WKS KV Bildung", "WKS KV Bildung in Bern", "an der WKS KV Bildung", (46.9459, 7.4283)),
    "Bildungszentrum Pflege (Freiburgstrasse 133)": ("BZ Pflege", "the Berner Bildungszentrum Pflege", "am Berner Bildungszentrum Pflege", (46.9431, 7.4088)),
    "Feusi Bildungszentrum (Max-Daetwyler-Platz 1)": ("Feusi", "Feusi Bildungszentrum in Bern", "am Feusi Bildungszentrum", (46.9664, 7.4655)),
}

# Free text (older profiles, pasted values) -> the closest campus entry.
DESTINATION_KEYWORDS = [
    (("vonroll", "von roll", "fabrikstrasse"), "Uni Bern: vonRoll (Fabrikstrasse 8)"),
    (("unitobler", "lerchenweg"), "Uni Bern: Unitobler (Lerchenweg 36)"),
    (("insel", "inselspital"), "Uni Bern: Insel campus, Medicine (Freiburgstrasse 18)"),
    (("ph bern", "phbern", "pädagogische"), "PHBern, University of Teacher Education (Fabrikstrasse 8)"),
    (("hkb", "hochschule der künste"), "BFH: HKB Arts, Bümpliz (Fellerstrasse 11)"),
    (("bfh", "berner fachhochschule", "fachhochschule", "applied sciences"), "BFH (Bern University of Applied Sciences)"),
    (("university of bern", "universität bern", "uni bern", "unibe", "hochschulstrasse"), "University of Bern"),
]
DEFAULT_DESTINATION = ("Bern station", (46.9490, 7.4391))


def campus(text: str | None) -> tuple[str, str, str, tuple[float, float]] | None:
    """The campus entry for a profile's destination, or None if it can't be placed."""
    if text in CAMPUSES:
        return CAMPUSES[text]
    query = (text or "").lower()
    for keywords, name in DESTINATION_KEYWORDS:
        if any(keyword in query for keyword in keywords):
            return CAMPUSES[name]
    return None


def school_name(text: str | None, german: bool = False) -> str:
    """How to name the student's school in an e-mail ("" if unknown)."""
    entry = campus(text)
    return entry[2 if german else 1] if entry else ""


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
    """Return (short name, coordinates, is_exact). Unknown places fall back to Bern station."""
    entry = campus(text)
    if entry:
        return entry[0], entry[3], True
    return DEFAULT_DESTINATION[0], DEFAULT_DESTINATION[1], False


def commute_minutes(origin: tuple[float, float], destination: tuple[float, float]) -> int:
    """Rough door-to-door public-transport estimate: tram/bus in town, train further out."""
    km = distance_km(origin, destination)
    return round(5 + km * 3.5) if km <= 6 else round(15 + km * 1.4)
