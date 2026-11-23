from fastapi import UploadFile, HTTPException

ALLOWED_EXTENSION = {".pdf", ".jpg", ".jpeg", ".png"}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png"
}

FILE_SIGNATURES = {
    ".pdf": (b"%PDF-", "application/pdf"),
    ".jpg": (b"\xff\xd8\xff", "image/jpeg"),
    ".jpeg": (b"\xff\xd8\xff", "image/jpeg"),
    ".png": (b"\x89PNG\r\n\x1a\n", "image/png")
}


def validate_invoice_file(file: UploadFile):
    filename = file.filename.lower()
    extension = "."+filename.split(".")[-1]

    if extension not in ALLOWED_EXTENSION:
        raise HTTPException(
            status_code=400,
            detail="Only PDF and image files are allowed"
        )

    signature, expected_content_type = FILE_SIGNATURES[extension]
    try:
        file.file.seek(0)
        file_signature = file.file.read(len(signature))
    finally:
        file.file.seek(0)

    if (
        file.content_type not in ALLOWED_CONTENT_TYPES
        or file.content_type != expected_content_type
        or not file_signature.startswith(signature)
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "File extension, content type, and file content "
                "do not match"
            )
        )

    return extension
