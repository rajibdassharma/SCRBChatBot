"""Shared PDF utilities for the Reports feature.

Every report (DSR, Mule, Case file, Date-range, Dashboard snapshot)
builds on these helpers so branding, fonts, page chrome, and table
styling stay consistent.

Design notes:
  - reportlab.platypus is used (Flowables + SimpleDocTemplate) — far
    easier to maintain than a low-level Canvas. Every report is a list
    of Flowables.
  - The branded header + page-numbered footer are drawn in
    `_draw_page_chrome`, attached via `onFirstPage` / `onLaterPages`.
  - Returns the PDF as `bytes` so the FastAPI route can wrap it in a
    StreamingResponse with a content-disposition attachment header.
"""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# ── KSP brand palette (matches the React frontend tokens) ────────────
KSP_NAVY = colors.HexColor("#0b2c4a")
KSP_YELLOW = colors.HexColor("#ffd400")
KSP_RED = colors.HexColor("#b10000")
KSP_GREY_SOFT = colors.HexColor("#f3f4f6")

# Logo lives in the React frontend assets; the PDF reads it directly.
_LOGO_PATH = Path(__file__).resolve().parent.parent.parent / "frontend" / "src" / "assets" / "ksp_logo.png"


# ── Style palette ────────────────────────────────────────────────────


def _make_styles() -> dict[str, ParagraphStyle]:
    """Reusable Paragraph styles. Use these instead of inline overrides
    so font sizes / colors stay consistent across reports."""
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ksp_title", parent=base["Title"],
            fontName="Helvetica-Bold", fontSize=18, leading=22,
            textColor=KSP_NAVY, alignment=TA_CENTER, spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "ksp_subtitle", parent=base["Normal"],
            fontName="Helvetica-Oblique", fontSize=10, leading=12,
            textColor=KSP_RED, alignment=TA_CENTER, spaceAfter=12,
        ),
        "section": ParagraphStyle(
            "ksp_section", parent=base["Heading2"],
            fontName="Helvetica-Bold", fontSize=12, leading=14,
            textColor=KSP_NAVY, spaceBefore=12, spaceAfter=6,
            borderPadding=(2, 2, 2, 4), borderColor=KSP_YELLOW,
        ),
        "body": ParagraphStyle(
            "ksp_body", parent=base["BodyText"],
            fontName="Helvetica", fontSize=9, leading=12,
            textColor=colors.black, alignment=TA_LEFT,
        ),
        "label": ParagraphStyle(
            "ksp_label", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=9, leading=11,
            textColor=KSP_NAVY,
        ),
        "value": ParagraphStyle(
            "ksp_value", parent=base["Normal"],
            fontName="Helvetica", fontSize=9, leading=11,
            textColor=colors.black,
        ),
    }


STYLES = _make_styles()


# ── Page chrome (header + footer) ────────────────────────────────────


def _draw_page_chrome(canvas: Canvas, doc) -> None:
    """Header and footer drawn on every page. The header is a yellow
    band with KSP logo and centered title; the footer carries page
    numbers and the generation timestamp."""
    canvas.saveState()

    page_w, page_h = doc.pagesize

    # ── Header band ──
    band_h = 18 * mm
    canvas.setFillColor(KSP_YELLOW)
    canvas.rect(0, page_h - band_h, page_w, band_h, fill=1, stroke=0)
    canvas.setFillColor(KSP_NAVY)
    canvas.rect(0, page_h - band_h - 1.5, page_w, 1.5, fill=1, stroke=0)

    # Logo (left), if it exists locally
    if _LOGO_PATH.exists():
        try:
            canvas.drawImage(
                str(_LOGO_PATH),
                10 * mm, page_h - band_h + 2 * mm,
                width=14 * mm, height=14 * mm,
                preserveAspectRatio=True, mask="auto",
            )
        except Exception:
            pass

    # Title (centered)
    canvas.setFillColor(KSP_NAVY)
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawCentredString(page_w / 2, page_h - band_h + 7 * mm, "Karnataka State Police")
    canvas.setFont("Helvetica-Oblique", 8)
    canvas.setFillColor(KSP_RED)
    canvas.drawCentredString(page_w / 2, page_h - band_h + 3 * mm, "Cyber Fraud Data Entry — Official Report")

    # ── Footer band ──
    canvas.setStrokeColor(KSP_NAVY)
    canvas.setLineWidth(0.4)
    canvas.line(15 * mm, 14 * mm, page_w - 15 * mm, 14 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.grey)
    canvas.drawString(15 * mm, 9 * mm, f"Generated: {datetime.now().strftime('%d %b %Y, %H:%M IST')}")
    canvas.drawCentredString(page_w / 2, 9 * mm, "Confidential — for official use only")
    canvas.drawRightString(page_w - 15 * mm, 9 * mm, f"Page {doc.page}")

    canvas.restoreState()


