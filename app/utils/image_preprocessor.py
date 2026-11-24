from time import perf_counter

import cv2
import numpy as np
from PIL import Image

from app.utils.performance_logging import log_performance


def pil_image_to_opencv(
    image: Image.Image,
    *,
    invoice_id: int | None = None,
    document_type: str | None = None,
    page_number: int | None = None
) -> np.ndarray:
    started_at = perf_counter()
    rgb_image = image.convert("RGB")
    opencv_image = cv2.cvtColor(
        np.array(rgb_image),
        cv2.COLOR_RGB2BGR
    )
    log_performance(
        stage="pillow_to_opencv_conversion",
        duration_ms=(perf_counter() - started_at) * 1000,
        invoice_id=invoice_id,
        document_type=document_type,
        page_number=page_number,
        page_mode="ocr",
        image_dimensions=image.size
    )
    return opencv_image


def preprocess_image_for_ocr(
    image: Image.Image,
    *,
    invoice_id: int | None = None,
    document_type: str | None = None,
    page_number: int | None = None
) -> Image.Image:
    """
    Basic OCR preprocessing:
    - convert to grayscale
    - enlarge small text
    - denoise
    - apply adaptive thresholding
    """

    started_at = perf_counter()

    opencv_image = pil_image_to_opencv(
        image,
        invoice_id=invoice_id,
        document_type=document_type,
        page_number=page_number
    )

    grayscale = cv2.cvtColor(
        opencv_image,
        cv2.COLOR_BGR2GRAY
    )

    height, width = grayscale.shape[:2]

    if width < 1600:
        scale = 1600 / width

        grayscale = cv2.resize(
            grayscale,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC
        )

    denoised = cv2.fastNlMeansDenoising(
        grayscale,
        None,
        h=10,
        templateWindowSize=7,
        searchWindowSize=21
    )

    thresholded = cv2.adaptiveThreshold(
        denoised,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        11
    )

    processed_image = Image.fromarray(thresholded)
    log_performance(
        stage="opencv_preprocessing",
        duration_ms=(perf_counter() - started_at) * 1000,
        invoice_id=invoice_id,
        document_type=document_type,
        page_number=page_number,
        page_mode="ocr",
        image_dimensions=(width, height)
    )
    return processed_image
