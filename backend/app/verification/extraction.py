"""Clearly labelled entity name and registration identifier extraction.

Extracts company names and Corporate Identification Numbers (CIN) from clearly
labelled job description text (e.g. 'Company Name: Infosys Limited').

Strict invariants:
1. ONLY extracts from unambiguous, clearly labelled field prefixes.
2. Never infers or guesses company names from arbitrary unlabelled words.
3. Detects ambiguity when multiple conflicting labelled candidate company names
   are present and reports them as ambiguous rather than silently picking one.
4. Rejects placeholders, boilerplate text, and invalid strings.
"""

from dataclasses import dataclass, field
import re
from typing import List, Optional, Set, Tuple

from app.verification.normalization import normalize_company_name

# Regex to match clearly labelled company/employer lines
# Handles variations like:
# - Company Name: Infosys Limited
# - Company: Infosys Limited
# - - **Company Name:** Infosys Limited
# - Employer Name: Tata Consultancy Services
# - Organisation Name: Wipro Limited
# - Hiring Entity: HCL Technologies
# - Client Name: Acme Corp
LABEL_COMPANY_RE = re.compile(
    r"(?:^|[\r\n])"
    r"[ \t]*(?:[-*#>]+\s+)?"  # Optional markdown bullet, heading, quote
    r"(?:\*\*)?"  # Optional opening bold
    r"(?:"
    r"Company\s+Name"
    r"|Company"
    r"|Employer\s+Name"
    r"|Employer"
    r"|Organisation\s+Name"
    r"|Organization\s+Name"
    r"|Organisation"
    r"|Organization"
    r"|Hiring\s+Entity"
    r"|Hiring\s+Company"
    r"|Hiring\s+Organisation"
    r"|Hiring\s+Organization"
    r"|Client\s+Name"
    r"|Client"
    r")"
    r"(?:\*\*)?"  # Optional closing bold
    r"[ \t]*[:\-=][ \t]*"  # Delimiter
    r"(?:\*\*)?"  # Optional opening bold after delimiter
    r"([^\r\n]+)",  # Candidate text to end of line
    re.IGNORECASE,
)

# Standard Indian CIN pattern: 21 characters (1 char + 5 digits + 2 chars + 4 digits + 3 chars + 6 digits)
CIN_PATTERN_RE = re.compile(
    r"\b([LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6})\b",
    re.IGNORECASE,
)

# Regex to extract CIN from labelled lines
LABEL_CIN_RE = re.compile(
    r"(?:^|[\r\n])"
    r"[ \t]*(?:[-*#>]+\s+)?"
    r"(?:\*\*)?"
    r"(?:CIN|Corporate\s+Identification\s+Number|Registration\s+Number|Reg\s+No\.?)"
    r"(?:\*\*)?"
    r"[ \t]*[:\-=][ \t]*"
    r"([^\r\n]+)",
    re.IGNORECASE,
)

# Placeholder strings that are not real company names
PLACEHOLDERS: Set[str] = {
    "n/a",
    "na",
    "none",
    "unknown",
    "undisclosed",
    "confidential",
    "private",
    "not disclosed",
    "not specified",
    "anonymous",
    "company name",
    "your company name",
    "our company",
    "client",
    "client name",
    "to be announced",
    "tba",
    "tbd",
    "hidden",
}

# Secondary header delimiters on the same line that truncate the company name
SECONDARY_HEADER_RE = re.compile(
    r"\s*[|;]\s*|\s+(?:Location|Role|Title|Position|Website|Email|Industry|Sector|Experience|Salary|CTC|Notice|Department|Reporting\s+To)\s*[:\-]",
    re.IGNORECASE,
)

# Unwanted surrounding markdown/punctuation characters
SURROUNDING_CHARS = " *\"'`[](){}<>.,:;-_"


def clean_company_candidate(raw: str) -> str:
    """Cleans a raw regex match into a candidate company name."""
    if not raw:
        return ""

    # Truncate if secondary field on the same line (e.g. 'Infosys Limited | Location: Bangalore')
    truncated = SECONDARY_HEADER_RE.split(raw)[0]

    # Strip surrounding markdown, quotes, and punctuation
    cleaned = truncated.strip(SURROUNDING_CHARS).strip()

    # Collapse internal whitespace
    cleaned = re.sub(r"\s+", " ", cleaned)

    return cleaned


def is_valid_company_name(name: str) -> bool:
    """Validates whether an extracted string is a plausible company name."""
    if not name or len(name) < 2 or len(name) > 120:
        return False

    lower = name.lower()
    if lower in PLACEHOLDERS:
        return False

    # Must contain at least one ASCII letter
    if not re.search(r"[A-Za-z]", name):
        return False

    # Reject sentences/descriptions mistakenly grabbed (e.g. 'We are hiring a python developer')
    if re.search(
        r"\b(?:is looking for|is hiring|we are hiring|we are a|join our team|apply now|opportunity to work)\b",
        lower,
    ):
        return False

    return True


@dataclass
class ExtractedCompanyInfo:
    """Structured extraction outcome."""

    company_name: Optional[str]
    cin: Optional[str]
    is_name_ambiguous: bool = False
    is_cin_ambiguous: bool = False
    candidate_names: List[str] = field(default_factory=list)
    candidate_cins: List[str] = field(default_factory=list)
    extraction_notes: Optional[str] = None


