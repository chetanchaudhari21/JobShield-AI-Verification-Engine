"""API Endpoints for Job Listing Ingestion, Duplicate Detection, and Impersonation Analysis.

Conforms to Section 8 (Tables 5 & 6) and Feature F4/F5 of PROJECT_SPECIFICATION.md:
- Register job listings with normalized URL and content hashing
- Query similarity matches and impersonation evidence
- Ad-hoc duplicate comparison against indexed repository records
"""

import logging
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.company import Company
from app.models.job import JobListing, JobSimilarityMatch
from app.schemas.listing import (
    DuplicateAnalysisSummary,
    JobDuplicateCheckRequest,
    JobListingCreate,
    JobListingResponse,
    JobSimilarityMatchItem,
)
from app.services.duplicate_detector import (
    analyze_duplicate_job,
    compute_content_hash,
    find_and_record_similarity_matches,
    normalize_job_text,
    normalize_job_url,
)
from app.verification.company_verifier import CompanyVerifier

logger = logging.getLogger("jobshield.api.v1.listings")

router = APIRouter(prefix="/listings", tags=["Job Listings & Duplicate Detection"])


@router.post(
    "/register-or-analyze",
    response_model=JobListingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register and Analyze Job Listing",
    description=(
        "Registers a job listing into the repository with normalized URL, domain extraction, "
        "and content hashing. Automatically evaluates exact and near-duplicate similarity "
        "against indexed listings and detects potential company impersonation signals."
    ),
)
def register_or_analyze_job_listing(
    payload: JobListingCreate,
    db: Session = Depends(get_db),
) -> JobListingResponse:
    # 1. Normalize URL and content
    norm_url, domain = normalize_job_url(payload.source_url)
    clean_text = normalize_job_text(payload.job_description)
    content_hash = compute_content_hash(clean_text)

    # 2. Resolve company entity if unambiguous
    company_id: Optional[int] = None
    if payload.claimed_company_name or payload.cin:
        try:
            verifier = CompanyVerifier()
            match_res = verifier.verify_company(
                query_name=payload.claimed_company_name,
                cin=payload.cin,
                db=db,
            )
            if match_res.company:
                company_id = match_res.company.id
        except Exception as e:
            logger.debug("Company lookup during listing registration skipped: %s", e)

    # 3. Create or find existing listing
    existing_listing: Optional[JobListing] = None
    if norm_url:
        existing_listing = (
            db.query(JobListing)
            .filter(JobListing.normalized_url == norm_url)
            .first()
        )

    if existing_listing:
        listing = existing_listing
        # Update mutable fields
        if payload.job_title:
            listing.job_title = payload.job_title
        if payload.claimed_company_name:
            listing.claimed_company_name = payload.claimed_company_name
        if company_id:
            listing.company_id = company_id
        if payload.job_location:
            listing.job_location = payload.job_location
        if payload.employment_type:
            listing.employment_type = payload.employment_type
        listing.job_description = payload.job_description
        listing.content_hash = content_hash
        listing.source_domain = domain
    else:
        listing = JobListing(
            id=str(uuid.uuid4()),
            source_url=payload.source_url,
            normalized_url=norm_url,
            claimed_company_name=payload.claimed_company_name,
            company_id=company_id,
            job_title=payload.job_title,
            job_description=payload.job_description,
            job_location=payload.job_location,
            employment_type=payload.employment_type,
            content_hash=content_hash,
            source_domain=domain,
            source_type=payload.source_type or "DIRECT_INPUT",
            extraction_status="COMPLETED",
        )
        db.add(listing)

    db.flush()

    # 4. Find and record similarity matches
    matches = find_and_record_similarity_matches(listing, db)
    db.commit()

    # 5. Format Duplicate Analysis Summary
    has_suspicious_copy = any(m.match_classification == "POTENTIAL_SUSPICIOUS_COPY" for m in matches)
    impersonation_warn = next((m.reasons[0] for m in matches if m.match_classification == "POTENTIAL_SUSPICIOUS_COPY" and m.reasons), None)

    if matches:
        top_match = matches[0]
        status_val = "POTENTIAL_SUSPICIOUS_COPY" if has_suspicious_copy else top_match.match_classification
        dup_summary = DuplicateAnalysisSummary(
            status=status_val,
            total_matches_found=len(matches),
            highest_similarity_score=top_match.similarity_score,
            top_matches=matches[:5],
            impersonation_warning=impersonation_warn,
            summary=f"Found {len(matches)} matching listing(s). Top classification: {top_match.match_classification} ({int(top_match.similarity_score * 100)}% similarity).",
            limitations="Duplicate analysis evaluated against indexed repository records.",
        )
    else:
        dup_summary = DuplicateAnalysisSummary(
            status="UNIQUE_LISTING",
            total_matches_found=0,
            highest_similarity_score=0.0,
            top_matches=[],
            impersonation_warning=None,
            summary="No duplicate postings found in repository. Vacancy text is unique among indexed records.",
            limitations="Comparison evaluated against currently indexed listings.",
        )

    return JobListingResponse(
        id=listing.id,
        job_title=listing.job_title,
        job_description=listing.job_description,
        claimed_company_name=listing.claimed_company_name,
        company_id=listing.company_id,
        source_url=listing.source_url,
        normalized_url=listing.normalized_url,
        content_hash=listing.content_hash,
        source_domain=listing.source_domain,
        job_location=listing.job_location,
        employment_type=listing.employment_type,
        source_type=listing.source_type,
        extraction_status=listing.extraction_status,
        collected_at=listing.collected_at,
        duplicate_analysis=dup_summary,
    )


