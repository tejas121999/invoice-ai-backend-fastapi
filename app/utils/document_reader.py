import logging
from io import BytesIO
from pathlib import Path
from time import perf_counter

import pymupdf  # type: ignore[import]
import pytesseract  # type: ignore[import]
from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError  # type: ignore[import]
from starlette import status

from app.core.config import settings
from app.utils.image_preprocessor import preprocess_image_for_ocr
from app.utils.performance_logging import log_performance
from app.utils.invoice_paths import (
    InvalidInvoicePathError,
    InvoiceFileAccessError,
    InvoiceFileNotFoundError,
    resolve_invoice_path
)

logger = logging.getLogger(__name__)


SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff"
}


def configure_tesseract() -> None:
    if settings.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = (
            settings.TESSERACT_CMD
        )


def run_ocr_on_image(
    image: Image.Image,
    *,
    invoice_id: int | None = None,
    document_type: str | None = None,
    page_number: int | None = None
) -> str:
    configure_tesseract()

    processed_image = preprocess_image_for_ocr(
        image,
        invoice_id=invoice_id,
        document_type=document_type,
        page_number=page_number
    )

    started_at = perf_counter()
    try:
        text = pytesseract.image_to_string(
            processed_image,
            lang=settings.OCR_LANGUAGE,
            config="--oem 3 --psm 6"
        )
    finally:
        log_performance(
            stage="tesseract_ocr",
            duration_ms=(perf_counter() - started_at) * 1000,
            invoice_id=invoice_id,
            document_type=document_type,
            page_number=page_number,
            page_mode="ocr",
            image_dimensions=processed_image.size
        )

    return text.strip()


def read_image_text(
    file_path: Path,
    *,
    invoice_id: int | None = None,
    document_type: str | None = None
) -> str:
    document_type = document_type or file_path.suffix.lstrip(".").lower()

    try:
        started_at = perf_counter()
        with Image.open(file_path) as image:
            image_dimensions = image.size
            log_performance(
                stage="image_load",
                duration_ms=(perf_counter() - started_at) * 1000,
                invoice_id=invoice_id,
                document_type=document_type,
                page_number=1,
                page_mode="ocr",
                image_dimensions=image_dimensions
            )
            logger.info(
                "OCR_PAGE invoice_id=%s document_type=%s "
                "page_number=1 page_mode=ocr image_dimensions=%sx%s",
                invoice_id,
                document_type,
                image_dimensions[0],
                image_dimensions[1]
            )
            return run_ocr_on_image(
                image,
                invoice_id=invoice_id,
                document_type=document_type,
                page_number=1
            )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice file not found."
        ) from exc

    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invoice file cannot be accessed."
        ) from exc

    except UnidentifiedImageError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded image could not be read."
        ) from exc

    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invoice file cannot be accessed."
        ) from exc


