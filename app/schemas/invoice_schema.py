import datetime

from pydantic import BaseModel


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
    uploadedAt: datetime.datetime | None


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
