"""Bayesian Company Reputation and Community Statistics Service (F8 & F9).

Conforms strictly to Section 8 & 9 of PROJECT_SPECIFICATION.md:
- Computes Bayesian reputation score: R = (n / (n + m)) * r_bar + (m / (n + m)) * C
- Configurable prior parameters m (strength) and C (mean rating) via app.core.config.settings
- Explicit confidence score: n / (n + m) in [0.0, 1.0)
- Excludes pending, rejected, flagged, and duplicate reviews from n and r_bar
- Provides 1-5 star distribution histogram
- Strictly isolates fraud allegations / recruiter reports from 1-5 star service ratings:
  Fraud reports are counted separately and NEVER converted into stars or fraud probabilities.
"""

import logging
from typing import Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.community import RecruiterReport, UserReview
from app.models.company import Company
from app.schemas.community import CompanyReputationResponse, UserReviewResponse
from app.services.recruiter_checker import mask_email

logger = logging.getLogger("jobshield.community.reputation")


def calculate_bayesian_reputation(
    approved_ratings: List[int],
    prior_m: Optional[float] = None,
    prior_c: Optional[float] = None,
) -> Dict[str, float]:
    """Calculates Bayesian damped reputation from a list of approved 1-5 ratings.

    Formula:
        R = (n / (n + m)) * r_bar + (m / (n + m)) * C
    Confidence:
        confidence = n / (n + m)

    Parameters:
        approved_ratings: List of integer ratings (1 to 5)
        prior_m: Prior strength (weight), defaults to settings.REPUTATION_PRIOR_STRENGTH_M
        prior_c: Prior mean rating, defaults to settings.REPUTATION_PRIOR_MEAN_C
    """
    m = float(prior_m if prior_m is not None else settings.REPUTATION_PRIOR_STRENGTH_M)
    c = float(prior_c if prior_c is not None else settings.REPUTATION_PRIOR_MEAN_C)

    if m <= 0:
        raise ValueError(f"Prior strength m must be positive, got {m}")
    if not (1.0 <= c <= 5.0):
        raise ValueError(f"Prior mean C must be between 1.0 and 5.0, got {c}")

    n = len(approved_ratings)

    if n == 0:
        return {
            "total_approved_reviews": 0,
            "raw_mean_rating": None,
            "bayesian_rating": round(c, 2),
            "prior_strength_m": m,
            "prior_mean_c": c,
            "confidence_score": 0.0,
        }

    raw_mean = sum(approved_ratings) / float(n)
    bayesian_score = ((n / (n + m)) * raw_mean) + ((m / (n + m)) * c)
    confidence = n / (n + m)

    return {
        "total_approved_reviews": n,
        "raw_mean_rating": round(raw_mean, 2),
        "bayesian_rating": round(bayesian_score, 2),
        "prior_strength_m": m,
        "prior_mean_c": c,
        "confidence_score": round(confidence, 4),
    }


def get_company_reputation(
    db: Session,
    company_id: int,
    limit_recent: int = 5,
) -> Optional[CompanyReputationResponse]:
    """Retrieves aggregated Bayesian reputation, distribution, and fraud reports for a company."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return None

    # Query approved reviews (exclude pending, rejected, flagged)
    approved_reviews_query = (
        db.query(UserReview)
        .filter(
            UserReview.company_id == company_id,
            func.upper(UserReview.moderation_status) == "APPROVED",
        )
        .order_by(UserReview.created_at.desc())
    )

    approved_reviews = approved_reviews_query.all()
    approved_ratings = [r.rating for r in approved_reviews]

    # Calculate Bayesian metrics
    metrics = calculate_bayesian_reputation(approved_ratings)

    # Calculate rating distribution (1 to 5)
    distribution: Dict[str, int] = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    for r in approved_ratings:
        star_key = str(r)
        if star_key in distribution:
            distribution[star_key] += 1

    # Query fraud allegations (recruiter reports) - KEPT STRICTLY SEPARATE
    fraud_reports = (
        db.query(RecruiterReport)
        .filter(RecruiterReport.company_id == company_id)
        .all()
    )

    fraud_reports_count = len(fraud_reports)
    fraud_by_type: Dict[str, int] = {}
    for rep in fraud_reports:
        rep_type = rep.report_type or "other"
        fraud_by_type[rep_type] = fraud_by_type.get(rep_type, 0) + 1

    # Recent reviews
    recent_items: List[UserReviewResponse] = []
    for r in approved_reviews[:limit_recent]:
        recent_items.append(
            UserReviewResponse(
                id=r.id,
                company_id=r.company_id,
                company_name=company.legal_name,
                recruiter_email_masked=None,
                scan_id=r.scan_id,
                rating=r.rating,
                category=r.experience_category,
                review_text=r.review_text,
                status=r.moderation_status,
                created_at=r.created_at,
            )
        )

    return CompanyReputationResponse(
        company_id=company.id,
        company_name=company.legal_name,
        total_approved_reviews=metrics["total_approved_reviews"],
        raw_mean_rating=metrics["raw_mean_rating"],
        bayesian_rating=metrics["bayesian_rating"],
        prior_strength_m=metrics["prior_strength_m"],
        prior_mean_c=metrics["prior_mean_c"],
        confidence_score=metrics["confidence_score"],
        rating_distribution=distribution,
        fraud_reports_count=fraud_reports_count,
        fraud_reports_by_type=fraud_by_type,
        recent_reviews=recent_items,
    )
