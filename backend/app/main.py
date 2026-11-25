"""Flatty API.

    uvicorn app.main:app --reload --port 8000
"""

import hashlib
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import accounts, db, llm, llm_worker, refresher, site_gate, wishes
from .config import RECHECK_MINUTES, STATIC_DIR
from .matching import card, search
from .ml.features import market_stats
from .ml.models import QualityModel
from .ml.models import load_risk_model
from .scoring import assess
from .scraper import flatfox, unibe
from .scraper.compliance import PoliteClient, ScrapeBlocked
from .scraper.sources import SOURCES, source_for_url
from .text import listing_from_text

@asynccontextmanager
async def lifespan(_app: FastAPI):
    refresher.start()  # daily automatic refresh (FLATTY_AUTO_REFRESH=0 turns it off)
    llm_worker.start()  # landlord wishes and English titles from the local LLM, in the background
    yield
    llm_worker.stop()
    refresher.stop()


app = FastAPI(title="Flatty API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)
# Developer password in front of everything (pages, API, files) when FLATTY_SITE_PASSWORD is set.
# Added last, so it runs first.
if site_gate.ENABLED:
    app.add_middleware(site_gate.SiteGate)
app.include_router(accounts.router)
# During a private test (see config.PRIVATE) these endpoints need a log-in.
GUARDED = [Depends(accounts.guard)]
SORT_PATTERN = "^(reply|price_asc|price_desc|newest|risk|commute|size)$"
MAX_SAVED = 200  # saved homes per account
MAX_SNAPSHOT_BYTES = 40_000


class Profile(BaseModel):
    name: str = ""  # only used to sign application e-mails
    languages: list[str] = ["English"]
    budget: float = 1800
    areas: list[str] = []
    destination: str = "University of Bern"
    priorities: list[str] = []
    country: str = ""
    hasGuarantor: str = ""
    hasViewingPerson: str = ""
    hasSwissNumber: str = ""
    hasSwissBank: str = ""
    hasResidencePermit: str = ""
    apartmentTypes: list[str] = []


class Filters(BaseModel):
    sources: list[str] = []
    priceMin: float | None = None
    priceMax: float | None = None
    roomsMin: float | None = None
    surfaceMin: float | None = None
    types: list[str] = []
    features: list[str] = []
    maxRisk: int | None = None
    rental: str = Field("any", pattern="^(any|permanent|temporary)$")
    withPhotos: bool = False
    availableBy: str | None = None  # the student needs the home from this date
    neededUntil: str | None = None  # ... until this date (empty = open-ended)
    # Area on the map: only listings within radiusKm of this point.
    areaLat: float | None = Field(None, ge=45.0, le=48.5)
    areaLng: float | None = Field(None, ge=5.5, le=11.0)
    radiusKm: float = Field(2.0, gt=0, le=50)


class MatchRequest(BaseModel):
    profile: Profile
    filters: Filters = Filters()
    sort: str = Field("reply", pattern=SORT_PATTERN)
    offset: int = Field(0, ge=0)
    limit: int = Field(30, ge=1, le=200)


class CheckRequest(BaseModel):
    profile: Profile
    url: str | None = None
    text: str | None = None


class GenerateRequest(BaseModel):
    kind: str = Field(pattern="^(email|summary|title)$")
    listing: dict
    profile: Profile
    language: str | None = Field(None, pattern="^(English|German)$")  # e-mails only


class TranslateTitleRequest(BaseModel):
    title: str


class PreferencesRequest(BaseModel):
    profile: Profile
    filters: Filters = Filters()
    sort: str = Field("reply", pattern=SORT_PATTERN)


class SaveRequest(BaseModel):
    listing: dict


def _load() -> tuple[list[dict], dict, dict | None]:
    with db.connect() as conn:
        listings = db.all_listings(conn)
        return listings, market_stats(listings), db.last_run(conn)


@app.get("/api/health")
def health():
    listings, market, last_run = _load()
    risk_model = load_risk_model()
    risk_version = risk_model.version if risk_model else "rules-v0 (model not trained yet)"
    return {
        "ok": True,
        "listings": len(listings),
        "lastScrape": last_run,
        "freshness": refresher.freshness(),
        "riskModel": risk_version,
        "qualityModel": QualityModel().version,
        "llm": {"model": llm.OLLAMA_MODEL, "available": llm.available()},
        # Listings whose landlord wishes the LLM hasn't read yet (None until the worker's first round).
        "wishesPending": llm_worker.state["wishes_pending"],
    }


@app.get("/api/sources", dependencies=GUARDED)
def sources():
    with db.connect() as conn:
        counts = dict(conn.execute("SELECT source, COUNT(*) FROM listings GROUP BY source").fetchall())
    return [{**source.public(), "listings": counts.get(source.key, 0)} for source in SOURCES if source.key != "other"]


@app.post("/api/match", dependencies=GUARDED)
def match(request: MatchRequest):
    listings, market, last_run = _load()
    result = search(
        listings, request.profile.model_dump(), market, request.filters.model_dump(),
        request.sort, request.offset, request.limit,
    )
    fresh = refresher.freshness()
    return {**result, "updatedAt": fresh["updatedAt"], "refreshing": fresh["refreshing"], "nextRefresh": fresh["nextRefresh"]}


def _gone(source_name: str) -> dict:
    return {
        "available": False,
        "checkedAt": db.now_iso(),
        "message": f"This listing is no longer online on {source_name}. It was probably rented or withdrawn.",
    }


@app.get("/api/listings/{listing_id:path}/check", dependencies=GUARDED)
def check_listing(listing_id: str):
    """Is this listing still online at its source? Checked with one request, at most once an hour."""
    with db.connect() as conn:
        listing = db.get_listing(conn, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail={"code": "unknown", "message": "Flatty doesn't know this listing."})
    source = next((s for s in SOURCES if s.key == listing["source"]), None)
    name = source.name if source else "the website"
    if not listing.get("active", True):
        return {**_gone(name), "checkedAt": listing.get("last_checked") or listing.get("inactive_since")}
    if listing["source"] == "studentlodge":
        return {"available": None, "message": "studentlodge lists room types; availability is confirmed when you book."}
    last = listing.get("last_checked")
    if last and datetime.now(timezone.utc) - datetime.fromisoformat(last) < timedelta(minutes=RECHECK_MINUTES):
        return {"available": True, "checkedAt": last, "cached": True}

    try:
        with PoliteClient(max_requests=2) as client:
            if listing["source"] == "flatfox":
                raw = flatfox.fetch_one(client, int(listing["source_id"]))
                online, fresh = flatfox.is_active(raw), (flatfox.normalise(raw) if raw else None)
            elif listing["source"] == "unibe":
                online, fresh = unibe.check(client, listing["url"])
            else:
                return {"available": None, "message": "This website can't be re-checked automatically."}
    except Exception as error:  # blocked, network trouble: say so instead of guessing
        return {"available": None, "message": f"Couldn't check right now ({type(error).__name__})."}

    with db.connect() as conn:
        if not online:
            db.mark_inactive(conn, listing_id)
            return _gone(name)
        if fresh and (listing["source"] != "flatfox" or flatfox.is_relevant(fresh)):
            db.upsert_listing(conn, fresh)  # keep price and details current
        db.mark_checked(conn, listing_id)
    return {"available": True, "checkedAt": db.now_iso()}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def _blocked(code: str, message: str, source: str):
    raise HTTPException(status_code=451, detail={"code": code, "message": message, "source": source})


@app.post("/api/check-link", dependencies=GUARDED)
def check_link(request: CheckRequest):
    profile = request.profile.model_dump()
    stored, market, _ = _load()

    if request.text and request.text.strip():
        # The id comes from the text, so two pasted listings can be saved side by side.
        digest = hashlib.sha256(request.text.strip().encode()).hexdigest()[:16]
        listing = {**listing_from_text(request.text), "id": f"pasted:{digest}", "source": "pasted", "url": ""}
    elif request.url and request.url.strip():
        url = request.url.strip()
        if not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail={"code": "bad_url", "message": "Please paste a full link starting with https://"})
        source = source_for_url(url)
        if not source.link_check_allowed:
            _blocked(
                "source_blocked",
                f"{source.name}'s terms don't allow automated reading of their pages, so Flatty won't open this link. "
                "Copy the listing text from the page and paste it below instead.",
                source.name,
            )
        try:
            with PoliteClient(max_requests=2) as client:
                if source.key == "flatfox":
                    pk = flatfox.pk_from_url(url)
                    if not pk:
                        raise HTTPException(status_code=400, detail={"code": "bad_url", "message": "This doesn't look like a Flatfox listing link."})
                    raw = flatfox.fetch_one(client, pk)
                    if not flatfox.is_active(raw):
                        raise HTTPException(status_code=410, detail={"code": "listing_inactive", "message": "This Flatfox listing is no longer online. It was probably rented or withdrawn."})
                    listing = flatfox.normalise(raw)
                elif source.key == "unibe":
                    online, parsed = unibe.check(client, url)
                    if not online:
                        raise HTTPException(status_code=410, detail={"code": "listing_inactive", "message": "This offer is no longer on the Uni Bern housing board."})
                    if not parsed:
                        raise HTTPException(status_code=502, detail={"code": "fetch_failed", "message": "Couldn't read this Uni Bern offer."})
                    listing = parsed
                else:
                    response = client.get(url)
                    if "html" not in response.headers.get("content-type", ""):
                        raise HTTPException(status_code=400, detail={"code": "not_html", "message": "That link isn't a web page."})
                    extractor = _TextExtractor()
                    extractor.feed(response.text)
                    text = "\n".join(extractor.parts)[:8000]
                    listing = {**listing_from_text(text), "id": f"link:{url}", "source": "link", "url": url}
        except ScrapeBlocked as error:
            _blocked("robots_disallow", f"This website doesn't allow automated access ({error}). Paste the listing text instead.", source.name)
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(status_code=502, detail={"code": "fetch_failed", "message": f"Couldn't load the page: {type(error).__name__}"})
    else:
        raise HTTPException(status_code=400, detail={"code": "empty", "message": "Paste a link or the listing text."})

    [result], version = assess([listing], market, context=stored + [listing])
    listing.update(risk_score=result["score"], risk_details=result, model_version=version)
    # One listing: worth a few seconds to read who the landlord is looking for. None if Ollama is off.
    with llm.for_a_person():
        listing["wishes"] = wishes.extract(listing) if llm.available() else None
    return {"listing": card(listing, profile, market, QualityModel(), enforce_budget=False)}


