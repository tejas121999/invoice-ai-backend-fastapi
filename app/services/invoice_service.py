from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.services.file_upload_service import save_invoice_file
from app.repositories.invoice_repository import create_invoice_record


async def upload_invoice_service(
    db: Session,
    file: UploadFile,
    uploadedBy: int | None = None
):
    file_data = await save_invoice_file(file)

    invoice = create_invoice_record(
        db=db,
        file_data=file_data,
        uploadedBy=uploadedBy
    )

    return invoice
