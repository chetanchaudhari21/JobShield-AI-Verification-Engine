"""
Pydantic schemas for request validation and response serialization.
"""

from app.schemas.analysis import (
    EvidenceItem,
    JobTextAnalysisRequest,
    JobTextAnalysisResponse,
    JobUrlAnalysisRequest,
    JobUrlAnalysisResponse,
    RecruiterEmailAnalysisRequest,
    RecruiterEmailAnalysisResponse,
)
from app.schemas.listing import (
    DuplicateAnalysisSummary,
    JobDuplicateCheckRequest,
    JobListingCreate,
    JobListingResponse,
    JobSimilarityMatchItem,
)

from app.schemas.offer import (
    ExtractedFeeDemand,
    ExtractedFieldItem,
    ExtractedSensitiveRequest,
    OfferLetterAnalysisResponse,
    OfferLetterExtractedData,
)
from app.schemas.community import (
    UserReviewCreate,
    UserReviewResponse,
    RecruiterReportCreate,
    RecruiterReportResponse,
    CompanyReputationResponse,
    ModerationDecisionRequest,
    ModerationDecisionResponse,
    ModerationAppealRequest,
    ModerationAppealResponse,
    TrainingLabelCreateRequest,
    TrainingLabelResponse,
)

__all__ = [
    "JobTextAnalysisRequest",
    "JobTextAnalysisResponse",
    "JobUrlAnalysisRequest",
    "JobUrlAnalysisResponse",
    "RecruiterEmailAnalysisRequest",
    "RecruiterEmailAnalysisResponse",
    "EvidenceItem",
    "JobListingCreate",
    "JobListingResponse",
    "JobSimilarityMatchItem",
    "DuplicateAnalysisSummary",
    "JobDuplicateCheckRequest",
    "ExtractedFieldItem",
    "ExtractedFeeDemand",
    "ExtractedSensitiveRequest",
    "OfferLetterExtractedData",
    "OfferLetterAnalysisResponse",
    "UserReviewCreate",
    "UserReviewResponse",
    "RecruiterReportCreate",
    "RecruiterReportResponse",
    "CompanyReputationResponse",
    "ModerationDecisionRequest",
    "ModerationDecisionResponse",
    "ModerationAppealRequest",
    "ModerationAppealResponse",
    "TrainingLabelCreateRequest",
    "TrainingLabelResponse",
]
