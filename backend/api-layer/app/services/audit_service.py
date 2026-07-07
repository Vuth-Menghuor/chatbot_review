from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


def add_audit_log(db: AsyncSession, action: str, resource: str, user_id: UUID | None = None, metadata: dict | None = None, ip_address: str | None = None) -> None:
    db.add(AuditLog(user_id=user_id, action=action, resource=resource, metadata_json=metadata, ip_address=ip_address))
