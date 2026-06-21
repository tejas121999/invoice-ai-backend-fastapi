from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session
from starlette import status

from app.services.file_upload_service import save_invoice_file
from app.repositories.invoice_repository import (
    create_invoice_record,
    get_all_invoices,
    count_invoice,
    get_invoice_by_id,
    get_extracted_invoice_data_by_invoice_id,
    save_extract_result
)
from app.services.python_ocr_client_service import extract_invoice_from_python_service


async def upload_invoice_service(
    db: Session,
    file: UploadFile,
    uploadedBy: int | None = None
):
    file_data = await save_invoice_file(file)

    invoice = create_invoice_record(
        db=db,
        file_data=file_data,
        uploadedBy=uploadedBy
    )

    return invoice


def get_invoice_services(db: Session, invoice_id: int):
    return get_invoice_by_id(db, invoice_id)


def list_invoice_service(db: Session, page: int = 1, limit: int = 10):
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Page number must be greater then or equal to 1"
        )

    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Limit must be between 1 and 100"
        )

    skip = (page - 1) * limit
    invoices = get_all_invoices(db, skip=skip, limit=limit)
    total_records = count_invoice(db)
    return {
        "invoices": invoices,
        "pagination": {
            "page": page,
            "limit": limit,
            "total_records": total_records,
            "total_pages": (total_records + limit - 1) // limit
        }
    }


def get_invoice_result_services(db: Session, invoice_id: int):
    invoice = get_invoice_by_id(db, invoice_id)

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_BAD_REQUEST,
            detail="Invoice not found."
        )

    extract_data = get_extracted_invoice_data_by_invoice_id(db, invoice_id)

    if not extract_data:
        raise HTTPException(
            status_code=status.HTTP_404_BAD_REQUEST,
            detail="Invoice extraction result not found. Please process the invoice first."
        )

    print(invoice, extract_data)
    return {
        "invoice": invoice,
        "extracted_data": extract_data
    }


async def process_invoice_service(db: Session, invoice_id: int):
    invoice = get_invoice_by_id(db, invoice_id)

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )

    payload = {
        "invoiceId": invoice.id,
        "filePath": invoice.filePath
    }

    extraction_response = await extract_invoice_from_python_service(payload)

    saved_result = save_extract_result(
        db=db,
        invoice_id=invoice.id,
        extraction_data=extraction_response
    )

    if not saved_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found."
        )

    return {
        "invoiceId": invoice.id,
        "processingStatus": "process"
    }
