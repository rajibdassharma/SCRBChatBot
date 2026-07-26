"""Shared field validators for Pydantic schemas.

Today this module hosts only the money-field sanity bound, but it is the
intended home for any cross-schema validator (Aadhar / PAN format checks,
phone-number canonicalisation, etc.) — keeps the threshold logic in one
place so a future re-tune doesn't drift between case.py and mule.py.
"""
from __future__ import annotations

import re
from decimal import Decimal


# FIR No format: server-side accepts 1-4 digits, slash, 4-digit year.
# The 4/4 canonical form is XXXX/YYYY (e.g. 0001/2026) and is what
# every UI entry point ENFORCES CLIENT-SIDE (fir-no.ts). The server
# regex is deliberately looser to grandfather legacy rows created
# before the format was standardised — early operators sometimes
# entered `42/2024` (2-digit numerator, no leading zeros) and the
# system accepted it. Those rows must still update cleanly today.
#
# Cases.fir_no is immutable-after-create (the PUT route silently
# ignores changes), so this validator only really matters for
# create-time writes — where the client already enforces 4/4. Any
# curl / Postman actor could POST a legacy-shaped value, but that
# would be a data-quality problem, not a security one.
_FIR_NO_RE = re.compile(r"^\d{1,4}/\d{4}$")


def validate_fir_no(cls, v):  # noqa: N805 — Pydantic v2 validator signature
    """Enforce the FIR-number format on the server.

    Accepts `X/YYYY` through `XXXX/YYYY` — the strict 4/4 form is
    enforced client-side for NEW writes; the loose 1-4/4 range is
    what legacy rows (created before the standard landed) look like.
    See the comment on `_FIR_NO_RE` above for the rationale.

    - Passes empty / None through unchanged so schemas can still
      accept draft submissions where the field is optional.
    - Trims surrounding whitespace before validating.

    Use with `field_validator(...)`:

        _check_fir_no = field_validator("fir_no")(validate_fir_no)
    """
    if v is None or v == "":
        return v
    s = str(v).strip()
    if not _FIR_NO_RE.fullmatch(s):
        raise ValueError(
            "FIR No must be numeric in the shape N/YYYY through NNNN/YYYY "
            "(new entries should use XXXX/YYYY, e.g. 0001/2026). "
            "Received: " + repr(s)
        )
    return s


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
