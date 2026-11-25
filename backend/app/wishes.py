"""Who the landlord or the flatmates are looking for, read from the listing text by the local LLM.

A listing can say "Schweizerdeutsch als Muttersprache", "Mitbewohnerin gesucht (18-28)",
"nur Berufstätige" or "Nichtraucher vorausgesetzt". Fixed keyword rules can't tell such a wish
from a sentence about the current flatmates ("Ich spreche Italienisch, Schweizerdeutsch
verstehe ich teilweise"), so the LLM decides, in three guarded steps:

1. Only sentences that mention a topic at all (language, gender, age, occupation, smoking) go to
   the model. A listing without such a sentence has no wishes and costs no LLM call.
2. The model labels each wish with the number of the sentence that states it.
3. A wish is kept only if that sentence really is about its topic (the same patterns as step 1;
   a language must be named, an age range must be written out), and if the model, asked once
   more about that one sentence alone, confirms it is a wish and not a fact about the flatmates.

`assess` compares the wishes with the student's profile. Language and occupation are known
(everyone using Flatty is a student), so they change the reply likelihood. Gender, age and
smoking aren't in the profile; they're shown to the student but not scored.

Runs in the background (app/llm_worker.py), never during a search.
"""

import json
import re

try:
    import httpx
except ImportError:
    httpx = None

from .config import OLLAMA_MODEL, OLLAMA_URL
from .rules import REPLY, WISHES, pattern, require

# Everything below comes from rules.toml [ai.wishes]: the topics, the language names, both
# prompts and the version. Bump the version there after a change: stored wishes are read again.
VERSION = WISHES["version"]
TOPICS = {topic: pattern(alternatives) for topic, alternatives in WISHES["topics"].items()}
require(TOPICS, ["language", "gender", "age", "occupation", "non_smoker"], "ai.wishes.topics")
_TOPIC_RE = {topic: re.compile(p, re.IGNORECASE) for topic, p in TOPICS.items()}
_ANY_TOPIC = re.compile(pattern(list(TOPICS.values())), re.IGNORECASE)

LANGUAGES = WISHES["languages"]
ALIASES = WISHES.get("language_aliases", {})  # "Swiss German" -> "German"


def same_language(name: str) -> str:
    return ALIASES.get(name, name)


# A language wish must name the language in its own sentence.
LANGUAGE_NAMES = {language: pattern(names) for language, names in WISHES["language_names"].items()}
require(LANGUAGE_NAMES, LANGUAGES, "ai.wishes.language_names")
MAX_SENTENCES = WISHES["max_sentences"]

SYSTEM = WISHES["prompt"]["text"].strip()
VERIFY_SYSTEM = WISHES["verify_prompt"]["text"].strip()

SCHEMA = {
    "type": "object",
    "properties": {"wishes": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "sentence": {"type": "integer"},
            "topic": {"type": "string", "enum": list(TOPICS)},
            "languages": {"type": "array", "items": {"type": "string", "enum": LANGUAGES}},
            "gender": {"type": ["string", "null"], "enum": ["female", "male", None]},
            "age_min": {"type": ["integer", "null"]},
            "age_max": {"type": ["integer", "null"]},
            "occupation": {"type": ["string", "null"], "enum": ["students", "working", "weekly_commuters", "no_students", None]},
            "strength": {"type": "string", "enum": ["required", "preferred"]},
        },
        "required": ["sentence", "topic", "strength"],
    }}},
    "required": ["wishes"],
}


def sentences(listing: dict) -> list[str]:
    """Title and description split into sentences and list items."""
    text = f"{listing.get('title') or ''}\n{listing.get('description') or ''}"
    text = re.sub(r"[*_\\#>]+", " ", text)  # Markdown
    parts = re.split(r"\n+|(?<=[.!?])\s+|\s+[•·]\s+", text)
    return [re.sub(r"\s+", " ", part).strip(" -–•·")[:300] for part in parts if part.strip(" -–•·")]


