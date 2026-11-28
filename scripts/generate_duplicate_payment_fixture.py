"""Generate a reproducible 12-supplier synthetic duplicate-payment pilot."""

from __future__ import annotations

import csv
import json
import random
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable


SEED = 20261128
DATASET_VERSION = "pilot-v3"
OUTPUT_DIR = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "synthetic"
    / "duplicate_payment_pilot"
)

FEATURE_ALLOWLIST = {
    "pair_id",
    "vendorSimilarity",
    "invoiceNumberSimilarity",
    "exactAmountMatch",
    "amountDifference",
    "amountSimilarity",
    "dateDifferenceDays",
    "currencyMatch",
    "paymentTermsSimilarity",
    "vendorOccurrenceCount",
    "invoiceNumberOccurrenceCount",
    "vendorInvoiceOccurrenceCount",
    "supplierIdMatch",
    "paidAmountMatch",
    "paidAmountSimilarity",
    "paymentReferenceSimilarity",
    "samePaymentRun",
    "allocationOverlapRatio",
    "partialPaymentRatio",
    "reversalStatusMatch",
}


def decimal(value: str) -> Decimal:
    return Decimal(value)


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return "".join(character.lower() for character in value if character.isalnum())


def text_similarity(first: str | None, second: str | None) -> float:
    left = normalize_text(first)
    right = normalize_text(second)
    if not left or not right:
        return 0.0
    return round(SequenceMatcher(None, left, right).ratio(), 4)


def amount_similarity(first: Decimal | None, second: Decimal | None) -> float:
    if first is None or second is None:
        return 0.0
    if first == second:
        return 1.0
    maximum = max(abs(first), abs(second))
    if maximum == 0:
        return 1.0
    result = Decimal("1") - abs(first - second) / maximum
    return round(float(max(Decimal("0"), result)), 4)


def calculate_partial_payment_ratio(
    invoice_id: int,
    invoice_by_id: dict[int, dict],
    allocations: list[dict],
) -> Decimal | None:
    invoice = invoice_by_id.get(invoice_id)
    if invoice is None:
        return None

    try:
        invoice_total = Decimal(invoice["total_amount"])
    except (ArithmeticError, KeyError, TypeError, ValueError):
        return None
    if invoice_total <= 0:
        return None

    eligible_allocations = [
        allocation
        for allocation in allocations
        if allocation["invoice_id"] == invoice_id
        and allocation["allocation_status"] in {
            "confirmed_paid",
            "reversed",
            "refunded",
        }
        and allocation["settlement_event"] in {
            "settled",
            "reversed_after_settlement",
            "refunded_after_settlement",
        }
    ]
    if not eligible_allocations:
        return None

    allocated_total = Decimal("0")
    for allocation in eligible_allocations:
        try:
            allocated_total += Decimal(allocation["allocated_amount"])
        except (ArithmeticError, KeyError, TypeError, ValueError):
            return None

    coverage = allocated_total / invoice_total
    return min(Decimal("1"), coverage)


def format_partial_payment_ratio(ratio: Decimal | None) -> str:
    if ratio is None:
        return ""
    ratio = ratio.quantize(Decimal("0.0001"))
    return "1.0" if ratio == Decimal("1") else str(ratio.normalize())


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def split_for_supplier(supplier_id: str) -> tuple[str, str]:
    number = int(supplier_id.split("-")[1])
    if number <= 4:
        return "supplier-cluster-train", "train"
    if number <= 8:
        return "supplier-cluster-validation", "validation"
    return "supplier-cluster-test", "test"


