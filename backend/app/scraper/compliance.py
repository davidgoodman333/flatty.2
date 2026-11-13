"""A polite HTTP client: robots.txt check, rate limit, request budget, honest user agent.

It never tries to get around bot protection. A 401/403 (for example a captcha or
DataDome block) stops the run instead of being retried with another identity.

The rate limit and the robots.txt cache are shared by every client in the process, so the
daily refresh, link checks and "is it still online?" checks together stay at one request
per host every MIN_REQUEST_INTERVAL seconds.
"""

import threading
import time
from urllib.parse import urlparse

import httpx

from ..config import MAX_REQUESTS_PER_RUN, MIN_REQUEST_INTERVAL, USER_AGENT
from .robots import ALLOW_ALL, DISALLOW_ALL, Robots


class ScrapeBlocked(Exception):
    """The site refused us or robots.txt disallows the URL. Stop, don't work around it."""


class BudgetExhausted(Exception):
    pass


ROBOTS_TTL = 24 * 3600  # re-read robots.txt once a day


class PoliteClient:
    _lock = threading.Lock()
    _last_request: dict[str, float] = {}  # shared by all clients
    _robots: dict[str, tuple[float, Robots]] = {}  # origin -> (fetched at, rules)

    def __init__(self, max_requests: int = MAX_REQUESTS_PER_RUN, interval: float = MIN_REQUEST_INTERVAL):
        self.client = httpx.Client(headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/html"}, timeout=30, follow_redirects=True)
        self.max_requests = max_requests
        self.interval = interval
        self.requests = 0

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _wait(self, host: str) -> None:
        # Reserve the next free slot for this host under the lock, then sleep outside it.
        with self._lock:
            slot = max(time.monotonic(), self._last_request.get(host, 0) + self.interval)
            self._last_request[host] = slot
        time.sleep(max(0.0, slot - time.monotonic()))

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        cached = self._robots.get(origin)
        if cached is None or time.monotonic() - cached[0] > ROBOTS_TTL:
            self._wait(parsed.netloc)
            try:
                response = self.client.get(f"{origin}/robots.txt")
            except httpx.HTTPError:
                response = None
            if response is None or response.status_code >= 500:
                rules = DISALLOW_ALL  # Unreachable: assume complete disallow (RFC 9309 §2.3.1.4).
            elif response.status_code >= 400:
                rules = ALLOW_ALL  # No robots.txt: everything allowed.
            else:
                rules = Robots(response.text)
            self._robots[origin] = cached = (time.monotonic(), rules)
        return cached[1].can_fetch(url)

    def get(self, url: str, params: dict | list | None = None, missing_ok: bool = False) -> httpx.Response:
        """GET politely. With missing_ok, a 404/410 is returned instead of raised (used to
        detect listings that were taken offline)."""
        full_url = str(httpx.URL(url, params=params))
        if not self.allowed(full_url):
            raise ScrapeBlocked(f"robots.txt disallows {full_url}")
        if self.requests >= self.max_requests:
            raise BudgetExhausted(f"request budget of {self.max_requests} used up")

        for attempt in range(3):
            self._wait(urlparse(full_url).netloc)
            self.requests += 1
            response = self.client.get(full_url)
            if response.status_code in (401, 403):
                raise ScrapeBlocked(f"{response.status_code} from {urlparse(full_url).netloc}: access refused, stopping")
            if response.status_code == 429 or response.status_code >= 500:
                retry_after = response.headers.get("Retry-After", "")
                time.sleep(min(int(retry_after) if retry_after.isdigit() else 10 * (attempt + 1), 120))
                continue
            if missing_ok and response.status_code in (404, 410):
                return response
            response.raise_for_status()
            return response
        raise ScrapeBlocked(f"{full_url} kept failing (rate limited or server errors), stopping")
