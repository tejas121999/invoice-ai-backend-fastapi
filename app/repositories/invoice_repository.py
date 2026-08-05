from datetime import datetime, timezone, date
from decimal import Decimal
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.models.invoice import Invoice
from app.models.extracted_invoice import ExtractedInvoiceData
from app.utils.invoice_status import InvoiceStatus
from sqlalchemy import func


def create_invoice_record(db: Session, file_data: dict, uploadedBy: int | None = None):
    invoice = Invoice(
        fileName=file_data["fileName"],
        filePath=file_data["filePath"],
        fileType=file_data["fileType"],
        uploadStatus="uploaded",
        processingStatus=InvoiceStatus.UPLOADED.value,
        uploadedBy=uploadedBy
    )

    db.add(invoice)
    db.flush()  # Flush to get the invoice ID

    return invoice


def get_invoice_by_id(db: Session, invoice_id: int):
    return db.query(Invoice).filter(Invoice.id == invoice_id).first()


def get_extracted_invoice_data_by_invoice_id(db: Session, invoice_id: int):
    return (
        db.query(ExtractedInvoiceData)
        .filter(ExtractedInvoiceData.invoiceId == invoice_id)
        .first()
    )


def save_extract_result(
    db: Session,
    invoice_id: int,
    extraction_data: dict
):
    invoice = get_invoice_by_id(db, invoice_id)

    if not invoice:
        return None

    normalized = normalization_extraction_payload(
        extraction_data
    )

    invoice.rawText = normalized["rawText"]
    invoice.processedAt = datetime.now(timezone.utc)

    existing_extraction = (
        get_extracted_invoice_data_by_invoice_id(
            db=db,
            invoice_id=invoice_id
        )
    )

    extracted_payload = {
        "invoiceId": invoice_id,
        "invoiceNumber": normalized["fields"].get(
            "invoiceNumber"
        ),
        "vendorName": normalized["fields"].get(
            "vendorName"
        ),
        "invoiceDate": normalized["fields"].get(
            "invoiceDate"
        ),
        "dueDate": normalized["fields"].get(
            "dueDate"
        ),
        "subtotal": normalized["fields"].get(
            "subtotal"
        ),
        "taxAmount": normalized["fields"].get(
            "taxAmount"
        ),
        "totalAmount": normalized["fields"].get(
            "totalAmount"
        ),
        "currency": normalized["fields"].get(
            "currency"
        ),
        "extractedFieldsJson": normalized["fields"],
        "confidenceJson": normalized["confidence"],
        "reviewedFieldsJson": {},
        "isReviewed": False,
        "reviewedBy": None
    }

    if existing_extraction:
        for key, value in extracted_payload.items():
            setattr(existing_extraction, key, value)
    else:
        existing_extraction = ExtractedInvoiceData(
            **extracted_payload
        )
        db.add(existing_extraction)

    db.add(invoice)
    db.flush()

    return {
        "invoice": invoice,
        "extracted_data": existing_extraction
    }


def normalization_extraction_payload(extraction_data: dict):
    data = extraction_data.get("data", extraction_data)

    return {
        "rawText": data.get("rawText", ""),
        "fields": data.get("fields", {}),
        "confidence": data.get("confidence", {})
    }


def get_all_invoices(db: Session, skip: int = 0, limit: int = 10):
    return (
        db.query(Invoice)
        .order_by(Invoice.createdAt.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def _to_json_safe(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(v) for v in value]
    return value


def update_invoice_review(
    db: Session,
    invoice_id: int,
    review_data: dict,
    reviewed_by: int
):

    invoice = get_invoice_by_id(db, invoice_id)

    if not invoice:
        return None

    extracted_data = get_extracted_invoice_data_by_invoice_id(
        db=db,
        invoice_id=invoice_id
    )

    if not extracted_data:
        return None

    reviewed_fields = {
        "invoiceNumber": review_data.get("invoiceNumber"),
        "vendorName": review_data.get("vendorName"),
        "invoiceDate": review_data.get("invoiceDate"),
        "dueDate": review_data.get("dueDate"),
        "subtotal": review_data.get("subtotal"),
        "taxAmount": review_data.get("taxAmount"),
        "totalAmount": review_data.get("totalAmount"),
        "currency": review_data.get("currency")
    }

    reviewed_fields_json = {
        key: _to_json_safe(value)
        for key, value in reviewed_fields.items()
    }

    now = datetime.now(timezone.utc)

    extracted_data.reviewedFieldsJson = reviewed_fields_json
    extracted_data.reviewedData = reviewed_fields_json
    extracted_data.isReviewed = True
    extracted_data.reviewedBy = reviewed_by
    extracted_data.updatedAt = now

    extracted_data.invoiceNumber = reviewed_fields.get("invoiceNumber")
    extracted_data.vendorName = reviewed_fields.get("vendorName")
    extracted_data.invoiceDate = reviewed_fields.get("invoiceDate")
    extracted_data.dueDate = reviewed_fields.get("dueDate")
    extracted_data.subtotal = reviewed_fields.get("subtotal")
    extracted_data.taxAmount = reviewed_fields.get("taxAmount")
    extracted_data.totalAmount = reviewed_fields.get("totalAmount")
    extracted_data.currency = reviewed_fields.get("currency")

    db.add(extracted_data)
    db.flush()

    return {
        "invoice": invoice,
        "extracted_data": extracted_data
    }


def count_invoice(db: Session):
    return db.query(Invoice).count()


def update_invoice_status(
    db: Session,
    invoice: Invoice,
    new_status: str,
) -> Invoice:
    invoice.processingStatus = new_status
    invoice.updatedAt = datetime.now(timezone.utc)

    db.add(invoice)
    db.flush()

    return invoice


def get_invoice_status_counts(db: Session):
    return (
        db.query(
            Invoice.processingStatus,
            func.count(Invoice.id)
        )
        .group_by(Invoice.processingStatus)
        .all()
    )
