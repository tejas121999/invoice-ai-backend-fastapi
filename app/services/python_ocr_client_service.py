import httpx
from fastapi import HTTPException, status
from requests import status_codes

from app.core.config import settings


async def extract_invoice_from_python_service(payload: dict):
    try:
        print("payload", payload)
        async with httpx.AsyncClient(timeout=30.0)as client:
            response = await client.post(
                f"{settings.PYTHON_OCR_SERVICE_URL}/api/extract",
                json=payload
            )

            if response.status_code >= 500:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Python OCR service returned a server error"
                )

            if response.status_code >= 400:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Python OCR service returned an invalid request error"
                )

            extraction = response.json()

            if not isinstance(extraction, dict):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Invalid response from Python OCR service."
                )

            return extraction

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Python OCR service time out"
        )

    except httpx.ConnectError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Python OCR service unavailable"
        )

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to connect to python OCR service"
        )
