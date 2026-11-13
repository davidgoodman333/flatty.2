"""Text generation with a local LLM through Ollama (http://127.0.0.1:11434).

The model runs on this machine; nothing is sent to an external API. If Ollama is not
running, a template is used instead so the app keeps working.
"""

import re

try:
    import httpx
except ImportError:
    httpx = None

from .config import OLLAMA_MODEL, OLLAMA_URL

_TRANSLATION_CACHE: dict[str, str] = {}

GERMAN_PHRASES = [
    (r"\bnachmieter(?:in)? gesucht(?: für)?\b", "replacement tenant wanted for"),
    (r"\bnachmieter(?:in)? gesucht\b", "replacement tenant wanted"),
    (r"\balles inklusive\b", "all inclusive"),
    (r"\bper sofort oder nach vereinbarung\b", "immediately or by arrangement"),
    (r"\bab sofort oder nach vereinbarung\b", "immediately or by arrangement"),
    (r"\bsofort frei\b", "free immediately"),
    (r"\bper sofort\b", "available immediately"),
    (r"\bab sofort\b", "available immediately"),
    (r"\bnach vereinbarung\b", "by arrangement"),
    (r"\ban ruhiger lage\b", "in a quiet location"),
    (r"\ban zentraler lage\b", "in a central location"),
    (r"\ban bester lage\b", "in prime location"),
    (r"\ban sonniger lage\b", "in a sunny location"),
    (r"\bin ruhiger lage\b", "in a quiet location"),
    (r"\bin zentraler lage\b", "in a central location"),
    (r"\bnähe bahnhof\b", "near train station"),
    (r"\bnähe uni(?:versität)?\b", "near university"),
    (r"\bnähe zentrum\b", "near city centre"),
    (r"\bin der nähe von\b", "near"),
    (r"\bin der nähe\b", "nearby"),
    (r"\bim zentrum\b", "in city centre"),
    (r"\bim stadtzentrum\b", "in city centre"),
    (r"\bim beliebten\b", "in popular"),
    (r"\bim herzen von\b", "in the heart of"),
    (r"\bin der\b", "in"),
    (r"\bmit aussicht\b", "with view"),
    (r"\bmit weitsicht\b", "with panoramic view"),
    (r"\bmit balkon\b", "with balcony"),
    (r"\bmit garten\b", "with garden"),
    (r"\bmit terrasse\b", "with terrace"),
    (r"\bmit lift\b", "with lift"),
    (r"\bmit parkplatz\b", "with parking"),
    (r"\bmit einstellhallenplatz\b", "with indoor parking"),
    (r"\bmit waschturm\b", "with washing tower"),
    (r"\bmit waschmaschine\b", "with washing machine"),
    (r"\binkl\.?\s*nebenkosten\b", "incl. utilities"),
    (r"\binkl\.?\s*nk\b", "incl. utilities"),
    (r"\binklusive nebenkosten\b", "including utilities"),
]

ROOM_PATTERNS = [
    (r"\bzimmer in netter (\d+)er[- ]?wg\b", r"Room in nice \1-person shared flat"),
    (r"\bzimmer in (?:einer )?(\d+)er[- ]?wg\b", r"Room in \1-person shared flat"),
    (r"\bzimmer in netter wg\b", r"Room in nice shared flat"),
    (r"\bzimmer in (?:einer )?wg\b", r"Room in shared flat"),
    (r"\bzimmer in (\d+(?:[.,]\d+)?)[- ]?zimmer[- ]?wohnung\b", r"Room in \1-room apartment"),
    (r"\bwg[- ]?zimmer\b", r"Room in shared flat"),
    (r"\bstudierendenzimmer\b", r"Student room"),
    (r"\bstudentenzimmer\b", r"Student room"),
    (r"\beinzelzimmer\b", r"Single room"),
    (r"\bdoppelzimmer\b", r"Double room"),
    (r"\bmöblierte?s? zimmer\b", r"Furnished room"),
    (r"\bbefristete?s? zimmer\b", r"Temporary room"),
    (r"\buntermiete\b", r"Sublet"),
    (r"(\d+(?:[.,]\d+)?)\s*[- ]?zi(?:mmer)?[- ]?(?:wohnung|whg)\b", r"\1-room apartment"),
    (r"(\d+(?:[.,]\d+)?)\s*[- ]?zimmer\b", r"\1-room"),
    (r"\baltbau[- ]?wohnung\b", r"Period apartment"),
    (r"\baltbau\b", r"Period building"),
    (r"\battika[- ]?wohnung\b", r"Penthouse apartment"),
    (r"\battika\b", r"Penthouse"),
    (r"\bdach[- ]?wohnung\b", r"Top-floor apartment"),
    (r"\bdachgeschosswohnung\b", r"Top-floor apartment"),
    (r"\bterrasen[- ]?wohnung\b", r"Terrace apartment"),
    (r"\bgarten[- ]?wohnung\b", r"Garden apartment"),
    (r"\bstudio[- ]?wohnung\b", r"Studio apartment"),
    (r"\bfamilien[- ]?wohnung\b", r"Family apartment"),
    (r"\bwohnung\b", r"Apartment"),
    (r"\bwohnungen\b", r"Apartments"),
    (r"\bzimmer\b", r"Room"),
]

