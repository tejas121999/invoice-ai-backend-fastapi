from sqlalchemy.orm import Session
from app.models.invoice import Invoice


def create_invoice_record(db: Session, file_data: dict, uploadedBy: int | None = None):
    invoice = Invoice(
        fileName=file_data["fileName"],
        filePath=file_data["filePath"],
        fileType=file_data["fileType"],
        uploadStatus="uploaded",
        processingStatus="pending",
        uploadedBy=uploadedBy
    )

    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    return invoice