def candidates(listing: dict) -> list[str]:
    return [s for s in sentences(listing) if _ANY_TOPIC.search(s)][:MAX_SENTENCES]


def _ask(numbered: str) -> list[dict]:
    response = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL, "stream": False, "think": False, "format": SCHEMA,
            "options": {"temperature": 0, "num_predict": 500, "num_ctx": 4096},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": numbered}],
        },
        timeout=90,
    )
    response.raise_for_status()
    return json.loads(response.json()["message"]["content"]).get("wishes") or []


def _clean(raw: dict, found: list[str]) -> dict | None:
    """One wish from the model, checked against its sentence; None if it doesn't hold up."""
    topic, index = raw.get("topic"), raw.get("sentence")
    if topic not in TOPICS or not isinstance(index, int) or not 1 <= index <= len(found):
        return None
    quote = found[index - 1]
    if not _TOPIC_RE[topic].search(quote):
        return None
    wish = {"topic": topic, "strength": "required" if raw.get("strength") == "required" else "preferred", "quote": quote}
    if topic == "language":
        languages = [same_language(l) for l in raw.get("languages") or []]
        languages = [l for l in languages if l in LANGUAGES and re.search(LANGUAGE_NAMES[l], quote, re.IGNORECASE)]
        if not languages:
            return None
        wish["languages"] = sorted(set(languages), key=LANGUAGES.index)
    elif topic == "gender":
        if raw.get("gender") not in ("female", "male"):
            return None
        wish["gender"] = raw["gender"]
    elif topic == "age":
        low, high = raw.get("age_min"), raw.get("age_max")
        low = low if isinstance(low, int) and 16 <= low <= 99 else None
        high = high if isinstance(high, int) and 16 <= high <= 99 else None
        numbers = {int(n) for n in re.findall(r"\d{2}", quote)}
        # "about my age" is no range: the numbers must be in the sentence itself.
        if (low is None and high is None) or any(n is not None and n not in numbers for n in (low, high)):
            return None
        wish.update(age_min=low, age_max=high)
    elif topic == "occupation":
        if raw.get("occupation") not in ("students", "working", "weekly_commuters", "no_students"):
            return None
        wish["occupation"] = raw["occupation"]
    return wish


def _claim(wish: dict) -> str:
    """The wish as a plain statement, for the yes/no check."""
    topic = wish["topic"]
    if topic == "language":
        return f"The new tenant should speak {_language_list(wish['languages'])}."
    if topic == "gender":
        return f"The new tenant should be a {'woman' if wish['gender'] == 'female' else 'man'}."
    if topic == "age":
        return f"The new tenant should be {_age_title(wish).removeprefix('Looking for someone ')}."
    if topic == "non_smoker":
        return "The new tenant must not smoke, or the flat is non-smoking."
    return {
        "students": "Students are welcome as the new tenant.",
        "working": "The new tenant should be someone who works (is employed).",
        "weekly_commuters": "The room is meant for weekly residents or commuters.",
        "no_students": "Students are not wanted as the new tenant.",
    }[wish["occupation"]]


def _confirmed(wish: dict) -> bool:
    response = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL, "stream": False, "think": False,
            "format": {"type": "object", "properties": {"answer": {"type": "string", "enum": ["yes", "no"]}}, "required": ["answer"]},
            "options": {"temperature": 0, "num_predict": 20},
            "messages": [
                {"role": "system", "content": VERIFY_SYSTEM},
                {"role": "user", "content": f"Sentence: «{wish['quote']}»\nStatement: {_claim(wish)}\nDoes the sentence say this about the new tenant?"},
            ],
        },
        timeout=60,
    )
    response.raise_for_status()
    return json.loads(response.json()["message"]["content"]).get("answer") == "yes"