WORDS = {
    "helle": "Bright", "heller": "Bright", "helles": "Bright", "hell": "Bright",
    "schöne": "Nice", "schöner": "Nice", "schönes": "Nice", "schön": "Nice",
    "wunderschöne": "Wonderful", "wunderschönes": "Wonderful",
    "charmante": "Charming", "charmanter": "Charming", "charmantes": "Charming",
    "moderne": "Modern", "moderner": "Modern", "modernes": "Modern", "modern": "Modern",
    "grosszügige": "Spacious", "grosszügiger": "Spacious", "grosszügiges": "Spacious", "großzügige": "Spacious",
    "grosse": "Large", "grosser": "Large", "grosses": "Large", "große": "Large", "großes": "Large", "gross": "Large",
    "kleine": "Small", "kleiner": "Small", "kleines": "Small", "klein": "Small",
    "ruhige": "Quiet", "ruhiger": "Quiet", "ruhiges": "Quiet", "ruhig": "Quiet",
    "zentrale": "Central", "zentraler": "Central", "zentrales": "Central", "zentral": "Central",
    "gemütliche": "Cosy", "gemütlicher": "Cosy", "gemütliches": "Cosy", "gemütlich": "Cosy",
    "möblierte": "Furnished", "möblierter": "Furnished", "möbliertes": "Furnished", "möbliert": "Furnished",
    "teilmöblierte": "Partly furnished", "teilmöbliertes": "Partly furnished", "teilmöbliert": "Partly furnished",
    "unmöbliert": "Unfurnished", "unmöblierte": "Unfurnished",
    "befristete": "Temporary", "befristeter": "Temporary", "befristetes": "Temporary", "befristet": "Temporary",
    "unbefristete": "Permanent", "unbefristet": "Permanent",
    "neue": "New", "neuer": "New", "neues": "New", "neu": "New",
    "neuwertige": "Like-new", "neuwertiges": "Like-new",
    "renovierte": "Renovated", "renovierter": "Renovated", "renoviertes": "Renovated", "renoviert": "Renovated",
    "teilsaniert": "Partly renovated", "saniert": "Renovated", "sanierte": "Renovated",
    "gepflegte": "Well-maintained", "gepflegtes": "Well-maintained",
    "luxuriöse": "Luxury", "luxuriöses": "Luxury", "luxus": "Luxury",
    "sonnige": "Sunny", "sonniger": "Sunny", "sonniges": "Sunny",
    "exklusive": "Exclusive", "exklusives": "Exclusive",
    "ideale": "Ideal", "ideales": "Ideal", "ideal": "Ideal",
    "perfekte": "Perfect", "perfektes": "Perfect", "perfekt": "Perfect",
    "praktische": "Practical", "praktisches": "Practical",
    "tolle": "Great", "tolles": "Great",
    "erstvermietung": "First-time let",
    "erstbezug": "First occupancy",
    "traumwohnung": "Dream apartment",
    "aussicht": "View",
    "balkon": "Balcony",
    "terrasse": "Terrace",
    "garten": "Garden",
    "lift": "Elevator",
    "mit": "with",
    "und": "and",
    "oder": "or",
    "für": "for",
    "im": "in",
    "in": "in",
    "an": "in",
    "am": "at",
    "ab": "from",
    "per": "from",
    "von": "from",
    "bis": "until",
    "zu": "to",
    "vermieten": "rent",
    "gesucht": "wanted",
    "sofort": "immediately",
    "frei": "available",
    "nähe": "near",
}

