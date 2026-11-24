from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExtractionRequest(BaseModel):
    invoice_id: int = Field(..., alias="invoiceId")
    file_path: str = Field(..., alias="filePath", min_length=1)

    model_config = ConfigDict(populate_by_name=True)


class ExtractionFields(BaseModel):
    invoice_number: str | None = Field(
        default=None,
        alias="invoiceNumber"
    )
    vendor_name: str | None = Field(
        default=None,
        alias="vendorName"
    )
    invoice_date: str | None = Field(
        default=None,
        alias="invoiceDate"
    )
    due_date: str | None = Field(
        default=None,
        alias="dueDate"
    )
    subtotal: float | None = None
    tax_amount: float | None = Field(
        default=None,
        alias="taxAmount"
    )
    total_amount: float | None = Field(
        default=None,
        alias="totalAmount"
    )
    currency: str | None = None
    po_number: str | None = Field(default=None, alias="poNumber")
    vendor_gst: str | None = Field(default=None, alias="vendorGst")
    payment_terms: str | None = Field(default=None, alias="paymentTerms")
    shipping_charges: float | None = Field(
        default=None,
        alias="shippingCharges"
    )
    discount: float | None = None
    vendor_address: str | None = Field(
        default=None,
        alias="vendorAddress"
    )
    payment_reference: str | None = Field(
        default=None,
        alias="paymentReference"
    )

    model_config = ConfigDict(populate_by_name=True)


class ExtractionConfidence(BaseModel):
    invoice_number: float = Field(
        default=0.0,
        alias="invoiceNumber"
    )
    vendor_name: float = Field(
        default=0.0,
        alias="vendorName"
    )
    invoice_date: float = Field(
        default=0.0,
        alias="invoiceDate"
    )
    due_date: float = Field(
        default=0.0,
        alias="dueDate"
    )
    subtotal: float = 0.0
    tax_amount: float = Field(
        default=0.0,
        alias="taxAmount"
    )
    total_amount: float = Field(
        default=0.0,
        alias="totalAmount"
    )
    currency: float = 0.0
    po_number: float = Field(default=0.0, alias="poNumber")
    vendor_gst: float = Field(default=0.0, alias="vendorGst")
    payment_terms: float = Field(default=0.0, alias="paymentTerms")
    shipping_charges: float = Field(
        default=0.0,
        alias="shippingCharges"
    )
    discount: float = 0.0
    vendor_address: float = Field(default=0.0, alias="vendorAddress")
    payment_reference: float = Field(
        default=0.0,
        alias="paymentReference"
    )

    model_config = ConfigDict(populate_by_name=True)


class ExtractionError(BaseModel):
    field: str | None = None
    message: str


class ExtractionData(BaseModel):
    invoice_id: int = Field(..., alias="invoiceId")
    raw_text: str = Field(default="", alias="rawText")
    fields: ExtractionFields
    confidence: ExtractionConfidence
    errors: list[ExtractionError | dict[str, Any]] = Field(
        default_factory=list
    )

    model_config = ConfigDict(populate_by_name=True)


class ExtractionResponse(BaseModel):
    success: bool
    message: str
    data: ExtractionData
