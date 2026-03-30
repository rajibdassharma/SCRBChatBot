from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, func
from database import Base
from sqlalchemy.orm import relationship

class AccusedDetail(Base):
    __tablename__ = "accused_details"
    id = Column(Integer, primary_key=True, autoincrement=True)
    arrest_id = Column(Integer, ForeignKey("arrests.id", ondelete="CASCADE"), nullable=False)
    photo_path = Column(String(500), nullable=True)
    email = Column(String(200), nullable=True)
    mobile = Column(String(20), nullable=True)
    occupation = Column(String(200), nullable=True)
    remarks = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    arrest = relationship("Arrest", back_populates="accused_details")
