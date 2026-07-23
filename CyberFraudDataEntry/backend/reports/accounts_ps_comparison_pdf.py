"""PDF renderer for the Account Details Dashboard → Per-PS Comparison
table.

Same visual shape + shared chrome as `fir_ps_performance_pdf.py` —
8 columns fit comfortably in landscape A4. Row order matches the
on-screen table (Total DESC).
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
from schemas.dashboard import AccountsPsComparison


def render_accounts_ps_comparison_pdf(
    rows: list[AccountsPsComparison],
    *,
    target_date: date_t,
) -> bytes:
    """Build a landscape PDF of the per-PS Account Details rollup.

    The `target_date` cut-off drives both the cumulative Total column
    (records created on-or-before) and the Yesterday column (records
    created on `target_date - 1`).
    """
    yesterday = target_date - timedelta(days=1)
    yday_header = yesterday.strftime("%d %b")   # e.g. "22 Jul"

    header = ["#", "District", "Police Station", "Total", yday_header, "Victim", "Mule", "Non-Mule"]
    body: list[list] = [
        [
            str(i + 1),
            r.unit_name,
            r.ps_name or "—",
            r.total,
            r.yesterday_count,
            r.victims,
            r.mules,
            r.non_mules,
        ]
        for i, r in enumerate(rows)
    ]

    # Column widths (landscape A4 minus margins ≈ 267mm).
    col_widths = [
        10 * mm,   # #
        45 * mm,   # District
        70 * mm,   # PS
        22 * mm,   # Total
        24 * mm,   # Yesterday
        22 * mm,   # Victim
        22 * mm,   # Mule
        26 * mm,   # Non-Mule
    ]

    grand_total = sum(r.total for r in rows)
    grand_yday  = sum(r.yesterday_count for r in rows)
    zero_count  = sum(1 for r in rows if r.total == 0)

    flowables: list = []
    flowables.extend(report_title(
        "Account Details — PS Comparison",
        f"Cumulative as of {target_date.strftime('%d %b %Y')} · "
        f"Yesterday column = {yesterday.strftime('%d %b %Y')}",
    ))
    flowables.append(spacer(2))
    flowables.append(section_heading(
        f"Grand Total: {grand_total} accounts · "
        f"Yesterday: {grand_yday} · "
        f"{zero_count} PSes with zero cumulative activity"
    ))
    flowables.append(spacer(2))
    flowables.append(data_table(header, body, col_widths=col_widths))

    return build_pdf(
        flowables,
        landscape_mode=True,
        title=f"Accounts PS Comparison — {target_date.isoformat()}",
    )
