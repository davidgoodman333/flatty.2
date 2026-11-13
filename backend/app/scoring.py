"""Glue between storage and the risk model: score listings and persist the result."""

import sqlite3

from . import db
from .ml.features import duplicate_texts, market_stats, risk_signals
from .ml.models import combine, fallback_text_probability, load_risk_model


def assess(listings: list[dict], market: dict, context: list[dict] | None = None) -> tuple[list[dict], str]:
    """Risk assessment for each listing. `context` (default: the listings themselves) is used
    to find duplicated texts across the whole database."""
    model = load_risk_model()
    if model is None:
        text_probabilities, version = [fallback_text_probability(l) for l in listings], "rules-v0 (model not trained yet)"
    else:
        text_probabilities, version = model.predict(listings), model.version
    duplicates = duplicate_texts(context if context is not None else listings)
    results = [
        combine(probability, listing, risk_signals(listing, market, duplicates))
        for listing, probability in zip(listings, text_probabilities)
    ]
    return results, version


def rescore_all(conn: sqlite3.Connection) -> int:
    listings = db.all_listings(conn)
    results, version = assess(listings, market_stats(listings))
    for listing, result in zip(listings, results):
        db.save_risk(conn, listing["id"], result, version)
    return len(listings)