def extract_company_name_from_text(text: str) -> Tuple[Optional[str], bool, List[str]]:
    """Extracts company name from clearly labelled lines in text.

    Returns:
        (company_name, is_ambiguous, candidate_names)
        - company_name: Extracted unambiguous name, or None if missing/ambiguous.
        - is_ambiguous: True if multiple conflicting distinct candidates were found.
        - candidate_names: List of all valid distinct candidates extracted.
    """
    if not text or not text.strip():
        return None, False, []

    raw_matches = LABEL_COMPANY_RE.findall(text)
    if not raw_matches:
        return None, False, []

    candidates: List[str] = []
    seen_raw: Set[str] = set()

    for m in raw_matches:
        cleaned = clean_company_candidate(m)
        if cleaned and is_valid_company_name(cleaned):
            if cleaned not in seen_raw:
                seen_raw.add(cleaned)
                candidates.append(cleaned)

    if not candidates:
        return None, False, []

    if len(candidates) == 1:
        return candidates[0], False, candidates

    # Multiple candidates: check if they normalize to the same entity
    norm_groups: dict[str, List[str]] = {}
    for cand in candidates:
        norm = normalize_company_name(cand)
        norm_groups.setdefault(norm, []).append(cand)

    if len(norm_groups) == 1:
        # All candidates resolve to the same underlying entity (e.g. 'Infosys Limited' and 'Infosys Ltd')
        # Pick the longest/most descriptive representation
        best = max(candidates, key=len)
        return best, False, candidates

    # Multiple distinct entities found -> Ambiguous
    return None, True, candidates


def extract_cin_from_text(text: str) -> Tuple[Optional[str], bool, List[str]]:
    """Extracts Corporate Identification Number (CIN) from text.

    Returns:
        (cin, is_ambiguous, candidate_cins)
    """
    if not text or not text.strip():
        return None, False, []

    # Find all CIN patterns matching standard 21-character format across text
    cins = [c.upper() for c in CIN_PATTERN_RE.findall(text)]
    unique_cins = sorted(list(set(cins)))
    if not unique_cins:
        return None, False, []

    if len(unique_cins) == 1:
        return unique_cins[0], False, unique_cins

    # Multiple distinct CINs found -> Ambiguous
    return None, True, unique_cins


def extract_company_info(
    text: str,
    explicit_company_name: Optional[str] = None,
    explicit_cin: Optional[str] = None,
) -> ExtractedCompanyInfo:
    """Master extractor resolving explicitly supplied and text-extracted company credentials.

    Priority:
    1. If explicit_company_name is non-empty, it takes precedence.
    2. Otherwise, extracts from clearly labelled text.
    3. Handles CIN explicitly supplied or extracted from text.
    4. Detects and flags ambiguity when conflicting candidates exist.
    """
    resolved_name: Optional[str] = None
    name_ambiguous = False
    name_candidates: List[str] = []
    notes: Optional[str] = None

    # 1. Company Name resolution
    if explicit_company_name and explicit_company_name.strip():
        clean_exp = explicit_company_name.strip()
        if is_valid_company_name(clean_exp):
            resolved_name = clean_exp
            name_candidates = [clean_exp]
        elif clean_exp.lower() in PLACEHOLDERS:
            # Explicit placeholder provided
            resolved_name = None
            name_candidates = [clean_exp]
            notes = f"Explicit company name '{clean_exp}' is an uninformative placeholder."
    else:
        # Extract from text
        extracted_name, is_ambig, candidates = extract_company_name_from_text(text)
        name_candidates = candidates
        if is_ambig:
            name_ambiguous = True
            resolved_name = None
            notes = f"Ambiguous company name: multiple conflicting candidates identified in text: {candidates}"
        else:
            resolved_name = extracted_name

    # 2. CIN resolution
    resolved_cin: Optional[str] = None
    cin_ambiguous = False
    cin_candidates: List[str] = []

    if explicit_cin and explicit_cin.strip():
        clean_cin = explicit_cin.strip().upper()
        if CIN_PATTERN_RE.match(clean_cin):
            resolved_cin = clean_cin
            cin_candidates = [clean_cin]
        else:
            # Invalid CIN format supplied
            resolved_cin = None
            notes = (notes or "") + f" Explicit CIN '{clean_cin}' does not match standard 21-character format."
    else:
        extracted_cin, is_cin_ambig, c_cins = extract_cin_from_text(text)
        cin_candidates = c_cins
        if is_cin_ambig:
            cin_ambiguous = True
            resolved_cin = None
            notes = (notes or "") + f" Ambiguous CIN: multiple distinct CINs identified: {c_cins}"
        else:
            resolved_cin = extracted_cin

    return ExtractedCompanyInfo(
        company_name=resolved_name,
        cin=resolved_cin,
        is_name_ambiguous=name_ambiguous,
        is_cin_ambiguous=cin_ambiguous,
        candidate_names=name_candidates,
        candidate_cins=cin_candidates,
        extraction_notes=notes.strip() if notes else None,
    )
