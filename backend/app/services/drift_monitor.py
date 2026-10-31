"""Privacy-Preserving Drift Monitoring Engine for JobShield AI.

Conforms to Section 5.12 (Feature F12) & Section 16 of PROJECT_SPECIFICATION.md:
- Strictly privacy-preserving: aggregates prediction metadata and score distributions.
- NEVER records or inspects raw job descriptions, emails, offer letters, or personal information.
- Compares observed inference distributions against baseline validation benchmarks.
- Calculates Population Stability Index (PSI) and category divergence.
- Explicitly treats drift as an observational warning for human review, NOT proof of model failure.
"""

from datetime import datetime, timedelta, timezone
import logging
import math
from typing import Any, Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.prediction import PredictionHistory
from app.models.scan import ScanRequest

logger = logging.getLogger("jobshield.ml.drift")

# Baseline expected distribution from validation split (EMSCAD v1.1.0)
BASELINE_CATEGORY_DISTRIBUTION = {
    "LOW": 0.85,
    "MODERATE": 0.08,
    "HIGH": 0.04,
    "CRITICAL": 0.03,
}

DRIFT_DISCLAIMER = (
    "Drift monitoring tracks aggregate statistical shifts in risk scores and category frequencies over time. "
    "Distribution drift indicates changes in incoming submission characteristics (e.g. seasonal shifts, new scam variants), "
    "NOT proof of model degradation. Drift alerts serve strictly as human-in-the-loop warnings and NEVER trigger "
    "automated retraining or unattended weight updates."
)


def calculate_psi(expected: List[float], actual: List[float], epsilon: float = 1e-4) -> float:
    """Calculates the Population Stability Index (PSI) between two discrete distributions."""
    psi = 0.0
    for e, a in zip(expected, actual):
        e_safe = max(e, epsilon)
        a_safe = max(a, epsilon)
        psi += (a_safe - e_safe) * math.log(a_safe / e_safe)
    return float(psi)


def get_privacy_preserving_drift_metrics(
    db: Session,
    window_days: int = 30,
) -> Dict[str, Any]:
    """Computes privacy-preserving aggregate distribution metrics across recent predictions.

    PRIVACY GUARANTEE:
    This function reads solely from `prediction_history` and `scan_requests`.
    It computes mathematical aggregates (counts, means, quantiles).
    No raw submitted text, candidate PII, or document contents are ever retrieved or exposed.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    # 1. Total volume in window
    query = db.query(PredictionHistory).filter(PredictionHistory.created_at >= cutoff)
    total_predictions = query.count()

    # 2. Risk Category Distribution
    category_counts_raw = (
        db.query(
            PredictionHistory.risk_category,
            func.count(PredictionHistory.id),
        )
        .filter(PredictionHistory.created_at >= cutoff)
        .group_by(PredictionHistory.risk_category)
        .all()
    )
    category_counts = {cat: count for cat, count in category_counts_raw}

    categories = ["LOW", "MODERATE", "HIGH", "CRITICAL", "INSUFFICIENT_EVIDENCE"]
    category_fractions = {}
    for cat in categories:
        count = category_counts.get(cat, 0)
        category_fractions[cat] = round(count / total_predictions, 4) if total_predictions > 0 else 0.0

    # 3. Numeric Score Distribution Aggregates (Mean, Min, Max)
    score_aggregates = (
        db.query(
            func.avg(PredictionHistory.risk_score),
            func.min(PredictionHistory.risk_score),
            func.max(PredictionHistory.risk_score),
            func.avg(PredictionHistory.model_probability),
        )
        .filter(PredictionHistory.created_at >= cutoff, PredictionHistory.risk_score >= 0)
        .first()
    )

    avg_score = round(float(score_aggregates[0]), 2) if score_aggregates and score_aggregates[0] is not None else None
    min_score = round(float(score_aggregates[1]), 2) if score_aggregates and score_aggregates[1] is not None else None
    max_score = round(float(score_aggregates[2]), 2) if score_aggregates and score_aggregates[2] is not None else None
    avg_prob = round(float(score_aggregates[3]), 4) if score_aggregates and score_aggregates[3] is not None else None

    # 4. Input Type Volume Breakdown (from scan_requests)
    type_counts_raw = (
        db.query(
            ScanRequest.input_type,
            func.count(ScanRequest.id),
        )
        .filter(ScanRequest.created_at >= cutoff)
        .group_by(ScanRequest.input_type)
        .all()
    )
    input_type_distribution = {t: count for t, count in type_counts_raw}

    # 5. PSI Calculation against Baseline
    # Expected vs Actual probabilities for standard 4 categories
    expected_probs = [
        BASELINE_CATEGORY_DISTRIBUTION["LOW"],
        BASELINE_CATEGORY_DISTRIBUTION["MODERATE"],
        BASELINE_CATEGORY_DISTRIBUTION["HIGH"],
        BASELINE_CATEGORY_DISTRIBUTION["CRITICAL"],
    ]

    # Normalize actual distribution excluding INSUFFICIENT_EVIDENCE for baseline comparison
    eval_total = sum(category_counts.get(c, 0) for c in ["LOW", "MODERATE", "HIGH", "CRITICAL"])
    if eval_total > 0:
        actual_probs = [
            category_counts.get("LOW", 0) / eval_total,
            category_counts.get("MODERATE", 0) / eval_total,
            category_counts.get("HIGH", 0) / eval_total,
            category_counts.get("CRITICAL", 0) / eval_total,
        ]
        psi = round(calculate_psi(expected_probs, actual_probs), 4)
    else:
        psi = 0.0

    # 6. Drift Classification
    if total_predictions < 10:
        drift_status = "INSUFFICIENT_DATA"
        drift_severity = "INFO"
        drift_message = f"Sample size ({total_predictions} predictions in {window_days} days) is insufficient to compute statistically reliable distribution drift."
    elif psi < 0.10:
        drift_status = "NORMAL"
        drift_severity = "LOW"
        drift_message = f"Population Stability Index (PSI={psi:.4f}) indicates stable prediction score distribution consistent with baseline training data."
    elif psi < 0.25:
        drift_status = "WARNING"
        drift_severity = "MODERATE"
        drift_message = f"Moderate distribution shift detected (PSI={psi:.4f}). Review incoming job fraud trends to determine if vocabulary patterns have evolved."
    else:
        drift_status = "DRIFT_DETECTED"
        drift_severity = "HIGH"
        drift_message = f"Significant distribution shift observed (PSI={psi:.4f}). Candidate opportunity patterns have diverged from baseline. Human review recommended."

    return {
        "window_days": window_days,
        "sample_size": total_predictions,
        "drift_status": drift_status,
        "drift_severity": drift_severity,
        "psi_score": psi,
        "message": drift_message,
        "risk_category_distribution": {
            "counts": category_counts,
            "fractions": category_fractions,
        },
        "score_statistics": {
            "mean_risk_score": avg_score,
            "min_risk_score": min_score,
            "max_risk_score": max_score,
            "mean_calibrated_probability": avg_prob,
        },
        "input_type_distribution": input_type_distribution,
        "baseline_comparison": {
            "baseline_low_fraud_prevalence": BASELINE_CATEGORY_DISTRIBUTION["LOW"],
            "observed_low_risk_fraction": category_fractions.get("LOW", 0.0),
        },
        "disclaimer": DRIFT_DISCLAIMER,
    }
