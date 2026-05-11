import uuid

from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey, func
from sqlalchemy.orm import relationship
from database import Base

class Arrest(Base):
    __tablename__ = "arrests"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(200), nullable=False)
    address = Column(Text, nullable=True)
    email = Column(String(200), nullable=True)
    aadhar = Column(String(12), nullable=True)
    pan = Column(String(10), nullable=True)
    date_of_arrest = Column(Date, nullable=True)
    statement = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    case = relationship("Case", back_populates="arrests")
    accomplices = relationship("Accomplice", back_populates="arrest", cascade="all, delete-orphan")
    accused_details = relationship("AccusedDetail", back_populates="arrest", cascade="all, delete-orphan")
