"""PDF renderer for the Portals DSR daily report.

Matches the paper layout the operators submit today
(Portal DSRs-17.07.2026 template):

  Row 1 : merged title
  Row 2 : subtitle (window date + count of PSes submitting)
  Row 3 : two-row header
            group row  : NCRP / Samanvaya / Sahayog / GRM / MRM /
                         Bharatpol / OCWC / NCMEC (Tipline)
            metric row : the 25 sub-column names
  Row 4+ : one row per PS (all 45 always shown, blank cells for
            non-submitters so silent PSes stay visible)

Landscape A3 -- 25 metric columns + Sl.No + PS name simply do not
fit on A4. build_pdf() doesn't support A3, so this file drives
SimpleDocTemplate directly and applies the shared page chrome.
"""
from __future__ import annotations

import io
from datetime import date as date_t

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from reports.base import (
    KSP_GREY_SOFT,
    KSP_NAVY,
    STYLES,
    _draw_page_chrome,
)


# Compact wrapping styles for header cells — needed because A4 landscape
# forces narrow columns and long labels like "NCMEC (Tipline)" or
# "Reply Recv" must wrap inside the cell instead of overflowing.
_HDR_GROUP_STYLE = ParagraphStyle(
    "portalsGroupHdr",
    fontName="Helvetica-Bold",
    fontSize=7.5,
    leading=8.5,
    alignment=TA_CENTER,
    textColor=colors.white,
)
_HDR_METRIC_STYLE = ParagraphStyle(
    "portalsMetricHdr",
    fontName="Helvetica-Bold",
    fontSize=6.5,
    leading=7.5,
    alignment=TA_CENTER,
    textColor=colors.white,
)
_PS_NAME_STYLE = ParagraphStyle(
    "portalsPsName",
    fontName="Helvetica-Bold",
    fontSize=6.5,
    leading=7.5,
    textColor=KSP_NAVY,
)


# ── Column groups (label, span, metric-field-names) ───────────────
# Order + labels match the paper form exactly. The metric field
# names match PortalsDsrEntry columns on the model.

_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("NCRP", [
        ("Received",  "ncrp_received"),
        ("Disposed",  "ncrp_disposed"),
        ("Pending",   "ncrp_pending"),
    ]),
    ("Samanvaya", [
        ("Req Recv",   "samanvaya_request_received"),
        ("Actions",    "samanvaya_actions"),
        ("Act Pend",   "samanvaya_action_pending"),
        ("Req Sent",   "samanvaya_request_sent"),
        ("Reply Recv", "samanvaya_reply_received"),
        ("Rep Pend",   "samanvaya_replies_pending"),
    ]),
    ("Sahayog", [
        ("Unlawful",     "sahayog_unlawful_content_removal"),
        ("Intermediary", "sahayog_intermediary_requests"),
        ("Crypto",       "sahayog_crypto_requests"),
    ]),
    ("GRM", [
        ("Req Recv", "grm_request_received"),
        ("Action",   "grm_action"),
        ("Pending",  "grm_pending"),
    ]),
    ("MRM", [
        ("Req Recv", "mrm_request_received"),
        ("Action",   "mrm_action"),
        ("Pending",  "mrm_pending"),
    ]),
    ("Bharatpol", [
        ("Req Sent", "bharatpol_request_received"),
    ]),
    ("OCWC", [
        ("Received", "ocwc_received"),
        ("Disposed", "ocwc_disposed"),
        ("Pending",  "ocwc_pending"),
    ]),
    ("NCMEC (Tipline)", [
        ("Received", "ncmec_received"),
        ("Disposed", "ncmec_disposed"),
        ("Pending",  "ncmec_pending"),
    ]),
]

_METRIC_COUNT = sum(len(cols) for _, cols in _GROUPS)  # 25
_FIXED_COLS = 2  # Sl.No + Police Station