FRENCH_PATTERNS = [
    (r"\bchambre en colocation\b", "Room in shared flat"),
    (r"\bchambre meublée\b", "Furnished room"),
    (r"\bchambre\b", "Room"),
    (r"\bcolocation\b", "Shared flat"),
    (r"(\d+(?:[.,]\d+)?)\s*pièces?\b", r"\1-room apartment"),
    (r"\bappartement meublé\b", "Furnished apartment"),
    (r"\bappartement\b", "Apartment"),
    (r"\bproche de la gare\b", "near train station"),
    (r"\bproche (?:de )?l'université\b", "near university"),
    (r"\blumineux\b", "bright"),
    (r"\blumineuse\b", "bright"),
]

GERMAN_INDICATORS = re.compile(
    r"\b(zimmer|wohnung|wohnungen|wg|whg|altbau|attika|dachwohnung|möbliert|möbliertes|möblierte|"
    r"nachmieter|befristet|unbefristet|sofort|per sofort|ab sofort|ruhige|ruhiger|ruhig|helle|helles|hell|"
    r"schöne|schönes|schön|grosse|grosses|grosszügige|zentrale|gemütliche|mit|und|für|im|an der|in der|"
    r"untermiete|erstvermietung|nähe|neuwertig|saniert)\b|[äöüÄÖÜß]",
    re.IGNORECASE,
)

ENGLISH_INDICATORS = re.compile(
    r"\b(apartment|flat|room|bedroom|studio near|bright|quiet|furnished|available|near|shared flat|"
    r"sublet|spacious|student|cosy|temporary|historic)\b",
    re.IGNORECASE,
)


def is_english_title(title: str) -> bool:
    if not title:
        return True
    has_german = bool(GERMAN_INDICATORS.search(title))
    has_english = bool(ENGLISH_INDICATORS.search(title))
    return has_english and not has_german


def fallback_translate_title(title: str) -> str:
    """Glossary and pattern-based translation for Swiss rental titles when Ollama is offline."""
    if not title or not title.strip():
        return ""
    text = title.strip()
    if is_english_title(text):
        return text

    for pattern, repl in FRENCH_PATTERNS:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)

    for pattern, repl in GERMAN_PHRASES:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)

    for pattern, repl in ROOM_PATTERNS:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)

    def replace_word(match):
        w = match.group(0)
        low = w.lower()
        if low in WORDS:
            target = WORDS[low]
            if match.start() == 0:
                return target.capitalize()
            return target.lower()
        return w

    text = re.sub(r"\b[a-zA-ZäöüÄÖÜßéèàâêîôûç]+\b", replace_word, text)
    text = re.sub(r"(\d+(?:\.\d+)?)\s+(room|person)\b", r"\1-\2", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    if text:
        text = text[0].upper() + text[1:]
    return text


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
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _natural(items: list[str]) -> str:
    items = [item for item in items if item]
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}" if items else ""


def _profile_facts(profile: dict) -> list[str]:
    facts = [
        f"From: {profile.get('country') or 'not given'}",
        f"Studies or works at: {profile.get('destination') or 'not given'}",
        f"Speaks: {_natural(profile.get('languages') or ['English'])}",
        f"Looking for: {_natural([t.lower() for t in profile.get('apartmentTypes') or []]) or 'a flat'}",
    ]
    for key, label in (
        ("hasGuarantor", "Has a guarantor living in Switzerland"),
        ("hasViewingPerson", "Has someone who can attend viewings on their behalf"),
        ("hasResidencePermit", "Has a Swiss residence permit"),
        ("hasSwissBank", "Has a Swiss bank account"),
        ("hasSwissNumber", "Has a Swiss phone number"),
    ):
        if profile.get(key) == "yes":
            facts.append(label)
    return facts