@router.get(
    "/{listing_id}",
    response_model=JobListingResponse,
    summary="Get Job Listing",
    description="Retrieves a registered job listing by its unique UUID identifier.",
)
def get_job_listing(
    listing_id: str,
    db: Session = Depends(get_db),
) -> JobListingResponse:
    listing = db.query(JobListing).filter(JobListing.id == listing_id).first()
    if not listing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job listing with ID '{listing_id}' not found.",
        )

    return JobListingResponse(
        id=listing.id,
        job_title=listing.job_title,
        job_description=listing.job_description,
        claimed_company_name=listing.claimed_company_name,
        company_id=listing.company_id,
        source_url=listing.source_url,
        normalized_url=listing.normalized_url,
        content_hash=listing.content_hash,
        source_domain=listing.source_domain,
        job_location=listing.job_location,
        employment_type=listing.employment_type,
        source_type=listing.source_type,
        extraction_status=listing.extraction_status,
        collected_at=listing.collected_at,
        duplicate_analysis=None,
    )


@router.get(
    "/{listing_id}/similar",
    response_model=DuplicateAnalysisSummary,
    summary="Get Similar Listings and Impersonation Evidence",
    description="Retrieves all recorded similarity matches and impersonation signals for a given job listing.",
)
def get_similar_listings(
    listing_id: str,
    db: Session = Depends(get_db),
) -> DuplicateAnalysisSummary:
    listing = db.query(JobListing).filter(JobListing.id == listing_id).first()
    if not listing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job listing with ID '{listing_id}' not found.",
        )

    # Query matches where listing is either listing_id_a or listing_id_b
    matches = (
        db.query(JobSimilarityMatch)
        .filter(
            (JobSimilarityMatch.listing_id_a == listing_id)
            | (JobSimilarityMatch.listing_id_b == listing_id)
        )
        .order_by(JobSimilarityMatch.similarity_score.desc())
        .all()
    )

    items: List[JobSimilarityMatchItem] = []
    has_suspicious_copy = False
    impersonation_warn: Optional[str] = None

    for m in matches:
        partner_id = m.listing_id_b if m.listing_id_a == listing_id else m.listing_id_a
        partner = db.query(JobListing).filter(JobListing.id == partner_id).first()

        if m.match_classification == "POTENTIAL_SUSPICIOUS_COPY":
            has_suspicious_copy = True
            if not impersonation_warn and m.reasons:
                impersonation_warn = m.reasons[0]

        items.append(
            JobSimilarityMatchItem(
                match_id=m.id,
                matched_listing_id=partner_id,
                is_exact_match=m.is_exact_match,
                similarity_score=m.similarity_score,
                match_classification=m.match_classification,
                confidence=m.confidence,
                matched_title=partner.job_title if partner else None,
                matched_company_name=partner.claimed_company_name if partner else None,
                matched_source_url=partner.source_url if partner else None,
                matched_domain=partner.source_domain if partner else None,
                matched_location=partner.job_location if partner else None,
                matched_collected_at=partner.collected_at if partner else None,
                supporting_evidence=m.supporting_evidence or [],
                contradictory_evidence=m.contradictory_evidence or [],
                reasons=m.reasons or [],
                impersonation_signals=[],
            )
        )

    if not items:
        return DuplicateAnalysisSummary(
            status="UNIQUE_LISTING",
            total_matches_found=0,
            highest_similarity_score=0.0,
            top_matches=[],
            impersonation_warning=None,
            summary="No similarity matches recorded for this listing.",
            limitations="Comparison evaluated against currently indexed listings.",
        )

    top = items[0]
    status_val = "POTENTIAL_SUSPICIOUS_COPY" if has_suspicious_copy else top.match_classification

    return DuplicateAnalysisSummary(
        status=status_val,
        total_matches_found=len(items),
        highest_similarity_score=top.similarity_score,
        top_matches=items,
        impersonation_warning=impersonation_warn,
        summary=f"Listing has {len(items)} recorded similarity match(es). Top match: {top.match_classification} ({int(top.similarity_score * 100)}% similarity).",
        limitations="Duplicate matches reflect textual similarity with indexed records.",
    )


@router.post(
    "/check-duplicate",
    response_model=DuplicateAnalysisSummary,
    summary="Ad-hoc Duplicate & Impersonation Check",
    description="Checks job text against indexed listings for duplicate copies or impersonation signals without persisting it.",
)
def check_duplicate_ad_hoc(
    payload: JobDuplicateCheckRequest,
    db: Session = Depends(get_db),
) -> DuplicateAnalysisSummary:
    return analyze_duplicate_job(
        text=payload.text,
        title=payload.title,
        company_name=payload.company_name,
        cin=payload.cin,
        source_url=payload.source_url,
        location=payload.location,
        db=db,
    )
