"""Human-readable rendering for Pydantic v2 validation errors.

Turns raw entries like:

    {"type": "string_too_long", "loc": ["body", "victim", "house_no"],
     "msg": "String should have at most 100 characters",
     "ctx": {"max_length": 100}}

into:

    "Victim House No must be at most 100 characters long."

so KSP operators (non-technical end users) see plain English in
the toast instead of Pydantic's error language. The 422 handler in
`cyber_fraud.py` calls `to_friendly()` for the response body while
logging the raw (PII-stripped) errors to the systemd journal — so
operators get plain sentences and developers still get exact
failure context.

Two-layer lookup:
  1. LABELS: field-path pattern → display label. Array positions
     become "#N" (1-indexed) so nested lists read naturally
     ("Arrest #1 Aadhar"). Unknown fields fall back to a prettified
     path.
  2. Type templates: error `type` → sentence clause with ctx values
     spliced in (min_length, max_length, ge, le, ...). Unknown
     types fall back to Pydantic's own `msg`.
"""
from __future__ import annotations

from typing import Any


# Field labels. Keys use dot notation with `[]` for list positions.
# Only entries useful to the end user; anything not listed here
# falls through to `_prettify`, which gives a readable-but-generic
# label.
LABELS: dict[str, str] = {
    # ── Case header ──────────────────────────────────────────────
    "fir_no": "FIR Number",
    "petition_no": "Petition Number",
    "registration_date": "Registration Date",
    "case_type": "Case Type",
    "crime_type": "Crime Type",
    "status": "Status",
    "facts": "Case Facts",
    "is_financial": "Financial / Non-Financial",

    # ── Victim ───────────────────────────────────────────────────
    "victim.first_name": "Victim First Name",
    "victim.last_name": "Victim Last Name",
    "victim.age": "Victim Age",
    "victim.gender": "Victim Gender",
    "victim.phone": "Victim Phone",
    "victim.email": "Victim Email",
    "victim.house_no": "Victim House No",
    "victim.street_name": "Victim Street Name",
    "victim.city": "Victim City",
    "victim.state": "Victim State",
    "victim.country": "Victim Country",
    "victim.pincode": "Victim Pincode",
    "victim.amount_lost": "Amount Lost",
    "victim.bank_account_no": "Victim Bank Account Number",
    "victim.bank_name": "Victim Bank Name",
    "victim.bank_branch_address": "Victim Bank Branch Address",

    # ── Arrests (array) ──────────────────────────────────────────
    "arrests[].name": "Arrest #{n} Name",
    "arrests[].address": "Arrest #{n} Address",
    "arrests[].email": "Arrest #{n} Email",
    "arrests[].aadhar": "Arrest #{n} Aadhar",
    "arrests[].pan": "Arrest #{n} PAN",
    "arrests[].date_of_arrest": "Arrest #{n} Date",
    "arrests[].statement": "Arrest #{n} Statement",

    # ── Accomplices + accused details (nested under arrests) ────
    "arrests[].accomplices[].where_met": "Arrest #{n} Accomplice #{m} Where Met",
    "arrests[].accomplices[].where_stayed": "Arrest #{n} Accomplice #{m} Where Stayed",
    "arrests[].accomplices[].interrogation_details": "Arrest #{n} Accomplice #{m} Interrogation Details",
    "arrests[].accused_details[].email": "Arrest #{n} Accused Email",
    "arrests[].accused_details[].mobile": "Arrest #{n} Accused Mobile",
    "arrests[].accused_details[].occupation": "Arrest #{n} Accused Occupation",
    "arrests[].accused_details[].remarks": "Arrest #{n} Accused Remarks",

    # ── Petitions (array) ────────────────────────────────────────
    "petitions[].petition_no": "Petition #{n} Number",
    "petitions[].fir_registered": "Petition #{n} FIR Registered?",
    "petitions[].nature": "Petition #{n} Nature",
    "petitions[].petition_type": "Petition #{n} Type",
    "petitions[].amount": "Petition #{n} Amount",

    # ── Lien accounts (array) ────────────────────────────────────
    "lien_accounts[].case_type": "Lien Account #{n} Case Type",
    "lien_accounts[].account_no": "Lien Account #{n} Account No",
    "lien_accounts[].amount_lien_marked": "Lien Account #{n} Amount",
    "lien_accounts[].layer": "Lien Account #{n} Layer",
    "lien_accounts[].total_amount_in_account": "Lien Account #{n} Total Balance",
    "lien_accounts[].bank_name": "Lien Account #{n} Bank",

    # ── Unfreeze (array) ─────────────────────────────────────────
    "unfreeze_details[].unfreeze_type": "Unfreeze #{n} Type",
    "unfreeze_details[].crime_no": "Unfreeze #{n} Crime No",
    "unfreeze_details[].bank_name": "Unfreeze #{n} Bank",
    "unfreeze_details[].account_no": "Unfreeze #{n} Account No",
    "unfreeze_details[].amount": "Unfreeze #{n} Amount",

    # ── Refunds (array) ──────────────────────────────────────────
    "refunds[].refunded": "Refund #{n} Status",
    "refunds[].victim_name": "Refund #{n} Victim Name",
    "refunds[].amount": "Refund #{n} Amount",
    "refunds[].crime_no_or_petition_no": "Refund #{n} Crime / Petition No",

    # ── Mule report header ───────────────────────────────────────
    "acknowledgement_no": "Acknowledgement Number",

    # ── NIL declaration ──────────────────────────────────────────
    "nil_date": "NIL Date",
    "reason": "Reason",
}


