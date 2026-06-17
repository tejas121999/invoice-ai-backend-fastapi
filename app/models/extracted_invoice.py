from sqlalchemy import Column, Integer, String, Float, ForeignKey
from app.core.database import Base


class ExtractedInvoiceData(Base):
    __tablename__ = "extracted_invoice_data"

    id = Column(Integer, primary_key=True, index=True)

    invoice_id = Column(Integer, ForeignKey("invoices.id"))

    vendor_name = Column(String(255))
    invoice_number = Column(String(100))
    invoice_date = Column(String(100))

    total_amount = Column(Float)
    tax_amount = Column(Float)

    confidence_score = Column(Float)
