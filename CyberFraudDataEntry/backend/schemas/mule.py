from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from utils.sanitize import strip_html
from utils.validators import validate_amount as _validate_amount


def _sanitize(cls, v):  # noqa: N805 - Pydantic validator signature
    return strip_html(v) if isinstance(v, str) else v


class MuleCreate(BaseModel):
    report_date: date

    accounts_most_liens: str | None = None
    recruiters_for_lien_accounts: str | None = None
    accounts_max_money_routed: str | None = None
    accounts_max_transactions: str | None = None
    recency_atm_transactions: str | None = None
    cash_withdrawals_mule_wise: str | None = None
    atm_geo_identification: str | None = None
    atm_table_by_transactions: str | None = None
    cheque_withdrawal_branches: str | None = None
    money_left_system_stats: str | None = None
    crypto_mule_accounts: str | None = None

    _sanitize_text = field_validator(
        "accounts_most_liens", "recruiters_for_lien_accounts",
        "accounts_max_money_routed", "accounts_max_transactions",
        "recency_atm_transactions", "cash_withdrawals_mule_wise",
        "atm_geo_identification", "atm_table_by_transactions",
        "cheque_withdrawal_branches", "money_left_system_stats",
        "crypto_mule_accounts",
    )(_sanitize)


class MuleResponse(MuleCreate):
    id: int
    unit_id: int
    unit_name: str | None = None
    submitted_by: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    class Config:
        from_attributes = True


# -- Mule Report child schemas ----------------------------------------

class MoneyTransferCreate(BaseModel):
    account_no: Optional[str] = None
    transaction_id: Optional[str] = None
    bank: Optional[str] = None
    layer: Optional[int] = None
    dest_account_no: Optional[str] = None
    ifsc_code: Optional[str] = None
    transaction_date: Optional[str] = None
    dest_transaction_id: Optional[str] = None
    transaction_amount: Decimal = Decimal('0')
    disputed_amount: Decimal = Decimal('0')
    reference_no: Optional[str] = None
    remarks: Optional[str] = None
    action_taken_by_bank: Optional[str] = None
    date_of_action: Optional[str] = None

    _sanitize_text = field_validator(
        "account_no", "transaction_id", "bank", "dest_account_no", "ifsc_code",
        "transaction_date", "dest_transaction_id", "reference_no", "remarks",
        "action_taken_by_bank", "date_of_action",
    )(_sanitize)
    _check_amounts = field_validator("transaction_amount", "disputed_amount")(_validate_amount)


class OtherTransactionCreate(BaseModel):
    account_no: Optional[str] = None
    transaction_id: Optional[str] = None
    transaction_date: Optional[str] = None
    transaction_amount: Decimal = Decimal('0')
    reference_no: Optional[str] = None
    remarks: Optional[str] = None
    action_taken_by_bank: Optional[str] = None
    date_of_action: Optional[str] = None

    _sanitize_text = field_validator(
        "account_no", "transaction_id", "transaction_date",
        "reference_no", "remarks", "action_taken_by_bank", "date_of_action",
    )(_sanitize)
    _check_amount = field_validator("transaction_amount")(_validate_amount)


class TransactionOnHoldCreate(BaseModel):
    account_no: Optional[str] = None
    transaction_id: Optional[str] = None
    hold_date: Optional[str] = None
    hold_amount: Decimal = Decimal('0')
    action_taken_by_bank: Optional[str] = None
    date_of_action: Optional[str] = None
    layer: Optional[int] = None

    _sanitize_text = field_validator(
        "account_no", "transaction_id", "hold_date",
        "action_taken_by_bank", "date_of_action",
    )(_sanitize)
    _check_amount = field_validator("hold_amount")(_validate_amount)


class OtherLessThan500Create(BaseModel):
    account_no: Optional[str] = None
    transaction_id: Optional[str] = None
    reference_no: Optional[str] = None
    remarks: Optional[str] = None
    action_taken_by_bank: Optional[str] = None
    date_of_action: Optional[str] = None

    _sanitize_text = field_validator(
        "account_no", "transaction_id", "reference_no", "remarks",
        "action_taken_by_bank", "date_of_action",
    )(_sanitize)


class AepsTransactionCreate(BaseModel):
    account_no: Optional[str] = None
    transaction_id: Optional[str] = None
    withdrawal_date: Optional[str] = None
    withdrawal_amount: Decimal = Decimal('0')
    reference_no: Optional[str] = None
    remarks: Optional[str] = None
    action_taken_by_bank: Optional[str] = None
    date_of_action: Optional[str] = None
    layer: Optional[int] = None

    _sanitize_text = field_validator(
        "account_no", "transaction_id", "withdrawal_date",
        "reference_no", "remarks", "action_taken_by_bank", "date_of_action",
    )(_sanitize)
    _check_amount = field_validator("withdrawal_amount")(_validate_amount)


class AtmWithdrawalCreate(BaseModel):
    account_no: Optional[str] = None
    transaction_id: Optional[str] = None
    withdrawal_datetime: Optional[str] = None
    withdrawal_amount: Decimal = Decimal('0')
    disputed_amount: Decimal = Decimal('0')
    atm_id: Optional[str] = None
    atm_location: Optional[str] = None
    reference_no: Optional[str] = None
    remarks: Optional[str] = None
    action_taken_by_bank: Optional[str] = None
    date_of_action: Optional[str] = None

    _sanitize_text = field_validator(
        "account_no", "transaction_id", "withdrawal_datetime",
        "atm_id", "atm_location", "reference_no", "remarks",
        "action_taken_by_bank", "date_of_action",
    )(_sanitize)
    _check_amounts = field_validator("withdrawal_amount", "disputed_amount")(_validate_amount)


# -- Mule Report Create / Response ------------------------------------

class MuleReportCreate(BaseModel):
    acknowledgement_no: str = ""
    fir_no: str = ""
    status: str = "draft"  # draft, submitted
    money_transfers: List[MoneyTransferCreate] = Field(default_factory=list)
    other_transactions: List[OtherTransactionCreate] = Field(default_factory=list)
    transactions_on_hold: List[TransactionOnHoldCreate] = Field(default_factory=list)
    others_less_than_500: List[OtherLessThan500Create] = Field(default_factory=list)
    aeps_transactions: List[AepsTransactionCreate] = Field(default_factory=list)
    atm_withdrawals: List[AtmWithdrawalCreate] = Field(default_factory=list)

    _sanitize_text = field_validator("acknowledgement_no", "fir_no")(_sanitize)


class MuleReportResponse(BaseModel):
    id: str
    unit_id: int
    unit_name: Optional[str] = None
    acknowledgement_no: str
    fir_no: str
    status: str = "draft"
    money_transfers: list = []
    other_transactions: list = []
    transactions_on_hold: list = []
    others_less_than_500: list = []
    aeps_transactions: list = []
    atm_withdrawals: list = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class MuleReportListItem(BaseModel):
    id: str
    acknowledgement_no: str
    fir_no: str
    status: str = "draft"
    unit_name: Optional[str] = None
    created_at: Optional[str] = None
    money_transfer_count: int = 0
    other_count: int = 0
    hold_count: int = 0
    less_500_count: int = 0
    aeps_count: int = 0
    atm_count: int = 0

    class Config:
        from_attributes = True
