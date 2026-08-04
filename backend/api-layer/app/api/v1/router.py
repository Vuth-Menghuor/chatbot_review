from fastapi import APIRouter

from app.api.v1.endpoints import api_keys, auth, chat, chats, files, health, jobs, projects, services, shared_chats

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(api_keys.router)
api_router.include_router(projects.router)
api_router.include_router(chats.router)
api_router.include_router(shared_chats.router)
api_router.include_router(chat.router)
api_router.include_router(jobs.router)
api_router.include_router(files.router)
api_router.include_router(services.router)
api_router.include_router(health.router)
