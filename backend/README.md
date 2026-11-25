# Flatty back-end

Local back-end for the Flatty prototype. It:

1. collects Bern rental listings from **Flatfox**, the **Uni Bern Welcome Center housing board** and **studentlodge.ch**. Other sites are disabled because their terms forbid it or they block bots; see [LEGAL.md](LEGAL.md);
2. scores every listing with two local AI models: **risk** (is it a scam?) and **quality** (will the landlord reply to this student?);
3. ranks listings for a student's profile by how likely the landlord is to reply, and explains why;
4. reads who the landlord is looking for (language, gender, age, students or not, smoking) and drafts application e-mails and summaries and translates German listing titles to English with a local LLM (Ollama).

5. keeps accounts: a student can log in, Flatty remembers the profile, and liked homes go on a Saved list.

No cloud AI API is used. Everything runs on this machine.

**All scoring rules are in [rules.toml](rules.toml)**: every risk and reply factor with its weight and threshold, the red-flag phrases scanned in the text, and the instructions the local AI follows when it reads the description. The app reads the file at start-up, so editing it changes the scores (restart the API afterwards).

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

## Accounts and saved homes

`app/accounts.py` handles sign-up, log-in and log-out. Passwords are stored as scrypt hashes. A session is a random token in an HttpOnly cookie that lasts 30 days; the database only keeps its SHA-256 hash.

- **Remembered:** the profile from the setup, the filters and the sort order. The app saves them shortly after each change and loads them at log-in, so a returning student lands on the results.
- **Saved homes:** the heart on a listing. The Saved tab scores each home again for the current profile and marks homes that went offline. A saved home is erased together with its listing under the 14-day retention rule. A pasted listing isn't in the database, so its card is stored with the save.
- **Deleting:** "Delete account" under "Edit profile" erases the account, profile, saved homes and sessions.

Without any setting, anyone who can reach the server can create an account and the search works without one. That is right for a laptop.

## Hosting a private test

For a few invited testers, run the whole site from this machine and open it to the internet through a tunnel. The models, the database and the accounts stay here.

1. Build the front-end once (again after every front-end change): `pnpm build` in the project root, or `npx vite build`. It writes `dist/`. When `dist/` exists, the API serves it, so port 8000 is the whole website.
2. Create `backend/.env` (git ignores it):

   ```
   FLATTY_ALLOWED_EMAILS=you@example.com,colleague1@example.com,colleague2@example.com,colleague3@example.com
   FLATTY_INVITE_CODE=a-long-code-you-make-up
   FLATTY_CONTACT=team@example.com
   ```

   The developer password (`app/site_gate.py`) is one fixed password for the team, kept in `backend/site_password.txt`. Git ignores that file, so it never reaches the public GitHub repository; it exists only on the laptop that runs the back-end (`FLATTY_SITE_PASSWORD` overrides it; without either there is no gate). It sits in front of the whole site: every page, API route, file and `/docs` first shows a Flatty password page, and `/api` answers 401 `site_locked`. The right password sets an HttpOnly cookie for 7 days (`FLATTY_GATE_DAYS`); "Lock site" in the header removes it, and changing the password logs everybody out. Wrong passwords cost a second each, and 5 within 15 minutes lock that address out for 15 minutes. All responses carry `X-Robots-Tag: noindex`. It also covers the development preview (Vite forwards `/__gate` to the back-end): the app sends you to the password page when its API calls are locked.

   The account lines work behind the gate: either of them starts the private test: only these e-mail addresses can create an account, creating one needs the code, and listings, link checks and e-mail drafts all answer 401 without a log-in. Use both. E-mail addresses aren't verified, so the code is what stops a stranger from registering with a colleague's address.
3. Start it: `cd backend && caffeinate -s .venv/bin/uvicorn app.main:app --port 8000 --env-file .env` (`caffeinate` keeps the Mac awake). Don't add `--reload`.
4. In a second terminal: `ngrok http 8000`. Send the https address it prints and the invite code to the testers.

