from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session
from starlette import status

from app.services.file_upload_service import save_invoice_file
from app.repositories.invoice_repository import (
    create_invoice_record,
    get_all_invoices,
    count_invoice,
    get_invoice_by_id
)


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


def get_invoice_services(db: Session, invoice_id: int):
    return get_invoice_by_id(db, invoice_id)


def list_invoice_service(db: Session, page: int = 1, limit: int = 10):
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Page number must be greater then or equal to 1"
        )

    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Limit must be between 1 and 100"
        )

    skip = (page - 1) * limit
    invoices = get_all_invoices(db, skip=skip, limit=limit)
    total_records = count_invoice(db)
    return {
        "invoices": invoices,
        "pagination": {
            "page": page,
            "limit": limit,
            "total_records": total_records,
            "total_pages": (total_records + limit - 1) // limit
        }
    }
