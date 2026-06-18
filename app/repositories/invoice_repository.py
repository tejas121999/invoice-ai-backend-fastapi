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


def get_invoice_by_id(db: Session, invoice_id: int):
    return db.query(Invoice).filter(Invoice.id == invoice_id).first()


def get_all_invoices(db: Session, skip: int = 0, limit: int = 10):
    return (
        db.query(Invoice)
        .order_by(Invoice.createdAt.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_invoice(db: Session):
    return db.query(Invoice).count()
