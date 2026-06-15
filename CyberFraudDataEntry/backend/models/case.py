import uuid

from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import relationship
from database import Base

class Case(Base):
    __tablename__ = "cases"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)
    # ps_id captures which PS within the district owns the case. FIRs are
    # independently numbered per PS in police operations, so uniqueness
    # must include this. Added by migration 002.
    ps_id = Column(Integer, ForeignKey("police_stations.id"), nullable=False)
    fir_no = Column(String(50), nullable=True)
    petition_no = Column(String(50), nullable=True)
    registration_date = Column(Date, nullable=True)
    case_type = Column(String(20), nullable=False)  # NCRP, Walk-In
    crime_type = Column(String(30), nullable=False)  # Internet, Digital, Crypto
    facts = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="draft")  # draft, submitted
    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    arrests = relationship("Arrest", back_populates="case", cascade="all, delete-orphan")
    petitions = relationship("Petition", back_populates="case", cascade="all, delete-orphan")
    lien_accounts = relationship("LienAccount", back_populates="case", cascade="all, delete-orphan")
    unfreeze_details = relationship("UnfreezeDetail", back_populates="case", cascade="all, delete-orphan")
    refunds = relationship("Refund", back_populates="case", cascade="all, delete-orphan")

    __table_args__ = (
        # Per-PS FIR namespace. Replaced uq_case_unit_fir in migration 002.
        UniqueConstraint("unit_id", "ps_id", "fir_no", name="uq_case_unit_ps_fir"),
    )
