from sqlalchemy import Column, Integer, String, JSON, DateTime
from app.core.database import Base
from datetime import datetime


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    entity = Column(String(100), nullable=False)
    entityId = Column(Integer, nullable=False)
    action = Column(String(50), nullable=False)
    performedBy = Column(Integer)
    oldData = Column(JSON)
    newData = Column(JSON)
    createdAt = Column(DateTime, default=datetime.utcnow)
