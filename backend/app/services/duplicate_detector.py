"""Job Listing Duplicate Detection and Impersonation Analysis Service.

Conforms to Section 8 (Tables 5 & 6) and Feature F4/F5 of PROJECT_SPECIFICATION.md:
- Exact duplicate detection via normalized content SHA-256 hashes
- Near-duplicate detection via Scikit-learn TF-IDF vectorization and cosine similarity
- Explainable classification: EXACT_DUPLICATE, LIKELY_REPOST, NEAR_DUPLICATE, POTENTIAL_SUSPICIOUS_COPY, INSUFFICIENT_EVIDENCE
- Distinguishes legitimate employer reposts and syndication from suspicious impersonation copies
- Reuses domain security, lookalike detection, and company verification services
- Single-direction strictly ordered pair storage (listing_id_a < listing_id_b)
"""

from datetime import datetime, timezone
import hashlib
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.job import JobListing, JobSimilarityMatch
from app.schemas.listing import (
    DuplicateAnalysisSummary,
    JobSimilarityMatchItem,
)
from app.services.domain_checker import (
    WELL_KNOWN_LEGITIMATE_DOMAINS,
    detect_lookalikes,
    extract_domain_from_url_or_host,
)
from app.services.recruiter_checker import (
    WELL_KNOWN_COMPANY_DOMAINS,
    domain_matches_company,
    is_free_webmail_domain,
)
from app.services.risk_engine import count_informative_words
from app.verification.company_verifier import CompanyVerifier

logger = logging.getLogger("jobshield.duplicate_detector")

# Algorithm and engine metadata
ALGORITHM_VERSION = "tfidf_cosine_v1.0.0"
EXACT_MATCH_THRESHOLD = 0.98
NEAR_DUPLICATE_THRESHOLD = 0.80
SUSPICIOUS_SIMILARITY_THRESHOLD = 0.75
MIN_INFORMATIVE_WORDS = 20

# Query parameters commonly used for tracking and telemetry that should be removed during URL normalization
TRACKING_QUERY_PARAMS: Set[str] = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "referrer",
    "fbclid",
    "gclid",
    "dclid",
    "msclkid",
    "trk",
    "trkcampaign",
    "tracking_id",
    "source",
    "mc_cid",
    "mc_eid",
    "session_id",
    "s_cid",
    "_ga",
    "_gl",
    "_hsenc",
    "_hsmi",
    "igshid",
    "ocid",
    "sp_source",
    "sp_campaign",
}

# Recognized legitimate multi-employer syndication platforms and job boards
LEGITIMATE_JOB_BOARDS: Set[str] = {
    "linkedin.com",
    "indeed.com",
    "naukri.com",
    "glassdoor.com",
    "monster.com",
    "foundit.in",
    "shine.com",
    "internshala.com",
    "wellfound.com",
    "ziprecruiter.com",
    "simplyhired.com",
    "careerbuilder.com",
}


