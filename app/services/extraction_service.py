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


async def extract_invoice(
    payload: ExtractionRequest
) -> ExtractionResponse:
    try:
        raw_text = read_document_text(
            payload.file_path
        )

        extraction = parse_invoice_fields(
            raw_text
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
