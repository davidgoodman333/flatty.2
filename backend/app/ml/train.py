"""Train the local models and re-score every stored listing.

    python -m app.ml.train

Training data for the risk model, in order of trust:
  1. data/labels/risk_labels.csv   expert ratings (columns: id,label  with label scam|real)
                                   or free-text rows (title,description,price,rooms,surface,label)
  2. seed_data.py                  hand-written bootstrap examples
  3. scraped Flatfox listings      weak label "real" (unless an expert label says otherwise)
"""

import csv
import json
import random
from datetime import date

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_score, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold

from .. import db
from ..config import LABEL_DIR, MODEL_DIR
from ..scoring import rescore_all
from .features import (
    PHOTO_SOURCES, QUALITY_FEATURES, SIGNAL_WEIGHTS, SIGNAL_WEIGHTS_PATH, description_length, market_stats,
    price_ratio, quality_features, text_flag_vector,
)
from .models import QUALITY_PATH, RiskModel, logit
from .seed_data import seed_examples

MAX_WEAK_NEGATIVES = 400
MIN_REPLY_LABELS = 30
MIN_SIGNAL_LABELS = 40


def _label(value: str) -> int | None:
    value = (value or "").strip().lower()
    if value in ("scam", "1", "fake", "fraud"):
        return 1
    if value in ("real", "0", "legit", "ok"):
        return 0
    return None


def _float(value):
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def load_expert_labels(by_id: dict[str, dict]) -> tuple[list[tuple[dict, int]], set[str]]:
    path = LABEL_DIR / "risk_labels.csv"
    examples, used_ids = [], set()
    if not path.exists():
        return examples, used_ids
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            label = _label(row.get("label", ""))
            if label is None:
                continue
            if row.get("id") and row["id"] in by_id:
                examples.append((by_id[row["id"]], label))
                used_ids.add(row["id"])
            elif row.get("description"):
                examples.append(({
                    "title": row.get("title", ""), "description": row["description"],
                    "price": _float(row.get("price")), "rooms": _float(row.get("rooms")),
                    "surface": _float(row.get("surface")), "category": row.get("category") or "APARTMENT",
                    "is_private": row.get("is_private", "1") not in ("0", "false", "no"),
                }, label))
    return examples, used_ids


def evaluate(examples: list[tuple[dict, int]]) -> dict:
    listings = [listing for listing, _ in examples]
    labels = np.array([label for _, label in examples])
    folds = StratifiedKFold(n_splits=min(5, int(labels.sum())), shuffle=True, random_state=7)
    probabilities = np.zeros(len(labels))
    for train_index, test_index in folds.split(listings, labels):
        model = RiskModel().fit([listings[i] for i in train_index], labels[train_index].tolist())
        probabilities[test_index] = model.predict([listings[i] for i in test_index])
    predicted = probabilities >= 0.5
    return {
        "roc_auc": round(float(roc_auc_score(labels, probabilities)), 3),
        "precision_scam": round(float(precision_score(labels, predicted, zero_division=0)), 3),
        "recall_scam": round(float(recall_score(labels, predicted, zero_division=0)), 3),
    }


def is_clean_weak_negative(listing: dict, market: dict) -> bool:
    """Only complete, unremarkable listings may serve as weak "real" examples. Otherwise the
    text model learns that empty, cheap, photo-less listings are normal (they are what we
    want to flag)."""
    complete_text = description_length(listing) >= 250
    complete_media = listing.get("source") not in PHOTO_SOURCES or len(listing.get("images") or []) >= 3
    no_red_flags = not any(text_flag_vector(listing))
    return complete_text and complete_media and no_red_flags and price_ratio(listing, market) >= 0.65


