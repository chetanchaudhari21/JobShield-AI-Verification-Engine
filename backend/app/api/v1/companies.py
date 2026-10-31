"""API Route for Company Entity Profile (GET /api/v1/companies/{id}).

Conforms to Feature F2 and Sections 8 & 9 of PROJECT_SPECIFICATION.md:
- Retrieves sourced company verification summary and provenance audit records
- Distinguishes MCA corporate standing from DPIIT startup recognition
- Transparently discloses limitations: neither status validates a specific job or recruiter
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.company import Company
from app.schemas.company import (
    CompanyDetailResponse,
    CompanyDomainOut,
    CompanySourceRecordOut,
    StartupRecognitionOut,
)
from app.schemas.community import CompanyReputationResponse
from app.services.reputation_service import get_company_reputation
from app.verification.company_verifier import CompanyVerifier

logger = logging.getLogger("jobshield.api.companies")

router = APIRouter(prefix="/companies", tags=["Companies"])


@router.get(
    "/{company_id}",
    response_model=CompanyDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Company Sourced Verification Summary",
    description=(
        "Retrieves sourced company registration details, provenance records, "
        "DPIIT startup recognition standing, and observed domains."
    ),
)
async def get_company_profile(
    company_id: int,
    db: Session = Depends(get_db),
) -> CompanyDetailResponse:
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company entity with ID {company_id} not found in the verified registry.",
        )

    # Format source records
    source_records = [
        CompanySourceRecordOut(
            id=sr.id,
            source_name=sr.source_name,
            source_url=sr.source_url,
            source_record_id=sr.source_record_id,
            source_status=sr.source_status,
            retrieved_at=sr.retrieved_at,
            source_updated_at=sr.source_updated_at,
            match_method=sr.match_method,
            match_confidence=sr.match_confidence,
            raw_metadata=sr.raw_metadata,
        )
        for sr in company.source_records
    ]

    # Format startup recognitions
    startup_recognitions = [
        StartupRecognitionOut(
            id=rec.id,
            recognition_status=rec.recognition_status,
            recognition_id=rec.recognition_id,
            source_url=rec.source_url,
            checked_at=rec.checked_at,
            status_details=rec.status_details,
        )
        for rec in company.startup_recognitions
    ]

    # Format company domains
    domains = [
        CompanyDomainOut(
            id=dom.id,
            domain=dom.domain,
            source_url=dom.source_url,
            verification_status=dom.verification_status,
            evidence_summary=dom.evidence_summary,
            checked_at=dom.checked_at,
            is_primary=dom.is_primary,
        )
        for dom in company.domains
    ]

    # Compute live verification summary
    verifier = CompanyVerifier()
    match_result = verifier.verify_company(
        query_name=company.legal_name,
        cin=company.cin,
        db=db,
    )
    summary = verifier.to_summary_schema(match_result)

    return CompanyDetailResponse(
        id=company.id,
        legal_name=company.legal_name,
        normalized_name=company.normalized_name,
        cin=company.cin,
        entity_type=company.entity_type,
        registry_status=company.registry_status,
        created_at=company.created_at,
        updated_at=company.updated_at,
        source_records=source_records,
        startup_recognitions=startup_recognitions,
        domains=domains,
        verification_summary=summary,
    )


@router.get(
    "/{company_id}/reputation",
    response_model=CompanyReputationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Sourced Bayesian Company Reputation",
    description=(
        "Retrieves Bayesian-adjusted community rating, review count, confidence score, "
        "and rating distribution strictly separated from fraud allegations. "
        "Conforms to Feature F9 and Section 8 & 9 of PROJECT_SPECIFICATION.md."
    ),
)
def get_company_reputation_endpoint(
    company_id: int,
    limit_recent: int = 5,
    db: Session = Depends(get_db),
) -> CompanyReputationResponse:
    reputation = get_company_reputation(db, company_id=company_id, limit_recent=limit_recent)
    if not reputation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID {company_id} was not found in the verified registry.",
        )
    return reputation
