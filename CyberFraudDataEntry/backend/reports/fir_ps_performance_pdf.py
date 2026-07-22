"""PDF renderer for the FIR Dashboard → PS-performance table.

Same shape as `submission_status_pdf.py` but only 4 columns, so the
page is portrait rather than landscape.

Mirrors the on-screen columns:
  # | District | Police Station | Total FIRs

Uses the shared chrome from `reports/base.py` so headers, fonts, and
colors stay consistent with the other reports.
"""
from __future__ import annotations

from datetime import date as date_t

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
    """
    header = ["#", "District", "Police Station", "Total FIRs"]
    body: list[list] = [
        [str(i + 1), r.district, r.ps_name or "—", r.fir_count]
        for i, r in enumerate(rows)
    ]

    # Column widths (portrait A4 minus margins ≈ 180mm).
    col_widths = [
        12 * mm,   # #
        58 * mm,   # District
        80 * mm,   # Police Station
        30 * mm,   # Total FIRs
    ]

    grand_total = sum(r.fir_count for r in rows)
    zero_count = sum(1 for r in rows if r.fir_count == 0)

    if date_from == date_to:
        window_label = date_from.strftime("%d %b %Y")
    else:
        window_label = (
            f"{date_from.strftime('%d %b %Y')} — {date_to.strftime('%d %b %Y')}"
        )

    flowables: list = []
    flowables.extend(report_title(
        "FIR Dashboard — PS Performance",
        f"FIRs registered during {window_label} · {len(rows)} police stations",
    ))
    flowables.append(spacer(2))
    flowables.append(section_heading(
        f"Grand Total: {grand_total} FIRs · {zero_count} PSes with zero activity"
    ))
    flowables.append(spacer(2))
    flowables.append(data_table(header, body, col_widths=col_widths))

    return build_pdf(
        flowables,
        landscape_mode=False,
        title=f"FIR PS Performance — {date_from.isoformat()} to {date_to.isoformat()}",
    )
