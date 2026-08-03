from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class ExtractionRequest(BaseModel):
    invoice_id: int = Field(..., alias="invoiceId")
    file_path: str = Field(..., alias="filePath", min_length=1)

    model_config = ConfigDict(
        populate_by_name=True
    )


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

    model_config = ConfigDict(
        populate_by_name=True
    )


class ExtractionConfidence(BaseModel):
    invoice_number: float | None = Field(
        default=None,
        alias="invoiceNumber"
    )
    vendor_name: float | None = Field(
        default=None,
        alias="vendorName"
    )
    invoice_date: float | None = Field(
        default=None,
        alias="invoiceDate"
    )
    due_date: float | None = Field(
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
    currency: float | None = None

    model_config = ConfigDict(
        populate_by_name=True
    )


class ExtractionData(BaseModel):
    invoice_id: int = Field(..., alias="invoiceId")
    raw_text: str = Field(default="", alias="rawText")
    fields: ExtractionFields
    confidence: ExtractionConfidence
    errors: list[Any] = Field(default_factory=list)

    model_config = ConfigDict(
        populate_by_name=True
    )


class ExtractionResponse(BaseModel):
    success: bool = True
    message: str
    data: ExtractionData
