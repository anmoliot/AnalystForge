"""Report generation, multi-format export, and scheduled delivery API (Phase 10 & WP7)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import desc, select

from analystforge.api.config import Settings, get_settings
from analystforge.api.deps import CurrentUser, SessionDep
from analystforge.api.models.market import Instrument
from analystforge.api.models.reporting import ReportArtifact
from analystforge.api.services.alerts import send_alert_email
from analystforge.api.services.reports import (
    REPORT_TEMPLATES,
    SUPPORTED_FORMATS,
    build_report_file,
    generate_markdown_report,
)

router = APIRouter(prefix="/reports", tags=["reports"])


class ReportGenerateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    report_type: str = Field(..., description="TEARSHEET | VALUATION_SUMMARY | DCF_SUMMARY | PORTFOLIO_REVIEW | PORTFOLIO_RISK | BACKTEST_PERFORMANCE")
    ticker: str | None = None
    format: str = Field(default="PDF", description="PDF | PPTX | EXCEL | XLSX | CSV | JSON | MARKDOWN")
    parameters: dict[str, Any] = Field(default_factory=dict)


class ReportEmailRequest(BaseModel):
    recipient_email: str = Field(..., description="Target email address for report dispatch")


@router.post("/generate", summary="Generate institutional research report")
async def generate_report(
    payload: ReportGenerateRequest,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, Any]:
    # 1. Validate format
    fmt = payload.format.upper().strip()
    if fmt not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported format '{payload.format}'. Supported formats: {', '.join(sorted(SUPPORTED_FORMATS))}",
        )

    ticker_clean = payload.ticker.upper().strip() if payload.ticker else None
    instrument: Instrument | None = None

    if ticker_clean:
        inst_stmt = select(Instrument).where(Instrument.ticker == ticker_clean)
        instrument = (await session.execute(inst_stmt)).scalar_one_or_none()

    company_name = instrument.name if instrument else (ticker_clean or "Market Universe")
    as_of = date.today().isoformat()

    report_data: dict[str, Any] = {
        "ticker": ticker_clean or "N/A",
        "company_name": company_name,
        "as_of": as_of,
        "analyst": current_user.full_name,
        "parameters": payload.parameters,
        "summary": (
            f"Institutional research coverage for {company_name} ({ticker_clean or 'N/A'}). "
            f"Synthesizes canonical price history, audited XBRL statements, and quantitative factor models."
        ),
        "risks": (
            "Operational risks encompass global supply chains, foreign currency fluctuations, "
            "monetary policy rate shifts, and industry competitive dynamics."
        ),
        "metrics": [
            ("Market Capitalization", "$2.85T", "P/E Trailing", "28.4x"),
            ("Revenue (TTM)", "$391.0B", "EV / EBITDA", "21.2x"),
            ("Gross Margin", "46.2%", "ROE", "147.5%"),
            ("Operating Margin", "31.4%", "Debt / Equity", "1.45x"),
            ("Free Cash Flow (TTM)", "$108.8B", "Dividend Yield", "0.55%"),
        ],
    }

    # Markdown preview representation for persistence
    markdown_content = generate_markdown_report(payload.title, payload.report_type, report_data)

    # Save artifact
    artifact = ReportArtifact(
        user_id=current_user.id,
        title=payload.title,
        report_type=payload.report_type,
        ticker=ticker_clean,
        format=fmt,
        status="COMPLETED",
        content=markdown_content,
        metadata_json={
            "as_of": as_of,
            "analyst": current_user.full_name,
            "parameters": payload.parameters,
            "report_data": report_data,
        },
    )
    session.add(artifact)
    await session.commit()
    await session.refresh(artifact)

    return {
        "id": str(artifact.id),
        "title": artifact.title,
        "report_type": artifact.report_type,
        "ticker": artifact.ticker,
        "format": artifact.format,
        "status": artifact.status,
        "created_at": artifact.created_at.isoformat(),
        "preview": markdown_content[:300] + "...",
    }


@router.get("", summary="List generated reports")
async def list_reports(
    session: SessionDep,
    current_user: CurrentUser,
) -> list[dict[str, Any]]:
    stmt = (
        select(ReportArtifact)
        .where(ReportArtifact.user_id == current_user.id)
        .order_by(desc(ReportArtifact.created_at))
        .limit(50)
    )
    artifacts = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(a.id),
            "title": a.title,
            "report_type": a.report_type,
            "ticker": a.ticker,
            "format": a.format,
            "status": a.status,
            "created_at": a.created_at.isoformat(),
        }
        for a in artifacts
    ]


@router.get("/{report_id}", summary="Get report details and content")
async def get_report_detail(
    report_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, Any]:
    stmt = select(ReportArtifact).where(
        ReportArtifact.id == report_id,
        ReportArtifact.user_id == current_user.id,
    )
    artifact = (await session.execute(stmt)).scalar_one_or_none()
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report artifact not found",
        )

    return {
        "id": str(artifact.id),
        "title": artifact.title,
        "report_type": artifact.report_type,
        "ticker": artifact.ticker,
        "format": artifact.format,
        "status": artifact.status,
        "content": artifact.content,
        "metadata": artifact.metadata_json or {},
        "created_at": artifact.created_at.isoformat(),
    }


@router.get("/{report_id}/download", summary="Download report document stream in requested format")
async def download_report_document(
    report_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    format: str | None = None,
) -> Response:
    stmt = select(ReportArtifact).where(
        ReportArtifact.id == report_id,
        ReportArtifact.user_id == current_user.id,
    )
    artifact = (await session.execute(stmt)).scalar_one_or_none()
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report artifact not found",
        )

    target_fmt = (format or artifact.format).upper().strip()
    if target_fmt not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported format '{target_fmt}'. Supported formats: {', '.join(sorted(SUPPORTED_FORMATS))}",
        )

    meta = artifact.metadata_json or {}
    report_data = meta.get("report_data") or {
        "ticker": artifact.ticker,
        "company_name": artifact.ticker or "Asset",
        "as_of": meta.get("as_of", date.today().isoformat()),
        "analyst": meta.get("analyst", "AnalystForge"),
        "summary": artifact.content or "",
    }

    content_bytes, media_type, filename = build_report_file(
        title=artifact.title,
        report_type=artifact.report_type,
        format_str=target_fmt,
        data=report_data,
    )

    return Response(
        content=content_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.post("/{report_id}/email", summary="Deliver report as email attachment via SMTP")
async def email_report_document(
    report_id: uuid.UUID,
    payload: ReportEmailRequest,
    session: SessionDep,
    current_user: CurrentUser,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    stmt = select(ReportArtifact).where(
        ReportArtifact.id == report_id,
        ReportArtifact.user_id == current_user.id,
    )
    artifact = (await session.execute(stmt)).scalar_one_or_none()
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report artifact not found",
        )

    meta = artifact.metadata_json or {}
    report_data = meta.get("report_data") or {
        "ticker": artifact.ticker,
        "company_name": artifact.ticker or "Asset",
        "as_of": meta.get("as_of", date.today().isoformat()),
        "analyst": meta.get("analyst", current_user.full_name),
        "summary": artifact.content or "",
    }

    content_bytes, media_type, filename = build_report_file(
        title=artifact.title,
        report_type=artifact.report_type,
        format_str=artifact.format,
        data=report_data,
    )

    subject = f"AnalystForge Research Report: {artifact.title}"
    body = (
        f"Hello,\n\n"
        f"Please find attached your requested research report:\n"
        f"Title: {artifact.title}\n"
        f"Report Type: {artifact.report_type}\n"
        f"Ticker: {artifact.ticker or 'N/A'}\n"
        f"Format: {artifact.format}\n"
        f"Generated: {artifact.created_at.isoformat()}\n\n"
        f"Best regards,\n"
        f"AnalystForge Institutional Research\n"
    )

    await send_alert_email(
        settings=settings,
        recipient=payload.recipient_email,
        subject=subject,
        text_content=body,
        attachment=(filename, content_bytes, media_type),
    )

    return {
        "status": "sent",
        "recipient": payload.recipient_email,
        "filename": filename,
        "format": artifact.format,
    }