def main() -> None:
    random.seed(SEED)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    start = date(2026, 1, 1)
    names = [
        "Northstar Retail",
        "Greenleaf Industries",
        "Metro Office Solutions",
        "Prime Electricals",
        "Bluewave Logistics",
        "Apex Cloud Services",
        "Zenith Technologies",
        "Global Tech Supplies",
        "Pioneer Business Consulting",
        "NovaTech Solutions",
        "Silverline Automation",
        "Redwood Materials",
    ]
    totals = [
        "100000.00", "88500.00", "74000.00", "48000.00",
        "26500.00", "120000.00", "600.00", "21000.00",
        "77500.00", "42000.00", "56000.00", "31500.00",
    ]

    suppliers = [
        {
            "supplier_id": f"SUP-{index:03d}",
            "supplier_name": names[index - 1],
            "supplier_name_normalized": normalize_text(names[index - 1]),
            "supplier_country": "IN",
            "supplier_tax_id_masked": f"TAX-{index:03d}",
            "supplier_bank_id_masked": f"BANK-{index:03d}",
        }
        for index in range(1, 13)
    ]

    invoices: list[dict] = []
    obligations: dict[int, str] = {}
    for supplier_index in range(1, 13):
        supplier_id = f"SUP-{supplier_index:03d}"
        base = decimal(totals[supplier_index - 1])
        duplicate_obligation = f"OBL-{supplier_index:03d}-DUP"
        distinct_obligation = f"OBL-{supplier_index:03d}-DISTINCT"
        invoice_offset = (supplier_index - 1) * 3

        for variant_index, invoice_number in enumerate(
            (
                f"INV-{supplier_index:04d}-A",
                f"INV-{supplier_index:04d}/A",
            )
        ):
            invoice_id = invoice_offset + variant_index + 1
            invoice_date = start + timedelta(days=invoice_id * 2)
            tax_amount = (base * Decimal("0.18")).quantize(
                Decimal("0.01")
            )
            subtotal = (base - tax_amount).quantize(Decimal("0.01"))
            invoices.append({
                "invoice_id": invoice_id,
                "supplier_id": supplier_id,
                "source_document_id": f"synthetic-invoice-{invoice_id:03d}.pdf",
                "invoice_number": invoice_number,
                "vendor_name": names[supplier_index - 1],
                "vendor_name_reviewed": names[supplier_index - 1],
                "invoice_date": invoice_date.isoformat(),
                "due_date": (invoice_date + timedelta(days=15)).isoformat(),
                "subtotal": str(subtotal),
                "tax_amount": str(tax_amount),
                "total_amount": str(base),
                "currency": "INR",
                "payment_terms": "Net 15 Days",
                "po_number": f"PO-{invoice_id:04d}",
                "is_reviewed": "true",
                "ocr_confidence": "0.95",
                "invoice_status": "Reviewed",
            })
            obligations[invoice_id] = duplicate_obligation

        invoice_id = invoice_offset + 3
        invoice_date = start + timedelta(days=invoice_id * 2)
        distinct_total = base + Decimal("500.00")
        if supplier_index == 7:
            distinct_total = Decimal("600.00")
        tax_amount = (distinct_total * Decimal("0.18")).quantize(
            Decimal("0.01")
        )
        subtotal = (distinct_total - tax_amount).quantize(
            Decimal("0.01")
        )
        invoices.append({
            "invoice_id": invoice_id,
            "supplier_id": supplier_id,
            "source_document_id": f"synthetic-invoice-{invoice_id:03d}.pdf",
            "invoice_number": f"DIST-{supplier_index:04d}",
            "vendor_name": names[supplier_index - 1],
            "vendor_name_reviewed": names[supplier_index - 1],
            "invoice_date": invoice_date.isoformat(),
            "due_date": (invoice_date + timedelta(days=15)).isoformat(),
            "subtotal": str(subtotal),
            "tax_amount": str(tax_amount),
            "total_amount": str(distinct_total),
            "currency": "INR",
            "payment_terms": "Net 15 Days",
            "po_number": f"PO-{invoice_id:04d}",
            "is_reviewed": "true",
            "ocr_confidence": "0.95",
            "invoice_status": "Reviewed",
        })
        obligations[invoice_id] = distinct_obligation

    invoice_by_id = {row["invoice_id"]: row for row in invoices}

    payments: list[dict] = []
    allocations: list[dict] = []

    def add_payment(
        *,
        supplier_id: str,
        amount: Decimal,
        status: str = "paid",
        settlement_event: str = "settled",
    ) -> dict:
        payment_index = len(payments) + 1
        payment_date = start + timedelta(days=50 + payment_index)
        payment = {
            "payment_id": f"PAY-{payment_index:04d}",
            "supplier_id": supplier_id,
            "payment_date": payment_date.isoformat(),
            "paid_amount": str(amount),
            "payment_currency": "INR",
            "payment_reference": f"TXN-{payment_index:05d}",
            "bank_transaction_id_masked": f"MASK-{payment_index:04d}",
            "payment_status": status,
            "payment_run_id": f"RUN-{((payment_index - 1) // 5) + 1:03d}",
            "payment_posted_at": payment_date.isoformat(),
            "settlement_event": settlement_event,
        }
        payments.append(payment)
        return payment

    def add_allocation(
        *,
        invoice_id: int,
        payment_id: str,
        allocated_amount: Decimal,
        status: str = "confirmed_paid",
        settlement_event: str = "settled",
    ) -> dict:
        invoice = invoice_by_id[invoice_id]
        payment = next(
            row for row in payments if row["payment_id"] == payment_id
        )
        if invoice["supplier_id"] != payment["supplier_id"]:
            raise RuntimeError(
                f"Supplier mismatch: invoice {invoice_id}, payment {payment_id}"
            )
        allocation = {
            "allocation_id": f"ALLOC-{len(allocations) + 1:04d}",
            "invoice_id": invoice_id,
            "payment_id": payment_id,
            "allocated_amount": str(allocated_amount),
            "allocation_status": status,
            "allocation_source": "synthetic",
            "settlement_event": settlement_event,
        }
        allocations.append(allocation)
        return allocation

    # Twenty-four duplicate-obligation settlement pairs.
    for supplier_index in range(1, 13):
        invoice_a = (supplier_index - 1) * 3 + 1
        invoice_b = (supplier_index - 1) * 3 + 2
        for invoice_id in (invoice_a, invoice_b):
            payment = add_payment(
                supplier_id=invoice_by_id[invoice_id]["supplier_id"],
                amount=decimal(invoice_by_id[invoice_id]["total_amount"]),
            )
            add_allocation(
                invoice_id=invoice_id,
                payment_id=payment["payment_id"],
                allocated_amount=decimal(
                    invoice_by_id[invoice_id]["total_amount"]
                ),
            )

    # Normal obligations: one successful payment per remaining distinct invoice.
    for supplier_index in range(1, 13):
        if supplier_index in (6, 7):
            continue
        invoice_id = supplier_index * 3
        invoice = invoice_by_id[invoice_id]
        payment = add_payment(
            supplier_id=invoice["supplier_id"],
            amount=decimal(invoice["total_amount"]),
        )
        add_allocation(
            invoice_id=invoice_id,
            payment_id=payment["payment_id"],
            allocated_amount=decimal(invoice["total_amount"]),
        )

    # Supplier 6: cancelled distinct invoice obligation.
    invoice_18 = invoice_by_id[18]
    cancelled_payment = add_payment(
        supplier_id="SUP-006",
        amount=decimal(invoice_18["total_amount"]),
        status="cancelled",
        settlement_event="cancelled_before_settlement",
    )
    add_allocation(
        invoice_id=18,
        payment_id=cancelled_payment["payment_id"],
        allocated_amount=decimal(invoice_18["total_amount"]),
        status="cancelled",
        settlement_event="cancelled_before_settlement",
    )

    # Supplier 7: legitimate partial payments to a single distinct invoice.
    invoice_21 = invoice_by_id[21]
    invoice_total = decimal(invoice_21["total_amount"])
    half = (invoice_total / Decimal("2")).quantize(Decimal("0.01"))
    for _ in range(2):
        payment = add_payment(
            supplier_id="SUP-007",
            amount=half,
        )
        add_allocation(
            invoice_id=21,
            payment_id=payment["payment_id"],
            allocated_amount=half,
        )

    # Supplier 1: one duplicate payment is reversed after both settlements.
    reversal_invoice = invoice_by_id[2]
    reversed_payment = next(
        row
        for row in payments
        if row["supplier_id"] == "SUP-001"
        and row["paid_amount"] == reversal_invoice["total_amount"]
        and row["payment_id"] != "PAY-0001"
    )
    reversed_payment["payment_status"] = "reversed"
    reversed_payment["settlement_event"] = "reversed_after_settlement"
    reversed_allocation = next(
        row
        for row in allocations
        if row["invoice_id"] == 2
        and row["payment_id"] == reversed_payment["payment_id"]
    )
    reversed_allocation["allocation_status"] = "reversed"
    reversed_allocation["settlement_event"] = "reversed_after_settlement"

    allocation_lookup = {
        (row["invoice_id"], row["payment_id"]): row
        for row in allocations
    }
    payment_by_id = {row["payment_id"]: row for row in payments}
    invoice_by_id = {row["invoice_id"]: row for row in invoices}

    def payment_for(invoice_id: int) -> str | None:
        candidates = [
            allocation["payment_id"]
            for allocation in allocations
            if allocation["invoice_id"] == invoice_id
            and allocation["allocation_status"] != "cancelled"
        ]
        if not candidates:
            return None
        return candidates[0]

    pair_specs: list[dict] = []

    # Twelve duplicate pairs, one per supplier.
    for supplier_index in range(1, 13):
        invoice_a = (supplier_index - 1) * 3 + 1
        invoice_b = (supplier_index - 1) * 3 + 2
        pair_specs.append({
            "scenario": "exact_duplicate",
            "a": invoice_a,
            "b": invoice_b,
            "label": "duplicate",
            "rationale": "DUP_EXACT_INVOICE_REPEAT",
        })

    # Distinct obligations, partial payment, cancellation and hard negatives.
    pair_specs.extend([
        {
            "scenario": "duplicate_after_reversal",
            "a": 1,
            "b": 2,
            "label": "duplicate",
            "rationale": "DUP_RECOVERED_OR_REVERSED",
        },
        {
            "scenario": "legitimate_partial_payment",
            "a": 21,
            "b": 21,
            "label": "not_duplicate",
            "rationale": "ND_PARTIAL_PAYMENT",
        },
        {
            "scenario": "legitimate_instalment",
            "a": 22,
            "b": 24,
            "label": "not_duplicate",
            "rationale": "ND_INSTALMENT",
        },
        {
            "scenario": "cancelled_before_settlement",
            "a": 18,
            "b": 16,
            "label": "not_duplicate",
            "rationale": "ND_CANCELLED_PAYMENT",
        },
        {
            "scenario": "distinct_obligation",
            "a": 1,
            "b": 3,
            "label": "not_duplicate",
            "rationale": "ND_DISTINCT_INVOICE",
        },
        {
            "scenario": "distinct_obligation",
            "a": 4,
            "b": 6,
            "label": "not_duplicate",
            "rationale": "ND_DISTINCT_INVOICE",
        },
        {
            "scenario": "distinct_obligation",
            "a": 7,
            "b": 9,
            "label": "not_duplicate",
            "rationale": "ND_DISTINCT_INVOICE",
        },
        {
            "scenario": "different_supplier_same_amount",
            "a": 3,
            "b": 12,
            "label": "not_duplicate",
            "rationale": "ND_DIFFERENT_SUPPLIER",
        },
        {
            "scenario": "similar_number_different_invoice",
            "a": 13,
            "b": 15,
            "label": "not_duplicate",
            "rationale": "ND_HARD_NEGATIVE",
        },
        {
            "scenario": "distinct_obligation",
            "a": 31,
            "b": 33,
            "label": "not_duplicate",
            "rationale": "ND_DISTINCT_INVOICE",
        },
        {
            "scenario": "distinct_obligation",
            "a": 34,
            "b": 36,
            "label": "not_duplicate",
            "rationale": "ND_DISTINCT_INVOICE",
        },
        {
            "scenario": "distinct_obligation",
            "a": 19,
            "b": 21,
            "label": "not_duplicate",
            "rationale": "ND_DISTINCT_INVOICE",
        },
        {
            "scenario": "hard_negative",
            "a": 22,
            "b": 24,
            "label": "not_duplicate",
            "rationale": "ND_HARD_NEGATIVE",
        },
        {
            "scenario": "refund_no_double_settlement",
            "a": 27,
            "b": 27,
            "label": "not_duplicate",
            "rationale": "ND_REFUND_NO_DOUBLE_SETTLEMENT",
        },
        {
            "scenario": "uncertain_missing_payment",
            "a": 25,
            "b": 26,
            "label": "uncertain",
            "rationale": "UNC_PAYMENT_EVIDENCE_MISSING",
        },
        {
            "scenario": "uncertain_missing_payment",
            "a": 31,
            "b": 33,
            "label": "uncertain",
            "rationale": "UNC_PAYMENT_EVIDENCE_MISSING",
        },
        {
            "scenario": "uncertain_credit_reversal",
            "a": 10,
            "b": 12,
            "label": "uncertain",
            "rationale": "UNC_CREDIT_REVERSAL_AMBIGUITY",
        },
        {
            "scenario": "uncertain_ocr",
            "a": 13,
            "b": 14,
            "label": "uncertain",
            "rationale": "UNC_OCR_UNRELIABLE",
        },
    ])

    pairs: list[dict] = []
    features: list[dict] = []
    hidden_metadata: list[dict] = []

    for pair_index, spec in enumerate(pair_specs, start=1):
        invoice_a = invoice_by_id[spec["a"]]
        invoice_b = invoice_by_id[spec["b"]]
        supplier_id_a = invoice_a["supplier_id"]
        supplier_id_b = invoice_b["supplier_id"]
        cluster, split_name = split_for_supplier(supplier_id_a)
        if split_for_supplier(supplier_id_b)[1] != split_name:
            raise RuntimeError(
                f"Cross-split pair: {spec['a']} / {spec['b']}"
            )

        if spec["label"] == "uncertain":
            payment_a = None
            payment_b = None
        elif spec["scenario"] == "legitimate_partial_payment":
            payment_a = next(
                allocation["payment_id"]
                for allocation in allocations
                if allocation["invoice_id"] == 21
            )
            partial_allocations = [
                allocation
                for allocation in allocations
                if allocation["invoice_id"] == 21
            ]
            payment_b = (
                partial_allocations[-1]["payment_id"]
                if len(partial_allocations) > 1
                else None
            )
        elif spec["scenario"] == "cancelled_before_settlement":
            cancelled_allocations = [
                allocation
                for allocation in allocations
                if allocation["allocation_status"] == "cancelled"
            ]
            if not cancelled_allocations:
                raise RuntimeError(
                    "Cancellation scenario has no cancelled allocation"
                )
            payment_a = cancelled_allocations[0]["payment_id"]
            payment_b = payment_for(spec["b"])
        elif spec["scenario"] == "cancelled_before_settlement":
            payment_a = payment_for(spec["a"])
            payment_b = payment_for(spec["b"])
        else:
            payment_a = payment_for(spec["a"])
            payment_b = payment_for(spec["b"])

        allocation_a = (
            allocation_lookup.get((spec["a"], payment_a))
            if payment_a
            else None
        )
        allocation_b = (
            allocation_lookup.get((spec["b"], payment_b))
            if payment_b
            else None
        )

        if spec["label"] != "uncertain":
            if not payment_a or not payment_b:
                raise RuntimeError(
                    f"Binary pair missing payment: PAIR-{pair_index:04d}"
                )
            if not allocation_a or not allocation_b:
                raise RuntimeError(
                    f"Binary pair missing allocation: PAIR-{pair_index:04d}"
                )

        pair_id = f"PAIR-{pair_index:04d}"
        pair_decision_timestamp = (
            max(
                date.fromisoformat(invoice_a["invoice_date"]),
                date.fromisoformat(invoice_b["invoice_date"]),
            )
            + timedelta(days=60)
        ).isoformat()

        pairs.append({
            "pair_id": pair_id,
            "invoice_id_a": spec["a"],
            "invoice_id_b": spec["b"],
            "extraction_id_a": spec["a"],
            "extraction_id_b": spec["b"],
            "payment_id_a": payment_a or "",
            "payment_id_b": payment_b or "",
            "allocation_id_a": allocation_a["allocation_id"] if allocation_a else "",
            "allocation_id_b": allocation_b["allocation_id"] if allocation_b else "",
            "supplier_id_a": supplier_id_a,
            "supplier_id_b": supplier_id_b,
            "invoice_number_a": invoice_a["invoice_number"],
            "invoice_number_b": invoice_b["invoice_number"],
            "invoice_date_a": invoice_a["invoice_date"],
            "invoice_date_b": invoice_b["invoice_date"],
            "due_date_a": invoice_a["due_date"],
            "due_date_b": invoice_b["due_date"],
            "subtotal_a": invoice_a["subtotal"],
            "subtotal_b": invoice_b["subtotal"],
            "tax_amount_a": invoice_a["tax_amount"],
            "tax_amount_b": invoice_b["tax_amount"],
            "total_amount_a": invoice_a["total_amount"],
            "total_amount_b": invoice_b["total_amount"],
            "currency_a": invoice_a["currency"],
            "currency_b": invoice_b["currency"],
            "payment_terms_a": invoice_a["payment_terms"],
            "payment_terms_b": invoice_b["payment_terms"],
            "is_reviewed_a": "true",
            "is_reviewed_b": "true",
            "vendor_name_a": invoice_a["vendor_name"],
            "vendor_name_b": invoice_b["vendor_name"],
            "vendor_name_reviewed_a": invoice_a["vendor_name_reviewed"],
            "vendor_name_reviewed_b": invoice_b["vendor_name_reviewed"],
            "payment_status_a": (
                payment_by_id[payment_a]["payment_status"] if payment_a else ""
            ),
            "payment_status_b": (
                payment_by_id[payment_b]["payment_status"] if payment_b else ""
            ),
            "paid_amount_a": (
                payment_by_id[payment_a]["paid_amount"] if payment_a else ""
            ),
            "paid_amount_b": (
                payment_by_id[payment_b]["paid_amount"] if payment_b else ""
            ),
            "payment_currency_a": (
                payment_by_id[payment_a]["payment_currency"] if payment_a else ""
            ),
            "payment_currency_b": (
                payment_by_id[payment_b]["payment_currency"] if payment_b else ""
            ),
            "payment_reference_a": (
                payment_by_id[payment_a]["payment_reference"] if payment_a else ""
            ),
            "payment_reference_b": (
                payment_by_id[payment_b]["payment_reference"] if payment_b else ""
            ),
            "label": spec["label"],
            "label_status": "synthetic",
            "rationale_code": spec["rationale"],
            "rationale_text": "",
            "reviewer_id_masked": "SYNTHETIC-GENERATOR",
            "review_confidence": "1.0" if spec["label"] != "uncertain" else "0.0",
            "evidence_source": "synthetic_ground_truth",
            "adjudicated_at": pair_decision_timestamp,
            "protocol_version": "approved-v1",
            "supplier_cluster_id": cluster,
            "split_name": split_name,
            "pair_decision_timestamp": pair_decision_timestamp,
            "dataset_version": DATASET_VERSION,
            "candidate_block_method": "supplier_obligation_window",
            "candidate_window_days": "30",
            "supplier_match_key": supplier_id_a,
            "invoice_number_match_key": normalize_text(
                invoice_a["invoice_number"]
            ),
        })

        amount_a = decimal(invoice_a["total_amount"])
        amount_b = decimal(invoice_b["total_amount"])
        date_a = date.fromisoformat(invoice_a["invoice_date"])
        date_b = date.fromisoformat(invoice_b["invoice_date"])
        paid_a = (
            decimal(payment_by_id[payment_a]["paid_amount"])
            if payment_a
            else None
        )
        paid_b = (
            decimal(payment_by_id[payment_b]["paid_amount"])
            if payment_b
            else None
        )

        coverage_a = calculate_partial_payment_ratio(
            spec["a"],
            invoice_by_id,
            allocations,
        )
        coverage_b = calculate_partial_payment_ratio(
            spec["b"],
            invoice_by_id,
            allocations,
        )
        if coverage_a is None or coverage_b is None:
            partial_ratio = ""
        else:
            partial_ratio = format_partial_payment_ratio(
                min(coverage_a, coverage_b)
            )

        reversal_status = ""
        for allocation in (allocation_a, allocation_b):
            if allocation and allocation["settlement_event"] in {
                "reversed_after_settlement",
                "refunded_after_settlement",
            }:
                reversal_status = "reversed_or_refunded"

        features.append({
            "pair_id": pair_id,
            "vendorSimilarity": text_similarity(
                invoice_a["vendor_name"],
                invoice_b["vendor_name"],
            ),
            "invoiceNumberSimilarity": text_similarity(
                invoice_a["invoice_number"],
                invoice_b["invoice_number"],
            ),
            "exactAmountMatch": str(amount_a == amount_b).lower(),
            "amountDifference": str(abs(amount_a - amount_b)),
            "amountSimilarity": amount_similarity(amount_a, amount_b),
            "dateDifferenceDays": abs((date_a - date_b).days),
            "currencyMatch": str(
                invoice_a["currency"] == invoice_b["currency"]
            ).lower(),
            "paymentTermsSimilarity": text_similarity(
                invoice_a["payment_terms"],
                invoice_b["payment_terms"],
            ),
            "vendorOccurrenceCount": sum(
                row["supplier_id"] == supplier_id_a
                for row in invoices
            ),
            "invoiceNumberOccurrenceCount": sum(
                normalize_text(row["invoice_number"])
                == normalize_text(invoice_a["invoice_number"])
                for row in invoices
            ),
            "vendorInvoiceOccurrenceCount": sum(
                row["supplier_id"] == supplier_id_a
                and normalize_text(row["invoice_number"])
                == normalize_text(invoice_a["invoice_number"])
                for row in invoices
            ),
            "supplierIdMatch": str(supplier_id_a == supplier_id_b).lower(),
            "paidAmountMatch": (
                str(paid_a == paid_b).lower()
                if paid_a is not None and paid_b is not None
                else ""
            ),
            "paidAmountSimilarity": amount_similarity(paid_a, paid_b),
            "paymentReferenceSimilarity": (
                text_similarity(
                    payment_by_id[payment_a]["payment_reference"],
                    payment_by_id[payment_b]["payment_reference"],
                )
                if payment_a and payment_b
                else ""
            ),
            "samePaymentRun": (
                str(
                    payment_by_id[payment_a]["payment_run_id"]
                    == payment_by_id[payment_b]["payment_run_id"]
                ).lower()
                if payment_a and payment_b
                else ""
            ),
            "allocationOverlapRatio": (
                "1.0" if spec["a"] == spec["b"] else "0.0"
            ),
            "partialPaymentRatio": partial_ratio,
            "reversalStatusMatch": reversal_status,
        })

        hidden_metadata.append({
            "pair_id": pair_id,
            "generator_version": "pilot-generator-v3",
            "generator_seed": SEED,
            "synthetic_scenario": spec["scenario"],
            "synthetic_ground_truth_label": spec["label"],
            "synthetic_duplicate_type": (
                spec["scenario"] if spec["label"] == "duplicate" else ""
            ),
            "synthetic_negative_type": (
                spec["scenario"] if spec["label"] == "not_duplicate" else ""
            ),
            "underlying_obligation_id_a": obligations[spec["a"]],
            "underlying_obligation_id_b": obligations[spec["b"]],
            "hidden_supplier_cluster": cluster,
            "hidden_pair_overlap": "false",
        })

    payload = {
        "suppliers.csv": (
            [
                "supplier_id", "supplier_name",
                "supplier_name_normalized", "supplier_country",
                "supplier_tax_id_masked", "supplier_bank_id_masked",
            ],
            suppliers,
        ),
        "invoices.csv": (
            [
                "invoice_id", "supplier_id", "source_document_id",
                "invoice_number", "vendor_name", "vendor_name_reviewed",
                "invoice_date", "due_date", "subtotal", "tax_amount",
                "total_amount", "currency", "payment_terms", "po_number",
                "is_reviewed", "ocr_confidence", "invoice_status",
            ],
            invoices,
        ),
        "payments.csv": (
            [
                "payment_id", "supplier_id", "payment_date", "paid_amount",
                "payment_currency", "payment_reference",
                "bank_transaction_id_masked", "payment_status",
                "payment_run_id", "payment_posted_at", "settlement_event",
            ],
            payments,
        ),
        "allocations.csv": (
            [
                "allocation_id", "invoice_id", "payment_id",
                "allocated_amount", "allocation_status",
                "allocation_source", "settlement_event",
            ],
            allocations,
        ),
        "pairs.csv": (list(pairs[0].keys()), pairs),
        "pair_features.csv": (list(features[0].keys()), features),
        "generator_metadata.csv": (
            list(hidden_metadata[0].keys()),
            hidden_metadata,
        ),
    }

    for filename, (fieldnames, rows) in payload.items():
        write_csv(OUTPUT_DIR / filename, fieldnames, rows)

    manifest = {
        "dataset_version": DATASET_VERSION,
        "generator_seed": SEED,
        "generator_version": "pilot-generator-v3",
        "supplier_count": len(suppliers),
        "invoice_count": len(invoices),
        "payment_count": len(payments),
        "allocation_count": len(allocations),
        "pair_count": len(pairs),
        "label_counts": dict(Counter(row["label"] for row in pairs)),
        "binary_pair_count": sum(
            row["label"] in {"duplicate", "not_duplicate"}
            for row in pairs
        ),
        "uncertain_pair_count": sum(
            row["label"] == "uncertain"
            for row in pairs
        ),
    }
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