def extract(listing: dict) -> list[dict] | None:
    """The listing's wishes; [] if it states none; None if the LLM couldn't be reached."""
    found = candidates(listing)
    if not found:
        return []
    if httpx is None:
        return None
    numbered = "\n".join(f"{i}. {sentence}" for i, sentence in enumerate(found, 1))
    try:
        raw = _ask(numbered)
    except Exception:
        return None
    wishes, seen = [], set()
    for item in raw:
        wish = _clean(item, found) if isinstance(item, dict) else None
        key = json.dumps(wish, sort_keys=True) if wish else None
        if wish and key not in seen:
            seen.add(key)
            wishes.append(wish)
    try:
        return [wish for wish in wishes if _confirmed(wish)]
    except Exception:
        return None


# --- Comparing with the student -----------------------------------------------------

STRENGTH_VALUE = {"required": REPLY["strength"]["required"], "preferred": REPLY["strength"]["preferred"]}


def profile_languages(profile: dict) -> set[str]:
    return {same_language(language) for language in profile.get("languages") or []}


def _language_list(languages: list[str]) -> str:
    return languages[0] if len(languages) == 1 else f"{', '.join(languages[:-1])} or {languages[-1]}"


def _gender_title(wish: dict) -> str:
    return "Looking for a woman" if wish["gender"] == "female" else "Looking for a man"


def _age_title(wish: dict) -> str:
    low, high = wish.get("age_min"), wish.get("age_max")
    if low and high:
        return f"Looking for someone aged {low}–{high}"
    return f"Looking for someone aged {low} or older" if low else f"Looking for someone aged {high} or younger"


OCCUPATION_TITLES = {
    "students": "Students welcome",
    "working": "Looking for someone who works",
    "weekly_commuters": "Meant for weekly commuters",
    "no_students": "No students",
}


def assess(wishes: list[dict] | None, profile: dict) -> dict:
    """What the wishes mean for this student.

    features   strengths (0, 0.6 or 1) for the quality model's wish features
    overrides  title and detail for those features, naming the listing's own words
    shown      every wish for the "Who they're looking for" list: fit is yes, no or unknown
    """
    features = {"language_wish_unmet": 0.0, "language_wish_met": 0.0, "not_for_students": 0.0, "students_welcome": 0.0}
    overrides: dict[str, tuple[str, str]] = {}
    shown = []
    languages = profile_languages(profile)
    for wish in wishes or []:
        value, said = STRENGTH_VALUE[wish["strength"]], f"The listing says: “{wish['quote']}”"
        strength = "required" if wish["strength"] == "required" else "preferred"
        topic = wish["topic"]
        if topic == "language":
            # Wishes stored before Swiss German counted as German may still name it.
            asked = list(dict.fromkeys(same_language(language) for language in wish["languages"]))
            wanted = _language_list(asked)
            title = f"Asks for {wanted}"
            if any(language in languages for language in asked):
                fit, name = "yes", "language_wish_met"
                detail = f"You speak {wanted}. {said}"
            else:
                fit, name = "no", "language_wish_unmet"
                detail = f"You haven't said you speak {wanted}. {said}"
            if value >= features[name]:
                features[name] = value
                overrides[name] = (title, detail)
        elif topic == "occupation":
            title = OCCUPATION_TITLES[wish["occupation"]]
            if wish["occupation"] == "students":
                fit, name = "yes", "students_welcome"
            else:
                fit, name = "no", "not_for_students"
            if value >= features[name]:
                features[name] = value
                overrides[name] = (title, said)
        else:
            title = {"gender": _gender_title, "age": _age_title}.get(topic, lambda _: "Non-smokers only")(wish)
            fit = "unknown"  # not part of the profile, so not part of the score
        same = next((item for item in shown if item["title"] == title), None)
        if same is None:
            shown.append({"topic": topic, "title": title, "quote": wish["quote"], "strength": strength, "fit": fit})
        elif strength == "required" and same["strength"] == "preferred":  # said twice: keep the stronger
            same.update(quote=wish["quote"], strength=strength)
    # A listing for students isn't also "not for students": the clearer statement wins.
    if features["students_welcome"] and features["not_for_students"]:
        weaker = "not_for_students" if features["students_welcome"] >= features["not_for_students"] else "students_welcome"
        features[weaker] = 0.0
    return {"features": features, "overrides": overrides, "shown": shown}
