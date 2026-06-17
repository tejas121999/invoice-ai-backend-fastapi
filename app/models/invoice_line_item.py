from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Numeric
from app.core.database import Base
from datetime import datetime


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"

    id = Column(Integer, primary_key=True)
    invoiceId = Column("invoiceId", Integer, ForeignKey(
        "invoices.id"), nullable=False)
    lineNumber = Column("lineNumber", Integer)
    description = Column(String(500))
    quantity = Column("quantity", Numeric(14, 3))
    unitPrice = Column("unitPrice", Numeric(14, 2))
    taxAmount = Column("taxAmount", Numeric(14, 2))
    totalAmount = Column("totalAmount", Numeric(14, 2))
    createdAt = Column("createdAt", DateTime, default=datetime.utcnow)
    updatedAt = Column("updatedAt", DateTime, default=datetime.utcnow)
