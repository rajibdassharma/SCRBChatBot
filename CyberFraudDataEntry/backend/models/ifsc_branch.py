"""IFSC -> bank branch directory (master data).

Loaded from the open Razorpay IFSC dataset by analysis/load_ifsc.py.
See migration 025 for why this is a table rather than a file, and why
it belongs in the nightly backup rather than the derived-table
exclusion list.
"""
from sqlalchemy import Column, DateTime, String, func

from database import Base


class IfscBranch(Base):
    __tablename__ = "ifsc_branch"

    #: The code itself, upper-cased on load. Format is 4 letters, a
    #: literal '0', then 6 alphanumerics -- but nothing here enforces
    #: that, because the table is a directory of real codes rather than
    #: a validator for the ones operators type.
    ifsc = Column(String(11), primary_key=True)

    bank = Column(String(200), nullable=True)
    branch = Column(String(200), nullable=True)

    #: The BANK BRANCH's district and state -- not the police district.
    #: all_accounts carries its own branch_district, entered by hand;
    #: the two are reported separately and never merged, because 49% of
    #: the entered values are the operator's own police district.
    district = Column(String(100), nullable=True, index=True)
    state = Column(String(100), nullable=True, index=True)

    #: CENTRE and CITY both appear in the source and often differ from
    #: DISTRICT (e.g. district BANGALORE, city BANGALORE URBAN). Kept
    #: because matching an entered value against all three is what
    #: raised agreement from 33% to 80%.
    city = Column(String(100), nullable=True)
    centre = Column(String(100), nullable=True)

    address = Column(String(500), nullable=True)

    #: Dataset release tag, so a stale load is visible.
    source = Column(String(50), nullable=True)
    loaded_at = Column(DateTime, server_default=func.now())
