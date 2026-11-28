"""add payment persistence

Revision ID: 7220ce4e703c
Revises: 
Create Date: 2026-11-28 20:50:26.255513

"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7220ce4e703c'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create payment records and initialize invoice payment summaries."""
    bind = op.get_bind()
    if context.is_offline_mode():
        table_names = {"invoices"}
        invoice_columns = set()
    else:
        inspector = sa.inspect(bind)
        table_names = set(inspector.get_table_names())
        invoice_columns = {
            column["name"]
            for column in inspector.get_columns("invoices")
        } if "invoices" in table_names else set()

    if "invoices" not in table_names:
        raise RuntimeError("Expected existing invoices table before migration")
    if "paidAmount" not in invoice_columns:
        op.add_column(
            "invoices",
            sa.Column(
                "paidAmount",
                sa.Numeric(14, 2),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
    if "paymentStatus" not in invoice_columns:
        op.add_column(
            "invoices",
            sa.Column(
                "paymentStatus",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'unpaid'"),
            ),
        )
    if "lastPaymentAt" not in invoice_columns:
        op.add_column(
            "invoices",
            sa.Column("lastPaymentAt", sa.DateTime(), nullable=True),
        )

    if "payments" not in table_names:
        op.create_table(
            "payments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("invoiceId", sa.Integer(), nullable=False),
            sa.Column("amount", sa.Numeric(14, 2), nullable=False),
            sa.Column("currency", sa.String(length=8), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column(
                "idempotencyKey",
                sa.String(length=100),
                nullable=False,
            ),
            sa.Column("paymentReference", sa.String(length=128), nullable=True),
            sa.Column("failureReason", sa.String(length=500), nullable=True),
            sa.Column("createdBy", sa.Integer(), nullable=False),
            sa.Column("attemptedAt", sa.DateTime(), nullable=False),
            sa.Column("statusUpdatedAt", sa.DateTime(), nullable=False),
            sa.Column("successfulAt", sa.DateTime(), nullable=True),
            sa.Column("createdAt", sa.DateTime(), nullable=False),
            sa.Column("updatedAt", sa.DateTime(), nullable=False),
            sa.CheckConstraint(
                "amount > 0",
                name="ck_payments_amount_positive",
            ),
            sa.CheckConstraint(
                "status IN ('pending', 'successful', 'failed')",
                name="ck_payments_status_valid",
            ),
            sa.ForeignKeyConstraint(
                ["createdBy"],
                ["users.id"],
                onupdate="CASCADE",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["invoiceId"],
                ["invoices.id"],
                onupdate="CASCADE",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "idempotencyKey",
                name="uq_payments_idempotency_key",
            ),
        )


def downgrade() -> None:
    """Remove payment records and invoice payment summary fields."""
    bind = op.get_bind()
    if context.is_offline_mode():
        table_names = {"invoices", "payments"}
        invoice_columns = {
            "paidAmount",
            "paymentStatus",
            "lastPaymentAt",
        }
    else:
        inspector = sa.inspect(bind)
        table_names = set(inspector.get_table_names())
        invoice_columns = (
            {
                column["name"]
                for column in inspector.get_columns("invoices")
            }
            if "invoices" in table_names
            else set()
        )
    if "payments" in table_names:
        op.drop_table("payments")
    if "invoices" in table_names:
        if "lastPaymentAt" in invoice_columns:
            op.drop_column("invoices", "lastPaymentAt")
        if "paymentStatus" in invoice_columns:
            op.drop_column("invoices", "paymentStatus")
        if "paidAmount" in invoice_columns:
            op.drop_column("invoices", "paidAmount")
