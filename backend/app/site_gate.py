"""Developer password in front of the whole site, for an online test.

The password is one fixed password for the whole team, kept in backend/site_password.txt. Git
ignores that file, so the password never reaches the (public) GitHub repository; it exists only
on the laptop that runs the back-end. FLATTY_SITE_PASSWORD overrides the file. Without either,
there is no gate (another developer's laptop without the file).

When there is a password, every request (pages, API, files, /docs) needs the gate
cookie. Without it, pages get a small password page and /api answers 401. The correct
password sets an HttpOnly cookie for FLATTY_GATE_DAYS days. Student accounts (app/accounts.py)
keep working behind the gate; they are a separate log-in.

The cookie holds an expiry time and an HMAC of it, keyed with the password. So no session
table is needed, and changing the password logs everybody out.

Wrong passwords are slowed down: each costs a second, and after MAX_FAILURES within
LOCK_MINUTES from one address, that address has to wait.
"""

import asyncio
import hashlib
import hmac
import html
import os
import time
from pathlib import Path
from urllib.parse import parse_qs

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from .config import BACKEND_DIR, SECURE_COOKIES

# git-ignored: stays on this laptop. The online copy (start-online.sh) points here with
# FLATTY_SITE_PASSWORD_FILE, so both copies share one password file.
PASSWORD_FILE = Path(os.getenv("FLATTY_SITE_PASSWORD_FILE", BACKEND_DIR / "site_password.txt"))
PASSWORD = os.getenv("FLATTY_SITE_PASSWORD") or (
    PASSWORD_FILE.read_text(encoding="utf-8").strip() if PASSWORD_FILE.exists() else "")
ENABLED = bool(PASSWORD)
DAYS = float(os.getenv("FLATTY_GATE_DAYS", "7"))
COOKIE = "flatty_gate"
LOGIN_PATH = "/__gate"
LOGOUT_PATH = "/__gate/logout"
MAX_FAILURES = 5
LOCK_MINUTES = 15

_KEY = hashlib.sha256(f"flatty-site-gate:{PASSWORD}".encode()).digest()
_failures: dict[str, list[float]] = {}


def _sign(expires: int) -> str:
    return hmac.new(_KEY, str(expires).encode(), hashlib.sha256).hexdigest()


def make_cookie() -> str:
    expires = int(time.time() + DAYS * 86400)
    return f"{expires}.{_sign(expires)}"


def valid(value: str | None) -> bool:
    try:
        expires, signature = (value or "").split(".", 1)
        return int(expires) > time.time() and hmac.compare_digest(signature, _sign(int(expires)))
    except ValueError:
        return False


def _client(request: Request) -> str:
    """The visitor's address, for the lockout. Behind a tunnel (cloudflared, ngrok) every request
    comes from this machine and the tunnel passes the visitor's address on in a header. Anyone
    can send that header, so it is only believed when the request really comes from this machine."""
    direct = request.client.host if request.client else "unknown"
    if direct in ("127.0.0.1", "::1"):
        forwarded = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "")
        return forwarded.split(",")[0].strip() or direct
    return direct


def _locked(client: str) -> bool:
    cutoff = time.time() - LOCK_MINUTES * 60
    recent = [t for t in _failures.get(client, []) if t > cutoff]
    _failures[client] = recent
    return len(recent) >= MAX_FAILURES


def _secure(request: Request) -> bool:
    # A request that came through Vercel or the tunnel was https in the visitor's browser, even
    # if the tunnel doesn't say so; only a direct local request (development) is plain http.
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    proxied = bool(request.headers.get("x-forwarded-for") or request.headers.get("cf-connecting-ip"))
    return SECURE_COOKIES or request.url.scheme == "https" or forwarded == "https" or proxied


def _safe_next(path: str | None) -> str:
    # Only paths on this site: "//evil.example" would leave it.
    return path if path and path.startswith("/") and not path.startswith("//") and not path.startswith(LOGIN_PATH) else "/"


