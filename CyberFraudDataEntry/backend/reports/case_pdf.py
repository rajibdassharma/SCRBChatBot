"""Case File PDF renderer.

One PDF = one `cases` row plus every nested child:
  - arrests[]   (each with accomplices[] + accused_details[])
  - petitions[]
  - lien_accounts[]
  - unfreeze_details[]
  - refunds[]

Portrait orientation; nested arrest blocks are rendered as labelled
key/value tables rather than a single wide row, since arrest names +
addresses can be long.

Used by `/api/v1/reports/case.pdf?fir_no=…`.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from reportlab.lib.units import mm

from models.case import Case
from .base import (
    build_pdf,
    data_table,
    kv_table,
    report_title,
    section_heading,
    spacer,
)


# ── Formatting helpers ───────────────────────────────────────────────


def _money(v) -> str:
    if v is None:
        return ""
    if isinstance(v, Decimal):
        v = float(v)
    return f"₹ {v:,.2f}"


def _txt(v) -> str:
    if v is None:
        return ""
    return str(v)


def _date(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (date, datetime)):
        return v.strftime("%d %b %Y")
    return str(v)


# ── Public renderer ──────────────────────────────────────────────────


def render_case_pdf(
    *,
    case: Case,
    ps_label: Optional[str],
    submitted_by_username: Optional[str],
    requested_by_username: str,
) -> bytes:
    """Render a full case file."""
    flow: list = []

    # Title
    title_subtitle = " · ".join([s for s in (
        case.fir_no and f"FIR: {case.fir_no}",
        case.petition_no and f"Petition: {case.petition_no}",
        ps_label,
    ) if s])
    flow += report_title("Case File", subtitle=title_subtitle or None)

    # ── Header block ──
    flow.append(kv_table([
        ("Case ID", case.id),
        ("FIR Number", case.fir_no or "—"),
        ("Petition Number", case.petition_no or "—"),
        ("Registration Date", _date(case.registration_date) or "—"),
        ("Case Type", case.case_type or "—"),
        ("Crime Type", case.crime_type or "—"),
        ("Status", (case.status or "—").upper()),
        ("Police Station", ps_label or "—"),
        ("Submitted by", submitted_by_username or "—"),
        ("Created", case.created_at.strftime("%d %b %Y, %H:%M") if case.created_at else "—"),
        ("Last Updated", case.updated_at.strftime("%d %b %Y, %H:%M") if case.updated_at else "—"),
        ("Generated for", requested_by_username),
    ], col_widths=(45 * mm, 130 * mm)))

    # ── Facts ──
    if case.facts:
        flow.append(spacer(4))
        flow.append(section_heading("Facts of the Case"))
        flow.append(kv_table([("", case.facts)], col_widths=(2 * mm, 173 * mm)))

    # ── 1. Arrests (with sub-tables) ──
    flow.append(spacer(4))
    arrests = list(case.arrests or [])
    flow.append(section_heading(f"Arrests ({len(arrests)})"))
    if not arrests:
        flow.append(kv_table([("", "No arrests recorded.")], col_widths=(2 * mm, 173 * mm)))
    for i, a in enumerate(arrests, 1):
        if i > 1:
            flow.append(spacer(3))
        flow.append(kv_table([
            (f"Arrest #{i} — Name", _txt(a.name)),
            ("Date of Arrest", _date(a.date_of_arrest) or "—"),
            ("Aadhar", _txt(a.aadhar) or "—"),
            ("PAN", _txt(a.pan) or "—"),
            ("Email", _txt(a.email) or "—"),
            ("Address", _txt(a.address) or "—"),
            ("Statement", _txt(a.statement) or "—"),
        ], col_widths=(45 * mm, 130 * mm)))

        # Accomplices
        accs = list(a.accomplices or [])
        if accs:
            flow.append(spacer(2))
            flow.append(data_table(
                ["Accomplice — Where Met", "Where Stayed", "Interrogation Details"],
                [[_txt(x.where_met), _txt(x.where_stayed), _txt(x.interrogation_details)] for x in accs],
                col_widths=[55 * mm, 55 * mm, 65 * mm],
            ))

        # Accused details
        adets = list(a.accused_details or [])
        if adets:
            flow.append(spacer(2))
            flow.append(data_table(
                ["Email", "Mobile", "Occupation", "Remarks"],
                [[_txt(x.email), _txt(x.mobile), _txt(x.occupation), _txt(x.remarks)] for x in adets],
                col_widths=[45 * mm, 30 * mm, 35 * mm, 65 * mm],
            ))

    # ── 2. Petitions ──
    flow.append(spacer(4))
    petitions = list(case.petitions or [])
    flow.append(section_heading(f"Petitions ({len(petitions)})"))
    flow.append(data_table(
        ["Petition No", "FIR Registered", "Why Not", "Nature", "Type", "Amount"],
        [[
            _txt(p.petition_no), _txt(p.fir_registered), _txt(p.why_not),
            _txt(p.nature), _txt(p.petition_type), _money(p.amount),
        ] for p in petitions],
        col_widths=[28 * mm, 25 * mm, 35 * mm, 30 * mm, 25 * mm, 32 * mm],
    ))

    # ── 3. Lien Accounts ──
    flow.append(spacer(4))
    liens = list(case.lien_accounts or [])
    flow.append(section_heading(f"Lien Accounts ({len(liens)})"))
    flow.append(data_table(
        ["Case Type", "Account No", "Amount Lien-Marked", "Layer", "Total in Account", "Bank"],
        [[
            _txt(l.case_type), _txt(l.account_no), _money(l.amount_lien_marked),
            _txt(l.layer), _money(l.total_amount_in_account), _txt(l.bank_name),
        ] for l in liens],
        col_widths=[20 * mm, 30 * mm, 32 * mm, 14 * mm, 32 * mm, 47 * mm],
    ))

    # ── 4. Unfreeze Details ──
    flow.append(spacer(4))
    unfs = list(case.unfreeze_details or [])
    flow.append(section_heading(f"Unfreeze Details ({len(unfs)})"))
    flow.append(data_table(
        ["Type", "Crime No", "Bank", "Account No", "Amount"],
        [[
            _txt(u.unfreeze_type), _txt(u.crime_no), _txt(u.bank_name),
            _txt(u.account_no), _money(u.amount),
        ] for u in unfs],
        col_widths=[28 * mm, 28 * mm, 50 * mm, 35 * mm, 34 * mm],
    ))

    # ── 5. Refunds ──
    flow.append(spacer(4))
    refunds = list(case.refunds or [])
    flow.append(section_heading(f"Refunds ({len(refunds)})"))
    flow.append(data_table(
        ["Refunded?", "Victim Name", "Amount", "Crime / Petition No"],
        [[
            (_txt(r.refunded) or "—").upper(), _txt(r.victim_name),
            _money(r.amount), _txt(r.crime_no_or_petition_no),
        ] for r in refunds],
        col_widths=[22 * mm, 60 * mm, 35 * mm, 58 * mm],
    ))

    return build_pdf(
        flow,
        title=f"Case File — {case.fir_no or case.petition_no or case.id}",
    )
