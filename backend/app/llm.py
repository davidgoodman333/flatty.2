"""Text generation with a local LLM through Ollama (http://127.0.0.1:11434).

The model runs on this machine; nothing is sent to an external API. If Ollama is not
running, a template is used instead so the app keeps working.
"""

import re
import threading
from contextlib import contextmanager

try:
    import httpx
except ImportError:
    httpx = None

from .config import OLLAMA_MODEL, OLLAMA_URL
from .geo import school_name
from .translations import is_already_english, translate_property_title

_TRANSLATION_CACHE: dict[str, str] = {}

# --- People first --------------------------------------------------------------------
# Ollama works on several requests at once (OLLAMA_NUM_PARALLEL, set by start-online.sh). The
# background jobs (app/llm_worker.py) wait while anyone is waiting for an e-mail, a summary, a
# translation or a pasted listing, so those get the graphics chip's full speed.
_people_waiting = 0
_people_lock = threading.Lock()
_nobody_waiting = threading.Event()
_nobody_waiting.set()


@contextmanager
def for_a_person():
    """Wrap AI work that someone is waiting for."""
    global _people_waiting
    with _people_lock:
        _people_waiting += 1
        _nobody_waiting.clear()
    try:
        yield
    finally:
        with _people_lock:
            _people_waiting -= 1
            if not _people_waiting:
                _nobody_waiting.set()


def wait_for_people(stop: threading.Event) -> None:
    """Block a background job until nobody is waiting for the AI (or the worker is stopped)."""
    while not _nobody_waiting.wait(timeout=1):
        if stop.is_set():
            return


def is_english_title(title: str) -> bool:
    return is_already_english(title)


def fallback_translate_title(title: str) -> str:
    """Glossary and pattern-based translation for Swiss rental titles when Ollama is offline."""
    return translate_property_title(title)


def _translate_title_llm(title: str) -> str:
    """Translates a rental title to natural English via the local Ollama LLM."""
    if httpx is None:
        raise RuntimeError("httpx is not installed")
    system = (
        "You translate Swiss rental listing titles from German or French into natural, concise English. "
        "Rules: Output ONLY the translated title, plain text, single line, no quotes, no commentary, no markdown. "
        "Real-estate terms: WG -> Shared flat, WG-Zimmer -> Room in shared flat, X-Zimmer-Wohnung -> X-room apartment, "
        "Altbau -> Period apartment, Attika -> Penthouse apartment, Möbliert -> Furnished, "
        "Nachmieter gesucht -> Replacement tenant wanted, per sofort -> available immediately, befristet -> temporary. "
        "Preserve Swiss neighbourhood names unchanged (Breitenrain, Länggasse, Mattenhof, Lorraine, Kirchenfeld, "
        "Bümpliz, Weissenbühl, Monbijou, Bern, Altstadt). Keep room numbers unchanged."
    )
    response = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "stream": False,
            "think": False,
            "options": {"temperature": 0.1, "num_predict": 60},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": title}],
        },
        timeout=8,
    )
    response.raise_for_status()
    text = response.json()["message"]["content"]
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"^(?:translation|english|title):\s*", "", text, flags=re.IGNORECASE)
    text = text.strip().strip('"\'`').strip()
    return text


def translate_title(title: str) -> str:
    """Translates a German listing title to English.

    Uses Ollama (local LLM) when running; falls back to the deterministic real-estate glossary
    so the app remains fully functional and compliant with local-only guidelines.
    """
    if not title or not title.strip():
        return ""
    clean = title.strip()
    if clean in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[clean]
    if is_english_title(clean):
        _TRANSLATION_CACHE[clean] = clean
        return clean

    translated = ""
    if available():
        try:
            translated = _translate_title_llm(clean)
        except Exception:
            translated = ""

    if not translated or len(translated) > len(clean) * 3:
        translated = fallback_translate_title(clean)

    _TRANSLATION_CACHE[clean] = translated
    return translated


_QUICK_CACHE: dict[str, str] = {}


def quick_title(title: str | None) -> str:
    """Instant English title for lists: the glossary, never the LLM (a search shows hundreds of
    listings, and one LLM call per title would block it for minutes)."""
    clean = (title or "").strip()
    if clean not in _QUICK_CACHE:
        _QUICK_CACHE[clean] = clean if not clean or is_english_title(clean) else fallback_translate_title(clean)
    return _QUICK_CACHE[clean]


