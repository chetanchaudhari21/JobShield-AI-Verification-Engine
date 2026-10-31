"""Company Name Normalization and Matching for JobShield AI.

Conforms to Feature F2 and Section 8 of PROJECT_SPECIFICATION.md:
- Canonical uppercase normalization
- Standardizes Indian corporate entity abbreviations (PVT LTD, OPC, LLP, etc.)
- Strips non-alphanumeric noise and standardizes punctuation (& -> AND)
- Extracts core entity stems for flexible matching
- Preserves full legal name provenance while enabling high-recall normalized queries
"""

import re
import unicodedata
from typing import Any, Dict, Optional

# Precompile regex replacements
AMPERSAND_RE = re.compile(r"&", re.UNICODE)
PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)
WHITESPACE_RE = re.compile(r"\s+")
DOTTED_INITIALS_RE = re.compile(r"(?<=[A-Za-z])\.(?=[A-Za-z])")

# Acronym and pattern standardization prior to punctuation stripping
DOTTED_PATTERNS = [
    # (OPC) or OPC variations
    (re.compile(r"\(\s*OPC\s*\)", re.IGNORECASE), " OPC "),
    # Standalone P. or (P) directly preceding Ltd or Limited
    (re.compile(r"\b\(?\s*P\s*\)?\s*\.\s*(?=\b(?:LTD|LIMITED)\b)", re.IGNORECASE), " PVT "),
    (re.compile(r"\(\s*P\s*\)\s*(?=\b(?:LTD|LIMITED)\b)", re.IGNORECASE), " PVT "),
    # Full phrases to canonical abbreviations
    (re.compile(r"\bLIMITED\s+LIABILITY\s+PARTNERSHIP\b", re.IGNORECASE), " LLP "),
]

# Word-level abbreviation expansions (applied on whole alphanumeric tokens)
WORD_EXPANSIONS = [
    (re.compile(r"\bPVT\b", re.IGNORECASE), "PRIVATE"),
    (re.compile(r"\bLTD\b", re.IGNORECASE), "LIMITED"),
    (re.compile(r"\bCORP\b", re.IGNORECASE), "CORPORATION"),
    (re.compile(r"\bINC\b", re.IGNORECASE), "INCORPORATED"),
    (re.compile(r"\bCO\b", re.IGNORECASE), "COMPANY"),
    (re.compile(r"\bMFG\b", re.IGNORECASE), "MANUFACTURING"),
]

# Trailing corporate entity suffixes for stem extraction
CORPORATE_SUFFIX_RE = re.compile(
    r"\s+\b(?:(?:OPC\s+)?PRIVATE\s+LIMITED|LIMITED|LLP|OPC\s+PRIVATE|COMPANY|CORPORATION|INCORPORATED)\b\s*$",
    re.IGNORECASE,
)


def normalize_company_name(name: Optional[str]) -> str:
    """
    Transforms a raw company or startup legal name into a canonical uppercase normalized string.

    Rules applied:
    1. Unicode normalization (NFKD to decompose compatibility characters).
    2. Conversion to uppercase.
    3. Replacement of '&' with ' AND '.
    4. Remove dots between initials/acronym letters (A.I. -> AI, L.L.P. -> LLP).
    5. Normalization of specific parenthetical and dotted forms ((OPC), (P) Ltd).
    6. Removal of punctuation and non-alphanumeric symbols.
    7. Whole-token expansion of standard abbreviations (PVT -> PRIVATE, LTD -> LIMITED, CO -> COMPANY).
    8. Collapsing of consecutive whitespaces to a single space.
    """
    if not name or not isinstance(name, str):
        return ""

    # 1. Unicode decomposition and ASCII encoding
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("utf-8")

    # 2. Uppercase
    text = text.upper().strip()

    # 3. & -> AND
    text = AMPERSAND_RE.sub(" AND ", text)

    # 4. Standardize dotted initials (A.I. -> AI, L.L.P. -> LLP, P.V.T. -> PVT)
    text = DOTTED_INITIALS_RE.sub("", text)

    # 5. Standardize parenthetical and phrase patterns
    for pattern, replacement in DOTTED_PATTERNS:
        text = pattern.sub(replacement, text)

    # 6. Remove remaining punctuation and replace with spaces
    text = PUNCTUATION_RE.sub(" ", text)

    # 7. Expand standalone abbreviation words
    for pattern, replacement in WORD_EXPANSIONS:
        text = pattern.sub(replacement, text)

    # 8. Collapse multiple whitespaces and strip boundaries
    text = WHITESPACE_RE.sub(" ", text).strip()

    return text


def extract_company_stem(normalized_name: str) -> str:
    """
    Extracts the core descriptive name stem by removing trailing corporate designator suffixes
    (e.g., 'PRIVATE LIMITED', 'LIMITED', 'LLP').

    Example:
    'INFOSYS LIMITED' -> 'INFOSYS'
    'ARYAANDARYA MANAGEMENT PRIVATE LIMITED' -> 'ARYAANDARYA MANAGEMENT'
    """
    if not normalized_name:
        return ""

    stem = CORPORATE_SUFFIX_RE.sub("", normalized_name).strip()
    return stem if stem else normalized_name


def match_company_names(query_name: str, candidate_name: str) -> Dict[str, Any]:
    """
    Compares two company names and returns match classification and confidence score.

    Match methods:
    - EXACT_LEGAL: Exact match on original string (1.0)
    - EXACT_NORMALIZED: Exact match on canonical normalized name (0.98)
    - STEM_MATCH: Match on extracted entity stem (0.85)
    - NO_MATCH: No substantial match (0.0)
    """
    trimmed_q = query_name.strip() if query_name else ""
    trimmed_c = candidate_name.strip() if candidate_name else ""

    if not trimmed_q or not trimmed_c:
        return {"is_match": False, "match_method": "NO_MATCH", "confidence": 0.0}

    # 1. Exact raw match (case-insensitive)
    if trimmed_q.upper() == trimmed_c.upper():
        return {"is_match": True, "match_method": "EXACT_LEGAL", "confidence": 1.0}

    # 2. Canonical normalized match
    norm_q = normalize_company_name(trimmed_q)
    norm_c = normalize_company_name(trimmed_c)

    if norm_q and norm_q == norm_c:
        return {"is_match": True, "match_method": "EXACT_NORMALIZED", "confidence": 0.98}

    # 3. Stem match (require at least 4 characters to avoid trivial stem matches)
    stem_q = extract_company_stem(norm_q)
    stem_c = extract_company_stem(norm_c)

    if stem_q and stem_c and len(stem_q) >= 4 and stem_q == stem_c:
        return {"is_match": True, "match_method": "STEM_MATCH", "confidence": 0.85}

    return {"is_match": False, "match_method": "NO_MATCH", "confidence": 0.0}
