from pathlib import Path
from time import perf_counter

from fastapi import HTTPException
from starlette import status

from app.schemas.extraction_schema import (
    ExtractionConfidence,
    ExtractionData,
    ExtractionFields,
    ExtractionRequest,
    ExtractionResponse
)
from app.utils.document_reader import read_document_text
from app.utils.invoice_parser import parse_invoice_fields
from app.utils.performance_logging import log_performance


async def extract_invoice(
    payload: ExtractionRequest
) -> ExtractionResponse:
    try:
        raw_text = read_document_text(
            payload.file_path,
            invoice_id=payload.invoice_id
        )

        started_at = perf_counter()
        try:
            extraction = parse_invoice_fields(raw_text)
        finally:
            log_performance(
                stage="invoice_parsing",
                duration_ms=(perf_counter() - started_at) * 1000,
                invoice_id=payload.invoice_id,
                document_type=(
                    Path(payload.file_path).suffix
                    .lstrip(".")
                    .lower()
                )
            )

        return ExtractionResponse(
            success=True,
            message="Extraction completed successfully.",
            data=ExtractionData(
                invoice_id=payload.invoice_id,
                raw_text=raw_text,
                fields=ExtractionFields(
                    **extraction["fields"]
                ),
                confidence=ExtractionConfidence(
                    **extraction["confidence"]
                ),
                errors=extraction["errors"]
            )
        )

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                f"Invoice extraction failed: {str(exc)}"
            )
        ) from exc
