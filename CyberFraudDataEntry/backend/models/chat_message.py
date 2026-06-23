import uuid

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from database import Base


class ChatMessage(Base):
    """Audit row for every chat question — what was asked, what SQL we
    generated, how many rows came back, and any error. Lets us trace
    misuse / hallucinations without having to enable verbose logging."""
    __tablename__ = "chat_messages"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    unit_id = Column(Integer, nullable=True)   # captured for analytics; not FK-enforced
    ps_id = Column(Integer, nullable=True)
    question = Column(Text, nullable=False)
    generated_sql = Column(Text, nullable=True)
    row_count = Column(Integer, nullable=True)
    error = Column(String(500), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
