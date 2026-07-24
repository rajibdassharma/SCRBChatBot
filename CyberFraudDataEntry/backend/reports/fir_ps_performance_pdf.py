"""PDF renderer for the FIR Dashboard → PS-performance table.

Mirrors the on-screen columns:
  # | District | Police Station | Yesterday | Total FIRs

Uses the shared chrome from `reports/base.py` so headers, fonts, and
colors stay consistent with the other reports.
"""
from __future__ import annotations

from datetime import date as date_t, timedelta

from reportlab.lib.units import mm

from reports.base import (
    build_pdf,
    data_table,
    report_title,
    section_heading,
    spacer,
)
from schemas.dashboard import FirPsPerformanceRow


def render_fir_ps_performance_pdf(
    rows: list[FirPsPerformanceRow],
    *,
    date_from: date_t,
    date_to: date_t,
) -> bytes:
    """Build a portrait PDF of the FIR PS-performance rollup.

    Rows arrive already sorted by the aggregation helper (fir_count
    DESC, then district / PS name). PDF preserves that order — the
    dashboard's client-side re-sort doesn't affect the exported file.

    The Yesterday column shows FIRs registered on the calendar day
    before the report was generated (server today − 1), independent
    of the from/to window — matches the dashboard's Yesterday column.
    """
    yesterday = date_t.today() - timedelta(days=1)
    yday_header = yesterday.strftime("%d %b")  # e.g. "24 Jul"

    header = ["#", "District", "Police Station", yday_header, "Total FIRs"]
    body: list[list] = [
        [str(i + 1), r.district, r.ps_name or "—", r.yesterday_count, r.fir_count]
        for i, r in enumerate(rows)
    ]

    # Column widths (portrait A4 minus margins ≈ 180mm).
    col_widths = [
        12 * mm,   # #
        50 * mm,   # District
        66 * mm,   # Police Station
        24 * mm,   # Yesterday
        28 * mm,   # Total FIRs
    ]

    grand_total = sum(r.fir_count for r in rows)
    grand_yday  = sum(r.yesterday_count for r in rows)
    zero_count  = sum(1 for r in rows if r.fir_count == 0)

    if date_from == date_to:
        window_label = date_from.strftime("%d %b %Y")
    else:
        window_label = (
            f"{date_from.strftime('%d %b %Y')} — {date_to.strftime('%d %b %Y')}"
        )

    flowables: list = []
    flowables.extend(report_title(
        "FIR Dashboard — PS Performance",
        f"FIRs registered during {window_label} · "
        f"Yesterday column = {yesterday.strftime('%d %b %Y')} · "
        f"{len(rows)} police stations",
    ))
    flowables.append(spacer(2))
    flowables.append(section_heading(
        f"Grand Total: {grand_total} FIRs · "
        f"Yesterday: {grand_yday} · "
        f"{zero_count} PSes with zero cumulative activity"
    ))
    flowables.append(spacer(2))
    flowables.append(data_table(header, body, col_widths=col_widths))

    return build_pdf(
        flowables,
        landscape_mode=False,
        title=f"FIR PS Performance — {date_from.isoformat()} to {date_to.isoformat()}",
    )
