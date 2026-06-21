from datetime import datetime, timezone
from locale import normalize
from sqlalchemy.orm import Session
from app.models.invoice import Invoice
from app.models.extracted_invoice import ExtractedInvoiceData


def create_invoice_record(db: Session, file_data: dict, uploadedBy: int | None = None):
    invoice = Invoice(
        fileName=file_data["fileName"],
        filePath=file_data["filePath"],
        fileType=file_data["fileType"],
        uploadStatus="uploaded",
        processingStatus="pending",
        uploadedBy=uploadedBy
    )

    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    return invoice


def get_invoice_by_id(db: Session, invoice_id: int):
    return db.query(Invoice).filter(Invoice.id == invoice_id).first()


def get_extracted_invoice_data_by_invoice_id(db: Session, invoice_id: int):
    return (
        db.query(ExtractedInvoiceData)
        .filter(ExtractedInvoiceData.invoiceId == invoice_id)
        .first()
    )


def save_extract_result(db: Session, invoice_id: int, extraction_data: dict):
    invoice = get_invoice_by_id(db, invoice_id)

    if not invoice:
        return None

    normalized = normalization_extraction_payload(extraction_data)

    invoice.processingStatus = "Processed"
    invoice.processedAt = datetime.now(timezone.utc)
    invoice.rawText = normalized["rawText"]

    existing_extraction = get_extracted_invoice_data_by_invoice_id(
        db, invoice_id)

    extracted_payload = {
        "invoiceId": invoice_id,
        "invoiceNumber": normalized["fields"].get("invoiceNumber"),
        "vendorName": normalized["fields"].get("vendorName"),
        "invoiceDate": normalized["fields"].get("invoiceDate"),
        "dueDate": normalized["fields"].get("dueDate"),
        "subtotal": normalized["fields"].get("subtotal"),
        "taxAmount": normalized["fields"].get("taxAmount"),
        "totalAmount": normalized["fields"].get("totalAmount"),
        "currency": normalized["fields"].get("currency"),
        "extractedFieldsJson": normalized["fields"],
        "confidenceJson": normalized["confidence"],
        "reviewedFieldsJson": {},
        "isReviewed": False,
        "reviewedBy": None,
    }

    if existing_extraction:
        for key, value in extracted_payload.item():
            setattr(existing_extraction, key, value)
    else:
        existing_extraction = ExtractedInvoiceData(**extracted_payload)
        db.add(existing_extraction)

    db.commit()
    db.refresh(invoice)
    db.refresh(existing_extraction)

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


def count_invoice(db: Session):
    return db.query(Invoice).count()
