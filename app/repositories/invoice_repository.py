from datetime import datetime, timezone, date
from decimal import Decimal
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.models.invoice import Invoice
from app.models.extracted_invoice import ExtractedInvoiceData
from app.utils.invoice_status import InvoiceStatus
from sqlalchemy import case, distinct, func, literal
from app.utils.similarity_utils import normalize_text


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

    reviewed_fields = dict(extracted_data.reviewedFieldsJson or {})
    fixed_fields = (
        "invoiceNumber",
        "vendorName",
        "invoiceDate",
        "dueDate",
        "subtotal",
        "taxAmount",
        "totalAmount",
        "currency"
    )
    reviewed_fields.update({
        field_name: review_data[field_name]
        for field_name in fixed_fields
        if field_name in review_data
    })

    dynamic_fields = (
        "poNumber",
        "vendorGst",
        "paymentTerms",
        "shippingCharges",
        "discount",
        "vendorAddress",
        "paymentReference"
    )
    reviewed_fields.update({
        field_name: review_data[field_name]
        for field_name in dynamic_fields
        if field_name in review_data
    })

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

    if "invoiceNumber" in review_data:
        extracted_data.invoiceNumber = review_data["invoiceNumber"]
    if "vendorName" in review_data:
        extracted_data.vendorName = review_data["vendorName"]
    if "invoiceDate" in review_data:
        extracted_data.invoiceDate = review_data["invoiceDate"]
    if "dueDate" in review_data:
        extracted_data.dueDate = review_data["dueDate"]
    if "subtotal" in review_data:
        extracted_data.subtotal = review_data["subtotal"]
    if "taxAmount" in review_data:
        extracted_data.taxAmount = review_data["taxAmount"]
    if "totalAmount" in review_data:
        extracted_data.totalAmount = review_data["totalAmount"]
    if "currency" in review_data:
        extracted_data.currency = review_data["currency"]

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


def get_feature_candidate_invoices(
    db: Session,
    current_invoice_id: int
):
    """
    Return extracted invoice records except the current invoice.

    Initially, compare against reviewed invoices because reviewed
    fields are more reliable than raw OCR fields.
    """

    return (
        db.query(ExtractedInvoiceData)
        .filter(
            ExtractedInvoiceData.invoiceId != current_invoice_id,
            ExtractedInvoiceData.isReviewed.is_(True)
        )
        .all()
    )


def get_duplicate_frequency_counts(
    db: Session,
    current_invoice_id: int,
    vendor_name: str | None,
    invoice_number: str | None
) -> dict[str, int]:
    normalized_vendor = normalize_text(vendor_name)
    normalized_invoice_number = normalize_text(invoice_number)

    if not normalized_vendor and not normalized_invoice_number:
        return {
            "vendorOccurrenceCount": 0,
            "invoiceNumberOccurrenceCount": 0,
            "vendorInvoiceOccurrenceCount": 0
        }

    vendor_name_expression = func.regexp_replace(
        func.lower(func.coalesce(ExtractedInvoiceData.vendorName, "")),
        r"[^a-z0-9]",
        "",
        "g"
    )
    invoice_number_expression = func.regexp_replace(
        func.lower(func.coalesce(ExtractedInvoiceData.invoiceNumber, "")),
        r"[^a-z0-9]",
        "",
        "g"
    )

    vendor_count = (
        func.count(distinct(case(
            (vendor_name_expression == normalized_vendor,
             ExtractedInvoiceData.invoiceId)
        )))
        if normalized_vendor
        else literal(0)
    )
    invoice_number_count = (
        func.count(distinct(case(
            (invoice_number_expression == normalized_invoice_number,
             ExtractedInvoiceData.invoiceId)
        )))
        if normalized_invoice_number
        else literal(0)
    )
    vendor_invoice_count = (
        func.count(distinct(case(
            (
                (vendor_name_expression == normalized_vendor)
                & (invoice_number_expression == normalized_invoice_number),
                ExtractedInvoiceData.invoiceId
            )
        )))
        if normalized_vendor and normalized_invoice_number
        else literal(0)
    )

    counts = (
        db.query(
            vendor_count,
            invoice_number_count,
            vendor_invoice_count
        )
        .filter(
            ExtractedInvoiceData.invoiceId != current_invoice_id,
            ExtractedInvoiceData.isReviewed.is_(True)
        )
        .one()
    )

    return {
        "vendorOccurrenceCount": counts[0],
        "invoiceNumberOccurrenceCount": counts[1],
        "vendorInvoiceOccurrenceCount": counts[2]
    }
