from pathlib import Path
import stat

from app.core.config import BASE_DIR, settings


class InvalidInvoicePathError(ValueError):
    pass


class InvoiceFileNotFoundError(FileNotFoundError):
    pass


class InvoiceFileAccessError(PermissionError):
    pass


def resolve_invoice_path(file_path: str | Path) -> Path:
    raw_path = str(file_path)
    if not raw_path.strip() or "\0" in raw_path:
        raise InvalidInvoicePathError("Invoice file path is invalid.")

    path = Path(raw_path.replace("\\", "/"))
    if not path.is_absolute():
        path = BASE_DIR / path

    try:
        upload_dir = Path(settings.UPLOAD_DIR).resolve()
        resolved_path = path.resolve()
    except PermissionError as exc:
        raise InvoiceFileAccessError(
            "Invoice file cannot be accessed."
        ) from exc
    except (OSError, RuntimeError, ValueError) as exc:
        raise InvalidInvoicePathError(
            "Invoice file path cannot be resolved."
        ) from exc

    try:
        resolved_path.relative_to(upload_dir)
    except ValueError as exc:
        raise InvalidInvoicePathError(
            "Invoice file path is outside the configured upload directory."
        ) from exc

    try:
        file_stat = resolved_path.stat()
    except FileNotFoundError as exc:
        raise InvoiceFileNotFoundError(
            "Invoice file not found."
        ) from exc
    except PermissionError as exc:
        raise InvoiceFileAccessError(
            "Invoice file cannot be accessed."
        ) from exc
    except OSError as exc:
        raise InvoiceFileAccessError(
            "Invoice file cannot be accessed."
        ) from exc

    if not stat.S_ISREG(file_stat.st_mode):
        raise InvalidInvoicePathError(
            "Invoice file path does not identify a regular file."
        )

    return resolved_path


def invoice_path_for_response(file_path: str) -> str:
    path = Path(file_path.replace("\\", "/"))
    if not path.is_absolute():
        return path.as_posix()

    try:
        return path.resolve().relative_to(BASE_DIR.resolve()).as_posix()
    except (OSError, RuntimeError, ValueError):
        return path.name
