from fastapi import APIRouter

router = APIRouter(tags=["services"])


@router.get("/services")
async def services():
    return {"services": [
        {"key": "orchestrator", "name": "GDCE Orchestrator", "description": "Routes chat questions to the appropriate GDCE service"},
        {"key": "general", "name": "General Information Service", "description": "Answers GDCE policy, procedure, and documentation questions"},
        {"key": "hs_code", "name": "HS Code Retrieval Service", "description": "Finds HS code candidates by product description"},
        {"key": "calculator", "name": "Calculator Service", "description": "Calculates customs duties, taxes, and import costs"},
        {"key": "trade", "name": "Trade Data Service", "description": "Answers trade statistics and data analysis questions"},
    ]}
