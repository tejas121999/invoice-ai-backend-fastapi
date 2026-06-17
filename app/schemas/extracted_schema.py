from pydantic import BaseModel


class ExtractedInvoiceResponse(BaseModel):
    vendor_name: str
    invoice_number: str
    total_amount: float
    confidence_score: float

    class Config:
        from_attributes = True
