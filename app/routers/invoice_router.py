from fastapi import APIRouter, Form, UploadFile, File, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.invoice_service import upload_invoice_service
from app.schemas.invoice_schema import InvoiceUploadResponse


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
