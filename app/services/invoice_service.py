from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session
from starlette import status
from sqlalchemy.exc import SQLAlchemyError
from app.services.file_upload_service import save_invoice_file
from app.services.audit_service import save_audit_log
from app.repositories.invoice_repository import (
    create_invoice_record,
    get_all_invoices,
    count_invoice,
    get_invoice_by_id,
    get_extracted_invoice_data_by_invoice_id,
    save_extract_result,
    update_invoice_review,
    get_invoice_status_counts
)
from app.services.invoice_status_service import change_invoice_status
from app.utils.invoice_status import InvoiceStatus
from app.services.audit_service import save_audit_log
from app.schemas.extraction_schema import ExtractionRequest
from app.services.extraction_service import extract_invoice
from datetime import date, datetime
from decimal import Decimal
from typing import Any


async def upload_invoice_service(
    db: Session,
    file: UploadFile,
    uploadedBy: int | None = None
):
    file_data = await save_invoice_file(file)
    try:
        invoice = create_invoice_record(
            db=db,
            file_data=file_data,
            uploadedBy=uploadedBy
        )

        save_audit_log(
            db=db,
            entity="Invoice",
            entity_id=invoice.id,
            action="CREATE",
            user_id=uploadedBy,
            old_data={},
            new_data={
                "fileName": invoice.fileName,
                "filePath": invoice.filePath,
                "uploadStatus": invoice.uploadStatus,
                "processingStatus": invoice.processingStatus
            }
        )

        db.commit()
        db.refresh(invoice)

        return invoice

    except SQLAlchemyError:
        db.rollback()
        raise


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


async def mark_invoice_processing_failed(
    db: Session,
    invoice_id: int,
    user_id: int | None,
    reason: str
) -> None:
    failed_invoice = get_invoice_by_id(
        db=db,
        invoice_id=invoice_id
    )

    if not failed_invoice:
        return

    try:
        change_invoice_status(
            db=db,
            invoice=failed_invoice,
            new_status=InvoiceStatus.FAILED,
            user_id=user_id,
            reason=reason
        )

        db.commit()

    except Exception:
        db.rollback()


async def process_invoice_service(
    db: Session,
    invoice_id: int
):
    invoice = get_invoice_by_id(
        db=db,
        invoice_id=invoice_id
    )

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )

    user_id = invoice.uploadedBy

    try:
        # Uploaded/Failed/Processed -> Processing
        change_invoice_status(
            db=db,
            invoice=invoice,
            new_status=InvoiceStatus.PROCESSING,
            user_id=user_id,
            reason="Invoice OCR processing started"
        )

        extraction_request = ExtractionRequest(
            invoice_id=invoice.id,
            file_path=invoice.filePath
        )

        extraction_result = await extract_invoice(
            extraction_request
        )
        extraction_response = extraction_result.model_dump(
            by_alias=True
        )

        saved_result = save_extract_result(
            db=db,
            invoice_id=invoice.id,
            extraction_data=extraction_response
        )

        if not saved_result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invoice extraction result could not be saved."
            )

        extraction_data = extraction_response["data"]

        # Processing -> Processed
        change_invoice_status(
            db=db,
            invoice=invoice,
            new_status=InvoiceStatus.PROCESSED,
            user_id=user_id,
            reason="Invoice OCR extraction completed successfully"
        )

        save_audit_log(
            db=db,
            entity="Invoice",
            entity_id=invoice.id,
            action="PROCESS",
            user_id=user_id,
            old_data={},
            new_data={
                "processingStatus": InvoiceStatus.PROCESSED.value,
                "rawText": extraction_data.get("rawText", ""),
                "fields": extraction_data.get("fields", {}),
                "confidence": extraction_data.get("confidence", {}),
                "errors": extraction_data.get("errors", [])
            }
        )

        db.commit()
        db.refresh(invoice)

        return {
            "invoiceId": invoice.id,
            "processingStatus": invoice.processingStatus
        }

    except HTTPException:
        db.rollback()
        await mark_invoice_processing_failed(
            db=db,
            invoice_id=invoice_id,
            user_id=user_id,
            reason="Invoice processing failed"
        )
        raise

    except Exception as exc:
        db.rollback()

        await mark_invoice_processing_failed(
            db=db,
            invoice_id=invoice_id,
            user_id=user_id,
            reason=str(exc)
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invoice processing failed."
        ) from exc


