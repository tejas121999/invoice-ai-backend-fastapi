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
    save_extract_result,
    update_invoice_review
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


def review_invoice_service(db: Session, invoice_id: int, review_data: dict):
    invoice = get_invoice_by_id(db, invoice_id)

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )

    extract_data = get_extracted_invoice_data_by_invoice_id(
        db=db, invoice_id=invoice_id)

    if not extract_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice extraction result not found. Please process the invoice first."
        )

    if invoice.processingStatus not in ["Processed", "Reviewed"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice must be processed before it can be reviewed."
        )

    invoice_date = review_data.get("invoiceDate")
    due_date = review_data.get("dueDate")

    if invoice_date and due_date and due_date < invoice_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Due date cannot be earlier than invoice date."
        )

    subtotal = review_data.get("subtotal")
    tax_amount = review_data.get("taxAmount")
    total_amount = review_data.get("totalAmount")

    if (
        subtotal is not None
        and tax_amount is not None
        and total_amount is not None
        and subtotal + tax_amount != total_amount
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subtotal plus tax amount must equal total amount."
        )

    result = update_invoice_review(
        db=db,
        invoice_id=invoice_id,
        review_data=review_data,
        reviewed_by=review_data.get("reviewedBy")
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update invoice review."
        )

    return result
