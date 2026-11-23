from io import BytesIO
from pathlib import Path

import pymupdf  # type: ignore[import]
import pytesseract  # type: ignore[import]
from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError  # type: ignore[import]
from starlette import status

from app.core.config import settings
from app.utils.image_preprocessor import preprocess_image_for_ocr
from app.utils.invoice_paths import (
    InvalidInvoicePathError,
    InvoiceFileAccessError,
    InvoiceFileNotFoundError,
    resolve_invoice_path
)


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


def run_ocr_on_image(image: Image.Image) -> str:
    configure_tesseract()

    processed_image = preprocess_image_for_ocr(image)

    text = pytesseract.image_to_string(
        processed_image,
        lang=settings.OCR_LANGUAGE,
        config="--oem 3 --psm 6"
    )

    return text.strip()


def read_image_text(file_path: Path) -> str:
    try:
        with Image.open(file_path) as image:
            return run_ocr_on_image(image)

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


def read_pdf_text(file_path: Path) -> str:
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
                embedded_text = page.get_text(
                    "text",
                    sort=True
                ).strip()

                # A digital invoice should normally contain useful text.
                # Very short text often means it is a scanned PDF.
                if len(embedded_text) >= 30:
                    page_text = embedded_text
                else:
                    pixmap = page.get_pixmap(
                        dpi=settings.OCR_PDF_DPI,
                        alpha=False
                    )

                    with BytesIO(pixmap.tobytes("png")) as image_data:
                        with Image.open(image_data) as image:
                            page_text = run_ocr_on_image(image)

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


def read_document_text(file_path: str) -> str:
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

    if extension == ".pdf":
        raw_text = read_pdf_text(path)

    elif extension in SUPPORTED_IMAGE_EXTENSIONS:
        raw_text = read_image_text(path)

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