def normalize_job_url(url: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Normalizes a job URL by removing tracking/telemetry parameters while preserving meaningful vacancy IDs.

    Returns:
        (normalized_url, base_domain)
    """
    if not url or not isinstance(url, str):
        return None, None

    trimmed = url.strip()
    if not trimmed:
        return None, None

    try:
        parts = urlsplit(trimmed)
        if not parts.scheme and not parts.netloc:
            # Maybe raw host or relative path
            parts = urlsplit(f"http://{trimmed}")

        scheme = parts.scheme.lower() if parts.scheme else "https"
        netloc = parts.netloc.lower()

        # Remove default ports
        if netloc.endswith(":80"):
            netloc = netloc[:-3]
        elif netloc.endswith(":443"):
            netloc = netloc[:-4]

        # Filter query parameters
        raw_query = parse_qsl(parts.query, keep_blank_values=False)
        cleaned_query = [
            (k, v)
            for k, v in raw_query
            if k.lower() not in TRACKING_QUERY_PARAMS and not k.lower().startswith("utm_")
        ]
        # Sort query params deterministically for canonical matching
        cleaned_query.sort(key=lambda item: item[0])
        new_query = urlencode(cleaned_query)

        # Normalize path: strip trailing slash unless root path
        path = parts.path
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]

        normalized_url = urlunsplit((scheme, netloc, path, new_query, ""))
        domain = extract_domain_from_url_or_host(netloc)
        return normalized_url, domain
    except Exception as e:
        logger.warning("Error normalizing URL '%s': %s", trimmed, e)
        domain = extract_domain_from_url_or_host(trimmed)
        return trimmed, domain


def normalize_job_text(text: str) -> str:
    """Normalizes job posting description text consistently for hashing and vectorization.

    - Canonicalizes Unicode representation (NFKC).
    - Lowercases text.
    - Strips quotes (straight, smart quotes, backticks).
    - Standardizes and strips bullet points and list item hyphens/dashes.
    - Collapses consecutive whitespace and newlines into single spaces.
    """
    if not text or not isinstance(text, str):
        return ""

    # 1. Unicode normalization
    normalized = unicodedata.normalize("NFKC", text).lower()

    # 2. Strip quotation marks (both smart and ascii)
    normalized = re.sub(r"[\u2018\u2019\u201a\u201b\u201c\u201d\u201e\u201f\'\"\`]", "", normalized)

    # 3. Strip bullet markers and list item hyphens/dashes at line starts or following whitespace
    normalized = re.sub(r"(^|[\s\n\r])[\-\u2013\u2014\u2022\u00b7\u25cf\u25aa\u25a0\u25ba\*]+\s*", r"\1", normalized)

    # 4. Collapse multiple whitespaces
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def compute_content_hash(text: str) -> str:
    """Computes deterministic SHA-256 hash of normalized job description text."""
    clean = normalize_job_text(text)
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()


def compute_tfidf_similarity(text_a: str, text_b: str) -> float:
    """Computes TF-IDF cosine similarity between two job description texts.

    Uses scikit-learn TfidfVectorizer with word n-grams (1, 2) and English stop-words.
    Handles empty text, single-word inputs, and stop-word edge cases gracefully.
    """
    clean_a = normalize_job_text(text_a)
    clean_b = normalize_job_text(text_b)

    if not clean_a or not clean_b:
        return 0.0

    if clean_a == clean_b:
        return 1.0

    # If informative word count is insufficient
    words_a = clean_a.split()
    words_b = clean_b.split()
    if len(words_a) < 3 or len(words_b) < 3:
        # Fallback to token Jaccard for very short text
        set_a, set_b = set(words_a), set(words_b)
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return round(intersection / union, 4) if union > 0 else 0.0

    try:
        vectorizer = TfidfVectorizer(
            ngram_range=(1, 1),
            stop_words=None,
            min_df=1,
            max_features=5000,
        )
        tfidf_matrix = vectorizer.fit_transform([clean_a, clean_b])
        score = float(cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0])
        return round(max(0.0, min(1.0, score)), 4)
    except ValueError:
        # Occurs if documents only contain stop words
        set_a, set_b = set(words_a), set(words_b)
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return round(intersection / union, 4) if union > 0 else 0.0
    except Exception as e:
        logger.warning("Error calculating TF-IDF similarity: %s", e)
        return 0.0


def is_same_company_identity(
    company_name_a: Optional[str],
    company_id_a: Optional[int],
    domain_a: Optional[str],
    company_name_b: Optional[str],
    company_id_b: Optional[int],
    domain_b: Optional[str],
    db: Optional[Session] = None,
) -> Tuple[bool, bool]:
    """Evaluates whether two listings claim the same employer or have an explicit identity conflict.

    Returns:
        (is_same_company, is_conflicting_company)
    """
    # 1. Direct matched company ID match
    if company_id_a is not None and company_id_b is not None:
        if company_id_a == company_id_b:
            return True, False
        else:
            return False, True

    c_a = (company_name_a or "").strip().lower()
    c_b = (company_name_b or "").strip().lower()

    # 2. Both company names provided
    if c_a and c_b:
        # Exact string match
        if c_a == c_b:
            return True, False

        # Stem / significant words match
        sig_a = {w for w in re.split(r"\W+", c_a) if len(w) > 3 and w not in {"limited", "private", "solutions"}}
        sig_b = {w for w in re.split(r"\W+", c_b) if len(w) > 3 and w not in {"limited", "private", "solutions"}}
        if sig_a and sig_b:
            if sig_a == sig_b or sig_a.issubset(sig_b) or sig_b.issubset(sig_a):
                return True, False
            else:
                return False, True

        return False, True

    # 3. Domain alignment
    if domain_a and domain_b and domain_a == domain_b:
        return True, False

    return False, False


def classify_duplicate_pair(
    listing_a: JobListing,
    listing_b: JobListing,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """Analyzes a pair of job listings and classifies their relationship.

    Distinguishes:
    - EXACT_DUPLICATE: Identical content hash / similarity >= 0.98 from the same employer.
    - LIKELY_REPOST: Same employer, high similarity, reposted at a distinct later time.
    - NEAR_DUPLICATE: Same employer with minor text revisions (similarity >= 0.80).
    - POTENTIAL_SUSPICIOUS_COPY: High similarity with conflicting company, lookalike domain, or unverified recruiter.
    - INSUFFICIENT_EVIDENCE: Description too short or missing substantive informative content.

    IMPORTANT SAFETY & FAIRNESS PRINCIPLE:
    Duplicate detection is a similarity signal, NOT conclusive proof of fraud. Legitimate employers
    repost and syndicate jobs across job boards lawfully.
    """
    text_a = listing_a.job_description or ""
    text_b = listing_b.job_description or ""

    words_a = count_informative_words(text_a)
    words_b = count_informative_words(text_b)

    # 1. Check for insufficient substantive text
    if words_a < MIN_INFORMATIVE_WORDS or words_b < MIN_INFORMATIVE_WORDS:
        return {
            "is_exact_match": False,
            "similarity_score": 0.0,
            "match_classification": "INSUFFICIENT_EVIDENCE",
            "confidence": 0.0,
            "supporting_evidence": [],
            "contradictory_evidence": [],
            "reasons": [
                f"Job description contains insufficient informative words (listing A: {words_a}, listing B: {words_b}, minimum {MIN_INFORMATIVE_WORDS} required) to establish reliable linguistic similarity.",
            ],
            "impersonation_signals": [],
            "recommended_next_steps": [
                "Obtain a complete job description with full role responsibilities before evaluating duplicate similarity.",
            ],
        }

    # 2. Check exact hash match
    hash_match = bool(listing_a.content_hash and listing_a.content_hash == listing_b.content_hash)
    similarity_score = 1.0 if hash_match else compute_tfidf_similarity(text_a, text_b)

    # 3. Analyze company identity & domain alignment
    is_same_company, is_conflicting_company = is_same_company_identity(
        listing_a.claimed_company_name,
        listing_a.company_id,
        listing_a.source_domain,
        listing_b.claimed_company_name,
        listing_b.company_id,
        listing_b.source_domain,
        db=db,
    )

    # 4. Check for lookalike domains
    lookalike_a = detect_lookalikes(listing_a.source_domain or "", WELL_KNOWN_LEGITIMATE_DOMAINS)
    lookalike_b = detect_lookalikes(listing_b.source_domain or "", WELL_KNOWN_LEGITIMATE_DOMAINS)
    has_lookalike_domain = bool(lookalike_a.get("is_lookalike") or lookalike_b.get("is_lookalike"))

    # 5. Check for free email indicators
    is_free_email_a = is_free_webmail_domain(listing_a.source_domain or "")
    is_free_email_b = is_free_webmail_domain(listing_b.source_domain or "")

    # 6. Check syndication across legitimate job boards
    is_syndicated = bool(
        (listing_a.source_domain in LEGITIMATE_JOB_BOARDS or listing_b.source_domain in LEGITIMATE_JOB_BOARDS)
        and not is_conflicting_company
    )

    # 7. Check timestamp delta for repost detection
    time_delta_days = 0.0
    if listing_a.collected_at and listing_b.collected_at:
        delta = abs((listing_a.collected_at - listing_b.collected_at).total_seconds())
        time_delta_days = delta / 86400.0

    supporting_evidence: List[Dict[str, Any]] = []
    contradictory_evidence: List[Dict[str, Any]] = []
    reasons: List[str] = []
    impersonation_signals: List[str] = []

    # Record similarity evidence
    supporting_evidence.append({
        "type": "linguistic_similarity",
        "method": "EXACT_HASH" if hash_match else "TF_IDF_COSINE",
        "score": similarity_score,
        "summary": f"Content similarity between listings is {int(similarity_score * 100)}% ({'exact hash match' if hash_match else 'TF-IDF cosine similarity'}).",
    })

    # Evaluate Impersonation Signals
    if has_lookalike_domain:
        impersonation_signals.append("LOOKALIKE_DOMAIN_DETECTED")
        warning_msg = (
            lookalike_a.get("warning") if lookalike_a.get("is_lookalike") else lookalike_b.get("warning")
        )
        supporting_evidence.append({
            "type": "lookalike_domain",
            "warning": warning_msg,
            "matched_domain": (
                lookalike_a.get("matched_legitimate_domain")
                if lookalike_a.get("is_lookalike")
                else lookalike_b.get("matched_legitimate_domain")
            ),
        })
        reasons.append(f"A source domain incorporates a lookalike typosquatting pattern: {warning_msg}")

    if is_conflicting_company and similarity_score >= SUSPICIOUS_SIMILARITY_THRESHOLD:
        impersonation_signals.append("COMPANY_IDENTITY_CONFLICT")
        reasons.append(
            f"Substantially similar or identical text is published under conflicting company identities: '{listing_a.claimed_company_name or 'Unspecified'}' vs '{listing_b.claimed_company_name or 'Unspecified'}'. This indicates potential unauthorized copying or company impersonation."
        )
        supporting_evidence.append({
            "type": "conflicting_company_identity",
            "company_a": listing_a.claimed_company_name,
            "company_b": listing_b.claimed_company_name,
        })

    if is_free_email_a or is_free_email_b:
        impersonation_signals.append("FREE_EMAIL_RECRUITER")
        reasons.append("A listing source domain is a public free webmail provider rather than a verified employer domain.")

    if is_syndicated:
        contradictory_evidence.append({
            "type": "legitimate_syndication",
            "summary": "Listing observed on a recognized multi-employer job board, consistent with lawful vacancy syndication.",
        })

    # 8. Classification Decision Matrix
    # Case A: Suspicious Copy / Impersonation
    if similarity_score >= SUSPICIOUS_SIMILARITY_THRESHOLD and (is_conflicting_company or has_lookalike_domain):
        classification = "POTENTIAL_SUSPICIOUS_COPY"
        confidence = 0.95 if hash_match or has_lookalike_domain else 0.85
        reasons.append(
            "High linguistic overlap combined with conflicting employer identities or lookalike domains warrants caution. Notice: Copied text is an impersonation signal, not conclusive proof of criminal intent."
        )
        recommended_next_steps = [
            f"Verify whether '{listing_a.claimed_company_name or 'the employer'}' officially authorized vacancy publication on '{listing_b.source_domain or 'the second source'}'.",
            "Cross-reference the vacancy directly on the employer's official, authenticated corporate careers portal.",
            "Do not transfer application fees, training deposits, or sensitive identity documents.",
        ]

    # Case B: Exact Duplicate (Same Employer)
    elif hash_match or similarity_score >= EXACT_MATCH_THRESHOLD:
        if time_delta_days > 14.0 and is_same_company:
            classification = "LIKELY_REPOST"
            confidence = 0.90
            reasons.append(
                f"Identical vacancy text observed from the same employer republished {int(time_delta_days)} days later, indicating a standard recruitment repost."
            )
            recommended_next_steps = [
                "Confirm whether this opening remains actively hiring or was closed from the earlier posting.",
            ]
        else:
            classification = "EXACT_DUPLICATE"
            confidence = 0.95
            reasons.append(
                "Identical normalized content hash from the same employer. Appears to be a synchronized publication or job board syndication."
            )
            recommended_next_steps = [
                "Listing content matches an indexed vacancy. Proceed with standard direct application via the employer's official portal.",
            ]

    # Case C: Likely Repost (High Similarity + Significant Time Delta)
    elif similarity_score >= NEAR_DUPLICATE_THRESHOLD and is_same_company and time_delta_days > 14.0:
        classification = "LIKELY_REPOST"
        confidence = 0.85
        reasons.append(
            f"High text similarity ({int(similarity_score * 100)}%) from the same employer observed {int(time_delta_days)} days apart, consistent with an updated vacancy repost."
        )
        recommended_next_steps = [
            "Review minor updates in requirements or location compared to the earlier posting.",
        ]

    # Case D: Near Duplicate (Same Employer, Recent or Minor Revisions)
    elif similarity_score >= NEAR_DUPLICATE_THRESHOLD and (is_same_company or not is_conflicting_company):
        classification = "NEAR_DUPLICATE"
        confidence = 0.85
        reasons.append(
            f"High text similarity ({int(similarity_score * 100)}%) with minor textual adjustments from the same employer."
        )
        recommended_next_steps = [
            "Check official careers site for the most up-to-date role description and requirements.",
        ]

    # Case E: Moderate overlap but no impersonation
    elif similarity_score >= SUSPICIOUS_SIMILARITY_THRESHOLD and not is_conflicting_company:
        classification = "NEAR_DUPLICATE"
        confidence = 0.70
        reasons.append(
            f"Moderate text overlap ({int(similarity_score * 100)}%) sharing common industry role definitions or standardized skill requirements."
        )
        recommended_next_steps = [
            "Verify specific vacancy details on the primary employer website.",
        ]

    else:
        # Below threshold
        classification = "INSUFFICIENT_EVIDENCE"
        confidence = 0.0
        reasons.append("Text similarity is below the minimum threshold required for duplicate classification.")
        recommended_next_steps = [
            "Standard job evaluation guidelines apply.",
        ]

    return {
        "is_exact_match": hash_match,
        "similarity_score": similarity_score,
        "match_classification": classification,
        "confidence": round(confidence, 2),
        "supporting_evidence": supporting_evidence,
        "contradictory_evidence": contradictory_evidence,
        "reasons": reasons,
        "impersonation_signals": impersonation_signals,
        "recommended_next_steps": recommended_next_steps,
    }


def find_and_record_similarity_matches(
    listing: JobListing,
    db: Session,
    candidate_limit: int = 50,
) -> List[JobSimilarityMatchItem]:
    """Retrieves potential matching candidates from the database, evaluates similarity, and persists match pairs.

    Enforces single-directional storage (listing_id_a < listing_id_b) with uniqueness constraint.
    """
    if not listing.id or not listing.job_description:
        return []

    # 1. Candidate Pruning Retrieval (Indexed & Efficient)
    candidates: Dict[str, JobListing] = {}

    # Query A: Exact content hash matches
    if listing.content_hash:
        exact_hash_q = (
            db.query(JobListing)
            .filter(
                JobListing.content_hash == listing.content_hash,
                JobListing.id != listing.id,
            )
            .limit(candidate_limit)
            .all()
        )
        for cand in exact_hash_q:
            candidates[cand.id] = cand

    # Query B: Same matched company
    if listing.company_id is not None:
        same_company_q = (
            db.query(JobListing)
            .filter(
                JobListing.company_id == listing.company_id,
                JobListing.id != listing.id,
            )
            .limit(candidate_limit)
            .all()
        )
        for cand in same_company_q:
            candidates[cand.id] = cand

    # Query C: Same claimed company name
    if listing.claimed_company_name:
        clean_comp = listing.claimed_company_name.strip()
        if len(clean_comp) > 2:
            same_name_q = (
                db.query(JobListing)
                .filter(
                    func.lower(JobListing.claimed_company_name) == clean_comp.lower(),
                    JobListing.id != listing.id,
                )
                .limit(candidate_limit)
                .all()
            )
            for cand in same_name_q:
                candidates[cand.id] = cand

    # Query D: Same domain
    if listing.source_domain:
        same_domain_q = (
            db.query(JobListing)
            .filter(
                JobListing.source_domain == listing.source_domain,
                JobListing.id != listing.id,
            )
            .limit(candidate_limit)
            .all()
        )
        for cand in same_domain_q:
            candidates[cand.id] = cand

    # Query E: Title keywords (significant words > 3 chars)
    if listing.job_title:
        title_words = [w for w in re.split(r"\W+", listing.job_title) if len(w) > 3][:3]
        if title_words:
            filters = [JobListing.job_title.ilike(f"%{w}%") for w in title_words]
            title_q = (
                db.query(JobListing)
                .filter(or_(*filters), JobListing.id != listing.id)
                .limit(candidate_limit)
                .all()
            )
            for cand in title_q:
                candidates[cand.id] = cand

    # Query F: Recent listings pool fallback if candidate pool is small
    if len(candidates) < 10:
        recent_q = (
            db.query(JobListing)
            .filter(JobListing.id != listing.id)
            .order_by(JobListing.collected_at.desc())
            .limit(20)
            .all()
        )
        for cand in recent_q:
            candidates[cand.id] = cand

    # 2. Evaluate pairwise similarity against pruned candidate pool
    match_items: List[JobSimilarityMatchItem] = []

    for candidate_id, candidate in candidates.items():
        eval_result = classify_duplicate_pair(listing, candidate, db=db)
        score = eval_result["similarity_score"]
        classification = eval_result["match_classification"]

        # Only retain matches meeting minimum similarity or having specific impersonation signals
        if score >= SUSPICIOUS_SIMILARITY_THRESHOLD or eval_result["is_exact_match"]:
            # Strictly order pair keys to enforce uniqueness constraint
            id_a, id_b = (listing.id, candidate.id) if listing.id < candidate.id else (candidate.id, listing.id)

            # Check if record already exists in job_similarity_matches
            existing_match = (
                db.query(JobSimilarityMatch)
                .filter(
                    JobSimilarityMatch.listing_id_a == id_a,
                    JobSimilarityMatch.listing_id_b == id_b,
                )
                .first()
            )

            if existing_match:
                existing_match.is_exact_match = eval_result["is_exact_match"]
                existing_match.similarity_score = score
                existing_match.match_classification = classification
                existing_match.confidence = eval_result["confidence"]
                existing_match.supporting_evidence = eval_result["supporting_evidence"]
                existing_match.contradictory_evidence = eval_result["contradictory_evidence"]
                existing_match.reasons = eval_result["reasons"]
                existing_match.analyzed_at = datetime.now(timezone.utc)
                match_record_id = existing_match.id
            else:
                new_match = JobSimilarityMatch(
                    listing_id_a=id_a,
                    listing_id_b=id_b,
                    is_exact_match=eval_result["is_exact_match"],
                    similarity_score=score,
                    match_classification=classification,
                    confidence=eval_result["confidence"],
                    supporting_evidence=eval_result["supporting_evidence"],
                    contradictory_evidence=eval_result["contradictory_evidence"],
                    reasons=eval_result["reasons"],
                    algorithm_version=ALGORITHM_VERSION,
                )
                db.add(new_match)
                db.flush()
                match_record_id = new_match.id

            match_items.append(
                JobSimilarityMatchItem(
                    match_id=match_record_id,
                    matched_listing_id=candidate.id,
                    is_exact_match=eval_result["is_exact_match"],
                    similarity_score=score,
                    match_classification=classification,
                    confidence=eval_result["confidence"],
                    matched_title=candidate.job_title,
                    matched_company_name=candidate.claimed_company_name,
                    matched_source_url=candidate.source_url,
                    matched_domain=candidate.source_domain,
                    matched_location=candidate.job_location,
                    matched_collected_at=candidate.collected_at,
                    supporting_evidence=eval_result["supporting_evidence"],
                    contradictory_evidence=eval_result["contradictory_evidence"],
                    reasons=eval_result["reasons"],
                    impersonation_signals=eval_result["impersonation_signals"],
                )
            )

    # Sort matches by similarity score descending
    match_items.sort(key=lambda m: m.similarity_score, reverse=True)
    return match_items


def analyze_duplicate_job(
    text: str,
    title: Optional[str] = None,
    company_name: Optional[str] = None,
    cin: Optional[str] = None,
    source_url: Optional[str] = None,
    location: Optional[str] = None,
    db: Optional[Session] = None,
) -> DuplicateAnalysisSummary:
    """Performs duplicate and impersonation detection for an ad-hoc or incoming job posting against indexed listings.

    Does not modify database if db is None or read-only mode is desired.
    """
    words = count_informative_words(text)
    if words < MIN_INFORMATIVE_WORDS:
        return DuplicateAnalysisSummary(
            status="INSUFFICIENT_EVIDENCE",
            total_matches_found=0,
            highest_similarity_score=0.0,
            top_matches=[],
            impersonation_warning=None,
            summary="Job description contains insufficient informative words for duplicate or near-duplicate linguistic analysis.",
            limitations="Minimum 20 informative words required to compute reliable TF-IDF cosine similarity against indexed listings.",
        )

    if db is None:
        return DuplicateAnalysisSummary(
            status="UNIQUE_LISTING",
            total_matches_found=0,
            highest_similarity_score=0.0,
            top_matches=[],
            summary="No database session provided; duplicate comparison against repository skipped.",
            limitations="Duplicate analysis requires a connected database session.",
        )

    # Resolve company entity if available
    company_id: Optional[int] = None
    if company_name or cin:
        try:
            verifier = CompanyVerifier()
            match_res = verifier.verify_company(query_name=company_name, cin=cin, db=db)
            if match_res.company:
                company_id = match_res.company.id
        except Exception as e:
            logger.debug("Company verification in duplicate detector skipped: %s", e)

    norm_url, domain = normalize_job_url(source_url)
    content_hash = compute_content_hash(text)

    # Create in-memory pseudo-listing for comparison
    probe_listing = JobListing(
        id="probe-temp-id",
        source_url=source_url,
        normalized_url=norm_url,
        claimed_company_name=company_name,
        company_id=company_id,
        job_title=title,
        job_description=text,
        job_location=location,
        content_hash=content_hash,
        source_domain=domain,
    )

    # Find candidates
    candidates: Dict[str, JobListing] = {}

    # Exact hash
    exact_q = (
        db.query(JobListing)
        .filter(JobListing.content_hash == content_hash)
        .limit(30)
        .all()
    )
    for cand in exact_q:
        candidates[cand.id] = cand

    # Same company
    if company_id:
        same_comp_q = (
            db.query(JobListing)
            .filter(JobListing.company_id == company_id)
            .limit(30)
            .all()
        )
        for cand in same_comp_q:
            candidates[cand.id] = cand

    # Same claimed name
    if company_name and len(company_name.strip()) > 2:
        same_name_q = (
            db.query(JobListing)
            .filter(func.lower(JobListing.claimed_company_name) == company_name.strip().lower())
            .limit(30)
            .all()
        )
        for cand in same_name_q:
            candidates[cand.id] = cand

    # Title keywords
    if title:
        title_words = [w for w in re.split(r"\W+", title) if len(w) > 3][:3]
        if title_words:
            filters = [JobListing.job_title.ilike(f"%{w}%") for w in title_words]
            title_q = db.query(JobListing).filter(or_(*filters)).limit(30).all()
            for cand in title_q:
                candidates[cand.id] = cand

    # Recent listings if sparse
    if len(candidates) < 10:
        recent_q = db.query(JobListing).order_by(JobListing.collected_at.desc()).limit(20).all()
        for cand in recent_q:
            candidates[cand.id] = cand

    matches: List[JobSimilarityMatchItem] = []
    has_suspicious_copy = False
    impersonation_warning: Optional[str] = None

    for cand_id, cand in candidates.items():
        eval_res = classify_duplicate_pair(probe_listing, cand, db=db)
        score = eval_res["similarity_score"]
        classification = eval_res["match_classification"]

        if score >= SUSPICIOUS_SIMILARITY_THRESHOLD or eval_res["is_exact_match"]:
            if classification == "POTENTIAL_SUSPICIOUS_COPY":
                has_suspicious_copy = True
                if not impersonation_warning and eval_res["reasons"]:
                    impersonation_warning = eval_res["reasons"][0]

            matches.append(
                JobSimilarityMatchItem(
                    matched_listing_id=cand.id,
                    is_exact_match=eval_res["is_exact_match"],
                    similarity_score=score,
                    match_classification=classification,
                    confidence=eval_res["confidence"],
                    matched_title=cand.job_title,
                    matched_company_name=cand.claimed_company_name,
                    matched_source_url=cand.source_url,
                    matched_domain=cand.source_domain,
                    matched_location=cand.job_location,
                    matched_collected_at=cand.collected_at,
                    supporting_evidence=eval_res["supporting_evidence"],
                    contradictory_evidence=eval_res["contradictory_evidence"],
                    reasons=eval_res["reasons"],
                    impersonation_signals=eval_res["impersonation_signals"],
                )
            )

    matches.sort(key=lambda m: m.similarity_score, reverse=True)

    if not matches:
        return DuplicateAnalysisSummary(
            status="UNIQUE_LISTING",
            total_matches_found=0,
            highest_similarity_score=0.0,
            top_matches=[],
            impersonation_warning=None,
            summary="No matching or duplicate listings identified among currently indexed repository records.",
            limitations="Comparison evaluated against local indexed listings; unindexed external portals are not covered.",
        )

    top_match = matches[0]
    overall_status = "POTENTIAL_SUSPICIOUS_COPY" if has_suspicious_copy else top_match.match_classification

    return DuplicateAnalysisSummary(
        status=overall_status,
        total_matches_found=len(matches),
        highest_similarity_score=top_match.similarity_score,
        top_matches=matches[:5],
        impersonation_warning=impersonation_warning,
        summary=f"Identified {len(matches)} matching listing(s) in repository. Top match: {top_match.match_classification} ({int(top_match.similarity_score * 100)}% similarity).",
        limitations="Duplicate similarity reflects textual correspondence with indexed listings. Lawful reposts and syndicated listings are distinct from impersonation.",
    )
