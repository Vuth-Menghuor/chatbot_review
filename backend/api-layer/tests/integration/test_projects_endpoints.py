from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import projects as projects_endpoint
from app.schemas.common import ProjectCreate, ProjectUpdate
from tests.factories import make_project, make_user, utc_now


# This file verifies project endpoint functions with fake auth and database dependencies.


# Result fake for list/get/count style SQLAlchemy calls.
class FakeResult:
    # Store rows and optional scalar count for endpoint queries.
    def __init__(self, rows=None, scalar_value=None) -> None:
        self.rows = rows or []
        self.scalar_value = scalar_value

    # Return one row for ownership lookups.
    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None

    # Return count values for ProjectDetail.
    def scalar_one(self):
        return self.scalar_value if self.scalar_value is not None else 0

    # Return self so endpoint code can chain scalars().all().
    def scalars(self):
        return self

    # Return all rows for list endpoints.
    def all(self):
        return self.rows


# Fake DB session that can return a sequence of query results.
class FakeProjectSession:
    # Configure sequential execute() results and capture write behavior.
    def __init__(self, *, execute_results=None) -> None:
        self.execute_results = execute_results or []
        self.added = []
        self.flushed = False
        self.committed = False
        self.refreshed = []
        self.execute_count = 0

    # Capture inserted projects.
    def add(self, item):
        self.added.append(item)

    # Simulate database defaults for ProjectRead response models.
    async def flush(self):
        self.flushed = True
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid4()
            if getattr(item, "status", None) is None:
                item.status = "active"
            if getattr(item, "is_pinned", None) is None:
                item.is_pinned = False
            if getattr(item, "is_archived", None) is None:
                item.is_archived = False
            if getattr(item, "created_at", None) is None:
                item.created_at = utc_now()
            if getattr(item, "updated_at", None) is None:
                item.updated_at = utc_now()

    # Return the next configured query result.
    async def execute(self, _statement):
        if self.execute_count < len(self.execute_results):
            result = self.execute_results[self.execute_count]
            self.execute_count += 1
            return result
        return FakeResult()

    # Capture transaction commits.
    async def commit(self):
        self.committed = True

    # Capture refresh calls before response serialization.
    async def refresh(self, item):
        self.refreshed.append(item)


# Avoid audit-log DB writes in endpoint tests.
def noop_add_audit_log(*_args, **_kwargs):
    return None


# Apply shared fakes to every project endpoint test.
@pytest.fixture(autouse=True)
def patch_external_dependencies(monkeypatch):
    monkeypatch.setattr(projects_endpoint, "add_audit_log", noop_add_audit_log)


# Creating a project should persist a user-owned active project.
@pytest.mark.asyncio
async def test_create_project_endpoint():
    user = make_user()
    db = FakeProjectSession()

    response = await projects_endpoint.create_project(ProjectCreate(name="Trade Docs"), user=user, db=db)

    assert response.name == "Trade Docs"
    assert response.user_id == user.id
    assert db.committed is True


# Listing projects should return the rows produced by the query.
@pytest.mark.asyncio
async def test_list_projects_endpoint():
    user = make_user()
    project = make_project(user_id=user.id, name="Trade Docs")

    response = await projects_endpoint.list_projects(
        limit=20,
        offset=0,
        user=user,
        db=FakeProjectSession(execute_results=[FakeResult(rows=[project])]),
    )

    assert response == [project]


# Getting a project should include detail fields such as chat_count and recent_chats.
@pytest.mark.asyncio
async def test_get_project_endpoint():
    user = make_user()
    project = make_project(user_id=user.id)
    db = FakeProjectSession(
        execute_results=[
            FakeResult(rows=[project]),
            FakeResult(scalar_value=0),
            FakeResult(rows=[]),
        ]
    )

    response = await projects_endpoint.get_project(project.id, user=user, db=db)

    assert response.id == project.id
    assert response.chat_count == 0
    assert response.recent_chats == []


# Updating a project should apply changed fields and commit.
@pytest.mark.asyncio
async def test_update_project_endpoint():
    user = make_user()
    project = make_project(user_id=user.id, name="Before")
    db = FakeProjectSession(execute_results=[FakeResult(rows=[project])])

    response = await projects_endpoint.update_project(project.id, ProjectUpdate(name="After"), user=user, db=db)

    assert response.name == "After"
    assert project.name == "After"
    assert db.committed is True


# Deleting a project should soft-delete it and detach chats from that project.
@pytest.mark.asyncio
async def test_delete_project_endpoint():
    user = make_user()
    project = make_project(user_id=user.id)
    db = FakeProjectSession(execute_results=[FakeResult(rows=[project]), FakeResult()])

    response = await projects_endpoint.delete_project(project.id, user=user, db=db)

    assert response == {"message": "Project deleted"}
    assert project.status == "deleted"
    assert project.is_archived is True
    assert db.committed is True


# Missing or non-owned projects should return 404.
@pytest.mark.asyncio
async def test_get_missing_project_endpoint_returns_404():
    user = make_user()

    with pytest.raises(HTTPException) as exc_info:
        await projects_endpoint.get_project(uuid4(), user=user, db=FakeProjectSession(execute_results=[FakeResult(rows=[])]))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Project not found"
