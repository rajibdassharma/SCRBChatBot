"""PDF renderer for the Daily Work Done report (per-PS aggregated).

Layout matches Pawan's paper template with one change: each row is
one PS (aggregated across every FIR that PS logged on the selected
date), not one FIR. The 'FIR No.' column is replaced with 'FIR
Count' and numeric fields are SUMMED. Final Report becomes
'A / B / C' counts (comma-joined non-zero counts).

  Row 1  : title
  Row 2  : subtitle
  Row 3+ : two-row grouped header + 45 PS rows + Totals row

Landscape A4 -- 15 columns fits with a thin body font.
"""
from __future__ import annotations

from datetime import date as date_t

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from reports.base import (
    KSP_GREY_SOFT,
    KSP_NAVY,
    STYLES,
    build_pdf,
)


_RED  = colors.HexColor("#b10000")
_YEL  = colors.HexColor("#c67c1d")   # yellow band on the paper form (deeper for legibility)
_GRN  = colors.HexColor("#0a6b28")


# Groups mirror the paper form's colour bands:
#   red   -- notices
#   yellow -- lien / unlien
#   green -- outcomes
# Each entry: (group_label, colour, list of (col_label, aggregator_key))

_GROUPS: list[tuple[str, colors.Color, list[tuple[str, str]]]] = [
    ("Notices", _RED, [
        ("35(3)/41A",            "notices_35_41a_count"),
        ("91/92/94 — Banks",     "notices_91_92_94_banks"),
        ("91/92/94 — Intermed.", "notices_91_92_94_intermediary"),
        ("91/92/94 — Acc. Hldr", "notices_91_92_94_account_holder"),
        ("91/92/94 — CDR/IPDR",  "notices_91_92_94_cdr_ipdr"),
    ]),
    ("Lien / Unlien", _YEL, [
        ("Lien Req",    "lien_requests_count"),
        ("Freeze Req",  "freeze_requests_count"),
        ("Lien Amount", "total_lien_amount"),
        ("Unlien Req",  "unlien_requests_count"),
        ("Defreeze Req","defreeze_requests_count"),
        ("Unlien Amt",  "total_unlien_amount"),
    ]),
    ("Outcomes", _GRN, [
        ("Arrests",      "arrests_count"),
        ("Statements",   "statements_count"),
        ("Final (A/B/C)", "final_report_abc"),  # composite string like "A:1, B:0, C:2"
    ]),
]

_METRIC_COUNT = sum(len(cols) for _, _, cols in _GROUPS)  # 14
_FIXED_COLS = 3  # Sl.No + Police Station + FIR Count
_COL_COUNT = _FIXED_COLS + _METRIC_COUNT  # 17


def _fmt_amount(v) -> str:
    if v is None or v == 0:
        return ""
    return f"{float(v):,.0f}"


def _fmt_int(v) -> str:
    if v is None or v == 0:
        return ""
    return str(int(v))