def best_title(title: str) -> str | None:
    """LLM translation of one title for the background worker (app/llm_worker.py).
    None means Ollama can't be reached right now, so the worker should try again later."""
    clean = title.strip()
    if is_english_title(clean):
        return clean
    try:
        translated = _translate_title_llm(clean)
    except Exception:
        return None
    return translated if translated and len(translated) <= len(clean) * 3 else fallback_translate_title(clean)


def available() -> bool:
    if httpx is None:
        return False
    try:
        tags = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2).json()
        return any(model["name"] == OLLAMA_MODEL for model in tags.get("models", []))
    except (getattr(httpx, "HTTPError", Exception), ValueError, Exception):
        return False


def _chat(system: str, user: str) -> str:
    if httpx is None:
        raise RuntimeError("httpx is not installed")
    response = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "stream": False,
            "think": False,
            "options": {"temperature": 0.2, "num_predict": 500},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        },
        timeout=120,
    )
    response.raise_for_status()
    text = response.json()["message"]["content"]
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"^\s*\[[^\]]{1,40}\]\s*$", "", text, flags=re.MULTILINE)  # drop "[Name]"-style lines
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)  # Markdown line breaks ("  ") at line ends
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _natural(items: list[str], german: bool = False) -> str:
    items = [item for item in items if item]
    joiner = " und " if german else " and "
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])}{joiner}{items[-1]}" if items else ""


EMAIL_LANGUAGES = ("English", "German")
GREETING = {"English": "Hello,", "German": "Guten Tag"}
CLOSING = {"English": "Kind regards", "German": "Freundliche Grüsse"}
# The request for a viewing is fixed: the small local model sometimes garbles this sentence in German.
VIEWING = {
    "English": "I would be glad to come for a viewing and can send you my documents.",
    "German": "Gerne komme ich für eine Besichtigung vorbei und sende Ihnen meine Unterlagen.",
}
CLOSING_LINE = re.compile(
    r"\s*(kind regards|best regards|warm regards|regards|sincerely|yours sincerely|yours faithfully|"
    r"freundliche gr[üu]sse|mit freundlichen gr[üu]ssen|beste gr[üu]sse|liebe gr[üu]sse|herzliche gr[üu]sse)\b",
    re.IGNORECASE,
)

LANGUAGES_DE = {
    "English": "Englisch", "German": "Deutsch", "French": "Französisch", "Italian": "Italienisch",
    "Albanian": "Albanisch", "Arabic": "Arabisch", "Bengali": "Bengalisch", "Bosnian": "Bosnisch",
    "Bulgarian": "Bulgarisch", "Croatian": "Kroatisch", "Czech": "Tschechisch", "Danish": "Dänisch",
    "Dutch": "Niederländisch", "Finnish": "Finnisch", "Greek": "Griechisch", "Hebrew": "Hebräisch",
    "Hindi": "Hindi", "Hungarian": "Ungarisch", "Indonesian": "Indonesisch", "Japanese": "Japanisch",
    "Korean": "Koreanisch", "Mandarin": "Mandarin", "Norwegian": "Norwegisch", "Persian": "Persisch",
    "Polish": "Polnisch", "Portuguese": "Portugiesisch", "Romanian": "Rumänisch", "Russian": "Russisch",
    "Serbian": "Serbisch", "Slovak": "Slowakisch", "Spanish": "Spanisch", "Swedish": "Schwedisch",
    "Tamil": "Tamil", "Thai": "Thailändisch", "Turkish": "Türkisch", "Ukrainian": "Ukrainisch",
    "Urdu": "Urdu", "Vietnamese": "Vietnamesisch",
}

