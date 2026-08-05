from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from click import Option
from pydantic import BaseModel, Field, ConfigDict


class InvoiceUploadResponse(BaseModel):
    success: bool
    message: str
    invoiceId: int
    fileName: str
    filePath: str
    uploadStatus: str
    processingStatus: str


class InvoiceResponse(BaseModel):
    id: int
    fileName: str
    filePath: str
    fileType: str
    uploadStatus: str
    processingStatus: str
    uploadedAt: Optional[datetime] | None


class InvoiceSummaryData(BaseModel):
    totalInvoices: int
    uploaded: int
    processing: int
    processed: int
    reviewed: int
    failed: int


class InvoiceSummaryResponse(BaseModel):
    success: bool
    message: str
    data: InvoiceSummaryData


class InvoiceReviewRequest(BaseModel):
    invoiceNumber: Optional[str] = Field(default=None, max_length=120)
    vendorName: Optional[str] = Field(default=None, max_length=255)
    invoiceDate: Optional[date] = None
    dueDate: Optional[date] = None
    subtotal: Optional[Decimal] = Field(default=None, ge=0)
    taxAmount: Optional[Decimal] = Field(default=None, ge=0)
    totalAmount: Optional[Decimal] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, max_length=8)
    reviewedBy: Optional[int] = None


class InvoiceReviewDataResponse(BaseModel):
    invoiceId: int
    status: str
    reviewedFieldsJson: dict
    isReviewed: bool
    reviewedBy: Optional[int] = None
    reviewedAt: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class InvoiceReviewResponse(BaseModel):
    success: bool
    message: str
    data: InvoiceReviewDataResponse


class PaginationMeta(BaseModel):
    page: int
    limit: int
    total_records: int
    total_pages: int


class InvoiceListResponse(BaseModel):
    invoices: list[InvoiceResponse]
    pagination: PaginationMeta


class InvoiceCreate(BaseModel):
    fileName: str
    original_name: str

    class Config:
        from_attributes = True
