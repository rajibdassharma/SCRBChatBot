"""Shared field validators for Pydantic schemas.

Today this module hosts only the money-field sanity bound, but it is the
intended home for any cross-schema validator (Aadhar / PAN format checks,
phone-number canonicalisation, etc.) — keeps the threshold logic in one
place so a future re-tune doesn't drift between case.py and mule.py.
"""
from __future__ import annotations

from decimal import Decimal


# A single bank-hold / refund / petition / mule-transfer above ₹100 crore is
# almost certainly a mis-keyed account number or transaction ID — the
# data-entry team has previously shifted those values into the wrong column.
# If a legitimate larger figure ever shows up, raise the constant after
# review rather than silently accepting outliers.
MAX_AMOUNT = Decimal("1000000000")  # ₹100 crore (10^9)


def validate_amount(cls, v):  # noqa: N805 — Pydantic v2 validator signature
    """Reject negatives and any value above MAX_AMOUNT with a clear message.

    Designed for direct use with `field_validator(...)` in a Pydantic schema:

        _check_amount = field_validator("amount")(validate_amount)
    """
    if v is None:
        return v
    if v < 0:
        raise ValueError("Amount cannot be negative.")
    if v > MAX_AMOUNT:
        raise ValueError(
            f"Amount {v:,.2f} exceeds the per-entry cap of {MAX_AMOUNT:,.2f} "
            f"(₹100 crore). Check whether an account number or transaction "
            f"ID was typed into the amount field by mistake."
        )
    return v
