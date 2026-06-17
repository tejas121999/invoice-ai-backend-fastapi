from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from app.core.database import Base
from datetime import datetime


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    invoiceId = Column("invoiceId", Integer, ForeignKey(
        "invoices.id"), nullable=False)
    fieldName = Column("fieldName", String(128), nullable=False)
    oldValue = Column("oldValue", Text)
    newValue = Column("newValue", Text)
    changedBy = Column("changedBy", Integer, ForeignKey("users.id"))
    changedAt = Column("changedAt", DateTime)
    createdAt = Column("createdAt", DateTime, default=datetime.utcnow)
    updatedAt = Column("updatedAt", DateTime, default=datetime.utcnow)