def render_daily_work_daily_pdf(
    rows: list[dict],
    *,
    target_date: date_t,
) -> bytes:
    """rows: one dict per PS. Each dict has 'unit_name', 'ps_name',
    'fir_count', every summed numeric key, and 'final_report_abc'
    (pre-formatted 'A:n, B:m, C:k')."""

    # ── Header rows ───────────────────────────────────────────────
    group_row: list[str] = ["Sl.No", "Police Station", "FIR Count"]
    metric_row: list[str] = ["", "", ""]
    for gname, _colour, cols in _GROUPS:
        group_row.append(gname)
        group_row.extend([""] * (len(cols) - 1))
        for label, _key in cols:
            metric_row.append(label)

    # ── Body ──────────────────────────────────────────────────────
    body: list[list[str]] = []
    totals: dict[str, float] = {k: 0 for _g, _c, cols in _GROUPS for k, _v in [(k, None) for _l, k in cols]}
    total_fir_count = 0
    total_final: dict[str, int] = {"A": 0, "B": 0, "C": 0}

    for i, r in enumerate(rows, start=1):
        fir_count = int(r.get("fir_count") or 0)
        total_fir_count += fir_count
        row = [
            str(i),
            r.get("ps_name") or "—",
            _fmt_int(fir_count) if fir_count else "",
        ]
        for _gname, _colour, cols in _GROUPS:
            for _label, key in cols:
                if key == "final_report_abc":
                    row.append(r.get("final_report_abc") or "")
                    for letter in ("A", "B", "C"):
                        total_final[letter] += int(r.get(f"final_report_{letter.lower()}") or 0)
                elif "amount" in key:
                    v = r.get(key) or 0
                    totals[key] = totals.get(key, 0) + float(v)
                    row.append(_fmt_amount(v))
                else:
                    v = r.get(key) or 0
                    totals[key] = totals.get(key, 0) + int(v)
                    row.append(_fmt_int(v))
        body.append(row)

    # Grand totals row
    total_row: list[str] = ["", "Grand Total", str(total_fir_count) if total_fir_count else ""]
    for _gname, _colour, cols in _GROUPS:
        for _label, key in cols:
            if key == "final_report_abc":
                parts = [f"{letter}:{n}" for letter, n in total_final.items() if n]
                total_row.append(", ".join(parts) if parts else "")
            elif "amount" in key:
                total_row.append(_fmt_amount(totals.get(key, 0)))
            else:
                total_row.append(_fmt_int(int(totals.get(key, 0))))

    # ── Column widths (landscape A4 usable ≈ 267mm) ───────────────
    # Sl.No 10, PS 46, FIR Count 15, then 14 metric cols share ≈ 196mm
    metric_w = 14 * mm
    col_widths = [10 * mm, 46 * mm, 15 * mm] + [metric_w] * _METRIC_COUNT

    # ── Style ─────────────────────────────────────────────────────
    style_cmds: list = [
        # Group header row -- coloured bands per section
        ("BACKGROUND", (0, 0), (2, 0), KSP_NAVY),      # Sl.No / PS / FIR Count span-header
        ("TEXTCOLOR",  (0, 0), (2, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, 0), 8),
        ("ALIGN",      (0, 0), (-1, 0), "CENTER"),
        ("VALIGN",     (0, 0), (-1, 1), "MIDDLE"),

        # Metric header row
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#1c4267")),
        ("TEXTCOLOR",  (0, 1), (-1, 1), colors.white),
        ("FONTNAME",   (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 1), (-1, 1), 7),
        ("ALIGN",      (0, 1), (-1, 1), "CENTER"),

        # First 3 columns span both header rows
        ("SPAN", (0, 0), (0, 1)),
        ("SPAN", (1, 0), (1, 1)),
        ("SPAN", (2, 0), (2, 1)),

        # Body
        ("FONTSIZE",   (0, 2), (-1, -2), 7),
        ("ALIGN",      (0, 2), (0, -1), "CENTER"),          # Sl.No
        ("ALIGN",      (2, 2), (-1, -1), "RIGHT"),
        ("ALIGN",      (1, 2), (1, -1), "LEFT"),            # PS name
        ("ROWBACKGROUNDS", (0, 2), (-1, -2), [colors.white, KSP_GREY_SOFT]),
        ("GRID",       (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("LEFTPADDING",   (0, 0), (-1, -1), 2),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 2),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),

        # Grand-total row -- bold yellow band
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ffd400")),
        ("FONTNAME",   (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE",   (0, -1), (-1, -1), 8),
        ("TEXTCOLOR",  (0, -1), (-1, -1), KSP_NAVY),
    ]

    # Merge + colour each group header cell
    col_cursor = _FIXED_COLS
    for _gname, colour, cols in _GROUPS:
        span_from = col_cursor
        span_to = col_cursor + len(cols) - 1
        if span_to > span_from:
            style_cmds.append(("SPAN", (span_from, 0), (span_to, 0)))
        style_cmds.append(("BACKGROUND", (span_from, 0), (span_to, 0), colour))
        col_cursor = span_to + 1

    table = Table(
        [group_row, metric_row] + body + [total_row],
        colWidths=col_widths,
        hAlign="LEFT",
        repeatRows=2,
    )
    table.setStyle(TableStyle(style_cmds))

    flowables = [
        Paragraph(f"Daily Work Done — {target_date.strftime('%d %b %Y')}", STYLES["title"]),
        Paragraph(
            f"Per-Police-Station totals across every FIR investigated on this date. "
            f"Amounts in ₹. Blank cells indicate no activity.",
            STYLES["subtitle"],
        ),
        Spacer(1, 4 * mm),
        table,
    ]

    return build_pdf(
        flowables,
        landscape_mode=True,
        title=f"Daily Work Done {target_date.isoformat()}",
    )