# ── Public builder ───────────────────────────────────────────────────


def build_pdf(
    flowables: Iterable,
    *,
    landscape_mode: bool = False,
    title: Optional[str] = None,
) -> bytes:
    """Render a list of platypus Flowables to a PDF and return the bytes.

    Args:
        flowables: any iterable of platypus elements (Paragraph, Table,
            Spacer, PageBreak, …).
        landscape_mode: True for wide tables (Mule report).
        title: PDF metadata title (shown in viewer chrome).
    """
    pagesize = landscape(A4) if landscape_mode else A4
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=pagesize,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=24 * mm,   # leave room for the yellow header band
        bottomMargin=18 * mm,
        title=title or "KSP Cyber Fraud Report",
        author="Cyber Fraud Data Entry",
    )
    doc.build(
        list(flowables),
        onFirstPage=_draw_page_chrome,
        onLaterPages=_draw_page_chrome,
    )
    return buf.getvalue()


# ── Reusable building blocks ─────────────────────────────────────────


def report_title(text: str, subtitle: Optional[str] = None) -> list:
    """Big centered title + optional red subtitle (typically the
    PS / unit / date the report covers)."""
    out: list = [Paragraph(text, STYLES["title"])]
    if subtitle:
        out.append(Paragraph(subtitle, STYLES["subtitle"]))
    return out


def section_heading(text: str) -> Paragraph:
    return Paragraph(text, STYLES["section"])


def kv_table(rows: list[tuple[str, str]], col_widths: Optional[tuple[float, float]] = None) -> Table:
    """A 2-column key/value table. Used for header blocks like
    'Date / Unit / Submitted by'. `rows` is a list of (label, value)."""
    data = [[Paragraph(k, STYLES["label"]), Paragraph(v or "—", STYLES["value"])] for k, v in rows]
    cw = col_widths or (45 * mm, 120 * mm)
    t = Table(data, colWidths=cw, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey),
    ]))
    return t


def data_table(
    header: list[str],
    rows: list[list[str]],
    *,
    col_widths: Optional[list[float]] = None,
    repeat_header: bool = True,
) -> Table:
    """A standard data table — KSP-navy header row, alternating row
    background, thin grid. Empty bodies render as a single 'No data' row."""
    cell_styles = STYLES["body"]

    def _fmt(v):
        return Paragraph("" if v is None else str(v), cell_styles)

    if not rows:
        rows = [["—"] * len(header)]

    data = [header] + [[_fmt(v) for v in r] for r in rows]
    t = Table(data, colWidths=col_widths, hAlign="LEFT", repeatRows=1 if repeat_header else 0)
    t.setStyle(TableStyle([
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), KSP_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (-1, 0), "LEFT"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        # Body
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("VALIGN", (0, 1), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, KSP_GREY_SOFT]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
    ]))
    return t


def spacer(height_mm: float = 4) -> Spacer:
    return Spacer(1, height_mm * mm)


def page_break() -> PageBreak:
    return PageBreak()
