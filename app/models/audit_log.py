from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from app.core.database import Base
from datetime import datetime


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)

    invoice_id = Column(Integer, ForeignKey("invoices.id"))

    field_name = Column(String(100))
    old_value = Column(String)
    new_value = Column(String)

    changed_at = Column(DateTime, default=datetime.utcnow)
