"""Loads backend/rules.toml: the weights, thresholds, scanned phrases and AI instructions behind
the risk and reply scores. Everything that decides a score is in that file, with a note on what
it does; the code only says how the rules are applied.

The file is read once at start-up. FLATTY_RULES points to another file (for experiments).
"""

import os
import tomllib
from pathlib import Path

from .config import BACKEND_DIR

RULES_PATH = Path(os.getenv("FLATTY_RULES", BACKEND_DIR / "rules.toml"))
RULES = tomllib.loads(RULES_PATH.read_text(encoding="utf-8"))

RISK = RULES["risk"]
REPLY = RULES["reply"]
WISHES = RULES["ai"]["wishes"]


def pattern(alternatives: list[str]) -> str:
    """One regular expression from a list of alternatives: any one of them is enough."""
    return "|".join(f"(?:{alternative})" for alternative in alternatives)


def require(section: dict, keys: list[str], where: str) -> None:
    """Stop at start-up with a clear message if the file lacks a rule the code needs."""
    missing = [key for key in keys if key not in section]
    if missing:
        raise RuntimeError(f"{RULES_PATH.name}: [{where}] is missing {', '.join(missing)}")
