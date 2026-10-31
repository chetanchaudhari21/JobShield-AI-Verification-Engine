"""
ORM models for JobShield AI.
Exports all models so Alembic metadata inspection discovers all tables.
"""
from app.models.community import (
    RecruiterReport,
    ReviewModeration,
    TrainingLabel,
    UserReview,
)
from app.models.company import (
    Company,
    CompanyDomain,
    CompanySourceRecord,
    StartupRecognition,
)
from app.models.domain import DomainCheck
from app.models.job import JobListing, JobSimilarityMatch
from app.models.ml import DatasetImport, ModelVersion
from app.models.offer import OfferLetterScan
from app.models.prediction import PredictionHistory
from app.models.recruiter import RecruiterEmailScan
from app.models.scan import ScanRequest
from app.models.user import (
    ModerationAppeal,
    RefreshToken,
    SecurityAuditLog,
    User,
)
from app.models.verification import VerificationEvidence
from app.models.worker import AsyncDocumentJob

__all__ = [
    "ScanRequest",
    "VerificationEvidence",
    "PredictionHistory",
    "ModelVersion",
    "DatasetImport",
    "Company",
    "CompanySourceRecord",
    "StartupRecognition",
    "CompanyDomain",
    "DomainCheck",
    "RecruiterEmailScan",
    "JobListing",
    "JobSimilarityMatch",
    "OfferLetterScan",
    "UserReview",
    "RecruiterReport",
    "ReviewModeration",
    "TrainingLabel",
    "User",
    "RefreshToken",
    "SecurityAuditLog",
    "ModerationAppeal",
    "AsyncDocumentJob",
]

