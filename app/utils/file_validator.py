from fastapi import UploadFile, HTTPException

ALLOWED_EXTENSION = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp"
}


def validate_invoice_file(file: UploadFile):
    filename = file.filename.lower()
    extension = "."+filename.split(".")[-1]

    if extension not in ALLOWED_EXTENSION:
        raise HTTPException(
            status_code=400,
            detail="Only PDF and image files are allowed"
        )

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type"
        )

    return extension
