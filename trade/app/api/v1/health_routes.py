from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok", "version": "1.0.0"}
