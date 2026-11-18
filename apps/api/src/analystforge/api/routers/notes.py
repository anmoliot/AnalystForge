"""Notes and comments API for research commentary on tickers, portfolios, and screens."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from analystforge.api.deps import CurrentUser, SessionDep
from analystforge.api.errors import NotFoundError
from analystforge.api.models.collaboration import AnalystNote

router = APIRouter(prefix="/notes", tags=["notes"])


class CreateNoteRequest(BaseModel):
    entity_type: str = Field(pattern="^(ticker|portfolio|screen|macro)$")
    entity_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class UpdateNoteRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    content: str | None = None
    tags: list[str] | None = None


@router.post("", status_code=201, summary="Create an analyst research note or comment")
async def create_note(
    payload: CreateNoteRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    note = AnalystNote(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id.upper()
        if payload.entity_type == "ticker"
        else payload.entity_id,
        title=payload.title,
        content=payload.content,
        tags=payload.tags,
    )
    session.add(note)
    await session.commit()
    await session.refresh(note)

    return {
        "id": str(note.id),
        "entity_type": note.entity_type,
        "entity_id": note.entity_id,
        "title": note.title,
        "content": note.content,
        "tags": note.tags,
        "created_at": note.created_at.isoformat(),
        "updated_at": note.updated_at.isoformat(),
    }


@router.get("", summary="List analyst notes filtered by entity")
async def list_notes(
    current_user: CurrentUser,
    session: SessionDep,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict[str, Any]]:
    stmt = (
        select(AnalystNote)
        .where(AnalystNote.tenant_id == current_user.tenant_id)
        .order_by(desc(AnalystNote.created_at))
        .limit(limit)
    )
    if entity_type:
        stmt = stmt.where(AnalystNote.entity_type == entity_type)
    if entity_id:
        norm_id = entity_id.upper() if entity_type == "ticker" else entity_id
        stmt = stmt.where(AnalystNote.entity_id == norm_id)

    notes = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(n.id),
            "entity_type": n.entity_type,
            "entity_id": n.entity_id,
            "title": n.title,
            "content": n.content,
            "tags": n.tags,
            "created_at": n.created_at.isoformat(),
            "updated_at": n.updated_at.isoformat(),
        }
        for n in notes
    ]


@router.get("/{note_id}", summary="Get note detail")
async def get_note(
    note_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    note = await session.get(AnalystNote, note_id)
    if not note or note.tenant_id != current_user.tenant_id:
        raise NotFoundError("Note not found.")

    return {
        "id": str(note.id),
        "entity_type": note.entity_type,
        "entity_id": note.entity_id,
        "title": note.title,
        "content": note.content,
        "tags": note.tags,
        "created_at": note.created_at.isoformat(),
        "updated_at": note.updated_at.isoformat(),
    }


@router.put("/{note_id}", summary="Update note")
async def update_note(
    note_id: uuid.UUID,
    payload: UpdateNoteRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    note = await session.get(AnalystNote, note_id)
    if not note or note.tenant_id != current_user.tenant_id:
        raise NotFoundError("Note not found.")

    if payload.title is not None:
        note.title = payload.title
    if payload.content is not None:
        note.content = payload.content
    if payload.tags is not None:
        note.tags = payload.tags

    await session.commit()
    return {
        "id": str(note.id),
        "entity_type": note.entity_type,
        "entity_id": note.entity_id,
        "title": note.title,
        "content": note.content,
        "tags": note.tags,
        "created_at": note.created_at.isoformat(),
        "updated_at": note.updated_at.isoformat(),
    }


@router.delete("/{note_id}", status_code=204, summary="Delete note")
async def delete_note(
    note_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    note = await session.get(AnalystNote, note_id)
    if not note or note.tenant_id != current_user.tenant_id:
        raise NotFoundError("Note not found.")

    await session.delete(note)
    await session.commit()
