from fastapi import APIRouter

router = APIRouter(tags=["services"])


@router.get("/services")
async def services():
    return {"services": [
        {"key": "qa", "name": "Q&A Generation Service", "description": "Generate questions and answers"},
        {"key": "hs_code", "name": "HS Code Service", "description": "Find HS code by product description"},
        {"key": "calculator", "name": "Calculator Service", "description": "Perform duty, tax, margin, and cost calculations"},
        {"key": "generate_chat", "name": "Generate Chat Service", "description": "Generate natural conversation responses"},
    ]}
