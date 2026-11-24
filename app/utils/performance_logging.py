import logging


_performance_logger = logging.getLogger("app.performance")


def log_performance(
    *,
    stage: str,
    duration_ms: float,
    invoice_id: int | None,
    document_type: str | None,
    page_number: int | None = None,
    page_mode: str | None = None,
    image_dimensions: tuple[int, int] | None = None
) -> None:
    dimensions = (
        f"{image_dimensions[0]}x{image_dimensions[1]}"
        if image_dimensions is not None
        else None
    )
    _performance_logger.info(
        "OCR_PERF stage=%s invoice_id=%s document_type=%s "
        "page_number=%s page_mode=%s image_dimensions=%s "
        "duration_ms=%.3f",
        stage,
        invoice_id,
        document_type,
        page_number,
        page_mode,
        dimensions,
        duration_ms
    )
