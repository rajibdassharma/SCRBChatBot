from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, func
from database import Base
from sqlalchemy.orm import relationship

class Accomplice(Base):
    __tablename__ = "accomplices"
    id = Column(Integer, primary_key=True, autoincrement=True)
    arrest_id = Column(Integer, ForeignKey("arrests.id", ondelete="CASCADE"), nullable=False)
    where_met = Column(String(500), nullable=True)
    where_stayed = Column(String(500), nullable=True)
    interrogation_details = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    arrest = relationship("Arrest", back_populates="accomplices")