@app.post("/api/generate", dependencies=GUARDED)
def generate(request: GenerateRequest):
    listing_id = request.listing.get("id")
    if listing_id:
        with db.connect() as conn:
            stored = db.get_listing(conn, listing_id)
        if stored and not stored.get("active", True):
            raise HTTPException(status_code=410, detail={"code": "listing_inactive", "message": "This listing is no longer online, so Flatty won't draft an application for it."})
    with llm.for_a_person():
        return llm.generate(request.kind, request.listing, request.profile.model_dump(), request.language)


@app.post("/api/translate-title", dependencies=GUARDED)
def translate_title(request: TranslateTitleRequest):
    original = request.title
    with llm.for_a_person():
        translated = llm.translate_title(original)
    return {
        "title": translated,
        "originalTitle": original,
        "engine": llm.OLLAMA_MODEL if llm.available() else "template",
    }


@app.post("/api/scrape", status_code=202, dependencies=GUARDED)
def scrape():
    """Start one polite scraper run in the background (local admin use)."""
    if refresher.state["running"]:
        raise HTTPException(status_code=409, detail={"code": "busy", "message": "A scraper run is already in progress."})
    refresher.start_in_background()
    return {"started": True}


@app.put("/api/account/preferences")
def save_preferences(request: PreferencesRequest, user: dict = Depends(accounts.require_user)):
    """Remembers the search profile, filters and sort order of the logged-in student."""
    with db.connect() as conn:
        db.save_preferences(conn, user["id"], request.profile.model_dump(), request.filters.model_dump(), request.sort)
    return {"ok": True}


