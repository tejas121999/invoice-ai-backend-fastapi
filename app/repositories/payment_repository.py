from datetime import datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.invoice import Invoice
from app.models.payment import Payment


def create_payment_attempt(
    db: Session,
    *,
    invoice_id: int,
    amount: Decimal,
    currency: str,
    idempotency_key: str,
    created_by: int,
    attempted_at: datetime,
    payment_reference: str | None = None,
) -> Payment:
    payment = Payment(
        invoiceId=invoice_id,
        amount=amount,
        currency=currency,
        status="pending",
        idempotencyKey=idempotency_key,
        paymentReference=payment_reference,
        createdBy=created_by,
        attemptedAt=attempted_at,
        statusUpdatedAt=attempted_at,
    )
    db.add(payment)
    db.flush()
    return payment


def get_payment_by_id(db: Session, payment_id: int) -> Payment | None:
    return db.query(Payment).filter(Payment.id == payment_id).first()


def get_payment_invoice_id(db: Session, payment_id: int) -> int | None:
    return (
        db.query(Payment.invoiceId)
        .filter(Payment.id == payment_id)
        .scalar()
    )


def get_invoice_for_update(
    db: Session,
    invoice_id: int,
) -> Invoice | None:
    return (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id)
        .with_for_update()
        .one_or_none()
    )


def get_payment_for_update(
    db: Session,
    payment_id: int,
) -> Payment | None:
    return (
        db.query(Payment)
        .filter(Payment.id == payment_id)
        .with_for_update()
        .one_or_none()
    )


def get_invoice_payment_attempts(
    db: Session,
    invoice_id: int,
) -> list[Payment]:
    return (
        db.query(Payment)
        .filter(Payment.invoiceId == invoice_id)
        .order_by(Payment.createdAt, Payment.id)
        .all()
    )


def find_payment_by_idempotency_key(
    db: Session,
    idempotency_key: str,
) -> Payment | None:
    return (
        db.query(Payment)
        .filter(Payment.idempotencyKey == idempotency_key)
        .first()
    )


def calculate_successful_payment_total(
    db: Session,
    invoice_id: int,
) -> Decimal:
    total = (
        db.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(
            Payment.invoiceId == invoice_id,
            Payment.status == "successful",
        )
        .scalar()
    )
    return Decimal(str(total or 0))


def get_latest_successful_payment_timestamp(
    db: Session,
    invoice_id: int,
) -> datetime | None:
    return (
        db.query(func.max(Payment.successfulAt))
        .filter(
            Payment.invoiceId == invoice_id,
            Payment.status == "successful",
        )
        .scalar()
    )
