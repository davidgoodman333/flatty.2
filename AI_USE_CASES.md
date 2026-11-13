# Flatty: AI use cases and current state

Flatty helps international students find a flat in Bern. This file lists every place where the prototype uses AI, or is planned to, and how far each one is.

Status as of 13 November 2026. Setup and API details are in [backend/README.md](backend/README.md).

## Overview

| # | Use case | What the student sees | How it works today | Language model? | State |
|---|---|---|---|---|---|
| 1 | Reply likelihood | "Reply likely" or "Reply unlikely" on every listing; the listing page adds the percentage and what each point counts | Hand-set weights | No | Works and is the headline, but nothing is learned from data |
| 2 | Fraud score | "Risk 27 %" and a list of warning signs | Trained text classifier plus hand-set weights | No | Works, trained on placeholder data only |
| 3 | Listing translation | Nothing yet | Nothing | Planned | Not implemented |
| 4 | Application e-mail | "Draft an email" button on a listing | One prompt to a local language model | Yes | Implemented, never evaluated |
| 5 | Listing summary | "Make a summary" button on a listing | One prompt to a local language model | Yes | Implemented, never evaluated |

Two things follow from this table:

- Use cases 1 and 2 do not use a language model or any prompt. The course grades a prototype "based on prompt engineering".
- The only prompts in the project (4 and 5) each exist in a single version. There is no prompt history, no comparison of techniques or models, and no gold standard to compare against.

## Decision: there is no match score

Decided on 13 November 2026 and implemented the same day. Until then the app showed a "match %" that was 60 % preference fit (budget, area, type, commute) and 40 % reply likelihood.

The match score was removed because the preference part only measured how close a listing is to what the student already entered. That is a filter, not a prediction. Reply likelihood is the part that tells the student something new, so it is now the headline number and the default sort order.

What replaced it ([backend/app/matching.py](backend/app/matching.py)):

- Every listing shows a reply likelihood as "likely" or "unlikely", with the facts behind it.
- Budget, commute, area and type are still reported for each listing, as plain notes under "Compared with your preferences". They are not part of any number.

Known gap: the areas and the type of home chosen during onboarding used to influence the ranking through the match score. They now appear only in the notes and do not change which listings are shown or their order. The type can be set as a filter on the results page; there is no area filter.

## 1. Reply likelihood

**Purpose.** Estimate how likely the landlord is to reply to this particular student, so the student can spend effort where it pays off.

**How it works today** ([backend/app/ml/models.py](backend/app/ml/models.py), `QualityModel`; [backend/app/ml/features.py](backend/app/ml/features.py), `quality_features`). The score is built from 12 yes/no facts, each with a weight the team set by hand (`QUALITY_PRIOR`):

| About the listing | About the student |
|---|---|
| Private landlord | Has a residence permit |
| Mentions students | Has a Swiss phone number |
| Shared flat | Has a Swiss bank account |
| Furnished or temporary | Has a guarantor |
| Cheap for the market (more competition) | Has someone who can attend viewings |
| Expensive for the market | |
| Written in a language the student doesn't speak | |

**What the student sees.**

- **Listing card:** only "Reply likely" or "Reply unlikely". "Likely" means the model's probability is 50 % or more, so a reply is more likely than not.
- **Listing page:** the same word plus the probability itself (for example "Likely. 62 %"), and the panel "What affects your reply chance". It lists every fact that applies, strongest first, each with a percentage: how much that fact counts, as its share of the weights of all facts that apply. The shares add up to 100 %; a + means the fact raises the chance, a − that it lowers it. Example: "Student-friendly +23 %", "Listing written in German −37 %".

The page ends with a note that the weights are Flatty's own assumption and not yet checked against real replies.

The share says how much a fact counts relative to the others on this listing. It is not the number of percentage points the fact adds to the probability; with a logistic model those depend on the other facts.

How this developed on 13 November 2026, for the paper's development section:

1. A percentage on every card ("62 % reply chance").
2. Three levels (highly likely, likely, unlikely), with a hover box on each card explaining the facts in words ("Raises your chance a lot").
3. Two levels on the card. The hover box was dropped as unnecessary, because the listing page shows the same. The words were replaced with the share in percent, and the listing page shows the probability next to the level.