def read_pdf_text(
    file_path: Path,
    *,
    invoice_id: int | None = None,
    document_type: str = "pdf"
) -> str:
    """
    First try embedded PDF text.

    If a page contains little or no embedded text, render that page as
    an image and run OCR.
    """

    page_texts: list[str] = []

    try:
        document = pymupdf.open(file_path)

    except (FileNotFoundError, pymupdf.FileNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice file not found."
        ) from exc

    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invoice file cannot be accessed."
        ) from exc

    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invoice file cannot be accessed."
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded PDF could not be opened."
        ) from exc

    try:
        if document.needs_pass:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded PDF is password-protected."
            )

        page_count = document.page_count
        if page_count == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No readable text was found in the invoice."
            )

        for page_index in range(page_count):
            page_number = page_index + 1
            pixmap = None

            try:
                page = document.load_page(page_index)
                started_at = perf_counter()
                try:
                    embedded_text = page.get_text(
                        "text",
                        sort=True
                    ).strip()
                except Exception:
                    log_performance(
                        stage="pdf_embedded_text_extraction",
                        duration_ms=(perf_counter() - started_at) * 1000,
                        invoice_id=invoice_id,
                        document_type=document_type,
                        page_number=page_number,
                        page_mode="failed"
                    )
                    raise

                embedded_text_duration_ms = (
                    perf_counter() - started_at
                ) * 1000

                # A digital invoice should normally contain useful text.
                # Very short text often means it is a scanned PDF.
                if len(embedded_text) >= 30:
                    page_text = embedded_text
                    page_mode = "embedded_text"
                    log_performance(
                        stage="pdf_embedded_text_extraction",
                        duration_ms=embedded_text_duration_ms,
                        invoice_id=invoice_id,
                        document_type=document_type,
                        page_number=page_number,
                        page_mode=page_mode
                    )
                    logger.info(
                        "OCR_PAGE invoice_id=%s document_type=%s "
                        "page_number=%s page_mode=embedded_text",
                        invoice_id,
                        document_type,
                        page_number
                    )
                else:
                    page_mode = "ocr"
                    log_performance(
                        stage="pdf_embedded_text_extraction",
                        duration_ms=embedded_text_duration_ms,
                        invoice_id=invoice_id,
                        document_type=document_type,
                        page_number=page_number,
                        page_mode=page_mode
                    )
                    logger.info(
                        "OCR_PAGE invoice_id=%s document_type=%s "
                        "page_number=%s page_mode=ocr",
                        invoice_id,
                        document_type,
                        page_number
                    )
                    started_at = perf_counter()
                    try:
                        pixmap = page.get_pixmap(
                            dpi=settings.OCR_PDF_DPI,
                            alpha=False
                        )
                    finally:
                        log_performance(
                            stage="pdf_page_render",
                            duration_ms=(perf_counter() - started_at) * 1000,
                            invoice_id=invoice_id,
                            document_type=document_type,
                            page_number=page_number,
                            page_mode=page_mode
                        )

                    started_at = perf_counter()
                    image_dimensions = None
                    with BytesIO(pixmap.tobytes("png")) as image_data:
                        with Image.open(image_data) as image:
                            image.load()
                            image_dimensions = image.size
                            log_performance(
                                stage="pdf_pixmap_to_pillow_conversion",
                                duration_ms=(
                                    perf_counter() - started_at
                                ) * 1000,
                                invoice_id=invoice_id,
                                document_type=document_type,
                                page_number=page_number,
                                page_mode="ocr",
                                image_dimensions=image_dimensions
                            )
                            page_text = run_ocr_on_image(
                                image,
                                invoice_id=invoice_id,
                                document_type=document_type,
                                page_number=page_number
                            )

                    if not page_text:
                        page_text = "[no text detected]"

                page_texts.append(
                    f"[Page {page_number}]\n{page_text}"
                )

            except Exception:
                page_texts.append(
                    f"[Page {page_number}: processing failed]"
                )
            finally:
                del pixmap

    finally:
        document.close()

    return "\n\n".join(page_texts).strip()


def read_document_text(
    file_path: str,
    *,
    invoice_id: int | None = None
) -> str:
    try:
        path = resolve_invoice_path(file_path)
    except InvoiceFileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice file not found."
        ) from exc
    except InvoiceFileAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invoice file cannot be accessed."
        ) from exc
    except InvalidInvoicePathError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        ) from exc

    extension = path.suffix.lower()
    document_type = extension.lstrip(".")

    if extension == ".pdf":
        raw_text = read_pdf_text(
            path,
            invoice_id=invoice_id,
            document_type=document_type
        )

    elif extension in SUPPORTED_IMAGE_EXTENSIONS:
        raw_text = read_image_text(
            path,
            invoice_id=invoice_id,
            document_type=document_type
        )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported invoice file type: {extension}"
            )
        )

    if not raw_text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No readable text was found in the invoice."
        )

    return raw_text
