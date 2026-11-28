import importlib.util
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.user import User


class PaymentPersistenceTests(unittest.TestCase):
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
            name="Payment Operator",
            email="payment@example.com",
            passwordHash="hash",
            role="operator",
        )
        self.invoice = Invoice(
            fileName="invoice.pdf",
            filePath="uploads/invoices/invoice.pdf",
            fileType="application/pdf",
            uploadStatus="uploaded",
            processingStatus="reviewed",
        )
        self.db.add_all([self.user, self.invoice])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def make_payment(self, **overrides) -> Payment:
        values = {
            "invoiceId": self.invoice.id,
            "amount": Decimal("125.50"),
            "currency": "INR",
            "status": "pending",
            "idempotencyKey": "attempt-001",
            "createdBy": self.user.id,
            "attemptedAt": datetime(2026, 11, 28, 12, 0),
            "statusUpdatedAt": datetime(2026, 11, 28, 12, 0),
        }
        values.update(overrides)
        return Payment(**values)

    def assert_integrity_error(self, payment: Payment) -> None:
        self.db.add(payment)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    def test_payment_creation_and_invoice_relationship(self):
        payment = self.make_payment()
        self.db.add(payment)
        self.db.commit()
        self.db.refresh(payment)

        self.assertEqual(payment.invoiceId, self.invoice.id)
        self.assertEqual(payment.invoice.id, self.invoice.id)
        self.assertEqual(payment.creator.id, self.user.id)
        self.assertEqual(payment.status, "pending")

    def test_multiple_independent_attempts_for_one_invoice(self):
        first = self.make_payment(
            idempotencyKey="attempt-001",
            status="failed",
        )
        retry = self.make_payment(
            idempotencyKey="attempt-002",
            status="pending",
        )
        self.db.add_all([first, retry])
        self.db.commit()

        self.db.refresh(self.invoice)
        self.assertEqual(
            sorted(payment.idempotencyKey for payment in self.invoice.payments),
            ["attempt-001", "attempt-002"],
        )

    def test_only_approved_statuses_are_accepted(self):
        for index, status in enumerate(("pending", "successful", "failed")):
            with self.subTest(status=status):
                payment = self.make_payment(
                    idempotencyKey=f"valid-status-{index}",
                    status=status,
                )
                self.db.add(payment)
                self.db.commit()

        self.assert_integrity_error(
            self.make_payment(
                idempotencyKey="invalid-status",
                status="reversed",
            )
        )

    def test_amount_must_be_positive(self):
        for amount in (Decimal("0"), Decimal("-1.00")):
            with self.subTest(amount=amount):
                self.assert_integrity_error(
                    self.make_payment(
                        idempotencyKey=f"invalid-amount-{amount}",
                        amount=amount,
                    )
                )

    def test_idempotency_key_is_unique(self):
        self.db.add(self.make_payment(idempotencyKey="same-request"))
        self.db.commit()

        self.assert_integrity_error(
            self.make_payment(idempotencyKey="same-request")
        )

    def test_invoice_and_user_foreign_keys_are_enforced(self):
        self.assert_integrity_error(
            self.make_payment(
                invoiceId=999999,
                idempotencyKey="missing-invoice",
            )
        )
        self.assert_integrity_error(
            self.make_payment(
                createdBy=999999,
                idempotencyKey="missing-user",
            )
        )

    def test_new_invoice_has_payment_summary_defaults(self):
        self.db.refresh(self.invoice)

        self.assertEqual(self.invoice.paidAmount, Decimal("0.00"))
        self.assertEqual(self.invoice.paymentStatus, "unpaid")
        self.assertIsNone(self.invoice.lastPaymentAt)


class PaymentMigrationTests(unittest.TestCase):
    def test_upgrade_preserves_existing_invoices_and_sets_defaults(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, "
                "name VARCHAR(255) NOT NULL, "
                "email VARCHAR(255) NOT NULL, "
                "passwordHash VARCHAR(255) NOT NULL)"
            ))
            connection.execute(text(
                "CREATE TABLE invoices (id INTEGER PRIMARY KEY, "
                "fileName VARCHAR(512) NOT NULL, "
                "filePath VARCHAR(1024) NOT NULL)"
            ))
            connection.execute(text(
                "INSERT INTO users (id, name, email, passwordHash) "
                "VALUES (1, 'Operator', 'operator@example.com', 'hash')"
            ))
            connection.execute(text(
                "INSERT INTO invoices (id, fileName, filePath) "
                "VALUES (10, 'existing.pdf', 'uploads/existing.pdf')"
            ))

            context = MigrationContext.configure(connection)
            operations = Operations(context)
            migration_path = (
                Path(__file__).resolve().parents[1]
                / "alembic"
                / "versions"
                / "7220ce4e703c_add_payment_persistence.py"
            )
            spec = importlib.util.spec_from_file_location(
                "payment_persistence_migration",
                migration_path,
            )
            if spec is None or spec.loader is None:
                raise RuntimeError("Unable to load payment migration")
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            original_op = migration.op
            original_context = migration.context
            migration.op = operations
            migration.context = SimpleNamespace(is_offline_mode=lambda: False)
            try:
                migration.upgrade()
            finally:
                migration.op = original_op
                migration.context = original_context

            inspector = inspect(connection)
            columns = {
                column["name"]
                for column in inspector.get_columns("invoices")
            }
            self.assertTrue({
                "paidAmount",
                "paymentStatus",
                "lastPaymentAt",
            }.issubset(columns))
            self.assertIn("payments", inspector.get_table_names())

            row = connection.execute(text(
                "SELECT id, fileName, paidAmount, paymentStatus, "
                "lastPaymentAt FROM invoices WHERE id = 10"
            )).mappings().one()
            self.assertEqual(row["fileName"], "existing.pdf")
            self.assertEqual(Decimal(str(row["paidAmount"])), Decimal("0"))
            self.assertEqual(row["paymentStatus"], "unpaid")
            self.assertIsNone(row["lastPaymentAt"])

        engine.dispose()


if __name__ == "__main__":
    unittest.main()
