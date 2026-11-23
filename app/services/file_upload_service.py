from pathlib import Path
import uuid

import aiofiles
from fastapi import HTTPException, UploadFile

from app.core.config import settings
from app.utils.file_validator import validate_invoice_file
from app.utils.invoice_paths import resolve_invoice_path


async def save_invoice_file(file: UploadFile):
    extension = validate_invoice_file(file)

    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)

    unique_file_name = f"{uuid.uuid4()}{extension}"
    file_path = upload_dir / unique_file_name

    max_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    total_size = 0

    try:
        async with aiofiles.open(file_path, "wb") as out_file:
            while chunk := await file.read(1024 * 1024):
                total_size += len(chunk)

                if total_size > max_size:
                    await out_file.close()

                    if file_path.exists():
                        file_path.unlink()

                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"File size must be less than "
                            f"{settings.MAX_FILE_SIZE_MB} MB"
                        )
                    )

                await out_file.write(chunk)

        return {
            "fileName": unique_file_name,
            "original_name": file.filename,
            "filePath": resolve_invoice_path(file_path).as_posix(),
            "fileType": file.content_type,
            "file_size": total_size
        }

    except HTTPException:
        raise

    except Exception as exc:
        if file_path.exists():
            file_path.unlink()

        raise HTTPException(
            status_code=500,
            detail=f"File upload failed: {str(exc)}"
        ) from exc

    finally:
        await file.close()