# "Ich komme …" for the German template (used only when Ollama is off). German needs the
# right article, so countries that aren't listed are simply left out of the sentence.
ORIGIN_DE = {
    "Switzerland": "aus der Schweiz", "Germany": "aus Deutschland", "Austria": "aus Österreich",
    "France": "aus Frankreich", "Italy": "aus Italien", "Spain": "aus Spanien", "Portugal": "aus Portugal",
    "United Kingdom": "aus Grossbritannien", "Ireland": "aus Irland", "Netherlands": "aus den Niederlanden",
    "Belgium": "aus Belgien", "Luxembourg": "aus Luxemburg", "Liechtenstein": "aus Liechtenstein",
    "Denmark": "aus Dänemark", "Sweden": "aus Schweden", "Norway": "aus Norwegen", "Finland": "aus Finnland",
    "Iceland": "aus Island", "Poland": "aus Polen", "Czechia": "aus Tschechien", "Slovakia": "aus der Slowakei",
    "Hungary": "aus Ungarn", "Romania": "aus Rumänien", "Bulgaria": "aus Bulgarien", "Greece": "aus Griechenland",
    "Croatia": "aus Kroatien", "Slovenia": "aus Slowenien", "Serbia": "aus Serbien",
    "Bosnia and Herzegovina": "aus Bosnien und Herzegowina", "Montenegro": "aus Montenegro",
    "North Macedonia": "aus Nordmazedonien", "Albania": "aus Albanien", "Kosovo": "aus dem Kosovo",
    "Ukraine": "aus der Ukraine", "Russia": "aus Russland", "Belarus": "aus Belarus", "Moldova": "aus Moldau",
    "Estonia": "aus Estland", "Latvia": "aus Lettland", "Lithuania": "aus Litauen", "Turkey": "aus der Türkei",
    "Cyprus": "aus Zypern", "Malta": "aus Malta", "Georgia": "aus Georgien", "Armenia": "aus Armenien",
    "United States": "aus den USA", "Canada": "aus Kanada", "Mexico": "aus Mexiko", "Brazil": "aus Brasilien",
    "Argentina": "aus Argentinien", "Chile": "aus Chile", "Colombia": "aus Kolumbien", "Peru": "aus Peru",
    "China": "aus China", "India": "aus Indien", "Japan": "aus Japan", "South Korea": "aus Südkorea",
    "Taiwan": "aus Taiwan", "Hong Kong": "aus Hongkong", "Singapore": "aus Singapur", "Vietnam": "aus Vietnam",
    "Thailand": "aus Thailand", "Indonesia": "aus Indonesien", "Malaysia": "aus Malaysia",
    "Philippines": "von den Philippinen", "Pakistan": "aus Pakistan", "Bangladesh": "aus Bangladesch",
    "Sri Lanka": "aus Sri Lanka", "Nepal": "aus Nepal", "Iran": "aus dem Iran", "Iraq": "aus dem Irak",
    "Israel": "aus Israel", "Lebanon": "aus dem Libanon", "Syria": "aus Syrien", "Egypt": "aus Ägypten",
    "Morocco": "aus Marokko", "Tunisia": "aus Tunesien", "Algeria": "aus Algerien", "Nigeria": "aus Nigeria",
    "Ghana": "aus Ghana", "Kenya": "aus Kenia", "Ethiopia": "aus Äthiopien", "South Africa": "aus Südafrika",
    "Australia": "aus Australien", "New Zealand": "aus Neuseeland",
}

FIRST_PERSON = {
    "English": {
        "hasGuarantor": "I have a guarantor who lives in Switzerland.",
        "hasViewingPerson": "Someone can attend a viewing on my behalf.",
        "hasResidencePermit": "I have a Swiss residence permit.",
        "hasSwissBank": "I have a Swiss bank account.",
        "hasSwissNumber": "I have a Swiss phone number.",
    },
    "German": {
        "hasGuarantor": "Eine Person mit Wohnsitz in der Schweiz bürgt für mich.",
        "hasViewingPerson": "Eine Vertrauensperson kann die Wohnung an meiner Stelle besichtigen.",
        "hasResidencePermit": "Ich habe eine Schweizer Aufenthaltsbewilligung.",
        "hasSwissBank": "Ich habe ein Schweizer Bankkonto.",
        "hasSwissNumber": "Ich habe eine Schweizer Telefonnummer.",
    },
}


def _name(profile: dict) -> str:
    return " ".join((profile.get("name") or "").split())[:80]


def _country(profile: dict) -> str:
    country = (profile.get("country") or "").strip()
    return "" if country == "Other" else country


