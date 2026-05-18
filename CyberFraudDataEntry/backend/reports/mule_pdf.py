"""Mule Report PDF renderer.

One PDF = one `mule_reports` row + all six related transaction tables
(money transfers, other transactions, transactions-on-hold, others<500,
AEPS, ATM withdrawals). Landscape orientation because some of those
tables are very wide.

Used by `/api/v1/reports/mule.pdf?ack_no=…` in routes_reports.py.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Optional

from reportlab.lib.units import mm

from models.mule_report import MuleReport
from .base import (
    build_pdf,
    data_table,
    kv_table,
    report_title,
    section_heading,
    spacer,
)


# ── Formatting helpers ──────────────────────────────────────────────


def _money(v) -> str:
    if v is None:
        return ""
    if isinstance(v, Decimal):
        v = float(v)
    return f"{v:,.2f}"


def _txt(v) -> str:
    if v is None:
        return ""
    return str(v)


def _date(v) -> str:
    """Field is stored as VARCHAR (not Date) in the schema — passthrough."""
    return _txt(v)


# ── Per-table renderers ─────────────────────────────────────────────


def _w(*widths_mm: float) -> list[float]:
    """Convert a tuple of mm widths to points (reportlab native unit).
    A4 landscape printable width ≈ 267 mm (after 15 mm side margins);
    keep the sum under that to avoid auto-wrap of column headers."""
    return [w * mm for w in widths_mm]


def _money_transfers_table(rows: Iterable) -> object:
    return data_table(
        ["Account", "Txn ID", "Bank", "Layer", "Dest Acct", "IFSC", "Date",
         "Amount", "Disputed", "Action by Bank", "Action Date"],
        [[
            _txt(r.account_no), _txt(r.transaction_id), _txt(r.bank), _txt(r.layer),
            _txt(r.dest_account_no), _txt(r.ifsc_code), _date(r.transaction_date),
            _money(r.transaction_amount), _money(r.disputed_amount),
            _txt(r.action_taken_by_bank), _date(r.date_of_action),
        ] for r in rows],
        col_widths=_w(24, 24, 28, 12, 24, 18, 22, 22, 22, 30, 22),
    )


def _other_txn_table(rows: Iterable) -> object:
    return data_table(
        ["Account", "Txn ID", "Date", "Amount", "Reference", "Action by Bank", "Action Date"],
        [[
            _txt(r.account_no), _txt(r.transaction_id), _date(r.transaction_date),
            _money(r.transaction_amount), _txt(r.reference_no),
            _txt(r.action_taken_by_bank), _date(r.date_of_action),
        ] for r in rows],
        col_widths=_w(35, 35, 28, 28, 35, 60, 28),
    )


def _hold_table(rows: Iterable) -> object:
    return data_table(
        ["Account", "Txn ID", "Hold Date", "Hold Amount", "Layer",
         "Action by Bank", "Action Date"],
        [[
            _txt(r.account_no), _txt(r.transaction_id), _date(r.hold_date),
            _money(r.hold_amount), _txt(r.layer),
            _txt(r.action_taken_by_bank), _date(r.date_of_action),
        ] for r in rows],
        col_widths=_w(35, 35, 28, 32, 16, 60, 28),
    )


def _less500_table(rows: Iterable) -> object:
    return data_table(
        ["Account", "Txn ID", "Reference", "Action by Bank", "Action Date"],
        [[
            _txt(r.account_no), _txt(r.transaction_id), _txt(r.reference_no),
            _txt(r.action_taken_by_bank), _date(r.date_of_action),
        ] for r in rows],
        col_widths=_w(45, 45, 50, 75, 32),
    )


def _aeps_table(rows: Iterable) -> object:
    return data_table(
        ["Account", "Txn ID", "Withdrawal Date", "Amount", "Layer",
         "Action by Bank", "Action Date"],
        [[
            _txt(r.account_no), _txt(r.transaction_id), _date(r.withdrawal_date),
            _money(r.withdrawal_amount), _txt(r.layer),
            _txt(r.action_taken_by_bank), _date(r.date_of_action),
        ] for r in rows],
        col_widths=_w(35, 35, 30, 28, 16, 60, 28),
    )


def _atm_table(rows: Iterable) -> object:
    return data_table(
        ["Account", "Txn ID", "Datetime", "Amount", "Disputed",
         "ATM ID", "ATM Location", "Action by Bank", "Action Date"],
        [[
            _txt(r.account_no), _txt(r.transaction_id), _date(r.withdrawal_datetime),
            _money(r.withdrawal_amount), _money(r.disputed_amount),
            _txt(r.atm_id), _txt(r.atm_location),
            _txt(r.action_taken_by_bank), _date(r.date_of_action),
        ] for r in rows],
        col_widths=_w(24, 24, 26, 22, 22, 20, 40, 30, 22),
    )


# ── Public renderer ─────────────────────────────────────────────────


def render_mule_pdf(
    *,
    report: MuleReport,
    ps_label: Optional[str],
    submitted_by_username: Optional[str],
    requested_by_username: str,
) -> bytes:
    """Render the mule report as a landscape PDF."""
    flow: list = []

    title_subtitle = " · ".join([s for s in (
        report.acknowledgement_no and f"Ack No: {report.acknowledgement_no}",
        report.fir_no and f"FIR: {report.fir_no}",
        ps_label,
    ) if s])

    flow += report_title("Mule Account Report", subtitle=title_subtitle or None)

    # Header metadata
    flow.append(kv_table([
        ("Acknowledgement No", report.acknowledgement_no or "—"),
        ("FIR No", report.fir_no or "—"),
        ("Status", (report.status or "—").upper()),
        ("Police Station", ps_label or "—"),
        ("Submitted by", submitted_by_username or "—"),
        ("Created", report.created_at.strftime("%d %b %Y, %H:%M") if report.created_at else "—"),
        ("Last Updated", report.updated_at.strftime("%d %b %Y, %H:%M") if report.updated_at else "—"),
        ("Generated for", requested_by_username),
    ], col_widths=(50 * mm, 130 * mm)))

    # ── Six sections, each with count in heading ──
    sections: list[tuple[str, list, callable]] = [
        ("Money Transfers", report.money_transfers or [], _money_transfers_table),
        ("Other Transactions", report.other_transactions or [], _other_txn_table),
        ("Transactions on Hold", report.transactions_on_hold or [], _hold_table),
        ("Others < ₹ 500", report.others_less_than_500 or [], _less500_table),
        ("AEPS Transactions", report.aeps_transactions or [], _aeps_table),
        ("ATM Withdrawals", report.atm_withdrawals or [], _atm_table),
    ]

    for label, rows, builder in sections:
        flow.append(spacer(4))
        flow.append(section_heading(f"{label} ({len(rows)})"))
        flow.append(builder(rows))

    return build_pdf(
        flow,
        landscape_mode=True,
        title=f"Mule Report — {report.acknowledgement_no or report.id}",
    )