The listing page is ordered: the listing (title, photos, details, comparison with the student's preferences) first, then the reply likelihood, then the fraud score.

These explanations come from the weights directly, not from a language model. A language model could later phrase them for each listing, which would turn this use case into prompt work.

**State.**

- Runs end to end on about 820 real listings. It is the label on every listing card, a section of the listing page and the default sort order. For one test profile (English only, has a guarantor) half of the 577 listings within budget are "likely". For a student with only English and no other profile facts it is about a third; with German, a residence permit and a Swiss phone number it is nine in ten.
- Nothing is learned. `data/labels/reply_labels.csv` is empty; the training script replaces the hand-set weights only once it has 30 rows with both outcomes.
- The weights encode the team's assumptions from the pitch. No student or landlord has confirmed them. The app says so on the listing page.
- The score depends strongly on the student's answers. For an English-speaking student with all five profile facts set to yes, every stored listing is "likely".

**Missing.** Real reply data or expert input to justify the weights, and a decision on whether this becomes a prompt-based assessment.

## 2. Fraud score

**Purpose.** Warn the student about listings that look like scams. The score never hides a listing.

**How it works today** ([backend/app/ml/models.py](backend/app/ml/models.py), [backend/app/ml/features.py](backend/app/ml/features.py), [backend/app/text.py](backend/app/text.py)). Two parts are added together:

1. **Text model.** A logistic regression on character patterns of the listing text plus five red-flag phrase groups: deposit before viewing, no viewing or owner abroad, contact off the platform, risky payment channel, time pressure. The phrase groups are regular expressions in German, French, Italian and English.
2. **Listing signals.** Hand-set weights (`SIGNAL_WEIGHTS`) for facts outside the text: rent far below similar listings, missing description, few photos, no street address, same text reused elsewhere, agency or known non-profit provider.

The app shows which signals raised and which lowered the score.

**State.**

- Runs on every stored listing and on listings the student pastes in.
- Training data: 448 examples, of which 28 are scams. All 28 scams come from 48 examples the team wrote by hand. The other 400 are scraped listings assumed to be real.
- Expert-rated listings: 0. `data/labels/risk_labels.csv` is empty.
- The reported cross-validation result (AUC 1.0) is measured on those hand-written examples and says nothing about real scams.
- The signal weights are learned from data only once 40 expert-rated listings exist.

**Missing.** Listings rated by people who know Swiss rental scams, and a test of the score against those ratings.

## 3. Listing translation

**Purpose.** Let a student read a German, French or Italian listing in a language they speak.

**State.** Not implemented. There is no endpoint, no prompt and no button in the app.

What exists already and could be reused:

- The language of each listing is detected ([backend/app/text.py](backend/app/text.py), `detect_language`) and returned to the front-end as `language`.
- The student's languages are collected during onboarding.
- [backend/app/llm.py](backend/app/llm.py) already has the call to the local language model and a fallback when it is not running.

## 4. Application e-mail

**Purpose.** Draft a short application e-mail to the landlord from the student's profile.

**How it works today** ([backend/app/llm.py](backend/app/llm.py), `POST /api/generate` with `kind: "email"`).

| Setting | Value |
|---|---|
| Model | `qwen3:8b` through Ollama, on the local machine |
| Temperature | 0.2 |
| Maximum output | 500 tokens |
| Reasoning mode | off |
| Technique | One system prompt and one user message, no examples (zero-shot) |

- The system prompt gives a role, a fixed structure for the e-mail, a 130-word limit and a ban on inventing facts, documents or names.
- The user message contains the listing facts and the applicant facts as a list.
- The e-mail is written in the listing's language if the student speaks it, otherwise in English. German output is adjusted to Swiss spelling.
- If Ollama is not running, a fixed template is used. The app shows whether the text came from the model or the template.

**State.**

- Implemented and wired into the app.
- On the machine where this was checked, Ollama is not installed, so the app currently returns the template there.
- One prompt version. No other technique, model or setting has been tried, and no output has been compared with an e-mail written by an expert.

## 5. Listing summary

**Purpose.** Give the key facts of a listing, its reply likelihood and its warning signs in one short English text.

**How it works today** ([backend/app/llm.py](backend/app/llm.py), `POST /api/generate` with `kind: "summary"`). Same model and settings as the e-mail. The system prompt limits the text to 90 words and to the facts given. The user message contains the listing facts, both scores, what affects the reply likelihood, how the listing compares with the student's preferences, and the warning signs. The user message was reworded on 13 November 2026, first when the match score was removed and again when the reply likelihood became a level; it now passes the level ("Likely" or "Unlikely") instead of a percentage. The earlier wording is in the git history.

**State.** Same as the e-mail: implemented, one prompt version, template fallback, never evaluated.

## Not AI, although it may look like it

These parts are fixed rules. They should not be described as AI in the paper or the presentation.

| Part | How it works | File |
|---|---|---|
| Language detection | Counts common words per language | [backend/app/text.py](backend/app/text.py) |
| Type of home (room, studio, apartment, house) | Rules on title, rooms, size and kitchen | [backend/app/kinds.py](backend/app/kinds.py) |
| Reading a pasted listing | Regular expressions for price, rooms and size | [backend/app/text.py](backend/app/text.py) |
| Commute time | Offline estimate from coordinates | [backend/app/geo.py](backend/app/geo.py) |
| Demo data | Three fixed listings shown when the back-end is not running | [src/api.ts](src/api.ts) |

## Open points for all use cases

- **No user or expert input yet.** No interviews have been held, so there is no collection of real inputs and no gold standard for any use case.
- **No prompt evaluation.** For use cases 4 and 5 there is nothing to compare outputs against. For 1 and 2 there are no prompts to evaluate.
- **No record of prompt changes.** The appendix of the final paper must show the prompts and how they evolved; today only the current version in `llm.py` exists.