def _profile_facts(profile: dict, german: bool = False) -> list[str]:
    school = school_name(profile.get("destination"), german)
    if german:
        school = re.sub(r"^(an der|am)\s+", "", school)  # the bare name; the model adds the preposition
    facts = [
        f"Name: {_name(profile)}" if _name(profile) else "",
        f"From: {_country(profile)}" if _country(profile) else "",
        f"Studies at: {school}" if school else "Studies in Bern",
        f"Languages: {_natural(profile.get('languages') or ['English'])}",
    ]
    for key, label in (
        ("hasGuarantor", "Guarantor living in Switzerland: yes"),
        ("hasViewingPerson", "Someone who can attend viewings on the applicant's behalf: yes"),
        ("hasResidencePermit", "Swiss residence permit: yes"),
        ("hasSwissBank", "Swiss bank account: yes"),
        ("hasSwissNumber", "Swiss phone number: yes"),
    ):
        if profile.get(key) == "yes":
            facts.append(label)
    return [fact for fact in facts if fact]


def _email_title(listing: dict, language: str) -> str:
    """The landlord's own title for a German e-mail, the English one otherwise."""
    return (listing.get("originalTitle") or listing.get("title")) if language == "German" else listing.get("title")


def _listing_facts(listing: dict, email_language: str | None = None) -> str:
    title = listing.get("title")
    orig = listing.get("originalTitle")
    if email_language:
        title_line = f"Title: {_email_title(listing, email_language)}"
    else:
        title_line = f"Title: {title} (Original listing title: {orig})" if orig and orig != title else f"Title: {title}"
    return (
        f"{title_line}\nArea: {listing.get('area')}, {listing.get('city') or 'Bern'}\n"
        f"Rent: {listing.get('rent')} per month\nSize: {listing.get('meta')}\n"
        f"Available from: {listing.get('movingDate') or 'not stated'}\nListing language: {listing.get('language')}"
    )


def email_language(listing: dict, profile: dict) -> str:
    """Default e-mail language: the listing's, if it is German; otherwise English."""
    return "German" if listing.get("language") == "German" else "English"


def sign(text: str, language: str, name: str) -> str:
    """End the e-mail with the standard closing and the student's name, replacing whatever
    the model wrote there (it sometimes invents a name or leaves a placeholder)."""
    lines = text.rstrip().splitlines()
    for index in range(len(lines) - 1, max(len(lines) - 6, -1), -1):
        if CLOSING_LINE.match(lines[index]):
            lines = lines[:index]
            break
    body = "\n".join(lines).rstrip()
    return f"{body}\n\n{CLOSING[language]}" + (f"\n{name}" if name else "")


def template_email(listing: dict, profile: dict, language: str | None = None) -> str:
    language = language if language in EMAIL_LANGUAGES else email_language(listing, profile)
    german = language == "German"
    name, country = _name(profile), _country(profile)
    school = school_name(profile.get("destination"), german)
    extras = [sentence for key, sentence in FIRST_PERSON[language].items() if profile.get(key) == "yes"]
    speaks = profile.get("languages") or ["English"]
    title = _email_title(listing, language)
    if german:
        origin = ORIGIN_DE.get(country, "")
        study = f"studiere {school}" if school else "studiere in Bern"
        intro = [
            f"Ich interessiere mich für Ihr Inserat «{title}» ({listing.get('area')}).",
            f"Ich heisse {name}." if name else "",
            f"Ich komme {origin} und {study}." if origin else f"Ich {study}.",
        ]
        about = f"Ich spreche {_natural([LANGUAGES_DE.get(item, item) for item in speaks], german=True)}."
        ask = VIEWING[language]
    else:
        study = f"study at {school}" if school else "study in Bern"
        intro = [
            f"I am interested in your listing “{title}” in {listing.get('area')}.",
            f"My name is {name}." if name else "",
            f"I am from {country} and {study}." if country else f"I {study}.",
        ]
        about = f"I speak {_natural(speaks)}."
        ask = VIEWING[language]
    lines = [
        GREETING[language],
        "",
        " ".join(sentence for sentence in intro if sentence),
        "",
        " ".join([about, *extras]),
        ask,
    ]
    return sign("\n".join(lines), language, name)


