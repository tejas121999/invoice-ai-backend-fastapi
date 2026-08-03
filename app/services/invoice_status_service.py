from fastapi import HTTPException
from starlette import status
from sqlalchemy.orm import Session
from app.utils.invoice_status import InvoiceStatus
from app.repositories.invoice_repository import update_invoice_status
from app.services.audit_service import save_audit_log

ALLOWED_STATUS_TRANSITIONS = {
    InvoiceStatus.UPLOADED: {
        InvoiceStatus.PROCESSING,
        InvoiceStatus.FAILED,
    },
    InvoiceStatus.PROCESSING: {
        InvoiceStatus.PROCESSED,
        InvoiceStatus.FAILED,
    },
    InvoiceStatus.PROCESSED: {
        InvoiceStatus.REVIEWED,
        InvoiceStatus.PROCESSING,
        InvoiceStatus.FAILED,
    },
    InvoiceStatus.REVIEWED: {
        InvoiceStatus.DUPLICATE_CHECKED,
        InvoiceStatus.PROCESSED,
        InvoiceStatus.REJECTED,
    },
    InvoiceStatus.DUPLICATE_CHECKED: {
        InvoiceStatus.APPROVED,
        InvoiceStatus.REJECTED,
        InvoiceStatus.REVIEWED,
    },
    InvoiceStatus.APPROVED: set(),
    InvoiceStatus.REJECTED: {
        InvoiceStatus.REVIEWED,
    },
    InvoiceStatus.FAILED: {
        InvoiceStatus.PROCESSING,
    },
}


def change_invoice_status(
    db: Session,
    invoice,
    new_status: InvoiceStatus,
    user_id: int | None = None,
    reason: str | None = None,
):
    old_status = invoice.processingStatus

    if old_status == new_status.value:
        return invoice

    validate_status_transition(
        current_status=old_status,
        new_status=new_status,
    )

    updated_invoice = update_invoice_status(
        db=db,
        invoice=invoice,
        new_status=new_status.value,
    )

    save_audit_log(
        db=db,
        entity="Invoice",
        entity_id=invoice.id,
        action="STATUS_CHANGE",
        user_id=user_id,
        old_data={
            "processingStatus": old_status,
        },
        new_data={
            "processingStatus": new_status.value,
            "reason": reason,
        },
    )

    return updated_invoice


def validate_status_transition(
    current_status: str,
    new_status: InvoiceStatus,
) -> None:
    try:
        current = InvoiceStatus(current_status)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid current invoice status: {current_status}",
        ) from exc

    allowed_statuses = ALLOWED_STATUS_TRANSITIONS.get(current, set())

    if new_status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invoice status cannot change from "
                f"{current.value} to {new_status.value}."
            ),
        )
