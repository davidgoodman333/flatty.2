"""Text generation with a local LLM through Ollama (http://127.0.0.1:11434).

The model runs on this machine; nothing is sent to an external API. If Ollama is not
running, a template is used instead so the app keeps working.
"""

import re

import httpx

from .config import OLLAMA_MODEL, OLLAMA_URL


def available() -> bool:
    try:
        tags = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2).json()
        return any(model["name"] == OLLAMA_MODEL for model in tags.get("models", []))
    except (httpx.HTTPError, ValueError):
        return False


def _chat(system: str, user: str) -> str:
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
    return (
        f"Title: {listing.get('title')}\nArea: {listing.get('area')}, {listing.get('city') or 'Bern'}\n"
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
    lines = [
        "Hello,",
        "",
        f"I am interested in your listing “{listing.get('title')}” in {listing.get('area')}. "
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
    reasons = "; ".join(f"{r['title'].lower()} ({r['detail']})" for r in listing.get("reasons", [])[:4])
    flags = listing.get("riskFlags") or []
    risk = f" Warning signs: {'; '.join(flags).lower()}." if flags else " No warning signs were found in the text."
    return (
        f"{listing.get('title')} in {listing.get('area')}. {listing.get('meta')} for {listing.get('rent')} per month. "
        f"{reasons.capitalize()}.{risk} Match {listing.get('match')} %, risk {listing.get('risk')} %."
    )


def generate(kind: str, listing: dict, profile: dict) -> dict:
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
            f"{_listing_facts(listing)}\nMatch: {listing.get('match')} %\nScam risk: {listing.get('risk')} %\n"
            f"Why it fits: {[r['title'] + ' - ' + r['detail'] for r in listing.get('reasons', [])]}\n"
            f"Warning signs: {listing.get('riskFlags') or 'none'}"
        )
    try:
        text = _chat(system, user)
        if kind == "email" and language == "German":
            text = text.replace("ß", "ss")  # Swiss Standard German
        return {"text": text, "engine": OLLAMA_MODEL}
    except (httpx.HTTPError, KeyError, ValueError):
        return {"text": fallback, "engine": "template"}