def _listing_facts(listing: dict) -> str:
    title = listing.get("title")
    orig = listing.get("originalTitle")
    title_line = f"Title: {title} (Original listing title: {orig})" if orig and orig != title else f"Title: {title}"
    return (
        f"{title_line}\nArea: {listing.get('area')}, {listing.get('city') or 'Bern'}\n"
        f"Rent: {listing.get('rent')} per month\nSize: {listing.get('meta')}\n"
        f"Available from: {listing.get('movingDate') or 'not stated'}\nListing language: {listing.get('language')}"
    )


def email_language(listing: dict, profile: dict) -> str:
    language = listing.get("language")
    return language if language in (profile.get("languages") or []) else "English"


FIRST_PERSON = {
    "hasGuarantor": "I have a guarantor who lives in Switzerland.",
    "hasViewingPerson": "Someone can attend a viewing on my behalf.",
    "hasResidencePermit": "I have a Swiss residence permit.",
    "hasSwissBank": "I have a Swiss bank account.",
    "hasSwissNumber": "I have a Swiss phone number.",
}


def template_email(listing: dict, profile: dict) -> str:
    extras = [sentence for key, sentence in FIRST_PERSON.items() if profile.get(key) == "yes"]
    # Reference the landlord's original listing title if German, otherwise the translated title
    lang = email_language(listing, profile)
    ref_title = (listing.get("originalTitle") or listing.get("title")) if lang == "German" else listing.get("title")
    lines = [
        "Hello,",
        "",
        f"I am interested in your listing “{ref_title}” in {listing.get('area')}. "
        f"I am from {profile.get('country') or 'abroad'} and study or work at {profile.get('destination') or 'a university in Bern'}.",
        "",
        f"I speak {_natural(profile.get('languages') or ['English'])}."
        + (" " + " ".join(extras) if extras else ""),
        "I would be happy to send my documents and to arrange a viewing.",
        "",
        "Kind regards",
    ]
    return "\n".join(lines)


def template_summary(listing: dict) -> str:
    facts = (listing.get("notes") or []) + (listing.get("reasons") or [])
    reasons = "; ".join(f"{r['title'].lower()} ({r['detail']})" for r in facts[:4])
    flags = listing.get("riskFlags") or []
    risk = f" Warning signs: {'; '.join(flags).lower()}." if flags else " No warning signs were found in the text."
    return (
        f"{listing.get('title')} in {listing.get('area')}. {listing.get('meta')} for {listing.get('rent')} per month. "
        f"{reasons.capitalize()}.{risk} A reply from the landlord is {(listing.get('replyLabel') or 'not rated').lower()}; risk {listing.get('risk')} %."
    )


def generate(kind: str, listing: dict, profile: dict) -> dict:
    if kind in ("title", "translate"):
        orig = listing.get("originalTitle") or listing.get("title") or ""
        trans = translate_title(orig)
        engine = OLLAMA_MODEL if available() else "template"
        return {"text": trans, "engine": engine}

    fallback = template_email(listing, profile) if kind == "email" else template_summary(listing)
    if not available():
        return {"text": fallback, "engine": "template"}

    if kind == "email":
        language = email_language(listing, profile)
        system = (
            "You write short, polite rental application e-mails for international students in Bern, Switzerland. "
            f"Write in {language}" + (" (Swiss Standard German: write 'ss', never 'ß')" if language == "German" else "") + ". "
            "Structure: greeting; one sentence saying you are interested in this specific listing (name its title and area); "
            "two or three sentences introducing the applicant using only the applicant facts; one sentence asking for a viewing "
            "and offering to send documents; a closing such as 'Kind regards' with no name after it. "
            "Never invent documents, income, names, dates or facts. No subject line, no placeholders in brackets. "
            "Maximum 130 words. Plain text."
        )
        user = f"Listing:\n{_listing_facts(listing)}\n\nApplicant:\n" + "\n".join(f"- {fact}" for fact in _profile_facts(profile))
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
        if kind == "email" and language == "German":
            text = text.replace("ß", "ss")  # Swiss Standard German
        return {"text": text, "engine": OLLAMA_MODEL}
    except (httpx.HTTPError, KeyError, ValueError):
        return {"text": fallback, "engine": "template"}
