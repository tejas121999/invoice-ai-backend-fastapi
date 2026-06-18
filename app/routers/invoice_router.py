from fastapi import APIRouter, Form, HTTPException, Query, UploadFile, File, Depends
from requests import session
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.invoice_service import (
    upload_invoice_service, get_invoice_services, list_invoice_service)
from app.schemas.invoice_schema import (
    InvoiceListResponse, InvoiceUploadResponse, InvoiceResponse
)


router = APIRouter(
    prefix="/api/invoices",
    tags=["Invoices"]
)


@router.post("/upload", response_model=InvoiceUploadResponse)
async def upload_invoices(
    uploadedBy: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):

    invoice = await upload_invoice_service(
        db=db,
        file=file,
        uploadedBy=uploadedBy
    )
    return {
        "success": True,
        "message": "Invoice uploaded successfully",
        "invoiceId": invoice.id,
        "fileName": invoice.fileName,
        "filePath": invoice.filePath,
        "uploadStatus": invoice.uploadStatus,
        "processingStatus": invoice.processingStatus
    }


@router.get("/", response_model=InvoiceListResponse)
def get_invoices(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100)
):
    return list_invoice_service(db, page=page, limit=limit)


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice = get_invoice_services(db, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice
