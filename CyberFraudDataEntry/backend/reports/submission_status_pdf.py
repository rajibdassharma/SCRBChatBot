"""PDF renderer for the Dashboard → Overview → Submission Status table.

Mirrors the on-screen columns:
  # | District | Police Station | Cases | Mule | Total | Last Entry | DSR | NIL

Uses the shared chrome from reports/base.py so headers, fonts, and
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
from schemas.dashboard import SubmissionStatus


def _fmt_last(iso: str | None) -> str:
    if not iso:
        return "Never"
    return iso


def _fmt_dsr(row: SubmissionStatus) -> str:
    return "Filed" if row.dsr_filed else "—"


def _fmt_nil(row: SubmissionStatus) -> str:
    """Cumulative NIL count for this PS. Matches the on-screen NIL
    column so the exported PDF and the dashboard read the same. A
    zero renders as a dash to keep the column visually quiet."""
    return str(row.nil_count) if row.nil_count > 0 else "—"


def render_submission_status_pdf(
    rows: list[SubmissionStatus],
    *,
    target_date: date_t,
) -> bytes:
    """Build a one-table PDF of the submission status rollup.

    Sorted by district then PS — same default the on-screen table
    starts with. Landscape so the 8-column body fits comfortably.
    """
    # Stable sort: district then PS. The frontend lets users re-sort
    # by other columns; the PDF picks the most-asked-for default.
    rows_sorted = sorted(rows, key=lambda r: (r.unit_name, r.ps_name))

    header = ["#", "District", "Police Station", "Cases", "Petitions", "Mule", "Total", "NIL", "Last Entry", "DSR"]
    body = [
        [
            str(i + 1),
            r.unit_name,
            r.ps_name or "—",
            r.cases_count,
            r.petitions_count,
            r.mule_count,
            r.entry_count,
            _fmt_nil(r),
            _fmt_last(r.last_entry_date),
            _fmt_dsr(r),
        ]
        for i, r in enumerate(rows_sorted)
    ]

    # Column widths (landscape A4 minus margins ≈ 267mm).
    col_widths = [
        10 * mm,   # #
        43 * mm,   # District
        60 * mm,   # PS
        16 * mm,   # Cases
        20 * mm,   # Petitions
        16 * mm,   # Mule
        16 * mm,   # Total
        16 * mm,   # NIL
        28 * mm,   # Last Entry
        18 * mm,   # DSR
    ]

    total_entries = sum(r.entry_count for r in rows_sorted)
    nil_count = sum(1 for r in rows_sorted if r.entry_count == 0 and r.nil_declared)
    zero_count = sum(1 for r in rows_sorted if r.entry_count == 0 and not r.nil_declared)

    flowables: list = []
    flowables.extend(report_title(
        "Submission Status",
        f"Daily rollup as of {target_date.strftime('%d %b %Y')} — {len(rows_sorted)} police stations",
    ))
    flowables.append(spacer(2))
    flowables.append(section_heading(
        f"Totals: {total_entries} entries • {nil_count} NIL-declared • {zero_count} silent"
    ))
    flowables.append(spacer(2))
    flowables.append(data_table(header, body, col_widths=col_widths))

    return build_pdf(
        flowables,
        landscape_mode=True,
        title=f"Submission Status — {target_date.isoformat()}",
    )
