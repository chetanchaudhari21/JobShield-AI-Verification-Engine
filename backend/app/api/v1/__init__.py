"""API Version 1 Router Aggregation."""

from fastapi import APIRouter
from app.api.v1.admin import router as admin_router
from app.api.v1.analyze import router as analyze_router
from app.api.v1.appeals import router as appeals_router
from app.api.v1.auth import router as auth_router
from app.api.v1.community import router as community_router
from app.api.v1.companies import router as companies_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.listings import router as listings_router
from app.api.v1.moderation import router as moderation_router
from app.api.v1.scans import router as scans_router

api_v1_router = APIRouter()
api_v1_router.include_router(auth_router)
api_v1_router.include_router(analyze_router)
api_v1_router.include_router(jobs_router)
api_v1_router.include_router(appeals_router)
api_v1_router.include_router(companies_router)
api_v1_router.include_router(moderation_router)
api_v1_router.include_router(community_router)
api_v1_router.include_router(listings_router)
api_v1_router.include_router(scans_router)
api_v1_router.include_router(admin_router)

__all__ = ["api_v1_router"]
