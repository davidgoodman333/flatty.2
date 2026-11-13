"""The two local models from the pitch.

Risk score     P(listing is a scam), built from two clearly separated parts:
               1. Text model (supervised ML): character n-gram TF-IDF of the listing text (works
                  across German, French, Italian and English) + red-flag phrases, then logistic
                  regression. Trained by `python -m app.ml.train`. It only judges the text.
                  A listing with little or no text gets little text evidence, so it falls back to
                  the base rate instead of looking "safe".
               2. Listing signals (features.risk_signals): price vs. market, missing description,
                  few photos, no street address, duplicated text, agency or trusted provider.
               Both are added in log-odds: logit(risk) = logit(text) + sum(signal weights).
Quality score  P(the landlord replies to this student). Until real reply labels from the
               interviews exist, a transparent prior encodes the team's assumptions. Once
               data/labels/reply_labels.csv has enough rows, a trained model replaces it.

Everything runs locally with scikit-learn. No data leaves the machine.
"""

from dataclasses import dataclass, field
from math import exp, log

import joblib
import numpy as np
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from ..config import MODEL_DIR
from ..text import red_flags
from .features import QUALITY_FEATURES, TEXT_FLAGS, description_length, listing_text, quality_features, text_flag_vector

RISK_PATH = MODEL_DIR / "risk_model.joblib"
QUALITY_PATH = MODEL_DIR / "quality_model.joblib"

# Assumed share of scams among listings when there is no evidence either way.
BASE_RATE = 0.06
# Characters of description needed before the text model's verdict counts fully.
FULL_TEXT_EVIDENCE = 300


def sigmoid(x: float) -> float:
    return 1 / (1 + exp(-x))


def logit(p: float) -> float:
    p = min(0.99, max(0.01, p))
    return log(p / (1 - p))


@dataclass
class RiskModel:
    version: str = "untrained"
    meta: dict = field(default_factory=dict)
    vectorizer: TfidfVectorizer = field(default_factory=lambda: TfidfVectorizer(
        analyzer="char_wb", ngram_range=(3, 5), min_df=2, max_features=20000, sublinear_tf=True))
    classifier: LogisticRegression = field(default_factory=lambda: LogisticRegression(
        C=0.5, class_weight="balanced", max_iter=2000))

    def _matrix(self, listings: list[dict], fit: bool = False):
        texts = [listing_text(l) for l in listings]
        text_part = self.vectorizer.fit_transform(texts) if fit else self.vectorizer.transform(texts)
        # Red-flag phrases are weighted up so that they, not writing style, drive the verdict.
        flags = csr_matrix(np.array([text_flag_vector(l) for l in listings]) * 2.0)
        return hstack([text_part, flags]).tocsr()

    def fit(self, listings: list[dict], labels: list[int]) -> "RiskModel":
        self.classifier.fit(self._matrix(listings, fit=True), labels)
        return self

    def predict(self, listings: list[dict]) -> list[float]:
        if not listings:
            return []
        return self.classifier.predict_proba(self._matrix(listings))[:, 1].tolist()

    def flag_weights(self) -> dict[str, float]:
        return dict(zip(TEXT_FLAGS, self.classifier.coef_[0][-len(TEXT_FLAGS):] * 2.0))

    def save(self) -> None:
        joblib.dump(self, RISK_PATH)


def fallback_text_probability(listing: dict) -> float:
    """Used only before the first training run: red-flag phrases with fixed weights."""
    flags = dict(zip(TEXT_FLAGS, text_flag_vector(listing)))
    score = -3.0 + 1.6 * (flags["deposit_before_viewing"] + flags["no_viewing"] + flags["payment_service"])
    return sigmoid(score + 1.0 * flags["off_platform_contact"] + 0.6 * flags["urgency"])


def combine(text_probability: float, listing: dict, signals: list[tuple[str, str, float]]) -> dict:
    """Merge text evidence and listing signals into one risk score with an explanation."""
    flags = red_flags(listing_text(listing))
    # A short text says little, unless it contains an explicit red-flag phrase.
    evidence = 1.0 if flags else min(1.0, description_length(listing) / FULL_TEXT_EVIDENCE)
    text_part = evidence * min(0.99, max(0.01, text_probability)) + (1 - evidence) * BASE_RATE
    score = sigmoid(logit(text_part) + sum(weight for _, _, weight in signals))
    return {
        "score": round(min(0.99, max(0.01, score)), 4),
        "text_probability": round(text_part, 4),
        "text_evidence": round(evidence, 2),
        "text_flags": flags,
        "signals": [{"key": key, "label": label, "weight": weight} for key, label, weight in signals],
    }


# Prior weights for the quality model (log-odds). They encode the pitch's assumptions:
# private landlords, student-friendly and furnished/temporary offers reply more often; cheap
# listings get flooded with applications; local credentials and a guarantor help.
QUALITY_PRIOR = {
    "bias": -0.6,
    "private_landlord": 0.6,
    "mentions_students": 0.7,
    "shared_flat": 0.5,
    "furnished_or_temporary": 0.4,
    "cheap_for_market": -0.6,
    "expensive_for_market": 0.3,
    "language_barrier": -0.7,
    "has_permit": 0.5,
    "has_swiss_phone": 0.3,
    "has_swiss_bank": 0.3,
    "has_guarantor": 0.6,
    "has_viewing_person": 0.5,
}


class QualityModel:
    def __init__(self):
        self.trained = joblib.load(QUALITY_PATH) if QUALITY_PATH.exists() else None
        self.version = self.trained["version"] if self.trained else "quality-prior-v0"

    def predict(self, listing: dict, profile: dict, market: dict) -> tuple[float, dict[str, float]]:
        features = quality_features(listing, profile, market)
        if self.trained:
            vector = np.array([[features[name] for name in QUALITY_FEATURES]])
            return float(self.trained["model"].predict_proba(vector)[0, 1]), features
        logit = QUALITY_PRIOR["bias"] + sum(QUALITY_PRIOR[name] * value for name, value in features.items())
        return 1 / (1 + exp(-logit)), features


def load_risk_model() -> RiskModel | None:
    return joblib.load(RISK_PATH) if RISK_PATH.exists() else None
