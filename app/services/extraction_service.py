from app.schemas.extraction_schema import (
    ExtractionConfidence,
    ExtractionData,
    ExtractionFields,
    ExtractionRequest,
    ExtractionResponse,
)


async def extract_invoice(
    payload: ExtractionRequest
) -> ExtractionResponse:
    """
    Internal invoice extraction helper.

    Current implementation is stubbed. It does not read the file or
    perform real OCR yet.
    """

    # This will be used when real OCR is implemented.
    _ = payload.file_path

    return ExtractionResponse(
        success=True,
        message="Extraction completed successfully",
        data=ExtractionData(
            invoice_id=payload.invoice_id,
            raw_text="Sample OCR text",
            fields=ExtractionFields(
                invoice_number="INV-001",
                vendor_name="ABC Ltd",
                invoice_date="2026-04-05",
                due_date=None,
                subtotal=None,
                tax_amount=None,
                total_amount=45000,
                currency=None
            ),
            confidence=ExtractionConfidence(
                invoice_number=0.95,
                vendor_name=0.88,
                invoice_date=0.90,
                due_date=None,
                subtotal=None,
                tax_amount=None,
                total_amount=0.97,
                currency=None
            ),
            errors=[]
        )
    )
