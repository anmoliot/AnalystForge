"""Research document chunks, sessions, messages, and call audit logs (Phase 9 Grounded AI & RAG)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analystforge.api.db import Base
from analystforge.api.models.base import uuid_pk


class ResearchSession(Base):
    __tablename__ = "research_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    messages: Mapped[list[ResearchMessage]] = relationship(
        "ResearchMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ResearchMessage.created_at",
    )


class ResearchMessage(Base):
    __tablename__ = "research_messages"

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[ResearchSession] = relationship("ResearchSession", back_populates="messages")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (Index("ix_doc_chunks_inst_source", "instrument_id", "source_type"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    instrument_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # "FILING" | "NEWS" | "FACT" | "NOTES"
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    section: Mapped[str | None] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ResearchCallLog(Base):
    __tablename__ = "research_call_logs"

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tool_calls_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    citations_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    refusal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
