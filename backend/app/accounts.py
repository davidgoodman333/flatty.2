"""Accounts: sign-up, log-in and the session cookie.

Passwords are stored as scrypt hashes, never in clear text. A session is a random token in an
HttpOnly cookie; the database only keeps its SHA-256 hash, so a copy of the database can't be
used to log in as someone.

Private test: when FLATTY_ALLOWED_EMAILS or FLATTY_INVITE_CODE is set, only invited people can
create an account, and every data endpoint needs a log-in (`guard`).
"""

import base64
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import db
from .config import ALLOWED_EMAILS, INVITE_CODE, PRIVATE, SECURE_COOKIES, SESSION_DAYS
from .site_gate import ENABLED as SITE_GATE

COOKIE = "flatty_session"
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Failed attempts per key (an e-mail address, or "register"), to slow down guessing.
MAX_FAILURES, FAILURE_WINDOW = 8, 15 * 60
_failures: dict[str, list[float]] = {}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return "$".join(["scrypt", str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P), base64.b64encode(salt).decode(), base64.b64encode(digest).decode()])


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Checked when the e-mail is unknown, so a wrong e-mail takes as long as a wrong password.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _throttled(key: str) -> bool:
    recent = [stamp for stamp in _failures.get(key, []) if time.monotonic() - stamp < FAILURE_WINDOW]
    _failures[key] = recent
    return len(recent) >= MAX_FAILURES


def _failed(key: str) -> None:
    _failures.setdefault(key, []).append(time.monotonic())


def current_user(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    with db.connect() as conn:
        return db.user_for_session(conn, _token_hash(token))


def require_user(user: dict | None = Depends(current_user)) -> dict:
    if user is None:
        raise _error(401, "login_required", "Please log in.")
    return user


def guard(user: dict | None = Depends(current_user)) -> None:
    """For data endpoints: open on a local machine, log-in only during a private test."""
    if PRIVATE and user is None:
        raise _error(401, "login_required", "Flatty is in a private test. Please log in.")


def _start_session(request: Request, response: Response, user_id: int) -> None:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    with db.connect() as conn:
        db.delete_expired_sessions(conn)
        db.create_session(conn, user_id, _token_hash(token), expires.isoformat(timespec="seconds"))
    # Behind a tunnel or reverse proxy the request arrives as http; the browser used https.
    https = (SECURE_COOKIES or request.url.scheme == "https"
             or request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"
             or bool(request.headers.get("x-forwarded-for")))  # came through Vercel or the tunnel
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", secure=https, path="/")


def public_user(user: dict) -> dict:
    return {
        "email": user["email"],
        "profile": user["profile"],
        "filters": user["filters"],
        "sort": user["sort"],
        "createdAt": user["created_at"],
    }


def session_info(user: dict | None) -> dict:
    return {"user": public_user(user) if user else None, "private": PRIVATE, "inviteRequired": bool(INVITE_CODE),
            "siteGate": SITE_GATE}  # behind the developer password (app/site_gate.py): the app offers "Lock site"


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class Registration(Credentials):
    inviteCode: str = Field("", max_length=200)


router = APIRouter(prefix="/api/auth")


@router.get("/me")
def me(user: dict | None = Depends(current_user)):
    return session_info(user)


@router.post("/register", status_code=201)
def register(body: Registration, request: Request, response: Response):
    email = body.email.strip().lower()
    if not EMAIL_PATTERN.match(email):
        raise _error(400, "bad_email", "Please enter a valid e-mail address.")
    if len(body.password) < 8:
        raise _error(400, "weak_password", "Please choose a password with at least 8 characters.")
    if _throttled("register"):
        raise _error(429, "too_many_attempts", "Too many attempts. Please try again in 15 minutes.")
    if ALLOWED_EMAILS and email not in ALLOWED_EMAILS:
        _failed("register")
        raise _error(403, "not_invited", "Flatty is in a private test. Only invited e-mail addresses can create an account.")
    if INVITE_CODE and not hmac.compare_digest(body.inviteCode.strip().encode(), INVITE_CODE.encode()):
        _failed("register")
        raise _error(403, "bad_invite", "That invite code isn't right.")
    taken = _error(409, "email_taken", "There is already an account with this e-mail address. Log in instead.")
    try:
        with db.connect() as conn:
            if db.user_by_email(conn, email):
                raise taken
            user_id = db.create_user(conn, email, hash_password(body.password))
    except sqlite3.IntegrityError:  # the same e-mail was registered at the same moment
        raise taken
    _start_session(request, response, user_id)
    with db.connect() as conn:
        return session_info(db.user_by_id(conn, user_id))


@router.post("/login")
def login(body: Credentials, request: Request, response: Response):
    email = body.email.strip().lower()
    if _throttled(email):
        raise _error(429, "too_many_attempts", "Too many attempts. Please try again in 15 minutes.")
    with db.connect() as conn:
        user = db.user_by_email(conn, email)
    correct = verify_password(body.password, user["password_hash"] if user else _DUMMY_HASH)
    # Someone removed from the invite list can't log in any more.
    if not user or not correct or (ALLOWED_EMAILS and email not in ALLOWED_EMAILS):
        _failed(email)
        raise _error(401, "bad_credentials", "Wrong e-mail address or password.")
    _failures.pop(email, None)
    _start_session(request, response, user["id"])
    return session_info(user)


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        with db.connect() as conn:
            db.delete_session(conn, _token_hash(token))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.post("/delete-account")
def delete_account(response: Response, user: dict = Depends(require_user)):
    """Erases the account with its profile, saved homes and sessions."""
    with db.connect() as conn:
        db.delete_user(conn, user["id"])
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}
