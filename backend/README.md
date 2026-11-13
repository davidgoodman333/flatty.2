# Flatty back-end

Local back-end for the Flatty prototype. It:

1. collects Bern rental listings from **Flatfox**, the **Uni Bern Welcome Center housing board** and **studentlodge.ch**. Other sites are disabled because their terms forbid it or they block bots; see [LEGAL.md](LEGAL.md);
2. scores every listing with two local AI models: **risk** (is it a scam?) and **quality** (will the landlord reply to this student?);
3. ranks listings for a student's profile by how likely the landlord is to reply, and explains why;
4. drafts application e-mails and summaries and translates German listing titles to English with a local LLM (Ollama).

No cloud AI API is used. Everything runs on this machine.

## Setup

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Optional, for e-mail drafting: a local LLM through Ollama (https://ollama.com)
ollama pull qwen3:8b
```

## Run

```bash
cd backend
.venv/bin/python -m app.scraper.run      # collect listings from all enabled sources (about 2.5 min)
.venv/bin/python -m app.scraper.run --source unibe   # or a single source
.venv/bin/python -m app.ml.train         # train the risk model and re-score all listings
.venv/bin/uvicorn app.main:app --port 8000 --reload
```

Then start the front-end from the project root (`pnpm dev`). Vite proxies `/api` to `http://127.0.0.1:8000`; set `FLATTY_API_URL` to use another address. If the back-end isn't running, the front-end shows demo data.

### Keeping listings current

| What | How |
|---|---|
| **Daily refresh** | While the API runs, a background thread (`app/refresher.py`) re-scrapes every source whose last complete run is older than 24 hours. It checks every 15 minutes. A failed or partial run is retried after 3 hours, and a run cut off by a restart is retried straight away. Turn it off with `FLATTY_AUTO_REFRESH=0`. |
| **Gone listings are hidden at once** | After a *complete* run of a source, its listings that the run didn't see are marked inactive and disappear from results. Nothing is hidden after a partial run, or when a run sees fewer than half of the active listings (that points to a site change, not a mass rent-out). |
| **Status check** | Flatfox listings count only with `status: "act"`. Rented or withdrawn ones (`"dis"`) are skipped, also for pasted links. |
| **Check when opened** | When a student opens a listing, `GET /api/listings/{id}/check` asks the source once whether it is still online: Flatfox API status, or whether the Uni Bern page still exists. The result is cached for an hour. If the listing is gone, the app says so, removes it from the results and won't draft an e-mail. studentlodge lists room types, so availability is confirmed when booking. |
| **Retention** | Inactive listings are deleted after 14 days (`FLATTY_RETENTION_DAYS`). That rule is only for data protection now; it no longer decides what is shown. |

The list shows "updated … ago" (the oldest of the sources' last complete runs). `/api/health` shows when each source last completed and when the next refresh is due.

All requests share one rate limit per site (one request every 2 s) and a robots.txt cache that is renewed daily. Refreshes, link checks and listing checks together stay polite.

## API

| Method | Path | What it does |
|---|---|---|
| GET | `/api/health` | Listing count, last scraper run, model versions, whether the LLM is available |
| GET | `/api/sources` | Every source with its robots.txt and terms assessment, and the number of stored listings |
| POST | `/api/match` | `{profile, filters, sort, offset, limit}` → `{total, listings, sourceCounts}`. Each listing has `replyLevel` (`likely`/`unlikely`), `replyLabel`, risk %, `reasons` (what affects the reply likelihood, each with a `share`: its percentage of the weights of all facts that apply, adding up to 100; `tone` `yes` raises the chance, `warn` lowers it), `notes` (how it compares with the student's preferences), warning signs, photos, features and details |
| POST | `/api/check-link` | `{profile, url}` or `{profile, text}` → one scored listing. Returns 451 for sites whose terms forbid automated reading |
| POST | `/api/generate` | `{kind: "email" \| "summary" \| "title", listing, profile}` → text from the local LLM, or from a template/glossary if Ollama isn't running |
| POST | `/api/translate-title` | `{title}` → `{title, originalTitle, engine}` (translates German listing title to English) |
| GET | `/api/listings/{id}/check` | Is this listing still online at its source? One request, cached for an hour |
| POST | `/api/scrape` | Starts a scraper run in the background (the daily refresh does this automatically) |

The `profile` has the same fields as the onboarding in `src/App.tsx`.

`filters` (all optional):
- `sources` (`["flatfox", "unibe", "studentlodge"]`);
- `priceMin`, `priceMax`, `roomsMin`, `surfaceMin`;
- `types` (`"Shared apartment"`, `"Studio"`, `"Proper flat"`);
- `features` (`"Furnished"`, `"Balcony or garden"`, `"Pets allowed"`, `"Dishwasher"`, `"Washing machine"`, `"Lift"`, `"Parking"`, `"Wheelchair accessible"`);
- `maxRisk` (0–100), `rental` (`any|permanent|temporary`), `withPhotos`, `availableBy` (`YYYY-MM-DD`).

Without `priceMax`, listings more than 15 % over the student's budget are hidden.

`sort`: `reply` (default), `price_asc`, `price_desc`, `newest`, `risk`, `commute` or `size`.

## The models

**Risk score** (`app/ml/models.py`, `app/ml/features.py`). There are two parts, added in log-odds:

```
logit(risk) = logit(text part) + sum of listing-signal weights
```

1. **Text part (AI model, trained by `app/ml/train.py`).** Logistic regression on:
   - character n-gram TF-IDF of the listing text (handles German, French, Italian and English without translation);
   - red-flag phrases (`app/text.py`): deposit before viewing, no viewing or owner abroad, contact off the platform, risky payment channels, time pressure.

   With little text (under 300 characters and no red-flag phrase), the model's verdict is blended towards the base rate (6 %). A missing description therefore no longer counts as proof that a listing is safe.
2. **Listing signals** (`SIGNAL_WEIGHTS` in `features.py`). Transparent evidence outside the text:

   | Signal | Effect on log-odds |
   |---|---|
   | Rent under 50 % / 50–65 % of similar listings | +1.2 / +0.6 |
   | No description / short description / detailed description | +0.9 / +0.4 / −0.2 |
   | No photos / one photo / five or more photos (Flatfox only) | +0.7 / +0.5 / −0.3 |
   | No street address (Flatfox only) | +0.3 |
   | Private landlord / agency / known non-profit provider | +0.2 / −0.7 / −2.0 |
   | Same text as a private listing in another town or at another price | +1.0 |

   These weights are an expert prior. Once at least 40 stored listings are rated in `risk_labels.csv`, `train.py` learns them from the ratings and saves them to `models/signal_weights.json`.

The result page lists what raised and what lowered the score.

Training data, in order of trust:
1. `data/labels/risk_labels.csv`: expert ratings from the interviews (see the header in that file).
2. `app/ml/seed_data.py`: hand-written bootstrap examples of known Swiss scam patterns.
3. Scraped listings, weakly labelled "real", but **only complete ones**: at least 250 characters of description, at least 3 photos on Flatfox, no red-flag phrase, and not cheap for the market. Otherwise the model would learn that empty, cheap listings are normal.

> ⚠️ The current model is a **bootstrap**. Its cross-validation (AUC 1.0) is measured on hand-written examples and is far too optimistic. Treat its scores as indicative until the expert-rated corpus from the interviews replaces the seed data. Flatty only warns and never hides a listing.

**Quality score / reply likelihood.** No reply data exists yet, so a transparent prior encodes the pitch's assumptions:
- private landlord, mentions students, shared flat, furnished or temporary: more replies;
- cheap for the market: more competition;
- listing in a language the student doesn't speak: fewer replies;
- residence permit, Swiss phone number, Swiss bank account, guarantor, someone to attend viewings: more replies.

The weights are in `QUALITY_PRIOR`. Once `data/labels/reply_labels.csv` has 30 or more rows covering both outcomes, `train.py` fits a logistic regression that replaces the prior.

**Type of home** (`app/kinds.py`). Platforms' own categories are unreliable: Flatfox marks some WG rooms as 1-room flats, and some providers call a room with a shared kitchen a "studio". Flatty therefore decides itself:

| Type | Rule |
|---|---|
| Room | The source says shared flat or room, or the title names a room ("Zimmer in…", "WG", "chambre", "room for rent"; a number before "Zimmer" is a room count, not a room), or the description starts like a WG ad, or the kitchen is shared ("Küche auf dem Stockwerk", "Gemeinschaftsküche"). |
| Studio | Self-contained (own kitchen and bathroom), at most 1.5 rooms, at most 50 m². |
| Apartment | Self-contained with 2+ rooms, or a 1–1.5-room flat over 50 m². |
| House | The source lists a house. |

The type filter and the notes on each listing both use these rules. Market prices compare rooms with rooms and flats with flats.

**Reply likelihood** is the quality score on its own, shown as "likely" (probability of 50 % or more) or "unlikely". It is the headline and the default sort order. The probability is returned as `replyScore`; the app shows it as a percentage on the listing page only, and uses it to sort. There is no match score: budget, area, type and commute are reported as plain `notes` on each listing and are not part of any number. The risk score is shown next to the reply likelihood but never filters anything out.

**E-mails, summaries and title translations** come from `qwen3:8b` through Ollama on `127.0.0.1:11434`. To use another model, set `FLATTY_OLLAMA_MODEL`. If Ollama is offline or unavailable, deterministic templates and an extensive Swiss rental glossary serve as transparent local fallbacks.

## Folders

```
app/
  main.py             FastAPI app
  matching.py         ranking and explanations
  llm.py              local LLM (Ollama) with template fallback
  geo.py              offline Bern neighbourhoods and commute estimate
  text.py             language detection, red flags, parsing pasted text
  scoring.py          scores listings and saves the result
  scraper/            sources.py (legal decisions), compliance.py, robots.py, run.py,
                      one collector per site: flatfox.py, unibe.py, studentlodge.py
  ml/                 features.py, models.py, seed_data.py, train.py
data/flatty.db        SQLite (created automatically, not committed)
data/labels/          expert labels (CSV)
models/               trained models (created by train.py)
```

## Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `FLATTY_CONTACT` | "student project, University of Bern" | Contact shown in the scraper's user agent. Set a real e-mail address |
| `FLATTY_MIN_INTERVAL` | 2.0 | Seconds between requests to the same site |
| `FLATTY_MAX_REQUESTS` | 40 | Maximum requests per scraper run |
| `FLATTY_RETENTION_DAYS` | 14 | Delete listings that haven't been seen for this long |
| `FLATTY_OLLAMA_URL`, `FLATTY_OLLAMA_MODEL` | `http://127.0.0.1:11434`, `qwen3:8b` | Local LLM |
