import os
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.extracted_invoice import ExtractedInvoiceData
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.user import User
from app.repositories.payment_repository import get_invoice_payment_attempts
from app.services.payment_service import (
    create_payment_attempt,
    update_payment_status,
)


class PaymentServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(
            name="Operator",
            email="operator@example.com",
            passwordHash="hash",
        )
        self.invoice = Invoice(
            fileName="invoice.pdf",
            filePath="uploads/invoice.pdf",
            fileType="application/pdf",
            uploadStatus="uploaded",
            processingStatus="reviewed",
        )
        self.db.add_all([self.user, self.invoice])
        self.db.flush()
        self.extraction = ExtractedInvoiceData(
            invoiceId=self.invoice.id,
            invoiceNumber="INV-001",
            vendorName="Vendor",
            totalAmount=Decimal("1000.00"),
            currency="INR",
            isReviewed=True,
        )
        self.db.add(self.extraction)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def create_attempt(
        self,
        key: str,
        amount=Decimal("250.00"),
        currency="INR",
    ):
        return create_payment_attempt(
            self.db,
            invoice_id=self.invoice.id,
            amount=amount,
            currency=currency,
            idempotency_key=key,
            authenticated_user_id=self.user.id,
            attempted_at=datetime(2026, 11, 28, 12, 0),
        )

    def assert_http_status(self, expected: int, callback) -> None:
        with self.assertRaises(HTTPException) as error:
            callback()
        self.assertEqual(error.exception.status_code, expected)

    def test_creates_pending_payment_attempt(self):
        payment = self.create_attempt("attempt-1")

        self.assertEqual(payment.status, "pending")
        self.assertEqual(payment.invoiceId, self.invoice.id)
        self.assertEqual(payment.amount, Decimal("250.00"))
        self.assertEqual(len(get_invoice_payment_attempts(self.db, self.invoice.id)), 1)

    def test_failed_attempt_is_preserved_when_retry_is_created(self):
        failed = self.create_attempt("attempt-1")
        update_payment_status(
            self.db,
            failed.id,
            "failed",
            failure_reason="Confirmation not received",
        )
        retry = self.create_attempt("attempt-2")

        attempts = get_invoice_payment_attempts(self.db, self.invoice.id)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0].status, "failed")
        self.assertEqual(attempts[0].id, failed.id)
        self.assertEqual(attempts[1].status, "pending")
        self.assertEqual(attempts[1].id, retry.id)

    def test_successful_and_multiple_payments_recalculate_summary(self):
        first = self.create_attempt("attempt-1", Decimal("400.00"))
        second = self.create_attempt("attempt-2", Decimal("350.00"))
        update_payment_status(self.db, first.id, "successful", updated_at=datetime(2026, 11, 28, 13, 0))
        update_payment_status(self.db, second.id, "successful", updated_at=datetime(2026, 11, 28, 14, 0))

        self.db.refresh(self.invoice)
        self.assertEqual(self.invoice.paidAmount, Decimal("750.00"))
        self.assertEqual(self.invoice.paymentStatus, "partially_paid")
        self.assertEqual(
            self.invoice.lastPaymentAt,
            datetime(2026, 11, 28, 14, 0),
        )

    def test_full_payment_and_overpayment_are_preserved(self):
        payment = self.create_attempt("attempt-1", Decimal("1000.00"))
        update_payment_status(self.db, payment.id, "successful")
        self.db.refresh(self.invoice)
        self.assertEqual(self.invoice.paymentStatus, "paid")
        self.assertEqual(self.invoice.paidAmount, Decimal("1000.00"))

        overpayment = self.create_attempt("attempt-2", Decimal("100.00"))
        update_payment_status(self.db, overpayment.id, "successful")
        self.db.refresh(self.invoice)
        self.assertEqual(self.invoice.paymentStatus, "paid")
        self.assertEqual(self.invoice.paidAmount, Decimal("1100.00"))

    def test_pending_and_failed_payments_do_not_contribute(self):
        pending = self.create_attempt("attempt-1", Decimal("300.00"))
        failed = self.create_attempt("attempt-2", Decimal("700.00"))
        update_payment_status(self.db, failed.id, "failed", failure_reason="Failed")

        self.db.refresh(self.invoice)
        self.assertEqual(pending.status, "pending")
        self.assertEqual(self.invoice.paidAmount, Decimal("0.00"))
        self.assertEqual(self.invoice.paymentStatus, "unpaid")
        self.assertIsNone(self.invoice.lastPaymentAt)

    def test_invalid_and_terminal_transitions_are_rejected(self):
        payment = self.create_attempt("attempt-1")
        self.assert_http_status(400, lambda: update_payment_status(self.db, payment.id, "pending"))

        update_payment_status(self.db, payment.id, "successful")
        self.assert_http_status(400, lambda: update_payment_status(self.db, payment.id, "failed"))

        retry = self.create_attempt("attempt-2")
        update_payment_status(self.db, retry.id, "failed")
        self.assert_http_status(400, lambda: update_payment_status(self.db, retry.id, "successful"))

    def test_duplicate_idempotency_request_returns_existing_payment(self):
        first = self.create_attempt("same-request")
        repeated = self.create_attempt("same-request")

        self.assertEqual(first.id, repeated.id)
        self.assertEqual(len(get_invoice_payment_attempts(self.db, self.invoice.id)), 1)

        self.assert_http_status(
            409,
            lambda: self.create_attempt("same-request", Decimal("500.00")),
        )

    def test_currency_must_match_reviewed_invoice_currency(self):
        self.assert_http_status(
            400,
            lambda: self.create_attempt("wrong-currency", currency="USD"),
        )

    def test_unreviewed_invoice_is_rejected(self):
        self.extraction.isReviewed = False
        self.db.commit()

        self.assert_http_status(
            400,
            lambda: self.create_attempt("unreviewed-invoice"),
        )

    def test_missing_reviewed_currency_is_rejected(self):
        self.extraction.currency = None
        self.db.commit()

        self.assert_http_status(
            400,
            lambda: self.create_attempt("missing-currency"),
        )

    def test_unexpected_creation_error_rolls_back_transaction(self):
        with patch(
            "app.services.payment_service.create_payment_record",
            side_effect=RuntimeError("unexpected creation failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.create_attempt("rollback-attempt")

        self.db.expire_all()
        self.assertEqual(
            get_invoice_payment_attempts(self.db, self.invoice.id),
            [],
        )

    def test_summary_failure_rolls_back_payment_status_change(self):
        payment = self.create_attempt("attempt-1")

        with patch(
            "app.services.payment_service._recalculate_invoice_payment_summary",
            side_effect=RuntimeError("summary failure"),
        ):
            with self.assertRaises(RuntimeError):
                update_payment_status(self.db, payment.id, "successful")

        self.db.expire_all()
        persisted = get_invoice_payment_attempts(self.db, self.invoice.id)[0]
        self.db.refresh(self.invoice)
        self.assertEqual(persisted.status, "pending")
        self.assertIsNone(persisted.successfulAt)
        self.assertEqual(self.invoice.paidAmount, Decimal("0.00"))
        self.assertEqual(self.invoice.paymentStatus, "unpaid")


@unittest.skipUnless(
    os.environ.get("PAYMENT_TEST_DATABASE_URL"),
    "PostgreSQL concurrency tests require PAYMENT_TEST_DATABASE_URL",
)
class PostgreSQLPaymentConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(os.environ["PAYMENT_TEST_DATABASE_URL"])
        if self.engine.dialect.name != "postgresql":
            self.skipTest("PAYMENT_TEST_DATABASE_URL must use PostgreSQL")
        self.Session = sessionmaker(bind=self.engine)
        unique = uuid.uuid4().hex
        self.user = User(
            name="Concurrency Operator",
            email=f"concurrency-{unique}@example.com",
            passwordHash="hash",
        )
        self.invoice = Invoice(
            fileName=f"concurrency-{unique}.pdf",
            filePath=f"uploads/concurrency-{unique}.pdf",
            fileType="application/pdf",
            uploadStatus="uploaded",
            processingStatus="reviewed",
        )
        with self.Session() as db:
            db.add_all([self.user, self.invoice])
            db.flush()
            self.extraction = ExtractedInvoiceData(
                invoiceId=self.invoice.id,
                invoiceNumber=f"CONCURRENT-{unique}",
                vendorName="Concurrency Vendor",
                totalAmount=Decimal("1000.00"),
                currency="INR",
                isReviewed=True,
            )
            db.add(self.extraction)
            db.commit()
            self.user_id = self.user.id
            self.invoice_id = self.invoice.id

    def tearDown(self):
        with self.Session() as db:
            extraction = db.query(ExtractedInvoiceData).filter(
                ExtractedInvoiceData.invoiceId == self.invoice_id
            ).first()
            invoice = db.query(Invoice).filter(Invoice.id == self.invoice_id).first()
            user = db.query(User).filter(User.id == self.user_id).first()
            if extraction is not None:
                db.delete(extraction)
            if invoice is not None:
                db.delete(invoice)
            if user is not None:
                db.delete(user)
            db.commit()
        self.engine.dispose()

    def create_attempt(self, key: str, amount: Decimal) -> int:
        with self.Session() as db:
            payment = create_payment_attempt(
                db,
                invoice_id=self.invoice_id,
                amount=amount,
                currency="INR",
                idempotency_key=key,
                authenticated_user_id=self.user_id,
            )
            return payment.id

    def test_concurrent_successes_preserve_complete_invoice_summary(self):
        first_id = self.create_attempt(f"first-{uuid.uuid4().hex}", Decimal("400.00"))
        second_id = self.create_attempt(f"second-{uuid.uuid4().hex}", Decimal("350.00"))
        barrier = threading.Barrier(2)

        def succeed(payment_id: int) -> None:
            with self.Session() as db:
                barrier.wait()
                update_payment_status(db, payment_id, "successful")

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(succeed, first_id),
                executor.submit(succeed, second_id),
            ]
            for future in futures:
                future.result()

        with self.Session() as db:
            invoice = db.query(Invoice).filter(Invoice.id == self.invoice_id).one()
            self.assertEqual(invoice.paidAmount, Decimal("750.00"))
            self.assertEqual(invoice.paymentStatus, "partially_paid")

    def test_concurrent_same_payment_update_allows_one_terminal_transition(self):
        payment_id = self.create_attempt(
            f"same-{uuid.uuid4().hex}",
            Decimal("400.00"),
        )
        barrier = threading.Barrier(2)

        def update(status_value: str):
            with self.Session() as db:
                barrier.wait()
                try:
                    return update_payment_status(db, payment_id, status_value)
                except HTTPException as exc:
                    db.rollback()
                    return exc.status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(update, "successful"),
                executor.submit(update, "failed"),
            ]
            results = [future.result() for future in futures]

        self.assertEqual(sum(isinstance(result, int) for result in results), 1)
        self.assertIn(400, results)
        with self.Session() as db:
            payment = db.query(Payment).filter(Payment.id == payment_id).one()
            self.assertIn(payment.status, {"successful", "failed"})


if __name__ == "__main__":
    unittest.main()
