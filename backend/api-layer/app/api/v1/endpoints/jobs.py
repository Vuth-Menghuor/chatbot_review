from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models import User
from app.services.main_chatbot_client import main_chatbot_client
from app.services.ownership import owned_chat

router = APIRouter(tags=["async jobs"])


@router.get("/jobs/{job_id}")
async def job_status(job_id: UUID, user: User = Depends(get_current_user)):
    return await main_chatbot_client.request("GET", f"/internal/jobs/{job_id}", params={"user_id": str(user.id)})


@router.get("/jobs/{job_id}/result")
async def job_result(job_id: UUID, user: User = Depends(get_current_user)):
    return await main_chatbot_client.request("GET", f"/internal/jobs/{job_id}/result", params={"user_id": str(user.id)})


@router.get("/chats/{chat_id}/jobs")
async def chat_jobs(chat_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await owned_chat(db, chat_id, user.id)
    return await main_chatbot_client.request("GET", f"/internal/chats/{chat_id}/jobs", params={"user_id": str(user.id)})
