"""Registry of listing sources and the legal decision for each one.

See backend/LEGAL.md for the full assessment. A source is only collected when
`scraping_allowed` is True. A pasted link is only fetched when `link_check_allowed`
is True; otherwise the user is asked to paste the listing text instead.
"""

from dataclasses import asdict, dataclass
from urllib.parse import urlparse

REVIEWED_ON = "2026-10-30"


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    domains: tuple[str, ...]
    scraping_allowed: bool
    link_check_allowed: bool
    robots_txt: str
    terms: str
    terms_url: str
    decision: str
    max_requests: int = 0  # request budget per scraper run

    def public(self) -> dict:
        data = asdict(self)
        data["reviewed_on"] = REVIEWED_ON
        return data


SOURCES = [
    Source(
        key="flatfox",
        name="Flatfox",
        domains=("flatfox.ch",),
        scraping_allowed=True,
        link_check_allowed=True,
        robots_txt="Allows / for all user agents (only /admin/, /partner/ and similar are disallowed).",
        terms="AGB 4.2: reuse of published listings is reserved to the advertiser and Flatfox. No explicit ban on automated access.",
        terms_url="https://flatfox.ch/c/de/agb/",
        decision=(
            "Enabled for the non-public prototype through Flatfox's public listing API, at a low request rate. "
            "Flatty stores facts only, links back to the original and never republishes text or photos. "
            "Written permission from Flatfox is required before a public or paid launch."
        ),
        max_requests=60,
    ),
    Source(
        key="unibe",
        name="Uni Bern housing board",
        domains=("unibe.ch",),
        scraping_allowed=True,
        link_check_allowed=True,
        robots_txt="Allows the accommodation pages (only print, search and admin views are disallowed).",
        terms=(
            "Legal notice: content may be copied 'for personal, academic and non-commercial use'; commercial use, "
            "and storing it on other servers or feeding it into online services, needs prior written consent."
        ),
        terms_url="https://www.unibe.ch/legal_notice/index_eng.html",
        decision=(
            "Enabled for the local, academic, non-commercial prototype. Contact names, e-mails, phone numbers and street "
            "addresses of private hosts are never stored. Ask the Welcome Center for written consent before any hosted "
            "or public version."
        ),
        max_requests=90,
    ),
    Source(
        key="studentlodge",
        name="studentlodge (non-profit)",
        domains=("studentlodge.ch", "vbsl.ch"),
        scraping_allowed=True,
        link_check_allowed=True,
        robots_txt="Allows all user agents except a list of SEO crawlers.",
        terms="AGB only cover tenancy; no restriction on using the website. Footer: '© studentlodge.ch'.",
        terms_url="https://www.studentlodge.ch/AGB-315",
        decision="Enabled. One request per run (all room types are on one page). Photos are linked, not copied.",
        max_requests=5,
    ),
    Source(
        key="homegate",
        name="Homegate",
        domains=("homegate.ch",),
        scraping_allowed=False,
        link_check_allowed=False,
        robots_txt="Partially allowed (many query parameters disallowed).",
        terms="SMG AGB §7 explicitly forbids systematic reading of content 'z.B. durch Scraping'.",
        terms_url="https://www.homegate.ch/c/de/ueber-uns/rechtliches/agb",
        decision="Disabled. Needs a licensed data feed or partnership with SMG. Users can paste listing text to check it.",
    ),
    Source(
        key="immoscout24",
        name="ImmoScout24",
        domains=("immoscout24.ch",),
        scraping_allowed=False,
        link_check_allowed=False,
        robots_txt="Partially allowed.",
        terms="Same SMG terms as Homegate: scraping explicitly forbidden.",
        terms_url="https://www.homegate.ch/c/de/ueber-uns/rechtliches/agb",
        decision="Disabled. Needs a licensed data feed or partnership with SMG. Users can paste listing text to check it.",
    ),
    Source(
        key="wgzimmer",
        name="WG-Zimmer",
        domains=("wgzimmer.ch",),
        scraping_allowed=False,
        link_check_allowed=False,
        robots_txt="Listings are not disallowed.",
        terms="AGB §8: third parties may not take over listings 'ohne unsere Zustimmung … auch nicht automatisiert'.",
        terms_url="https://www.wgzimmer.ch/wgzimmer/agb.html",
        decision="Disabled until WG-Zimmer gives written consent. Users can paste listing text to check it.",
    ),
    Source(
        key="housinganywhere",
        name="HousingAnywhere",
        domains=("housinganywhere.com",),
        scraping_allowed=False,
        link_check_allowed=False,
        robots_txt="Allowed for most paths.",
        terms="Terms §5.9 forbid 'web spiders, crawlers, or similar tools for mass accessing or saving Platform content'; §8.7.2 forbids automated collection.",
        terms_url="https://housinganywhere.com/terms",
        decision="Disabled. Users can paste listing text to check it.",
    ),
    Source(
        key="newhome",
        name="newhome",
        domains=("newhome.ch",),
        scraping_allowed=False,
        link_check_allowed=False,
        robots_txt="Listings not disallowed, but the site answers bots with HTTP 403.",
        terms="Could not be read (403 for automated clients).",
        terms_url="https://www.newhome.ch",
        decision="Disabled: the site actively blocks bots and Flatty never works around that.",
    ),
    Source(
        key="studentsch",
        name="students.ch",
        domains=("students.ch", "uniboard.ch"),
        scraping_allowed=False,
        link_check_allowed=False,
        robots_txt="Listings not disallowed for generic bots.",
        terms="Pages sit behind an automatic bot check ('automatische Sicherheitsprüfung').",
        terms_url="https://www.students.ch",
        decision="Disabled: protected by a bot check, which Flatty never works around.",
    ),
    Source(
        key="other",
        name="Other websites",
        domains=(),
        scraping_allowed=False,
        link_check_allowed=True,
        robots_txt="Checked automatically for every single page.",
        terms="Not reviewed.",
        terms_url="",
        decision=(
            "No bulk collection. A single page the user pasted is fetched once, only if robots.txt allows it, "
            "and is not stored."
        ),
    ),
]

BY_KEY = {source.key: source for source in SOURCES}


def source_for_url(url: str) -> Source:
    host = (urlparse(url).hostname or "").lower()
    for source in SOURCES:
        if any(host == domain or host.endswith("." + domain) for domain in source.domains):
            return source
    return BY_KEY["other"]
