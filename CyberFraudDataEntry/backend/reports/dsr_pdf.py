"""DSR PDF renderer.

Reads pre-aggregated `DsrAggregateRow`s from `dsr_aggregator.py` and
produces a branded PDF. Supports three modes:

  - Single PS, single date  : one section
  - Single PS, date range   : same layout, different title
  - All PSes (super_admin)  : one section per active PS + a TOTAL section

The numbers are computed live from cases / arrests / petitions /
lien_accounts / refunds / mule_reports, filtered on `created_at`.
"""
from __future__ import annotations

from datetime import date
from typing import Sequence

from reportlab.lib.units import mm

from .base import (
    build_pdf,
    data_table,
    kv_table,
    page_break,
    report_title,
    section_heading,
    spacer,
)
from .dsr_aggregator import DsrAggregateRow


def _money(v: float) -> str:
    return f"₹ {v:,.2f}"


def _date_label(date_from: date, date_to: date) -> str:
    if date_from == date_to:
        return date_from.strftime("%d %B %Y")
    return f"{date_from.strftime('%d %b %Y')} – {date_to.strftime('%d %b %Y')}"


def render_dsr_pdf(
    *,
    rows: Sequence[DsrAggregateRow],
    date_from: date,
    date_to: date,
    requested_by_username: str,
    is_all_ps: bool,
) -> bytes:
    """Build the DSR PDF from pre-aggregated rows."""
    flow: list = []
    period_label = _date_label(date_from, date_to)

    # Title — the totals row's label captures the multi-PS scope cleanly:
    # "TOTAL — All Police Stations" or "TOTAL — All Police Stations in <district>"
    if is_all_ps:
        # Last row in multi-PS mode is the TOTAL row; strip the leading
        # "TOTAL — " prefix to use as the title scope.
        if rows and rows[-1].ps_id is None:
            scope_label = rows[-1].ps_label.replace("TOTAL — ", "", 1)
        else:
            scope_label = "All Police Stations"
    else:
        scope_label = rows[0].ps_label if rows else "—"
    flow += report_title(
        "Daily Status Report",
        subtitle=f"{scope_label} — {period_label}",
    )

    # Header metadata
    flow.append(kv_table([
        ("Period", period_label),
        ("Scope", scope_label),
        ("Generated for", requested_by_username),
        ("Filter", "Records created in the selected period"),
    ]))

    if not rows:
        flow.append(spacer(8))
        flow.append(section_heading("No activity in the selected period."))
        return build_pdf(flow, title=f"DSR {date_from.isoformat()}")

    # Render sections
    for i, row in enumerate(rows):
        if i > 0:
            flow.append(page_break() if is_all_ps else spacer(6))
        _render_one_section(flow, row, is_all_ps=is_all_ps)

    return build_pdf(flow, title=f"DSR {date_from.isoformat()} — {scope_label}")


# ── Per-PS section ───────────────────────────────────────────────────


def _render_one_section(flow: list, r: DsrAggregateRow, *, is_all_ps: bool) -> None:
    is_total = r.ps_id is None
    heading = r.ps_label if (is_all_ps or is_total) else "Summary"
    flow.append(section_heading(heading))

    # ── 1. Cases ──
    by_type = ", ".join(f"{k}: {v}" for k, v in sorted(r.cases_by_type.items())) or "—"
    by_crime = ", ".join(f"{k}: {v}" for k, v in sorted(r.cases_by_crime.items())) or "—"
    flow.append(kv_table([
        ("Cases registered", str(r.cases_total)),
        ("By case type", by_type),
        ("By crime type", by_crime),
    ], col_widths=(45 * mm, 130 * mm)))

    flow.append(spacer(3))

    # ── 2. Combined activity table ──
    flow.append(data_table(
        ["Arrests", "Petitions", "Petition Amount",
         "Lien Accounts", "Lien Amount",
         "Refund Records", "Refunds Done", "Refunded Amount",
         "Mule Reports"],
        [[
            str(r.arrests_total),
            str(r.petitions_total),
            _money(r.petitions_amount),
            str(r.lien_count),
            _money(r.lien_amount),
            str(r.refunds_total),
            str(r.refunds_done),
            _money(r.refunds_amount),
            str(r.mule_reports_total),
        ]],
        col_widths=[18 * mm, 20 * mm, 28 * mm, 22 * mm, 26 * mm,
                    25 * mm, 22 * mm, 28 * mm, 22 * mm],
    ))

    # ── 3. Lien per bank (only if there's anything to show) ──
    if r.lien_by_bank:
        flow.append(spacer(4))
        flow.append(section_heading("Lien Accounts by Bank"))
        bank_rows = sorted(r.lien_by_bank.items(), key=lambda kv: -kv[1][1])
        flow.append(data_table(
            ["Bank", "Accounts", "Amount Lien-Marked"],
            [[bank, str(c), _money(amt)] for bank, (c, amt) in bank_rows],
            col_widths=[90 * mm, 30 * mm, 50 * mm],
        ))

    # ── 4. FIRs registered in the period (skip in the TOTAL row —
    #      the same rows already showed in the per-PS sections). ──
    if not is_total and r.firs:
        flow.append(spacer(4))
        flow.append(section_heading("FIRs Registered"))
        flow.append(data_table(
            ["FIR No", "Registration Date", "Case Type", "Crime Type", "Arrests"],
            [
                [
                    f.fir_no or "—",
                    f.registration_date.strftime("%d %b %Y") if f.registration_date else "—",
                    f.case_type or "—",
                    f.crime_type or "—",
                    str(f.arrest_count),
                ]
                for f in r.firs
            ],
            col_widths=[35 * mm, 32 * mm, 28 * mm, 28 * mm, 20 * mm],
        ))

    # ── 5. Arrest details keyed to the FIR ──
    if not is_total and r.arrests:
        flow.append(spacer(4))
        flow.append(section_heading("Arrest Details"))
        flow.append(data_table(
            ["FIR No", "Name", "Date of Arrest", "Aadhar", "Address"],
            [
                [
                    a.fir_no or "—",
                    a.name or "—",
                    a.date_of_arrest.strftime("%d %b %Y") if a.date_of_arrest else "—",
                    a.aadhar or "—",
                    a.address or "—",
                ]
                for a in r.arrests
            ],
            col_widths=[30 * mm, 45 * mm, 25 * mm, 25 * mm, 55 * mm],
        ))
