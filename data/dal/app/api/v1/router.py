"""V1 API router aggregator."""

from fastapi import APIRouter

from app.api.v1.endpoints import crud, health, metadata, query

router = APIRouter()
router.include_router(health.router)
router.include_router(query.router)
router.include_router(metadata.router)
router.include_router(crud.router)
