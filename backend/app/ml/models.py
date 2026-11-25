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
from ..rules import REPLY, RISK
from ..text import red_flags
from .features import QUALITY_FEATURES, TEXT_FLAGS, description_length, listing_text, quality_features, text_flag_vector

RISK_PATH = MODEL_DIR / "risk_model.joblib"
QUALITY_PATH = MODEL_DIR / "quality_model.joblib"

# rules.toml [risk]: assumed share of scams without evidence; characters of description needed
# before the text model's verdict counts fully; weight of the red-flag phrases in the text model.
BASE_RATE = RISK["base_rate"]
FULL_TEXT_EVIDENCE = RISK["full_text_evidence"]
RED_FLAG_SCALE = RISK["red_flag_scale"]


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
        flags = csr_matrix(np.array([text_flag_vector(l) for l in listings]) * RED_FLAG_SCALE)
        return hstack([text_part, flags]).tocsr()

    def fit(self, listings: list[dict], labels: list[int]) -> "RiskModel":
        self.classifier.fit(self._matrix(listings, fit=True), labels)
        return self

    def predict(self, listings: list[dict]) -> list[float]:
        if not listings:
            return []
        return self.classifier.predict_proba(self._matrix(listings))[:, 1].tolist()

    def flag_weights(self) -> dict[str, float]:
        return dict(zip(TEXT_FLAGS, self.classifier.coef_[0][-len(TEXT_FLAGS):] * RED_FLAG_SCALE))

    def save(self) -> None:
        joblib.dump(self, RISK_PATH)


def fallback_text_probability(listing: dict) -> float:
    """Used only before the first training run: red-flag phrases with fixed weights (rules.toml
    [risk.text_fallback])."""
    weights = RISK["text_fallback"]
    flags = dict(zip(TEXT_FLAGS, text_flag_vector(listing)))
    return sigmoid(weights["bias"] + sum(weights.get(flag, 0.0) * value for flag, value in flags.items()))


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


# Prior weights for the quality model (log-odds): rules.toml [reply] and [reply.factors]. They
# encode the team's assumptions until real reply labels exist.
QUALITY_PRIOR = {"bias": REPLY["bias"], **{name: rule["weight"] for name, rule in REPLY["factors"].items()}}


class QualityModel:
    def __init__(self):
        self.trained = joblib.load(QUALITY_PATH) if QUALITY_PATH.exists() else None
        if self.trained and self.trained["model"].coef_.shape[1] != len(QUALITY_FEATURES):
            self.trained = None  # trained before features were added: use the prior until it's retrained
        self.version = self.trained["version"] if self.trained else "quality-prior-v0"

    def weights(self) -> dict[str, float]:
        """Log-odds weight per feature: learned if a trained model exists, otherwise the prior."""
        if self.trained:
            return dict(zip(QUALITY_FEATURES, self.trained["model"].coef_[0].tolist()))
        return {name: QUALITY_PRIOR[name] for name in QUALITY_FEATURES}

    def predict(self, listing: dict, profile: dict, market: dict) -> tuple[float, dict[str, float]]:
        features = quality_features(listing, profile, market)
        if self.trained:
            vector = np.array([[features[name] for name in QUALITY_FEATURES]])
            return float(self.trained["model"].predict_proba(vector)[0, 1]), features
        logit = QUALITY_PRIOR["bias"] + sum(QUALITY_PRIOR[name] * value for name, value in features.items())
        return 1 / (1 + exp(-logit)), features


def load_risk_model() -> RiskModel | None:
    return joblib.load(RISK_PATH) if RISK_PATH.exists() else None
