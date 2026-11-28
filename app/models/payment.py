from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        CheckConstraint(
            "status IN ('pending', 'successful', 'failed')",
            name="ck_payments_status_valid",
        ),
        UniqueConstraint(
            "idempotencyKey",
            name="uq_payments_idempotency_key",
        ),
    )

    id = Column(Integer, primary_key=True)
    invoiceId = Column(
        "invoiceId",
        Integer,
        ForeignKey("invoices.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(8), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    idempotencyKey = Column(
        "idempotencyKey",
        String(100),
        nullable=False,
    )
    paymentReference = Column("paymentReference", String(128))
    failureReason = Column("failureReason", String(500))
    createdBy = Column(
        "createdBy",
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    attemptedAt = Column("attemptedAt", DateTime, nullable=False, default=datetime.utcnow)
    statusUpdatedAt = Column(
        "statusUpdatedAt",
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    successfulAt = Column("successfulAt", DateTime)
    createdAt = Column(
        "createdAt",
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updatedAt = Column(
        "updatedAt",
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    invoice = relationship("Invoice", back_populates="payments")
    creator = relationship("User", foreign_keys=[createdBy])
