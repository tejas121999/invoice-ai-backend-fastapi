import cv2
import numpy as np
from PIL import Image


def pil_image_to_opencv(image: Image.Image) -> np.ndarray:
    rgb_image = image.convert("RGB")
    return cv2.cvtColor(
        np.array(rgb_image),
        cv2.COLOR_RGB2BGR
    )


def preprocess_image_for_ocr(image: Image.Image) -> Image.Image:
    """
    Basic OCR preprocessing:
    - convert to grayscale
    - enlarge small text
    - denoise
    - apply adaptive thresholding
    """

    opencv_image = pil_image_to_opencv(image)

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

    return Image.fromarray(thresholded)