# Placeholders substituted from array positions, in order of nesting.
_PLACEHOLDERS = ("n", "m", "o", "p")


def _pattern_key_and_positions(loc: tuple[Any, ...]) -> tuple[str, list[int]]:
    """From a Pydantic loc like `('body', 'arrests', 0, 'aadhar')` build:
      - the pattern key: `'arrests[].aadhar'`
      - the array positions: `[0]`
    The `body` prefix (FastAPI's marker for request body) is stripped."""
    parts = [p for p in loc if p != "body"]
    positions: list[int] = []
    key_parts: list[str] = []
    for p in parts:
        if isinstance(p, int):
            positions.append(p)
            if key_parts:
                key_parts[-1] += "[]"
        else:
            key_parts.append(str(p))
    return ".".join(key_parts), positions


def _label_for_loc(loc: tuple[Any, ...]) -> str:
    """Look up a display label for a Pydantic loc. Falls back to a
    prettified path if the field isn't registered in LABELS."""
    key, positions = _pattern_key_and_positions(loc)
    if key in LABELS:
        label = LABELS[key]
        for i, pos in enumerate(positions):
            if i < len(_PLACEHOLDERS):
                label = label.replace("{" + _PLACEHOLDERS[i] + "}", str(pos + 1))
        return label
    # Fallback: build a readable label from the path itself.
    parts = [p for p in loc if p != "body"]
    words: list[str] = []
    for p in parts:
        if isinstance(p, int):
            words.append(f"#{p + 1}")
        else:
            words.append(str(p).replace("_", " ").title())
    return " ".join(words) if words else "Value"


def _clause_for_type(err_type: str, msg: str, ctx: dict) -> str:
    """Turn Pydantic v2's error `type` + `ctx` into the tail of a
    plain-English sentence. Falls back to the raw msg if the type
    isn't in our whitelist."""
    if err_type == "missing":
        return "is required."
    if err_type == "string_too_short":
        n = ctx.get("min_length")
        return f"must be at least {n} characters long." if n else "is too short."
    if err_type == "string_too_long":
        n = ctx.get("max_length")
        return f"must be at most {n} characters long." if n else "is too long."
    if err_type in ("string_pattern_mismatch", "pattern"):
        return "is not in the correct format."
    if err_type in ("int_parsing", "int_type", "int_from_float"):
        return "must be a whole number."
    if err_type in ("float_parsing", "decimal_parsing", "float_type"):
        return "must be a number."
    if err_type in ("date_from_datetime_parsing", "date_parsing", "date_type"):
        return "must be a valid date."
    if err_type == "greater_than_equal":
        return f"must be {ctx.get('ge')} or greater."
    if err_type == "less_than_equal":
        return f"must be {ctx.get('le')} or less."
    if err_type == "greater_than":
        return f"must be greater than {ctx.get('gt')}."
    if err_type == "less_than":
        return f"must be less than {ctx.get('lt')}."
    if err_type == "value_error":
        # Pydantic prefixes these with "Value error, "; strip it so
        # the sentence reads naturally when concatenated to the label.
        stripped = msg.removeprefix("Value error, ")
        return stripped if stripped.endswith(".") else stripped + "."
    if err_type == "type_error":
        return "has an invalid value."
    if err_type in ("enum", "literal_error"):
        expected = ctx.get("expected")
        return f"must be one of: {expected}." if expected else "must be one of the allowed values."
    if err_type == "email":
        return "is not a valid email address."
    # Last-resort fallback — echo Pydantic's message with a lowercase
    # first letter so it reads like a sentence tail.
    return (msg[:1].lower() + msg[1:] + ".") if msg else "is invalid."


def to_friendly(errors: list[dict]) -> list[str]:
    """Convert a Pydantic v2 error list into human-readable strings.
    One string per input entry; caller decides whether to join them."""
    out: list[str] = []
    for err in errors:
        loc = tuple(err.get("loc", ()))
        etype = str(err.get("type", ""))
        msg = str(err.get("msg", ""))
        ctx = err.get("ctx") or {}
        label = _label_for_loc(loc)
        clause = _clause_for_type(etype, msg, ctx)
        out.append(f"{label} {clause}".strip())
    return out