def train_risk(listings: list[dict], market: dict) -> RiskModel:
    by_id = {listing["id"]: listing for listing in listings}
    expert, expert_ids = load_expert_labels(by_id)
    seeds = seed_examples()
    candidates = [l for l in listings if l["id"] not in expert_ids and is_clean_weak_negative(l, market)]
    random.Random(7).shuffle(candidates)
    weak = [(listing, 0) for listing in candidates[:MAX_WEAK_NEGATIVES]]
    examples = expert + seeds + weak

    metrics = evaluate(examples)
    model = RiskModel().fit([l for l, _ in examples], [label for _, label in examples])
    model.version = f"risk-text-logreg-{date.today():%Y%m%d}" + ("" if expert else "-bootstrap")
    model.meta = {
        "examples": len(examples),
        "scam_examples": sum(label for _, label in examples),
        "expert_labels": len(expert),
        "seed_examples": len(seeds),
        "weak_real_examples": len(weak),
        "excluded_incomplete_listings": len(listings) - len(expert_ids) - len(candidates),
        "text_flag_weights": {k: round(float(v), 2) for k, v in model.flag_weights().items()},
        "cross_validation_text_model": metrics,
        "note": "Metrics on bootstrap data are optimistic; replace with expert-rated listings.",
    }
    model.save()
    return model


def fit_signal_weights(listings: list[dict], market: dict) -> str:
    """Once experts have rated enough listings, learn the listing-signal weights from them
    instead of using the expert prior in features.SIGNAL_WEIGHTS."""
    by_id = {listing["id"]: listing for listing in listings}
    expert, _ = load_expert_labels(by_id)
    rated = [(l, label) for l, label in expert if l.get("id") in by_id]
    if len(rated) < MIN_SIGNAL_LABELS or len({label for _, label in rated}) < 2:
        if SIGNAL_WEIGHTS_PATH.exists():
            SIGNAL_WEIGHTS_PATH.unlink()
        return f"only {len(rated)} expert-rated stored listings (need {MIN_SIGNAL_LABELS}, both labels); using the expert prior"
    from ..scoring import assess  # local import: scoring depends on the trained text model

    results, _ = assess([l for l, _ in rated], market, context=listings)
    keys = sorted(SIGNAL_WEIGHTS)
    rows = [[logit(r["text_probability"])] + [float(any(s["key"] == k for s in r["signals"])) for k in keys] for r in results]
    model = LogisticRegression(C=1.0, max_iter=1000).fit(np.array(rows), [label for _, label in rated])
    weights = {k: round(float(w), 3) for k, w in zip(keys, model.coef_[0][1:])}
    SIGNAL_WEIGHTS_PATH.write_text(json.dumps(weights, indent=2))
    return f"learned signal weights from {len(rated)} expert labels"


def train_quality(by_id: dict[str, dict], market: dict) -> str:
    """Columns: id,replied (0/1) plus the applicant profile at that time:
    languages (e.g. "English;German"), hasResidencePermit, hasSwissNumber, hasSwissBank,
    hasGuarantor, hasViewingPerson (yes/no)."""
    path = LABEL_DIR / "reply_labels.csv"
    if not path.exists():
        return f"no {path.name}; using the prior weights"
    rows = [row for row in csv.DictReader(path.open(newline="", encoding="utf-8")) if row.get("id") in by_id]
    if len(rows) < MIN_REPLY_LABELS or len({row["replied"] for row in rows}) < 2:
        return f"only {len(rows)} usable reply labels (need {MIN_REPLY_LABELS}, both outcomes); using the prior weights"
    vectors, labels = [], []
    for row in rows:
        profile = {**row, "languages": (row.get("languages") or "").split(";")}
        features = quality_features(by_id[row["id"]], profile, market)
        vectors.append([features[name] for name in QUALITY_FEATURES])
        labels.append(int(row["replied"]))
    model = LogisticRegression(class_weight="balanced", max_iter=1000).fit(np.array(vectors), labels)
    version = f"quality-logreg-{date.today():%Y%m%d}"
    joblib.dump({"model": model, "version": version, "rows": len(rows)}, QUALITY_PATH)
    return f"trained {version} on {len(rows)} reply labels"


def main() -> None:
    with db.connect() as conn:
        listings = db.all_listings(conn)
        market = market_stats(listings)
        risk = train_risk(listings, market)
        print(f"Risk model {risk.version}:")
        print(json.dumps(risk.meta, indent=2))
        print("Quality model:", train_quality({l["id"]: l for l in listings}, market))
        print(f"Re-scored {rescore_all(conn)} stored listings.")
    (MODEL_DIR / "risk_model_meta.json").write_text(json.dumps({"version": risk.version, **risk.meta}, indent=2))


if __name__ == "__main__":
    main()
