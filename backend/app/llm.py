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
from .translations import is_already_english, translate_property_title

_TRANSLATION_CACHE: dict[str, str] = {}


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