def template_summary(listing: dict) -> str:
    facts = (listing.get("notes") or []) + (listing.get("reasons") or [])
    reasons = "; ".join(f"{r['title'].lower()} ({r['detail']})" for r in facts[:4])
    flags = listing.get("riskFlags") or []
    risk = f" Warning signs: {'; '.join(flags).lower()}." if flags else " No warning signs were found in the text."
    return (
        f"{listing.get('title')} in {listing.get('area')}. {listing.get('meta')} for {listing.get('rent')} per month. "
        f"{reasons.capitalize()}.{risk} A reply from the landlord is {(listing.get('replyLabel') or 'not rated').lower()}; risk {listing.get('risk')} %."
    )


def generate(kind: str, listing: dict, profile: dict, language: str | None = None) -> dict:
    """E-mails come in English or German (`language`; default: the listing's language if it is
    German, otherwise English). The reply says which language was written."""
    if kind in ("title", "translate"):
        orig = listing.get("originalTitle") or listing.get("title") or ""
        trans = translate_title(orig)
        engine = OLLAMA_MODEL if available() else "template"
        return {"text": trans, "engine": engine}

    if kind == "email":
        language = language if language in EMAIL_LANGUAGES else email_language(listing, profile)
        fallback = {"text": template_email(listing, profile, language), "engine": "template", "language": language}
    else:
        fallback = {"text": template_summary(listing), "engine": "template"}
    if not available():
        return fallback

    if kind == "email":
        german = language == "German"
        name = _name(profile)
        system = (
            "You write short, polite rental application e-mails for international students in Bern, Switzerland. "
            "The applicant sends the e-mail themselves, so write it in the first person ('I'), never about the applicant "
            "in the third person, and never guess the applicant's gender. "
            f"Write in {language}"
            + (" (Swiss Standard German: write 'ss', never 'ß'; address the landlord formally with 'Sie')" if german else "") + ". "
            f"Structure: the greeting '{GREETING[language]}'; one sentence saying you are interested in this specific listing "
            "(name its title and area); one to three sentences introducing the applicant that state the applicant facts and nothing else"
            + (", beginning with their name" if name else "") + f"; then exactly this sentence as its own paragraph: '{VIEWING[language]}'; "
            f"then the closing line '{CLOSING[language]}'. Write nothing after the closing line: no name, no signature. "
            "Use every applicant fact once. If there are only a few facts, keep the e-mail short: never add wishes, "
            "preferences, flatmates, hobbies, language skills or anything else that is not in the facts. "
            "Never invent documents, income, names, dates or facts, and do not suggest a day or time for the viewing. "
            + ("Write 'Ich studiere an …', never 'Student' or 'Studentin'. " if german else "Write 'I study at …'. ")
            + "No subject line, no placeholders in brackets. Put an empty line between the greeting, each paragraph and "
            "the closing. Maximum 130 words. Plain text."
        )
        user = (
            f"Listing:\n{_listing_facts(listing, language)}\n\nApplicant:\n"
            + "\n".join(f"- {fact}" for fact in _profile_facts(profile, german))
        )
    else:
        system = (
            "You summarise apartment listings for international students in Bern. English, plain text, "
            "at most 90 words. Use only the facts given. Mention warning signs if there are any."
        )
        user = (
            f"{_listing_facts(listing)}\nWill the landlord reply: {listing.get('replyLabel')}\n"
            f"Scam risk: {listing.get('risk')} %\n"
            f"What affects the reply likelihood: {[r['title'] + ' - ' + r['detail'] for r in listing.get('reasons') or []]}\n"
            f"Compared with the student's preferences: {[r['title'] + ' - ' + r['detail'] for r in listing.get('notes') or []]}\n"
            f"Warning signs: {listing.get('riskFlags') or 'none'}"
        )
    try:
        text = _chat(system, user)
    except (httpx.HTTPError, KeyError, ValueError):
        return fallback
    if kind != "email":
        return {"text": text, "engine": OLLAMA_MODEL}
    if german:
        text = text.replace("ß", "ss")  # Swiss Standard German
    return {"text": sign(text, language, name), "engine": OLLAMA_MODEL, "language": language}
