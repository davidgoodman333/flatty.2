"""Multilingual (de/fr/it/en) text signals used by the models and for explanations."""

import re

STOPWORDS = {
    "German": {"und", "die", "der", "das", "mit", "ist", "wir", "sie", "für", "eine", "zimmer", "wohnung", "nicht", "auf", "im"},
    "English": {"the", "and", "with", "is", "for", "you", "room", "flat", "apartment", "are", "this", "we", "in", "to"},
    "French": {"le", "la", "les", "et", "avec", "est", "pour", "une", "appartement", "nous", "vous", "dans", "des"},
    "Italian": {"il", "che", "con", "per", "una", "appartamento", "sono", "della", "nel", "gli", "camera"},
}

# Each red flag: (key, user-facing explanation, pattern). Patterns are deliberately
# simple and multilingual; the classifier learns how much each one matters.
RED_FLAGS = [
    (
        "deposit_before_viewing",
        "Asks for a deposit or payment before a viewing",
        r"(kaution|depot|deposit|caution|anzahlung|vorauszahlung|vorkasse|first month).{0,100}"
        r"(vor der besichtigung|vorab|im voraus|in advance|before (the )?(viewing|visit|keys)|avant (la )?visite|überweis|transfer|virement)",
    ),
    (
        "no_viewing",
        "No viewing offered or the owner is abroad",
        r"(keine besichtigung|besichtigung (ist )?nicht möglich|no viewings?|cannot show|can't show|not possible to visit|"
        r"(bin|wohne|lebe|befinde mich|arbeite) (zurzeit |derzeit |momentan |beruflich )?im ausland\b|i am (currently )?(abroad|overseas|in (the )?uk|in london)|"
        r"je (suis|vis|travaille) .{0,25}(à|a) l['’ ]?étranger|können (wir|ich) (leider )?nicht nach bern kommen|"
        r"schlüssel (werden |wird )?(per post|per kurier|zugeschickt|versendet)|keys? (will be )?(sent|mailed|posted|shipped)|clés .{0,30}(envoyées|par la poste))",
    ),
    (
        "off_platform_contact",
        "Pushes contact off the platform (WhatsApp, private e-mail)",
        r"(whatsapp|telegram|signal app|@gmail\.|@hotmail\.|@yahoo\.|@outlook\.|@gmx\.|contact me (directly )?(at|by|via)|"
        r"schreiben sie mir (direkt )?(an|per|auf)|kontaktieren sie mich (direkt )?(per|unter|über)|écrivez-moi)",
    ),
    (
        "payment_service",
        "Mentions a risky payment channel",
        r"(western union|moneygram|bitcoin|crypto|paysafe|gift ?card|airbnb.{0,40}(zahlung|payment|paiement|kaution|deposit)|"
        r"(zahlung|payment|paiement|kaution|caution|deposit|dépôt).{0,40}airbnb|treuhand.{0,30}(agentur|service)|escrow)",
    ),
    (
        "urgency",
        "Creates time pressure",
        r"(sehr dringend|first come,? first served|nur heute|only today|act fast|schnell entscheiden|sofort überweisen|urgent)",
    ),
]

STUDENT_PATTERN = re.compile(
    r"(student|studierend|studentin|studenten|étudiant|studente|uni(versität|versity)?\b|wg[- ]tauglich|azubi|praktikant|intern)",
    re.IGNORECASE,
)


def detect_language(text: str) -> str:
    words = re.findall(r"[a-zà-ÿäöü]+", (text or "").lower())
    if not words:
        return "Unknown"
    scores = {language: sum(word in stop for word in words) for language, stop in STOPWORDS.items()}
    language, score = max(scores.items(), key=lambda item: item[1])
    return language if score >= 2 else "Unknown"


def red_flags(text: str) -> list[str]:
    lowered = (text or "").lower()
    return [key for key, _, pattern in RED_FLAGS if re.search(pattern, lowered)]


FLAG_LABELS = {key: label for key, label, _ in RED_FLAGS}


def mentions_students(text: str) -> bool:
    return bool(STUDENT_PATTERN.search(text or ""))


def parse_number(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    raw = match.group(1).replace("'", "").replace("’", "").replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def listing_from_text(text: str) -> dict:
    """Extract the basic facts from listing text pasted by the user."""
    price = parse_number(r"(?:chf|fr\.?)\s*([\d'’ ]{3,7})", text) or parse_number(r"([\d'’]{3,6})\s*(?:chf|fr\.?)", text)
    rooms = parse_number(r"(\d(?:[.,]5)?)\s*(?:-?\s*)(?:zimmer|zi\.?|rooms?|pièces|locali)", text)
    surface = parse_number(r"(\d{2,3})\s*(?:m2|m²|qm)", text)
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "Pasted listing")
    first_line = re.split(r"(?<=[.!?])\s|,\s*(?=chf|fr\.)", first_line, maxsplit=1, flags=re.IGNORECASE)[0].rstrip(".")
    is_shared = bool(re.search(r"\b(wg|shared flat|colocation|wg-zimmer|zimmer in)\b", text, re.IGNORECASE))
    return {
        "title": first_line[:90],
        "description": text,
        "price": price,
        "rooms": rooms if not is_shared else 1.0,
        "surface": surface,
        "category": "SHARED" if is_shared else "APARTMENT",
        "object_type": "SHARED_FLAT" if is_shared else "APARTMENT",
        "is_private": not re.search(r"\b(ag|gmbh|verwaltung|immobilien|régie|treuhand)\b", text, re.IGNORECASE),
        "is_furnished": bool(re.search(r"(möbliert|furnished|meublé|arredato)", text, re.IGNORECASE)),
        "is_temporary": bool(re.search(r"(befristet|temporary|temporaire|untermiete|sublet)", text, re.IGNORECASE)),
    }