def page(next_path: str, message: str = "", status: int = 401) -> HTMLResponse:
    error = f'<p class="error" role="alert">{html.escape(message)}</p>' if message else ""
    return HTMLResponse(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>Flatty · Developer preview</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px 16px;
         background: #fff9f3; color: #4c2730; font-family: Manrope, system-ui, -apple-system, sans-serif; }}
  main {{ width: 100%; max-width: 380px; padding: 32px 28px; border: 1px solid #ead9d5; background: #fffdfa; }}
  .brand {{ display: flex; align-items: center; gap: 9px; font-size: 23px; font-weight: 700; letter-spacing: -.04em; }}
  .mark {{ display: grid; width: 31px; height: 31px; place-items: center; background: #e55242; color: #fff9f3;
          box-shadow: 3px 3px 0 #ffc857; font-size: 17px; }}
  .code {{ margin: 28px 0 6px; color: #e55242; font-family: "Space Mono", ui-monospace, monospace; font-size: 13px;
          font-weight: 700; letter-spacing: .13em; }}
  h1 {{ margin: 0 0 20px; font-size: 22px; letter-spacing: -.02em; }}
  label {{ display: block; margin-bottom: 7px; font-size: 14px; font-weight: 600; }}
  input {{ width: 100%; padding: 12px 13px; border: 1px solid #c9b6b2; background: #fff; color: inherit; font: inherit; font-size: 16px; }}
  input:focus {{ outline: 2px solid #e55242; outline-offset: 1px; }}
  button {{ width: 100%; margin-top: 16px; padding: 12px; border: 0; background: #e55242; color: #fff9f3;
           font: inherit; font-weight: 700; cursor: pointer; box-shadow: 3px 3px 0 #ffc857; }}
  .error {{ margin: 14px 0 0; padding: 10px 12px; background: #fff0b5; color: #6e5100; font-size: 14px; }}
  .note {{ margin: 18px 0 0; color: #89777a; font-size: 13px; }}
</style></head>
<body><main>
  <div class="brand"><span class="mark" aria-hidden="true">⌂</span>Flatty</div>
  <p class="code">DEVELOPER PREVIEW</p>
  <h1>Enter the admin password</h1>
  <form method="post" action="{LOGIN_PATH}">
    <input type="hidden" name="next" value="{html.escape(next_path)}">
    <label for="password">Password</label>
    <input id="password" name="password" type="password" autocomplete="current-password" required autofocus>
    <button type="submit">Continue</button>
  </form>
  {error}
  <p class="note">This test version is only open to the Flatty team.</p>
</main></body></html>""", status_code=status, headers={"Cache-Control": "no-store"})


class SiteGate(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        if path == LOGIN_PATH and request.method == "POST":
            form = parse_qs((await request.body()).decode("utf-8", "replace"))
            next_path = _safe_next((form.get("next") or ["/"])[0])
            client = _client(request)
            if _locked(client):
                return page(next_path, f"Too many wrong passwords. Try again in {LOCK_MINUTES} minutes.", status=429)
            password = (form.get("password") or [""])[0]
            if not hmac.compare_digest(password.encode(), PASSWORD.encode()):
                _failures.setdefault(client, []).append(time.time())
                await asyncio.sleep(1)
                return page(next_path, "That password isn't right.")
            _failures.pop(client, None)
            response = RedirectResponse(next_path, status_code=303)
            response.set_cookie(COOKIE, make_cookie(), max_age=int(DAYS * 86400), httponly=True,
                                secure=_secure(request), samesite="lax", path="/")
            return response

        if path == LOGOUT_PATH:
            response = RedirectResponse("/", status_code=303)
            response.delete_cookie(COOKIE, path="/")
            return response

        if path == LOGIN_PATH and valid(request.cookies.get(COOKIE)):
            return RedirectResponse(_safe_next(request.query_params.get("next")), status_code=303)

        if not valid(request.cookies.get(COOKIE)):
            if path.startswith("/api/"):
                return JSONResponse({"detail": {"code": "site_locked", "message": "Enter the developer password first."}},
                                    status_code=401, headers={"Cache-Control": "no-store"})
            if path == LOGIN_PATH:  # the app sends people here when its API calls are locked
                return page(_safe_next(request.query_params.get("next")))
            query = f"?{request.url.query}" if request.url.query else ""
            return page(_safe_next(path + query))

        response = await call_next(request)
        response.headers["X-Robots-Tag"] = "noindex, nofollow"  # keep the test version out of search engines
        return response
