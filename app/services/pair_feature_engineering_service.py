"""Invoice-level feature generation for synthetic candidate pairs."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.adapters.synthetic_csv_adapter import (
    AllocationRecord,
    InvoiceRecord,
    PaymentRecord,
    SyntheticPairRecord,
    SyntheticPilotData,
)
from app.utils.similarity_utils import calculate_text_similarity


INVOICE_FEATURE_NAMES = (
    "vendorSimilarity",
    "invoiceNumberSimilarity",
    "exactAmountMatch",
    "amountDifference",
    "amountSimilarity",
    "dateDifferenceDays",
    "currencyMatch",
    "paymentTermsSimilarity",
)

PAYMENT_FEATURE_NAMES = (
    "paidAmountMatch",
    "paidAmountSimilarity",
    "paymentReferenceSimilarity",
    "samePaymentRun",
    "partialPaymentRatio",
)


def _normalize_currency(currency: str | None) -> str | None:
    if currency is None:
        return None
    normalized = currency.strip().upper()
    return normalized or None


def _to_finite_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return parsed if parsed.is_finite() else None


def _vendor_name(invoice: InvoiceRecord) -> str | None:
    if isinstance(invoice.vendor_name_reviewed, str):
        reviewed = invoice.vendor_name_reviewed.strip()
        if reviewed:
            return reviewed
    return invoice.vendor_name


def _matching_invoice_amounts(
    invoice_a: InvoiceRecord,
    invoice_b: InvoiceRecord,
) -> tuple[Decimal, Decimal] | None:
    currency_a = _normalize_currency(invoice_a.currency)
    currency_b = _normalize_currency(invoice_b.currency)
    if currency_a is None or currency_b is None or currency_a != currency_b:
        return None

    amount_a = _to_finite_decimal(invoice_a.total_amount)
    amount_b = _to_finite_decimal(invoice_b.total_amount)
    if amount_a is None or amount_b is None:
        return None
    return amount_a, amount_b


def _calculate_amount_similarity(amount_a: Decimal, amount_b: Decimal) -> float:
    if amount_a == Decimal("0") and amount_b == Decimal("0"):
        return 1.0

    maximum_amount = max(abs(amount_a), abs(amount_b))
    if maximum_amount == Decimal("0"):
        return 1.0
    if amount_a == Decimal("0") or amount_b == Decimal("0"):
        return 0.0

    similarity = Decimal("1") - (
        abs(amount_a - amount_b) / maximum_amount
    )
    similarity = max(Decimal("0"), min(Decimal("1"), similarity))
    return round(float(similarity), 4)


def _parse_invoice_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        return None


def generate_invoice_pair_features(
    pair: SyntheticPairRecord,
) -> dict[str, float | bool | int | Decimal | None]:
    """Generate the eight approved invoice-level features for one pair."""
    invoice_a = pair.invoice_a
    invoice_b = pair.invoice_b

    matching_amounts = _matching_invoice_amounts(invoice_a, invoice_b)
    amount_difference = None
    amount_similarity = None
    exact_amount_match = False

    if matching_amounts is not None:
        amount_a, amount_b = matching_amounts
        amount_difference = abs(amount_a - amount_b)
        exact_amount_match = amount_a == amount_b
        amount_similarity = _calculate_amount_similarity(amount_a, amount_b)

    date_a = _parse_invoice_date(invoice_a.invoice_date)
    date_b = _parse_invoice_date(invoice_b.invoice_date)
    date_difference = None
    if date_a is not None and date_b is not None:
        date_difference = abs((date_a - date_b).days)

    payment_terms_a = invoice_a.payment_terms
    payment_terms_b = invoice_b.payment_terms
    payment_terms_similarity = None
    if (
        isinstance(payment_terms_a, str)
        and payment_terms_a.strip()
        and isinstance(payment_terms_b, str)
        and payment_terms_b.strip()
    ):
        payment_terms_similarity = calculate_text_similarity(
            payment_terms_a,
            payment_terms_b,
        )

    currency_a = _normalize_currency(invoice_a.currency)
    currency_b = _normalize_currency(invoice_b.currency)

    return {
        "vendorSimilarity": calculate_text_similarity(
            _vendor_name(invoice_a),
            _vendor_name(invoice_b),
        ),
        "invoiceNumberSimilarity": calculate_text_similarity(
            invoice_a.invoice_number,
            invoice_b.invoice_number,
        ),
        "exactAmountMatch": exact_amount_match,
        "amountDifference": amount_difference,
        "amountSimilarity": amount_similarity,
        "dateDifferenceDays": date_difference,
        "currencyMatch": (
            currency_a is not None
            and currency_b is not None
            and currency_a == currency_b
        ),
        "paymentTermsSimilarity": payment_terms_similarity,
    }


def _is_eligible_allocation(allocation: AllocationRecord) -> bool:
    # Reversal/refund-effective timestamps are not represented by the
    # AllocationRecord or PaymentRecord. Do not infer eligibility from status.
    return (
        allocation.allocation_status == "confirmed_paid"
        and allocation.settlement_event == "settled"
    )


def _invoice_allocations(
    invoice: InvoiceRecord,
    pilot: SyntheticPilotData,
) -> list[AllocationRecord]:
    return [
        allocation
        for allocation in pilot.allocations.values()
        if allocation.invoice_id == invoice.invoice_id
    ]


def _sum_allocation_amounts(
    invoice: InvoiceRecord,
    allocations: list[AllocationRecord],
    pilot: SyntheticPilotData,
) -> Decimal | None:
    invoice_currency = _normalize_currency(invoice.currency)
    if invoice_currency is None:
        return None

    total = Decimal("0")
    for allocation in allocations:
        allocated_amount = _to_finite_decimal(allocation.allocated_amount)
        if allocated_amount is None or allocated_amount < Decimal("0"):
            return None

        associated_payment = pilot.payments.get(allocation.payment_id)
        if associated_payment is None:
            return None
        allocation_currency = _normalize_currency(
            associated_payment.payment_currency
        )
        if allocation_currency is None or allocation_currency != invoice_currency:
            return None
        total += allocated_amount
    return total


def _aggregate_eligible_paid_amount(
    invoice: InvoiceRecord,
    payment: PaymentRecord | None,
    pilot: SyntheticPilotData,
) -> Decimal | None:
    if payment is None:
        return None

    invoice_allocations = _invoice_allocations(invoice, pilot)
    eligible_allocations = [
        allocation
        for allocation in invoice_allocations
        if _is_eligible_allocation(allocation)
    ]

    if eligible_allocations:
        return _sum_allocation_amounts(
            invoice,
            eligible_allocations,
            pilot,
        )

    if invoice_allocations:
        return None

    payment_allocations = [
        allocation
        for allocation in pilot.allocations.values()
        if allocation.payment_id == payment.payment_id
    ]
    if payment_allocations:
        return None

    paid_amount = _to_finite_decimal(payment.paid_amount)
    payment_currency = _normalize_currency(payment.payment_currency)
    invoice_currency = _normalize_currency(invoice.currency)
    if (
        paid_amount is None
        or paid_amount < Decimal("0")
        or payment_currency is None
        or invoice_currency is None
        or payment_currency != invoice_currency
    ):
        return None
    return paid_amount


def _has_reversal_or_refund_evidence(
    allocations: list[AllocationRecord],
    pilot: SyntheticPilotData,
) -> bool:
    uncertain_statuses = {"reversed", "refunded"}
    uncertain_events = {
        "reversed_after_settlement",
        "refunded_after_settlement",
    }
    for allocation in allocations:
        if (
            allocation.allocation_status in uncertain_statuses
            or allocation.settlement_event in uncertain_events
        ):
            return True
        payment = pilot.payments.get(allocation.payment_id)
        if payment is not None and (
            payment.payment_status in uncertain_statuses
            or payment.settlement_event in uncertain_events
        ):
            return True
    return False


def _calculate_invoice_payment_coverage(
    invoice: InvoiceRecord,
    pilot: SyntheticPilotData,
) -> Decimal | None:
    invoice_total = _to_finite_decimal(invoice.total_amount)
    if invoice_total is None or invoice_total <= Decimal("0"):
        return None
    if _normalize_currency(invoice.currency) is None:
        return None

    allocations = _invoice_allocations(invoice, pilot)
    if not allocations or _has_reversal_or_refund_evidence(allocations, pilot):
        return None

    eligible_allocations = [
        allocation
        for allocation in allocations
        if _is_eligible_allocation(allocation)
    ]
    if not eligible_allocations:
        return None

    for allocation in eligible_allocations:
        associated_payment = pilot.payments.get(allocation.payment_id)
        if associated_payment is None or (
            associated_payment.payment_status != "paid"
            or associated_payment.settlement_event != "settled"
        ):
            return None

    eligible_amount = _sum_allocation_amounts(
        invoice,
        eligible_allocations,
        pilot,
    )
    if eligible_amount is None:
        return None
    return min(Decimal("1"), eligible_amount / invoice_total)


def _calculate_partial_payment_ratio(
    pair: SyntheticPairRecord,
    pilot: SyntheticPilotData,
) -> float | None:
    coverage_a = _calculate_invoice_payment_coverage(
        pair.invoice_a,
        pilot,
    )
    coverage_b = _calculate_invoice_payment_coverage(
        pair.invoice_b,
        pilot,
    )
    if coverage_a is None or coverage_b is None:
        return None
    return float(min(coverage_a, coverage_b))


def _calculate_paid_amount_similarity(
    amount_a: Decimal,
    amount_b: Decimal,
) -> float:
    if amount_a == Decimal("0") and amount_b == Decimal("0"):
        return 1.0

    maximum_amount = max(abs(amount_a), abs(amount_b))
    if maximum_amount == Decimal("0"):
        return 1.0
    if amount_a == Decimal("0") or amount_b == Decimal("0"):
        return 0.0

    similarity = Decimal("1") - (
        abs(amount_a - amount_b) / maximum_amount
    )
    similarity = max(Decimal("0"), min(Decimal("1"), similarity))
    return round(float(similarity), 4)


def generate_payment_pair_features(
    pair: SyntheticPairRecord,
    pilot: SyntheticPilotData,
) -> dict[str, float | bool | None]:
    """Generate the five approved payment and allocation features for one pair."""
    amount_a = _aggregate_eligible_paid_amount(
        pair.invoice_a,
        pair.payment_a,
        pilot,
    )
    amount_b = _aggregate_eligible_paid_amount(
        pair.invoice_b,
        pair.payment_b,
        pilot,
    )

    paid_amount_match = None
    paid_amount_similarity = None
    if amount_a is not None and amount_b is not None:
        paid_amount_match = amount_a == amount_b
        paid_amount_similarity = _calculate_paid_amount_similarity(
            amount_a,
            amount_b,
        )

    payment_reference_similarity = None
    if (
        pair.payment_a is not None
        and pair.payment_b is not None
        and isinstance(pair.payment_a.payment_reference, str)
        and pair.payment_a.payment_reference.strip()
        and isinstance(pair.payment_b.payment_reference, str)
        and pair.payment_b.payment_reference.strip()
    ):
        payment_reference_similarity = calculate_text_similarity(
            pair.payment_a.payment_reference,
            pair.payment_b.payment_reference,
        )

    same_payment_run = None
    if pair.payment_a is not None and pair.payment_b is not None:
        run_a = pair.payment_a.payment_run_id
        run_b = pair.payment_b.payment_run_id
        if (
            isinstance(run_a, str)
            and run_a.strip()
            and isinstance(run_b, str)
            and run_b.strip()
        ):
            same_payment_run = run_a.strip() == run_b.strip()

    return {
        "paidAmountMatch": paid_amount_match,
        "paidAmountSimilarity": paid_amount_similarity,
        "paymentReferenceSimilarity": payment_reference_similarity,
        "samePaymentRun": same_payment_run,
        "partialPaymentRatio": _calculate_partial_payment_ratio(pair, pilot),
    }