@app.get("/api/saved")
def saved(user: dict = Depends(accounts.require_user)):
    """The student's saved homes, newest first, scored for their current profile.

    A home that is still in the database gets a fresh card (`available` says whether it is
    still online). A pasted listing is shown as it was when it was saved.
    """
    profile = Profile(**(user["profile"] or {})).model_dump()
    with db.connect() as conn:
        rows = db.saved_rows(conn, user["id"])
        stored = {row["listing_id"]: db.get_listing(conn, row["listing_id"]) for row in rows}
        market = market_stats(db.all_listings(conn)) if any(stored.values()) else {}
    model = QualityModel()
    items = []
    for row in rows:
        listing = stored[row["listing_id"]]
        if listing:
            item = {"listing": card(listing, profile, market, model, enforce_budget=False), "available": bool(listing.get("active", True))}
        elif row["snapshot"]:
            item = {"listing": row["snapshot"], "available": None}
        else:
            continue  # the listing was erased under the retention rule
        items.append({**item, "savedAt": row["saved_at"]})
    return {"items": items}


@app.post("/api/saved", status_code=201)
def save_listing(request: SaveRequest, user: dict = Depends(accounts.require_user)):
    listing_id = request.listing.get("id")
    if not isinstance(listing_id, str) or not listing_id or len(listing_id) > 600:
        raise HTTPException(status_code=400, detail={"code": "bad_listing", "message": "This listing can't be saved."})
    with db.connect() as conn:
        known = db.get_listing(conn, listing_id) is not None
        # Listings from the database are looked up again when shown; only pasted ones need a copy.
        snapshot = None if known else request.listing
        if snapshot is not None and len(json.dumps(snapshot)) > MAX_SNAPSHOT_BYTES:
            raise HTTPException(status_code=413, detail={"code": "too_large", "message": "This listing is too large to save."})
        if db.count_saved(conn, user["id"]) >= MAX_SAVED:
            raise HTTPException(status_code=409, detail={"code": "saved_full", "message": f"You can save up to {MAX_SAVED} homes. Remove one first."})
        saved_at = db.save_listing(conn, user["id"], listing_id, snapshot)
    return {"id": listing_id, "savedAt": saved_at}


@app.delete("/api/saved")
def unsave_listing(id: str, user: dict = Depends(accounts.require_user)):
    with db.connect() as conn:
        db.unsave_listing(conn, user["id"], id)
    return {"ok": True}


# The built front-end, served from the same address as the API (after every /api route).
if (STATIC_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="site")
