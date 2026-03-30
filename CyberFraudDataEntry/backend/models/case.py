from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import relationship
from database import Base

class Case(Base):
    __tablename__ = "cases"
    id = Column(Integer, primary_key=True, autoincrement=True)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)
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
        UniqueConstraint("unit_id", "fir_no", name="uq_case_unit_fir"),
    )
