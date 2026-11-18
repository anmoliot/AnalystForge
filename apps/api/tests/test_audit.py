from unittest.mock import AsyncMock

from sqlalchemy import select

from analystforge.api.models.core import AuditLog


async def event_for(db, response):
    async with db.session() as session:
        return (
            await session.scalars(
                select(AuditLog).where(AuditLog.request_id == response.headers["x-request-id"])
            )
        ).one()


async def test_failed_auth_is_audited(client, db):
    response = await client.post(
        "/api/v1/auth/login", json={"email": "absent@example.com", "password": "private"}
    )
    assert response.status_code == 401
    event = await event_for(db, response)
    assert event.status_code == 401
    assert event.action == "user.login.failed"
    assert event.actor_id is None
    assert event.tenant_id is None
    assert event.entity_id is None
    assert event.before is None
    assert event.after is None


async def test_note_mutations_record_actor_resource_and_outcome(client, db):
    account = {"email": "audit@example.com", "password": "TestAccount123"}
    register = await client.post(
        "/api/v1/auth/register", json={**account, "full_name": "Audit", "tenant_name": "Audit"}
    )
    user = register.json()
    token = (await client.post("/api/v1/auth/login", json=account)).json()["access_token"]
    headers = {"Authorization": "Bearer " + token}
    created = await client.post(
        "/api/v1/notes",
        headers=headers,
        json={
            "entity_type": "ticker",
            "entity_id": "AAPL",
            "title": "Private",
            "content": "Private analyst note",
        },
    )
    assert created.status_code == 201
    note_id = created.json()["id"]
    updated = await client.put(
        "/api/v1/notes/" + note_id, headers=headers, json={"title": "Revised"}
    )
    deleted = await client.delete("/api/v1/notes/" + note_id, headers=headers)
    for response in (created, updated, deleted):
        event = await event_for(db, response)
        assert 200 <= response.status_code < 300
        assert event.status_code == response.status_code
        assert str(event.actor_id) == user["id"]
        assert str(event.tenant_id) == user["tenant_id"]
        assert event.entity_id == note_id
        assert event.created_at is not None
        assert event.before is None
        assert event.after is None


async def test_audit_failure_preserves_response_and_increments_metric(client, monkeypatch):
    from analystforge.api.metrics import AUDIT_FAILURES

    before = AUDIT_FAILURES._value.get()
    monkeypatch.setattr("analystforge.api.audit.record_mutation", AsyncMock(side_effect=OSError()))
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"
    assert AUDIT_FAILURES._value.get() == before + 1
