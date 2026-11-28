from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette import status

from app.repositories.invoice_repository import (
    get_extracted_invoice_data_by_invoice_id,
    get_invoice_by_id,
)
from app.repositories.payment_repository import (
    calculate_successful_payment_total,
    create_payment_attempt as create_payment_record,
    find_payment_by_idempotency_key,
    get_invoice_for_update,
    get_latest_successful_payment_timestamp,
    get_payment_for_update,
    get_payment_invoice_id,
)
from app.models.payment import Payment


VALID_PAYMENT_TRANSITIONS = {
    "pending": {"successful", "failed"},
    "successful": set(),
    "failed": set(),
}
TERMINAL_STATUSES = {"successful", "failed"}


def _payment_validation_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=detail,
    )


def _normalize_currency(currency: str | None) -> str | None:
    if not isinstance(currency, str):
        return None
    normalized = currency.strip().upper()
    return normalized or None


def _reviewed_invoice_financials(
    db: Session,
    invoice_id: int,
    *,
    invoice=None,
) -> tuple[object, str, Decimal]:
    invoice = invoice or get_invoice_by_id(db, invoice_id)
    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found.",
        )

    extraction = get_extracted_invoice_data_by_invoice_id(db, invoice_id)
    if extraction is None or not extraction.isReviewed:
        raise _payment_validation_error(
            "Invoice financial information must be reviewed before payment tracking."
        )

    invoice_currency = _normalize_currency(extraction.currency)
    if invoice_currency is None:
        raise _payment_validation_error(
            "Reviewed invoice currency is required for payment tracking."
        )
    try:
        invoice_total = Decimal(str(extraction.totalAmount))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise _payment_validation_error(
            "Reviewed invoice total is required for payment tracking."
        ) from exc
    if not invoice_total.is_finite() or invoice_total <= Decimal("0"):
        raise _payment_validation_error(
            "Reviewed invoice total must be positive for payment tracking."
        )
    return invoice, invoice_currency, invoice_total


def _positive_decimal(value: Decimal | str | int | float) -> Decimal:
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise _payment_validation_error(
            "Payment amount must be a valid positive decimal."
        ) from exc
    if not amount.is_finite() or amount <= Decimal("0"):
        raise _payment_validation_error(
            "Payment amount must be greater than zero."
        )
    return amount


def _same_create_request(
    payment: Payment,
    invoice_id: int,
    amount: Decimal,
    currency: str,
    authenticated_user_id: int,
    payment_reference: str | None,
) -> bool:
    return (
        payment.invoiceId == invoice_id
        and payment.amount == amount
        and _normalize_currency(payment.currency) == currency
        and payment.createdBy == authenticated_user_id
        and payment.paymentReference == payment_reference
    )


def create_payment_attempt(
    db: Session,
    *,
    invoice_id: int,
    amount: Decimal | str | int | float,
    currency: str,
    idempotency_key: str,
    authenticated_user_id: int,
    attempted_at: datetime | None = None,
    payment_reference: str | None = None,
) -> Payment:
    normalized_key = idempotency_key.strip() if isinstance(idempotency_key, str) else ""
    if not normalized_key:
        raise _payment_validation_error("Idempotency key is required.")
    payment_currency = _normalize_currency(currency)
    if payment_currency is None:
        raise _payment_validation_error("Payment currency is required.")
    normalized_amount = _positive_decimal(amount)
    _, invoice_currency, _ = _reviewed_invoice_financials(db, invoice_id)
    if payment_currency != invoice_currency:
        raise _payment_validation_error(
            "Payment currency must match the reviewed invoice currency."
        )

    existing = find_payment_by_idempotency_key(db, normalized_key)
    if existing is not None:
        if not _same_create_request(
            existing,
            invoice_id,
            normalized_amount,
            payment_currency,
            authenticated_user_id,
            payment_reference,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key is already used by another payment request.",
            )
        return existing

    try:
        payment = create_payment_record(
            db,
            invoice_id=invoice_id,
            amount=normalized_amount,
            currency=payment_currency,
            idempotency_key=normalized_key,
            created_by=authenticated_user_id,
            attempted_at=attempted_at or datetime.utcnow(),
            payment_reference=payment_reference,
        )
        db.commit()
        db.refresh(payment)
        return payment
    except IntegrityError as exc:
        db.rollback()
        existing = find_payment_by_idempotency_key(db, normalized_key)
        if existing is not None and _same_create_request(
            existing,
            invoice_id,
            normalized_amount,
            payment_currency,
            authenticated_user_id,
            payment_reference,
        ):
            return existing
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment request conflicts with an existing record.",
        ) from exc
    except SQLAlchemyError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def _recalculate_invoice_payment_summary(
    db: Session,
    invoice,
    invoice_total: Decimal | None,
) -> None:
    paid_amount = calculate_successful_payment_total(db, invoice.id)
    latest_success = get_latest_successful_payment_timestamp(db, invoice.id)

    if invoice_total is None or invoice_total <= Decimal("0"):
        if paid_amount != Decimal("0"):
            raise _payment_validation_error(
                "Invoice total is invalid; successful payment summary cannot be derived."
            )
        payment_status = "unpaid"
    elif paid_amount == Decimal("0"):
        payment_status = "unpaid"
    elif paid_amount < invoice_total:
        payment_status = "partially_paid"
    else:
        payment_status = "paid"

    invoice.paidAmount = paid_amount
    invoice.paymentStatus = payment_status
    invoice.lastPaymentAt = latest_success
    invoice.updatedAt = datetime.utcnow()
    db.add(invoice)
    db.flush()


def update_payment_status(
    db: Session,
    payment_id: int,
    new_status: str,
    *,
    payment_reference: str | None = None,
    failure_reason: str | None = None,
    updated_at: datetime | None = None,
) -> Payment:
    if new_status not in {"successful", "failed"}:
        raise _payment_validation_error(
            "Payment status can only be updated to successful or failed."
        )

    try:
        invoice_id = get_payment_invoice_id(db, payment_id)
        if invoice_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment attempt not found.",
            )

        invoice = get_invoice_for_update(db, invoice_id)
        if invoice is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invoice not found.",
            )
        payment = get_payment_for_update(db, payment_id)
        if payment is None or payment.invoiceId != invoice_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment attempt not found.",
            )

        if new_status not in VALID_PAYMENT_TRANSITIONS.get(payment.status, set()):
            if payment.status in TERMINAL_STATUSES:
                detail = (
                    f"Payment attempt is already {payment.status} "
                    "and cannot be changed."
                )
            else:
                detail = (
                    f"Payment status cannot change from "
                    f"{payment.status} to {new_status}."
                )
            raise _payment_validation_error(detail)

        _, invoice_currency, invoice_total = _reviewed_invoice_financials(
            db,
            invoice_id,
            invoice=invoice,
        )
        if _normalize_currency(payment.currency) != invoice_currency:
            raise _payment_validation_error(
                "Payment currency must match the reviewed invoice currency."
            )

        transition_time = updated_at or datetime.utcnow()
        payment.status = new_status
        payment.statusUpdatedAt = transition_time
        payment.updatedAt = transition_time
        if new_status == "successful":
            if payment_reference is not None:
                payment.paymentReference = payment_reference
            payment.failureReason = None
            payment.successfulAt = transition_time
        else:
            payment.successfulAt = None
            if payment_reference is not None:
                payment.paymentReference = payment_reference
            payment.failureReason = failure_reason

        db.flush()
        _recalculate_invoice_payment_summary(db, invoice, invoice_total)
        db.commit()
        db.refresh(payment)
        db.refresh(invoice)
        return payment
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