def render_portals_dsr_daily_pdf(
    rows: list[dict],
    *,
    target_date: date_t,
) -> bytes:
    """rows: list of dicts, one per PS, containing 'unit_name',
    'ps_name', and every metric key from `_GROUPS`. Missing rows
    render as blanks (cells stay empty)."""

    # ── Build the two-row header ─────────────────────────────────
    # Header cells are Paragraphs (not plain strings) so long labels
    # like "NCMEC (Tipline)" / "Reply Recv" wrap inside the narrow
    # A4-landscape columns instead of overflowing.
    group_row: list = [
        Paragraph("Sl.No", _HDR_GROUP_STYLE),
        Paragraph("Police Station", _HDR_GROUP_STYLE),
    ]
    metric_row: list = ["", ""]
    for gname, cols in _GROUPS:
        group_row.append(Paragraph(gname, _HDR_GROUP_STYLE))
        group_row.extend([""] * (len(cols) - 1))  # placeholders for SPAN
        for label, _key in cols:
            metric_row.append(Paragraph(label, _HDR_METRIC_STYLE))

    # ── Data rows ─────────────────────────────────────────────────
    body: list[list] = []
    totals: dict[str, int] = {}
    for i, r in enumerate(rows, start=1):
        row: list = [
            str(i),
            Paragraph(r.get("ps_name") or "—", _PS_NAME_STYLE),
        ]
        for _gname, cols in _GROUPS:
            for _label, key in cols:
                v = r.get(key)
                # Blank (not "0") when the PS didn't submit — matches
                # the paper form's empty-cell convention. Real zero
                # submissions still show "0".
                row.append("" if v is None else str(v))
                if v is not None:
                    totals[key] = totals.get(key, 0) + int(v)
        body.append(row)

    # ── Grand total row (bold yellow band, sums every metric col) ─
    total_row: list = ["", "Grand Total"]
    for _gname, cols in _GROUPS:
        for _label, key in cols:
            n = totals.get(key, 0)
            total_row.append(str(n) if n else "")

    # ── Column widths ─────────────────────────────────────────────
    # Landscape A4 = 297mm × 210mm. With 8mm side margins the usable
    # width is 281mm. Everything MUST fit here — the user reads this
    # on standard printers, not A3.
    #   Sl.No     8mm
    #   Police    40mm  (fits "Bengaluru City (South-East)" wrapped)
    #   25 metrics × 9.3mm = 232.5mm
    #   Total    280.5mm  ⇒ ~0.5mm slack, safely inside 281mm
    metric_w = 9.3 * mm
    col_widths = [8 * mm, 40 * mm] + [metric_w] * _METRIC_COUNT

    # ── Style: header row spans, colours, tight body font ─────────
    style_cmds: list = [
        # Group header (row 0) — navy background, Paragraph carries the font
        ("BACKGROUND", (0, 0), (-1, 0), KSP_NAVY),
        ("VALIGN",     (0, 0), (-1, 1), "MIDDLE"),

        # Metric header (row 1) — lighter navy
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#1c4267")),

        # Sl.No + PS: span both header rows vertically
        ("SPAN", (0, 0), (0, 1)),
        ("SPAN", (1, 0), (1, 1)),

        # Body — 6.5pt so 3-digit values still fit inside 9.3mm cols
        ("FONTSIZE",   (0, 2), (-1, -2), 6.5),
        ("ALIGN",      (0, 2), (0, -1), "CENTER"),         # Sl.No
        ("ALIGN",      (2, 2), (-1, -1), "RIGHT"),         # metric cells
        ("VALIGN",     (0, 2), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 2), (-1, -2), [colors.white, KSP_GREY_SOFT]),
        ("GRID",       (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("LEFTPADDING",   (0, 0), (-1, -1), 1),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 1),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),

        # Grand-total row -- bold yellow band, same treatment as the
        # Daily Work Done report so the two files feel consistent.
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ffd400")),
        ("FONTNAME",   (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE",   (0, -1), (-1, -1), 7),
        ("TEXTCOLOR",  (0, -1), (-1, -1), KSP_NAVY),
        ("ALIGN",      (1, -1), (1, -1), "RIGHT"),          # "Grand Total" label
        ("SPAN",       (0, -1), (1, -1)),                    # merge Sl.No + PS cells
    ]

    # Merge each group header horizontally.
    col_cursor = _FIXED_COLS
    for _gname, cols in _GROUPS:
        span_from = col_cursor
        span_to = col_cursor + len(cols) - 1
        if span_to > span_from:  # skip 1-col groups (Bharatpol)
            style_cmds.append(("SPAN", (span_from, 0), (span_to, 0)))
        col_cursor = span_to + 1

    table = Table([group_row, metric_row] + body + [total_row],
                  colWidths=col_widths,
                  hAlign="LEFT",
                  repeatRows=2)
    table.setStyle(TableStyle(style_cmds))

    flowables = [
        Paragraph(f"Portals DSR — {target_date.strftime('%d %b %Y')}", STYLES["title"]),
        Paragraph(
            f"Daily counters across all 8 external portals, per Police Station. "
            f"Submitted rows only; drafts excluded.",
            STYLES["subtitle"],
        ),
        Spacer(1, 4 * mm),
        table,
    ]

    # Landscape A4 — standard printer paper. Margins tightened to 8mm
    # sides (vs base.py's 15) so we can afford wider columns.
    # build_pdf() bakes 15mm margins so this file drives
    # SimpleDocTemplate directly.
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=8 * mm,
        rightMargin=8 * mm,
        topMargin=24 * mm,
        bottomMargin=14 * mm,
        title=f"Portals DSR {target_date.isoformat()}",
        author="Cyber Fraud Data Entry",
    )
    doc.build(flowables, onFirstPage=_draw_page_chrome, onLaterPages=_draw_page_chrome)
    return buf.getvalue()
