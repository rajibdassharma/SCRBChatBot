import uuid

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, func
from database import Base
from sqlalchemy.orm import relationship

class AccusedDetail(Base):
    __tablename__ = "accused_details"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    arrest_id = Column(String(36), ForeignKey("arrests.id", ondelete="CASCADE"), nullable=False)
    photo_path = Column(String(500), nullable=True)
    email = Column(String(200), nullable=True)
    mobile = Column(String(20), nullable=True)
    occupation = Column(String(200), nullable=True)
    remarks = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    arrest = relationship("Arrest", back_populates="accused_details")
