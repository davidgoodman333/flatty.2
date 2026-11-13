"""Minimal robots.txt matcher following RFC 9309, including `*` and `$` wildcards.

(Python's urllib.robotparser ignores wildcards, which many Swiss listing sites use.)
"""

import re
from urllib.parse import urlparse

PRODUCT_TOKEN = "flattybot"


class Robots:
    def __init__(self, text: str):
        self.rules = self._parse(text)

    @staticmethod
    def _parse(text: str) -> list[tuple[bool, str]]:
        groups: dict[str, list[tuple[bool, str]]] = {}
        agents: list[str] = []
        in_rules = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            field, value = (part.strip() for part in line.split(":", 1))
            field = field.lower()
            if field == "user-agent":
                if in_rules:
                    agents, in_rules = [], False
                agents.append(value.lower())
                for agent in agents:
                    groups.setdefault(agent, [])
            elif field in ("allow", "disallow"):
                in_rules = True
                if value:
                    for agent in agents:
                        groups[agent].append((field == "allow", value))
        if PRODUCT_TOKEN in groups:
            return groups[PRODUCT_TOKEN]
        return groups.get("*", [])

    @staticmethod
    def _matches(pattern: str, path: str) -> bool:
        regex = re.escape(pattern).replace(r"\*", ".*")
        if regex.endswith(r"\$"):
            regex = regex[:-2] + "$"
        return re.match(regex, path) is not None

    def can_fetch(self, url: str) -> bool:
        parsed = urlparse(url)
        path = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
        best: tuple[int, bool] | None = None
        for allow, pattern in self.rules:
            if self._matches(pattern, path):
                candidate = (len(pattern), allow)
                # Longest match wins; on a tie, Allow wins (RFC 9309 §2.2.2).
                if best is None or candidate[0] > best[0] or (candidate[0] == best[0] and allow):
                    best = candidate
        return True if best is None else best[1]


ALLOW_ALL = Robots("")
DISALLOW_ALL = Robots("User-agent: *\nDisallow: /")
