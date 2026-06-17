import os
import uuid
import aiofiles
from fastapi import UploadFile, HTTPException

from app.core.config import settings
from app.utils.file_validator import validate_invoice_file


async def save_invoice_file(file: UploadFile):
    extension = validate_invoice_file(file)
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    unique_fileName = f"{uuid.uuid4()}{extension}"
    filePath = os.path.join(settings.UPLOAD_DIR, unique_fileName)

    max_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    total_size = 0

    try:
        async with aiofiles.open(filePath, "wb") as out_file:
            while chunk := await file.read(1024 * 1024):
                total_size += len(chunk)

                if total_size > max_size:
                    await out_file.close()
                    os.remove(filePath)

                    raise HTTPException(
                        status_code=400,
                        detail=f"File size must be less than {settings.MAX_FILE_SIZE_MB} MB"
                    )

                await out_file.write(chunk)

        return {
            "fileName": unique_fileName,
            "original_name": file.filename,
            "filePath": filePath,
            "fileType": file.content_type,
            "file_size": total_size
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"File upload failed: {str(e)}"
        )
