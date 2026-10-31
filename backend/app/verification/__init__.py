"""
Evidence-based verification logic (MCA, Startup India, DNS/MX, lookalike domains).
"""
from app.verification.normalization import (
    extract_company_stem,
    match_company_names,
    normalize_company_name,
)

__all__ = [
    "normalize_company_name",
    "extract_company_stem",
    "match_company_names",
]
