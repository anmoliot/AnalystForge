"""Institutional report generator supporting PDF (ReportLab), PowerPoint (python-pptx), Excel (live formulas), CSV, JSON, and Markdown."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SUPPORTED_FORMATS = {"PDF", "PPTX", "EXCEL", "XLSX", "CSV", "JSON", "MARKDOWN"}

REPORT_TEMPLATES = {
    "TEARSHEET",
    "VALUATION_SUMMARY",
    "DCF_SUMMARY",
    "PORTFOLIO_REVIEW",
    "PORTFOLIO_RISK",
    "BACKTEST_PERFORMANCE",
}

# ---------------------------------------------------------------------------
# 1. PDF Export (ReportLab)
# ---------------------------------------------------------------------------


def generate_pdf_report(title: str, report_type: str, data: dict[str, Any]) -> bytes:
    """Generate institutional research PDF document."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=12,
    )
    h2_style = ParagraphStyle(
        "SectionH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=14,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "BodyDark",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#334155"),
        spaceAfter=6,
    )
    meta_style = ParagraphStyle(
        "MetaText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#64748b"),
    )

    story = []

    # Title & Metadata
    story.append(Paragraph(title, title_style))
    ticker = data.get("ticker", "N/A")
    analyst = data.get("analyst", "AnalystForge Research")
    as_of = data.get("as_of", datetime.now(UTC).strftime("%Y-%m-%d"))

    meta_table = Table(
        [
            [
                Paragraph(f"<b>Ticker:</b> {ticker}", meta_style),
                Paragraph(f"<b>Template:</b> {report_type}", meta_style),
            ],
            [
                Paragraph(f"<b>Analyst:</b> {analyst}", meta_style),
                Paragraph(f"<b>As Of:</b> {as_of}", meta_style),
            ],
        ],
        colWidths=[260, 260],
    )
    meta_table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, -1), (-1, -1), 1, colors.HexColor("#e2e8f0")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 14))

    # Executive Summary Section
    story.append(Paragraph("1. Executive Summary & Investment Thesis", h2_style))
    summary_text = data.get(
        "summary",
        f"Institutional evaluation for {data.get('company_name', ticker)}. "
        "Analysis synthesizes audited regulatory filings, quantitative valuation models, and verified market intelligence.",
    )
    story.append(Paragraph(summary_text, body_style))
    story.append(Spacer(1, 10))

    # Financial & Valuation Multiples Table
    story.append(Paragraph("2. Financial Performance & Valuation Benchmarks", h2_style))
    metrics = data.get("metrics", [])

    table_data = [["Metric", "Value", "Source", "As of"]]
    for row in metrics:
        table_data.append(list(row))

    pdf_table = Table(table_data, colWidths=[140, 120, 140, 120])
    pdf_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                ("ALIGN", (3, 1), (3, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(pdf_table)
    story.append(Spacer(1, 14))

    # Risk & Disclaimers Section
    story.append(Paragraph("3. Operational Risks & Attestation", h2_style))
    risk_text = data.get("risks", "No risk assessment supplied.")
    story.append(Paragraph(risk_text, body_style))

    doc.build(story)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 2. PowerPoint Tear Sheet Export (python-pptx)
# ---------------------------------------------------------------------------


def generate_pptx_report(title: str, report_type: str, data: dict[str, Any]) -> bytes:
    """Generate 16:9 widescreen PowerPoint research presentation."""
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    blank_layout = prs.slide_layouts[6]

    # --- Slide 1: Cover Slide (Dark Navy) ---
    slide1 = prs.slides.add_slide(blank_layout)
    bg1 = slide1.shapes.add_shape(
        1, 0, 0, prs.slide_width, prs.slide_height
    )  # MSO_SHAPE.RECTANGLE = 1
    bg1.fill.solid()
    bg1.fill.fore_color.rgb = RGBColor(15, 23, 42)  # #0f172a
    bg1.line.color.rgb = RGBColor(15, 23, 42)

    tx_box = slide1.shapes.add_textbox(Inches(1.5), Inches(2.2), Inches(10.3), Inches(3.0))
    tf = tx_box.text_frame
    p1 = tf.paragraphs[0]
    p1.text = title
    p1.font.size = Pt(36)
    p1.font.bold = True
    p1.font.color.rgb = RGBColor(255, 255, 255)

    p2 = tf.add_paragraph()
    p2.text = f"{report_type} | Asset: {data.get('ticker', 'N/A')} | As Of: {data.get('as_of', datetime.now(UTC).strftime('%Y-%m-%d'))}"
    p2.font.size = Pt(18)
    p2.font.color.rgb = RGBColor(148, 163, 184)
    p2.space_before = Pt(12)

    p3 = tf.add_paragraph()
    p3.text = "AnalystForge Institutional Equity Research Terminal"
    p3.font.size = Pt(13)
    p3.font.color.rgb = RGBColor(59, 130, 246)
    p3.space_before = Pt(24)

    # --- Slide 2: Executive Summary & Performance ---
    slide2 = prs.slides.add_slide(blank_layout)
    # Header
    h_box = slide2.shapes.add_textbox(Inches(1.0), Inches(0.6), Inches(11.3), Inches(1.0))
    p_h = h_box.text_frame.paragraphs[0]
    p_h.text = f"{data.get('ticker', 'Asset')} - Investment Thesis & Performance"
    p_h.font.size = Pt(24)
    p_h.font.bold = True
    p_h.font.color.rgb = RGBColor(15, 23, 42)

    # Summary box
    s_box = slide2.shapes.add_textbox(Inches(1.0), Inches(1.8), Inches(5.3), Inches(4.8))
    stf = s_box.text_frame
    sp1 = stf.paragraphs[0]
    sp1.text = "Executive Summary"
    sp1.font.size = Pt(16)
    sp1.font.bold = True
    sp1.font.color.rgb = RGBColor(30, 41, 59)

    summary_bullets = [
        data.get("summary", "Report inputs unavailable."),
        data.get("risks", "No risk assessment supplied."),
    ]
    for b in summary_bullets:
        bp = stf.add_paragraph()
        bp.text = f"• {b}"
        bp.font.size = Pt(13)
        bp.font.color.rgb = RGBColor(71, 85, 105)
        bp.space_before = Pt(10)

    # Table on Right Side
    metrics_pairs = [
        ("Metric", "Value"),
        *((str(row[0]), str(row[1])) for row in data.get("metrics", [])),
    ]
    rows = len(metrics_pairs)
    cols = 2
    tbl_shape = slide2.shapes.add_table(
        rows, cols, Inches(6.8), Inches(1.8), Inches(5.5), Inches(4.5)
    )
    tbl = tbl_shape.table
    tbl.columns[0].width = Inches(3.2)
    tbl.columns[1].width = Inches(2.3)

    for r_idx, (m_label, m_val) in enumerate(metrics_pairs):
        c0 = tbl.cell(r_idx, 0)
        c1 = tbl.cell(r_idx, 1)
        c0.text = m_label
        c1.text = m_val
        for c in (c0, c1):
            for para in c.text_frame.paragraphs:
                para.font.size = Pt(13)
                if r_idx == 0:
                    para.font.bold = True
                    para.font.color.rgb = RGBColor(255, 255, 255)
                    c.fill.solid()
                    c.fill.fore_color.rgb = RGBColor(15, 23, 42)
                else:
                    para.font.color.rgb = RGBColor(30, 41, 59)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 3. Excel Live Formula Export (xlsxwriter)
# ---------------------------------------------------------------------------


def generate_excel_report(title: str, report_type: str, data: dict[str, Any]) -> bytes:
    """Generate Excel workbook with live formulas for financial analysis."""
    import xlsxwriter

    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(
        buf, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False}
    )
    ws = wb.add_worksheet("Financial Model")
    facts = wb.add_worksheet("Report")
    facts.set_column("A:D", 28)
    facts.write_string("A1", title)
    facts.write_string("A2", data.get("summary", "No report inputs supplied."))
    for idx, row in enumerate(data.get("metrics", []), start=3):
        facts.write_row(idx, 0, row)
    ws.set_column("A:F", 23)
    ws.write_string(
        "A1", "Enter sourced annual inputs to calculate gross profit and operating income."
    )
    ws.write_row("A3", ["Line item", *(f"Period {i}" for i in range(1, 6))])
    for idx, label in enumerate(
        ("Revenue", "Cost of goods sold", "Gross profit", "Operating expenses", "Operating income"),
        start=3,
    ):
        ws.write_string(idx, 0, label)
    for col in "BCDEF":
        ws.write_formula(f"{col}6", f'=IF(COUNT({col}4:{col}5)=2,{col}4-{col}5,"")', None, "")
        ws.write_formula(f"{col}8", f'=IF(COUNT({col}6:{col}7)=2,{col}6-{col}7,"")', None, "")
    ws.write_string("A10", "Average annual revenue")
    ws.write_formula("B10", '=IF(COUNT(B4:F4)>0,AVERAGE(B4:F4),"")', None, "")
    ws.write_string("A11", "Cumulative operating income")
    ws.write_formula("B11", '=IF(COUNT(B8:F8)=5,SUM(B8:F8),"")', None, "")
    wb.close()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 4. CSV, JSON, Markdown String Generators
# ---------------------------------------------------------------------------


def generate_markdown_report(title: str, report_type: str, data: dict[str, Any]) -> str:
    """Generate clean GitHub Flavored Markdown."""
    ticker = data.get("ticker", "N/A")
    as_of = data.get("as_of", datetime.now(UTC).strftime("%Y-%m-%d"))
    analyst = data.get("analyst", "AnalystForge Quantitative System")

    type_display = (
        f"Institutional Equity {report_type.capitalize()}"
        if report_type == "TEARSHEET"
        else report_type
    )
    return (
        f"# {title}\n\n"
        f"**Report Type:** {type_display} | **Ticker:** {ticker} | **Date:** {as_of}\n"
        f"**Analyst:** {analyst}\n\n"
        f"## 1. Executive Summary\n"
        f"{data.get('summary', 'Institutional investment analysis based on audited regulatory disclosures.')}\n\n"
        f"## 2. Key Valuation Multiples & Financials\n"
        + "\n".join(" | ".join(str(value) for value in row) for row in data.get("metrics", []))
        + "\n"
    )


def generate_csv_report(title: str, report_type: str, data: dict[str, Any]) -> str:
    """Generate structured CSV table."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Title", title])
    writer.writerow(["Report Type", report_type])
    writer.writerow(["Ticker", data.get("ticker", "N/A")])
    writer.writerow(["As Of", data.get("as_of", datetime.now(UTC).strftime("%Y-%m-%d"))])
    writer.writerow([])
    writer.writerow(["Metric", "Value", "Source", "As of"])
    for row in data.get("metrics", []):
        writer.writerow(list(row))
    return buf.getvalue()


def generate_json_report(title: str, report_type: str, data: dict[str, Any]) -> str:
    """Generate formatted JSON report."""
    return json.dumps(
        {
            "title": title,
            "report_type": report_type,
            "ticker": data.get("ticker"),
            "as_of": data.get("as_of", datetime.now(UTC).strftime("%Y-%m-%d")),
            "data": data,
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# 5. Master Dispatcher
# ---------------------------------------------------------------------------


def build_report_file(
    title: str,
    report_type: str,
    format_str: str,
    data: dict[str, Any],
) -> tuple[bytes, str, str]:
    """Compile report in target format; returns (binary_content, media_type, filename)."""
    fmt = format_str.upper().strip()
    safe_title = title.lower().replace(" ", "_").replace("/", "_")[:32]

    if fmt == "PDF":
        content = generate_pdf_report(title, report_type, data)
        return content, "application/pdf", f"{safe_title}.pdf"

    elif fmt == "PPTX":
        content = generate_pptx_report(title, report_type, data)
        return (
            content,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            f"{safe_title}.pptx",
        )

    elif fmt in {"EXCEL", "XLSX"}:
        content = generate_excel_report(title, report_type, data)
        return (
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"{safe_title}.xlsx",
        )

    elif fmt == "MARKDOWN":
        md = generate_markdown_report(title, report_type, data)
        return md.encode("utf-8"), "text/markdown", f"{safe_title}.md"

    elif fmt == "CSV":
        csv_str = generate_csv_report(title, report_type, data)
        return csv_str.encode("utf-8"), "text/csv", f"{safe_title}.csv"

    elif fmt == "JSON":
        js_str = generate_json_report(title, report_type, data)
        return js_str.encode("utf-8"), "application/json", f"{safe_title}.json"

    else:
        raise ValueError(
            f"Unsupported format '{fmt}'. Supported formats: {', '.join(sorted(SUPPORTED_FORMATS))}"
        )