def review_invoice_service(
    db: Session,
    invoice_id: int,
    review_data: dict
):
    invoice = get_invoice_by_id(db, invoice_id)

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )

    extract_data = get_extracted_invoice_data_by_invoice_id(
        db=db,
        invoice_id=invoice_id
    )

    if not extract_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Invoice extraction result not found. "
                "Please process the invoice first."
            )
        )

    if invoice.processingStatus not in [
        InvoiceStatus.PROCESSED.value,
        InvoiceStatus.REVIEWED.value
    ]:
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

    reviewed_by = review_data.get("reviewedBy")

    old_data = {
        "processingStatus": invoice.processingStatus,
        "reviewFields": get_invoice_review_snapshot(extract_data)
    }

    try:
        # Update reviewed invoice fields.
        # This repository function should use db.flush(), not db.commit().
        result = update_invoice_review(
            db=db,
            invoice_id=invoice_id,
            review_data=review_data,
            reviewed_by=reviewed_by
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update invoice review."
            )

        updated_invoice = result["invoice"]
        updated_extract_data = result["extracted_data"]

        # Processed -> Reviewed.
        # If it is already Reviewed, change_invoice_status() should return
        # without creating another status transition.
        change_invoice_status(
            db=db,
            invoice=updated_invoice,
            new_status=InvoiceStatus.REVIEWED,
            user_id=reviewed_by,
            reason="Invoice fields reviewed and saved"
        )

        new_data = {
            "processingStatus": updated_invoice.processingStatus,
            "reviewFields": get_invoice_review_snapshot(
                updated_extract_data
            )
        }

        # Business-action audit log.
        save_audit_log(
            db=db,
            entity="Invoice",
            entity_id=invoice_id,
            action="REVIEW",
            user_id=reviewed_by,
            old_data=old_data,
            new_data=new_data
        )

        # Commit:
        # 1. Reviewed field updates
        # 2. Status change
        # 3. STATUS_CHANGE audit
        # 4. REVIEW audit
        db.commit()

        db.refresh(updated_invoice)
        db.refresh(updated_extract_data)

        return {
            "invoice": updated_invoice,
            "extracted_data": updated_extract_data
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save invoice review."
        ) from exc


def make_json_serializable(value: Any):
    if isinstance(value, (date, datetime)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, dict):
        return {
            key: make_json_serializable(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            make_json_serializable(item)
            for item in value
        ]

    return value


def get_invoice_review_snapshot(extract_data) -> dict:
    return make_json_serializable({
        "invoiceNumber": extract_data.invoiceNumber,
        "vendorName": extract_data.vendorName,
        "invoiceDate": extract_data.invoiceDate,
        "dueDate": extract_data.dueDate,
        "subtotal": extract_data.subtotal,
        "taxAmount": extract_data.taxAmount,
        "totalAmount": extract_data.totalAmount,
        "currency": extract_data.currency,
        "isReviewed": extract_data.isReviewed,
        "reviewedBy": extract_data.reviewedBy
    })


def get_invoice_summary_service(db: Session):
    total_invoices = count_invoice(db)
    status_rows = get_invoice_status_counts(db)

    status_counts = {
        status_name: count
        for status_name, count in status_rows
    }

    return {
        "totalInvoices": total_invoices,
        "uploaded": status_counts.get(
            InvoiceStatus.UPLOADED.value,
            0
        ),
        "processing": status_counts.get(
            InvoiceStatus.PROCESSING.value,
            0
        ),
        "processed": status_counts.get(
            InvoiceStatus.PROCESSED.value,
            0
        ),
        "reviewed": status_counts.get(
            InvoiceStatus.REVIEWED.value,
            0
        ),
        "failed": status_counts.get(
            InvoiceStatus.FAILED.value,
            0
        )
    }
