from unittest import result

from fastapi import APIRouter, Form, HTTPException, Query, UploadFile, File, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import invoice
from app.services.invoice_service import (
    upload_invoice_service,
    get_invoice_services,
    list_invoice_service,
    get_invoice_result_services,
    process_invoice_service,
    review_invoice_service,
    get_invoice_summary_service
)
from app.schemas.invoice_schema import (
    InvoiceListResponse,
    InvoiceReviewRequest,
    InvoiceReviewResponse,
    InvoiceUploadResponse,
    InvoiceResponse,
    InvoiceSummaryResponse
)
from app.schemas.feature_schema import InvoiceFeatureResponse
from app.services.feature_engineering_service import (
    generate_invoice_features_service
)
from app.utils.invoice_paths import invoice_path_for_response

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
        "filePath": invoice_path_for_response(invoice.filePath),
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


@router.get("/metrics/summary", response_model=InvoiceSummaryResponse)
def get_invoice_summary(
    db: Session = Depends(get_db)
):
    summary = get_invoice_summary_service(db)

    return {
        "success": True,
        "message": "Invoice summary fetched successfully.",
        "data": summary
    }


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice = get_invoice_services(db, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.get("/{invoice_id}/result")
def get_invoice_result(
    invoice_id: int,
    db: Session = Depends(get_db)
):
    result = get_invoice_result_services(db, invoice_id)
    print("result", result)
    invoice = result["invoice"]
    extracted_data = result["extracted_data"]

    return {
        "success": True,
        "message": "Invoice result fetched successfully.",
        "data": {
            "invoiceId": invoice.id,
            "status": invoice.processingStatus,  # or processingStatus value like "processed"
            "fileName": invoice.fileName,
            "filePath": invoice_path_for_response(invoice.filePath),
            "uploadedAt": invoice.uploadedAt,
            "processedAt": extracted_data.updatedAt,
            "rawText": invoice.rawText,
            "fields": extracted_data.extractedFieldsJson or {},
            "confidence": extracted_data.confidenceJson,  # Make sure this is parsed JSON
            "reviewedFieldsJson": extracted_data.reviewedFieldsJson or {},
            "isReviewed": extracted_data.isReviewed
        }
    }


@router.put("/{invoice_id}/review", response_model=InvoiceReviewResponse)
def review_invoice(
    invoice_id: int,
    payload: InvoiceReviewRequest,
    db: Session = Depends(get_db)
):

    result = review_invoice_service(
        db=db,
        invoice_id=invoice_id,
        review_data=payload.model_dump()
    )

    invoice = result["invoice"]
    extracted_data = result["extracted_data"]

    return {
        "success": True,
        "message": "Invoice reviewed successfully.",
        "data": {
            "invoiceId": invoice.id,
            "status": invoice.processingStatus,
            "reviewedFieldsJson": extracted_data.reviewedFieldsJson or {},
            "isReviewed": extracted_data.isReviewed,
            "reviewedBy": extracted_data.reviewedBy,
            "reviewedAt": extracted_data.updatedAt
        }
    }


@router.post("/{invoice_id}/process")
async def process_invoice(
    invoice_id: int,
    db: Session = Depends(get_db)
):
    result = await process_invoice_service(
        db=db,
        invoice_id=invoice_id
    )

    return {
        "success": True,
        "message": "Invoice process successfully.",
        "data": result
    }


@router.get(
    "/{invoice_id}/features",
    response_model=InvoiceFeatureResponse
)
def generate_invoice_features(
    invoice_id: int,
    db: Session = Depends(get_db)
):
    result = generate_invoice_features_service(
        db=db,
        invoice_id=invoice_id
    )

    return {
        "success": True,
        "message": "Invoice features generated successfully.",
        "data": result
    }