The site is reachable only while steps 3 and 4 are running. Before hosting on a rented server instead, read "Private test" in [LEGAL.md](LEGAL.md): the Uni Bern source isn't cleared for that.

## Online test through Vercel

The team's chosen set-up: the link is a Vercel address, and Vercel forwards **every** request (pages, API, files) to one team member's Mac, which runs the whole back-end and Ollama. Everyone who opens the link, from any laptop, uses that Mac's database and AI. The developer password (`backend/site_password.txt`, see above) protects every route, because every route is served by the Mac. Vercel only provides the address and serves nothing itself.

```
browser ──https──> flatty.vercel.app ──(rewrite: everything)──> your-mac.tailXXXX.ts.net ──Tailscale Funnel──> 127.0.0.1:8100
                                                                             (~/flatty-online: code from GitHub main; data from this folder)
```

The tunnel is **Tailscale Funnel**: free, a fixed address, and no warning page in front of the site. (Free ngrok shows its own warning page to browsers, which would replace Flatty when Vercel forwards to it.)

**Once, on the Mac that hosts:**

1. Install Tailscale (https://tailscale.com/download/mac), sign in, and in the admin console (https://login.tailscale.com/admin) turn on *MagicDNS*, *HTTPS certificates* and *Funnel* for this machine (Access controls → `nodeAttrs` with `funnel`; the console offers it the first time you run `tailscale funnel`).
2. Run `tailscale funnel --bg 8100` once and note the address it prints (`https://<mac-name>.<tailnet>.ts.net`). Turn it off again with `tailscale funnel --https=443 off`.
3. Put that address into [`vercel/vercel.json`](../vercel/vercel.json) instead of `YOUR-MAC.YOUR-TAILNET.ts.net`.
4. Make sure `backend/site_password.txt` holds the team password (one line). Cookies of requests that came through Vercel or the tunnel are marked https-only automatically (`FLATTY_SECURE_COOKIES=1` forces it for every request).
5. Deploy the Vercel project from the `vercel/` folder only: either `npx vercel --cwd vercel --prod` (asks you to log in the first time), or import the GitHub repository at vercel.com with **Root Directory** set to `vercel` and no build command. The folder holds nothing but `vercel.json`, so Vercel has no files of its own and forwards everything.

**Each time you want the site online:** run `./start-online.sh` in the project root (in a Terminal window that stays open). Ctrl+C stops it and closes the Funnel; while it isn't running, the Vercel link shows an error page.

**The online site runs the code from GitHub, not this folder.** `start-online.sh` keeps a separate copy in `~/flatty-online` (cloned the first time, with its own `.venv` and `node_modules`) and runs it on port 8100. Every 3 minutes it checks `main` on GitHub; when anyone on the team has pushed, it pulls, installs dependencies if `requirements.txt` or the lockfile changed, builds the front-end into `dist.new`, and restarts. If the new version doesn't build or doesn't answer within a minute, the previous version keeps running and that commit is skipped. So: **push to `main` to put a change online**; half-finished edits in your working folder never go online. The log is `~/flatty-online.log`.

The data stays on the Mac and is shared by both copies: the online copy reads the database and models of this folder (`FLATTY_DATA_DIR`, `FLATTY_MODEL_DIR`) and its password file (`FLATTY_SITE_PASSWORD_FILE`). Only the online copy should run the daily scraper and the background AI jobs; start the development back-end with `FLATTY_AUTO_REFRESH=0 FLATTY_LLM_WORKER=0` while the online site runs, so nothing is done twice. The script also sets Ollama to 4 parallel requests and keeps the Mac awake.

Things to know:
- The Funnel address also works on its own, without Vercel; it is just as protected by the password.
- If the AI takes very long, Vercel's time limit for forwarded requests can cut the request off; then the app shows the template e-mail.
- The lockout after 5 wrong passwords uses the visitor's address that the tunnel passes on. If it turns out to receive only Vercel's address, one person's wrong guesses lock out everyone for 15 minutes; check this once after the first deployment.
- The Uni Bern source can stay on: the listings never leave the Mac (see [LEGAL.md](LEGAL.md), "Private test").

## API

| Method | Path | What it does |
|---|---|---|
| GET | `/api/health` | Listing count, last scraper run, model versions, whether the LLM is available |
| GET | `/api/sources` | Every source with its robots.txt and terms assessment, and the number of stored listings |
| POST | `/api/match` | `{profile, filters, sort, offset, limit}` → `{total, listings, sourceCounts}`. Each listing has `replyLevel` (`likely`/`unlikely`), `replyLabel`, risk %, `reasons` (what affects the reply likelihood, each with a `share`: its percentage of the weights of all facts that apply, adding up to 100; `tone` `yes` raises the chance, `warn` lowers it), `notes` (how it compares with the student's preferences), `wishes` (who the landlord is looking for: `title`, `quote`, `strength`, `fit` `yes`/`no`/`unknown`; `null` until the LLM has read the listing), warning signs, photos, features and details |
| POST | `/api/check-link` | `{profile, url}` or `{profile, text}` → one scored listing. Returns 451 for sites whose terms forbid automated reading |
| POST | `/api/generate` | `{kind: "email" \| "summary" \| "title", listing, profile, language?}` → text from the local LLM, or from a template/glossary if Ollama isn't running. For e-mails, `language` is `"English"` or `"German"` (default: German if the listing is in German, otherwise English); the app asks for both |
| POST | `/api/translate-title` | `{title}` → `{title, originalTitle, engine}` (translates German listing title to English) |
| GET | `/api/listings/{id}/check` | Is this listing still online at its source? One request, cached for an hour |
| POST | `/api/scrape` | Starts a scraper run in the background (the daily refresh does this automatically) |
| GET | `/api/auth/me` | `{user, private, inviteRequired}`. `user` is `null` when nobody is logged in, otherwise `{email, profile, filters, sort}` |
| POST | `/api/auth/register` | `{email, password, inviteCode?}` → creates the account and logs in. 403 if the e-mail isn't invited or the code is wrong |
| POST | `/api/auth/login`, `/api/auth/logout` | `{email, password}` → sets the session cookie; log-out removes it. Eight wrong passwords lock the address for 15 minutes |
| POST | `/api/auth/delete-account` | Erases the logged-in account and everything stored for it |
| PUT | `/api/account/preferences` | `{profile, filters, sort}` → remembered for the logged-in student |
| GET | `/api/saved` | `{items: [{listing, savedAt, available}]}`, newest first. `available` is `false` for a home that went offline and `null` for a pasted listing |
| POST, DELETE | `/api/saved` | `POST {listing}` saves a home; `DELETE ?id=…` removes it |

During a private test, every row above `/api/auth/me` except `/api/health` needs a log-in.

The `profile` has the same fields as the onboarding in `src/App.tsx`. `name` is only used to sign e-mails. `destination` is one of the campuses in `app/geo.py` (`CAMPUSES`); the same list is in `src/options.ts`, so change both together.

`filters` (all optional):
- `sources` (`["flatfox", "unibe", "studentlodge"]`);
- `priceMin`, `priceMax`, `roomsMin`, `surfaceMin`;
- `types` (`"Shared apartment"`, `"Studio"`, `"Proper flat"`);
- `features` (`"Furnished"`, `"Balcony or garden"`, `"Pets allowed"`, `"Dishwasher"`, `"Washing machine"`, `"Lift"`, `"Parking"`, `"Wheelchair accessible"`);
- `maxRisk` (0–100), `rental` (`any|permanent|temporary`), `withPhotos`;
- `availableBy` and `neededUntil` (`YYYY-MM-DD`): the period the student needs the home for. A listing is hidden if it is free only after `availableBy`, or if its rental ends before `neededUntil`. Dates come from Flatfox's move-in date and from the Uni Bern board's free text (`app/dates.py`); a listing with unknown dates is never hidden.

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
2. **Listing signals** (`[risk.signals]` in [rules.toml](rules.toml)). Transparent evidence outside the text:

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
- residence permit, Swiss phone number, Swiss bank account, guarantor, someone to attend viewings: more replies;
- the landlord's own wishes, read by the local LLM (see "Landlord wishes" below): asks for a language the student doesn't speak (−2.0 if required, −1.2 if preferred, on top of the −0.7 for a text in that language), not looking for students (−1.8 / −1.08), the student speaks the language asked for (+0.5 / +0.3). Swiss German counts as German.

The weights are in [rules.toml](rules.toml) (`[reply.factors]`). Once `data/labels/reply_labels.csv` has 30 or more rows covering both outcomes, `train.py` fits a logistic regression that replaces the prior.

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

Ollama has to be running (`ollama serve`, or open the Ollama app); `/api/health` shows `llm.available`. For the team testing at the same time, Ollama runs 4 requests in parallel and keeps the model loaded (`OLLAMA_NUM_PARALLEL=4`, `OLLAMA_KEEP_ALIVE=24h`; `start-online.sh` sets both and restarts the Ollama app if needed). The background jobs wait while anyone is waiting for an e-mail, a summary, a translation or a pasted listing (`llm.for_a_person`). Measured on an M5 with 16 GB: an e-mail, a summary and three title translations requested at the same moment by three people all finished within 8 s, each close to its time alone. Without it, e-mails and summaries come from templates and titles from the glossary.

- **E-mails** are written in English and in German, in the first person, from the profile facts only, and always end with the fixed closing and the student's name (`llm.sign`).
- **Landlord wishes** (`app/wishes.py`): many listings say who they want: "Schweizerdeutsch als Muttersprache", "Mitbewohnerin gesucht (18-28)", "ideal für Berufstätige", "Nichtraucher vorausgesetzt". Keyword rules can't tell these from sentences about the current flatmates ("Ich spreche Italienisch, Schweizerdeutsch verstehe ich teilweise"), so the LLM reads them, following `[ai.wishes]` in [rules.toml](rules.toml), with guards: only sentences that mention one of the topics are sent (a listing without one costs no LLM call); each wish must point to its sentence, and that sentence must be about the topic (a language must be named, an age range written out); and the model confirms each wish once more with a yes/no question about that sentence alone. Language and occupation wishes change the reply likelihood and appear in `reasons` with the listing's own words. Gender, age and smoking aren't in the profile, so they are shown (`wishes` on each listing, `fit: unknown`) but not scored. Results are stored per listing (`wishes`, `wishes_version`) and read again when the text changes or `version` in `[ai.wishes]` is bumped. Pasted listings are read straight away. `/api/health` shows `wishesPending`.
- **Titles**: a search never waits for the LLM. Lists show the stored translation (`title_en`) or, until there is one, the instant glossary translation. `app/llm_worker.py` translates the remaining titles one at a time in the background (after the wishes) and stores them, so this is done once per listing.

## Folders

```
app/
  main.py             FastAPI app
  matching.py         ranking and explanations
  llm.py              local LLM (Ollama) with template fallback
  llm_worker.py       background LLM jobs: landlord wishes first, then English titles; stores both
  wishes.py           reads who the landlord is looking for and compares it with the profile
  rules.py            loads rules.toml (all weights, thresholds, scanned phrases and AI prompts)
  accounts.py         sign-up, log-in, session cookie, the private-test lock
  dates.py            reads "available from … to …" from a listing
  geo.py              offline Bern neighbourhoods, campuses and commute estimate
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
| `FLATTY_LLM_WORKER` | 1 | Set to 0 to stop the background LLM jobs (landlord wishes and title translation). The old name `FLATTY_TRANSLATE_TITLES` still works |
| `FLATTY_ALLOWED_EMAILS` | empty | Comma-separated e-mail addresses that may create an account and log in. Setting it starts the private test |
| `FLATTY_INVITE_CODE` | empty | Code that must be entered when creating an account. Setting it starts the private test |
| `FLATTY_SESSION_DAYS` | 30 | How long a log-in lasts |
| `FLATTY_STATIC_DIR` | `../dist` | The built front-end that the API serves |
