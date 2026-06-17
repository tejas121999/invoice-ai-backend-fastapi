from sqlalchemy import Column, Integer, String, Float, ForeignKey, Date, Numeric, JSON, Boolean, DateTime
from app.core.database import Base
from datetime import datetime


class ExtractedInvoiceData(Base):
    __tablename__ = "extracted_invoice_data"

    id = Column(Integer, primary_key=True, index=True)
    invoiceId = Column("invoiceId", Integer, ForeignKey(
        "invoices.id"), nullable=False)
    invoiceNumber = Column("invoiceNumber", String(128))
    vendorName = Column("vendorName", String(255))
    invoiceDate = Column("invoiceDate", Date)
    dueDate = Column("dueDate", Date)
    subtotal = Column("subtotal", Numeric(14, 2))
    taxAmount = Column("taxAmount", Numeric(14, 2))
    totalAmount = Column("totalAmount", Numeric(14, 2))
    currency = Column("currency", String(8))
    confidenceScore = Column("confidenceScore", Float)
    reviewedData = Column("reviewedData", JSON)
    isReviewed = Column("isReviewed", Boolean, nullable=False, default=False)
    reviewedBy = Column("reviewedBy", Integer, ForeignKey("users.id"))
    createdAt = Column("createdAt", DateTime, default=datetime.utcnow)
    updatedAt = Column("updatedAt", DateTime, default=datetime.utcnow)
    extractedFieldsJson = Column("extractedFieldsJson", JSON)
    confidenceJson = Column("confidenceJson", JSON)
    reviewedFieldsJson = Column("reviewedFieldsJson", JSON)
