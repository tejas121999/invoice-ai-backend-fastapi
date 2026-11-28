"""Independent validation for the 12-supplier duplicate-payment pilot."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path


BASE_DIR = (
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

FORBIDDEN_FEATURE_COLUMNS = {
    "label",
    "synthetic_scenario",
    "synthetic_ground_truth_label",
    "underlying_obligation_id",
    "underlying_obligation_id_a",
    "underlying_obligation_id_b",
    "rationale_code",
    "rationale_text",
    "reviewer_id_masked",
    "review_confidence",
    "evidence_source",
    "adjudicated_at",
    "protocol_version",
    "split_name",
    "supplier_cluster_id",
    "hidden_supplier_cluster",
    "hidden_pair_overlap",
    "generator_seed",
    "generator_metadata",
}


def read_csv(filename: str) -> list[dict]:
    with (BASE_DIR / filename).open("r", newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def norm(value: str | None) -> str:
    if not value:
        return ""
    return "".join(character.lower() for character in value if character.isalnum())


def text_similarity(first: str | None, second: str | None) -> float:
    left = norm(first)
    right = norm(second)
    if not left or not right:
        return 0.0
    return round(SequenceMatcher(None, left, right).ratio(), 4)


def calculate_partial_payment_ratio(
    invoice_id: str,
    invoice_by_id: dict[str, dict],
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

    return min(Decimal("1"), allocated_total / invoice_total)


def format_partial_payment_ratio(ratio: Decimal | None) -> str:
    if ratio is None:
        return ""
    ratio = ratio.quantize(Decimal("0.0001"))
    return "1.0" if ratio == Decimal("1") else str(ratio.normalize())


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


def main() -> int:
    suppliers = read_csv("suppliers.csv")
    invoices = read_csv("invoices.csv")
    payments = read_csv("payments.csv")
    allocations = read_csv("allocations.csv")
    pairs = read_csv("pairs.csv")
    features = read_csv("pair_features.csv")
    hidden_metadata = read_csv("generator_metadata.csv")

    supplier_by_id = {row["supplier_id"]: row for row in suppliers}
    invoice_by_id = {row["invoice_id"]: row for row in invoices}
    payment_by_id = {row["payment_id"]: row for row in payments}
    allocation_by_id = {
        row["allocation_id"]: row
        for row in allocations
    }
    allocation_by_relationship = {
        (row["invoice_id"], row["payment_id"]): row
        for row in allocations
    }
    metadata_by_pair = {
        row["pair_id"]: row
        for row in hidden_metadata
    }

    exceptions: list[dict] = []

    def fail(category: str, record_id: str, detail: str) -> None:
        exceptions.append({
            "category": category,
            "record_id": record_id,
            "detail": detail,
        })

    # Entity integrity derived from source rows.
    for invoice in invoices:
        if invoice["supplier_id"] not in supplier_by_id:
            fail("entity", f"invoice:{invoice['invoice_id']}",
                 f"missing supplier {invoice['supplier_id']}")
    for payment in payments:
        if payment["supplier_id"] not in supplier_by_id:
            fail("entity", f"payment:{payment['payment_id']}",
                 f"missing supplier {payment['supplier_id']}")
    for allocation in allocations:
        invoice = invoice_by_id.get(allocation["invoice_id"])
        payment = payment_by_id.get(allocation["payment_id"])
        if invoice is None:
            fail("entity", f"allocation:{allocation['allocation_id']}",
                 f"missing invoice {allocation['invoice_id']}")
        if payment is None:
            fail("entity", f"allocation:{allocation['allocation_id']}",
                 f"missing payment {allocation['payment_id']}")
        if invoice is not None and payment is not None:
            if invoice["supplier_id"] != payment["supplier_id"]:
                fail(
                    "entity",
                    f"allocation:{allocation['allocation_id']}",
                    "invoice/payment supplier mismatch "
                    f"{invoice['supplier_id']} != {payment['supplier_id']}",
                )

    # Independent pair relationship and source-derived label validation.
    pair_label_results: list[dict] = []
    for pair in pairs:
        pair_id = pair["pair_id"]
        invoice_a = invoice_by_id.get(pair["invoice_id_a"])
        invoice_b = invoice_by_id.get(pair["invoice_id_b"])

        if invoice_a is None:
            fail("pair", pair_id,
                 f"missing invoice {pair['invoice_id_a']}")
            continue
        if invoice_b is None:
            fail("pair", pair_id,
                 f"missing invoice {pair['invoice_id_b']}")
            continue

        supplier_a = invoice_a["supplier_id"]
        supplier_b = invoice_b["supplier_id"]
        if supplier_a != pair["supplier_id_a"]:
            fail("pair", pair_id,
                 f"supplier A mismatch: source={supplier_a}, "
                 f"pair={pair['supplier_id_a']}")
        if supplier_b != pair["supplier_id_b"]:
            fail("pair", pair_id,
                 f"supplier B mismatch: source={supplier_b}, "
                 f"pair={pair['supplier_id_b']}")

        allocations_a = []
        allocations_b = []
        payments_a = []
        payments_b = []

        for side in ("a", "b"):
            invoice_id = pair[f"invoice_id_{side}"]
            payment_id = pair[f"payment_id_{side}"]
            allocation_id = pair[f"allocation_id_{side}"]
            if invoice_id not in invoice_by_id:
                fail("pair", pair_id, f"missing source invoice {invoice_id}")
            if payment_id:
                if payment_id not in payment_by_id:
                    fail("pair", pair_id, f"missing source payment {payment_id}")
                else:
                    payment = payment_by_id[payment_id]
                    if side == "a":
                        payments_a.append(payment)
                    else:
                        payments_b.append(payment)
            if allocation_id:
                if allocation_id not in allocation_by_id:
                    fail("pair", pair_id,
                         f"missing source allocation {allocation_id}")
                else:
                    allocation = allocation_by_id[allocation_id]
                    if (
                        allocation["invoice_id"] != invoice_id
                        or allocation["payment_id"] != payment_id
                    ):
                        fail(
                            "pair",
                            pair_id,
                            f"allocation relationship mismatch {allocation_id}",
                        )
                    if side == "a":
                        allocations_a.append(allocation)
                    else:
                        allocations_b.append(allocation)

        metadata = metadata_by_pair.get(pair_id)
        if metadata is None:
            fail("pair", pair_id, "missing hidden obligation metadata")
            obligation_a = None
            obligation_b = None
        else:
            obligation_a = metadata["underlying_obligation_id_a"]
            obligation_b = metadata["underlying_obligation_id_b"]

        missing_evidence = (
            not pair["payment_id_a"]
            or not pair["payment_id_b"]
            or not pair["allocation_id_a"]
            or not pair["allocation_id_b"]
            or len(allocations_a) != 1
            or len(allocations_b) != 1
        )

        derived = None
        reason = ""

        if missing_evidence:
            derived = "uncertain"
            reason = "missing payment or allocation evidence"
        elif supplier_a != supplier_b:
            derived = "not_duplicate"
            reason = "different suppliers"
        elif obligation_a is None or obligation_a != obligation_b:
            derived = "not_duplicate"
            reason = "different underlying obligations"
        else:
            allocation_a = allocations_a[0]
            allocation_b = allocations_b[0]
            payment_a = payments_a[0]
            payment_b = payments_b[0]

            allocation_cancelled_a = (
                allocation_a["settlement_event"]
                == "cancelled_before_settlement"
            )
            allocation_cancelled_b = (
                allocation_b["settlement_event"]
                == "cancelled_before_settlement"
            )
            if allocation_cancelled_a or allocation_cancelled_b:
                derived = "not_duplicate"
                reason = "cancelled payment before settlement"
            elif pair["invoice_id_a"] == pair["invoice_id_b"]:
                invoice = invoice_by_id[pair["invoice_id_a"]]
                invoice_allocations = [
                    allocation
                    for allocation in allocations
                    if allocation["invoice_id"] == pair["invoice_id_a"]
                    and allocation["settlement_event"]
                    in {
                        "settled",
                        "reversed_after_settlement",
                        "refunded_after_settlement",
                    }
                ]
                settled_total = sum(
                    (Decimal(row["allocated_amount"]) for row in invoice_allocations),
                    Decimal("0"),
                )
                invoice_total = Decimal(invoice["total_amount"])
                if settled_total == invoice_total:
                    derived = "not_duplicate"
                    reason = "single invoice paid by partial allocations"
                elif len(invoice_allocations) >= 2:
                    derived = "not_duplicate"
                    reason = "multiple allocations do not prove duplicate obligation"
                else:
                    derived = "uncertain"
                    reason = "insufficient partial-payment evidence"
            else:
                distinct_payments = payment_a["payment_id"] != payment_b["payment_id"]
                settled_a = (
                    allocation_a["settlement_event"] in {
                        "settled",
                        "reversed_after_settlement",
                        "refunded_after_settlement",
                    }
                    or payment_a["settlement_event"]
                    in {
                        "settled",
                        "reversed_after_settlement",
                        "refunded_after_settlement",
                    }
                )
                settled_b = (
                    allocation_b["settlement_event"] in {
                        "settled",
                        "reversed_after_settlement",
                        "refunded_after_settlement",
                    }
                    or payment_b["settlement_event"]
                    in {
                        "settled",
                        "reversed_after_settlement",
                        "refunded_after_settlement",
                    }
                )
                if (
                    distinct_payments
                    and settled_a
                    and settled_b
                ):
                    derived = "duplicate"
                    reason = (
                        "same supplier and obligation; "
                        "two distinct completed/historical settlements"
                    )
                else:
                    derived = "not_duplicate"
                    reason = "no two completed settlements"

        stored = pair["label"]
        if derived != stored:
            fail(
                "label",
                pair_id,
                f"stored={stored}, independently_derived={derived}",
            )

        pair_label_results.append({
            "pair_id": pair_id,
            "invoice_ids": [
                pair["invoice_id_a"],
                pair["invoice_id_b"],
            ],
            "supplier_ids": [supplier_a, supplier_b],
            "payment_ids": [
                pair["payment_id_a"] or None,
                pair["payment_id_b"] or None,
            ],
            "allocation_ids": [
                pair["allocation_id_a"] or None,
                pair["allocation_id_b"] or None,
            ],
            "underlying_obligation_ids": [
                obligation_a,
                obligation_b,
            ],
            "stored_label": stored,
            "derived_label": derived,
            "reason": reason,
        })

    # Financial consistency.
    for invoice in invoices:
        subtotal = Decimal(invoice["subtotal"])
        tax = Decimal(invoice["tax_amount"])
        total = Decimal(invoice["total_amount"])
        if subtotal + tax != total:
            fail(
                "financial",
                f"invoice:{invoice['invoice_id']}",
                f"subtotal+tax={subtotal + tax}, total={total}",
            )

    allocations_by_payment: dict[str, list[dict]] = defaultdict(list)
    allocations_by_invoice: dict[str, list[dict]] = defaultdict(list)
    for allocation in allocations:
        allocations_by_payment[allocation["payment_id"]].append(
            allocation
        )
        allocations_by_invoice[allocation["invoice_id"]].append(
            allocation
        )

    for payment in payments:
        if payment["payment_currency"] != "INR":
            fail(
                "financial",
                f"payment:{payment['payment_id']}",
                f"unexpected currency {payment['payment_currency']}",
            )
        allocated = sum(
            (
                Decimal(row["allocated_amount"])
                for row in allocations_by_payment[payment["payment_id"]]
                if row["allocation_status"] in {
                    "confirmed_paid",
                    "reversed",
                }
            ),
            Decimal("0"),
        )
        if allocated > Decimal(payment["paid_amount"]):
            fail(
                "financial",
                f"payment:{payment['payment_id']}",
                f"allocated={allocated}, paid={payment['paid_amount']}",
            )

    for invoice in invoices:
        allocated = sum(
            (
                Decimal(row["allocated_amount"])
                for row in allocations_by_invoice[invoice["invoice_id"]]
            ),
            Decimal("0"),
        )
        if allocated and allocated != Decimal(invoice["total_amount"]):
            fail(
                "financial",
                f"invoice:{invoice['invoice_id']}",
                f"allocated={allocated}, "
                f"invoice_total={invoice['total_amount']}",
            )

    # Cancellation and reversal consistency.
    for payment in payments:
        related_allocations = allocations_by_payment[payment["payment_id"]]
        if payment["payment_status"] == "cancelled":
            if not all(
                row["allocation_status"] == "cancelled"
                and row["settlement_event"]
                == "cancelled_before_settlement"
                for row in related_allocations
            ):
                fail(
                    "scenario",
                    f"payment:{payment['payment_id']}",
                    "cancelled payment lacks cancelled allocation evidence",
                )
        if payment["payment_status"] == "reversed":
            if not all(
                row["settlement_event"] == "reversed_after_settlement"
                for row in related_allocations
            ):
                fail(
                    "scenario",
                    f"payment:{payment['payment_id']}",
                    "reversed payment lacks historical settlement evidence",
                )

    # Recompute every approved model feature from source records.
    recomputed_feature_mismatches = []
    feature_by_pair = {row["pair_id"]: row for row in features}
    for pair in pairs:
        feature = feature_by_pair.get(pair["pair_id"])
        if feature is None:
            fail("feature", pair["pair_id"], "missing feature row")
            continue
        invoice_a = invoice_by_id[pair["invoice_id_a"]]
        invoice_b = invoice_by_id[pair["invoice_id_b"]]
        payment_a = (
            payment_by_id[pair["payment_id_a"]]
            if pair["payment_id_a"]
            else None
        )
        payment_b = (
            payment_by_id[pair["payment_id_b"]]
            if pair["payment_id_b"]
            else None
        )
        allocation_a = (
            allocation_by_id[pair["allocation_id_a"]]
            if pair["allocation_id_a"]
            else None
        )
        allocation_b = (
            allocation_by_id[pair["allocation_id_b"]]
            if pair["allocation_id_b"]
            else None
        )

        amount_a = Decimal(invoice_a["total_amount"])
        amount_b = Decimal(invoice_b["total_amount"])
        paid_a = (
            Decimal(payment_a["paid_amount"])
            if payment_a
            else None
        )
        paid_b = (
            Decimal(payment_b["paid_amount"])
            if payment_b
            else None
        )
        date_a = date.fromisoformat(invoice_a["invoice_date"])
        date_b = date.fromisoformat(invoice_b["invoice_date"])
        coverage_a = calculate_partial_payment_ratio(
            pair["invoice_id_a"],
            invoice_by_id,
            allocations,
        )
        coverage_b = calculate_partial_payment_ratio(
            pair["invoice_id_b"],
            invoice_by_id,
            allocations,
        )
        partial_ratio = (
            min(coverage_a, coverage_b)
            if coverage_a is not None and coverage_b is not None
            else None
        )

        expected = {
            "pair_id": pair["pair_id"],
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
                row["supplier_id"] == invoice_a["supplier_id"]
                for row in invoices
            ),
            "invoiceNumberOccurrenceCount": sum(
                norm(row["invoice_number"])
                == norm(invoice_a["invoice_number"])
                for row in invoices
            ),
            "vendorInvoiceOccurrenceCount": sum(
                row["supplier_id"] == invoice_a["supplier_id"]
                and norm(row["invoice_number"])
                == norm(invoice_a["invoice_number"])
                for row in invoices
            ),
            "supplierIdMatch": str(
                invoice_a["supplier_id"] == invoice_b["supplier_id"]
            ).lower(),
            "paidAmountMatch": (
                str(paid_a == paid_b).lower()
                if paid_a is not None and paid_b is not None
                else ""
            ),
            "paidAmountSimilarity": amount_similarity(paid_a, paid_b),
            "paymentReferenceSimilarity": (
                text_similarity(
                    payment_a["payment_reference"],
                    payment_b["payment_reference"],
                )
                if payment_a and payment_b
                else ""
            ),
            "samePaymentRun": (
                str(
                    payment_a["payment_run_id"]
                    == payment_b["payment_run_id"]
                ).lower()
                if payment_a and payment_b
                else ""
            ),
            "allocationOverlapRatio": (
                "1.0" if pair["invoice_id_a"] == pair["invoice_id_b"] else "0.0"
            ),
            "partialPaymentRatio": format_partial_payment_ratio(partial_ratio),
            "reversalStatusMatch": (
                "reversed_or_refunded"
                if (
                    allocation_a
                    and allocation_a["settlement_event"]
                    in {"reversed_after_settlement", "refunded_after_settlement"}
                )
                or (
                    allocation_b
                    and allocation_b["settlement_event"]
                    in {"reversed_after_settlement", "refunded_after_settlement"}
                )
                else ""
            ),
        }

        mismatches = {}
        for field_name, expected_value in expected.items():
            actual_value = feature[field_name]
            if str(actual_value) != str(expected_value):
                mismatches[field_name] = {
                    "actual": actual_value,
                    "expected": str(expected_value),
                }
        if mismatches:
            recomputed_feature_mismatches.append({
                "pair_id": pair["pair_id"],
                "mismatches": mismatches,
            })
            fail(
                "feature",
                pair["pair_id"],
                f"recomputed feature mismatches: {mismatches}",
            )

    # Allowlist and forbidden feature columns.
    if features:
        feature_columns = set(features[0].keys())
        not_allowed = sorted(feature_columns - FEATURE_ALLOWLIST)
        forbidden = sorted(feature_columns & FORBIDDEN_FEATURE_COLUMNS)
        if not_allowed:
            fail(
                "feature",
                "pair_features.csv",
                f"columns outside allowlist: {not_allowed}",
            )
        if forbidden:
            fail(
                "feature",
                "pair_features.csv",
                f"forbidden columns present: {forbidden}",
            )
        if len(features) != len(pairs):
            fail(
                "feature",
                "pair_features.csv",
                f"feature rows={len(features)}, pair rows={len(pairs)}",
            )
        if [row["pair_id"] for row in features] != [
            row["pair_id"] for row in pairs
        ]:
            fail(
                "feature",
                "pair_features.csv",
                "feature pair IDs do not match pair CSV",
            )

    # Split disjointness and distributions.
    split_counts: dict[str, dict] = {}
    split_entities: dict[str, dict[str, set[str]]] = {}
    for split_name in ("train", "validation", "test"):
        split_pairs = [
            row for row in pairs
            if row["split_name"] == split_name
        ]
        supplier_ids = {
            value
            for row in split_pairs
            for value in (row["supplier_id_a"], row["supplier_id_b"])
        }
        invoice_ids = {
            value
            for row in split_pairs
            for value in (row["invoice_id_a"], row["invoice_id_b"])
        }
        payment_ids = {
            value
            for row in split_pairs
            for value in (row["payment_id_a"], row["payment_id_b"])
            if value
        }
        split_counts[split_name] = {
            "pair_count": len(split_pairs),
            "label_counts": dict(
                Counter(row["label"] for row in split_pairs)
            ),
            "supplier_count": len(supplier_ids),
            "invoice_count": len(invoice_ids),
            "payment_count": len(payment_ids),
        }
        split_entities[split_name] = {
            "suppliers": supplier_ids,
            "invoices": invoice_ids,
            "payments": payment_ids,
        }

    split_overlaps = []
    for left, right in (
        ("train", "validation"),
        ("train", "test"),
        ("validation", "test"),
    ):
        for entity_type in ("suppliers", "invoices", "payments"):
            overlap = sorted(
                split_entities[left][entity_type]
                & split_entities[right][entity_type]
            )
            if overlap:
                split_overlaps.append({
                    "left_split": left,
                    "right_split": right,
                    "entity_type": entity_type,
                    "overlap": overlap,
                })

    binary_split_deficiencies = []
    for split_name, split in split_counts.items():
        label_counts = split["label_counts"]
        if label_counts.get("duplicate", 0) == 0:
            binary_split_deficiencies.append({
                "split": split_name,
                "issue": "missing duplicate",
            })
        if label_counts.get("not_duplicate", 0) == 0:
            binary_split_deficiencies.append({
                "split": split_name,
                "issue": "missing not_duplicate",
            })

    report = {
        "overall_pass": (
            not exceptions
            and not split_overlaps
            and not binary_split_deficiencies
            and not recomputed_feature_mismatches
        ),
        "seed": 20261128,
        "counts": {
            "suppliers": len(suppliers),
            "invoices": len(invoices),
            "payments": len(payments),
            "allocations": len(allocations),
            "pairs": len(pairs),
            "duplicates": sum(
                row["label"] == "duplicate"
                for row in pairs
            ),
            "not_duplicates": sum(
                row["label"] == "not_duplicate"
                for row in pairs
            ),
            "uncertain": sum(
                row["label"] == "uncertain"
                for row in pairs
            ),
        },
        "split_counts": split_counts,
        "split_overlaps": split_overlaps,
        "binary_split_deficiencies": binary_split_deficiencies,
        "pair_label_results": pair_label_results,
        "feature_allowlist": sorted(FEATURE_ALLOWLIST),
        "recomputed_feature_mismatches": recomputed_feature_mismatches,
        "exceptions": exceptions,
        "summary": {
            "entity_integrity_pass": not any(
                item["category"] == "entity"
                for item in exceptions
            ),
            "pair_integrity_pass": not any(
                item["category"] == "pair"
                or item["category"] == "label"
                for item in exceptions
            ),
            "financial_integrity_pass": not any(
                item["category"] == "financial"
                for item in exceptions
            ),
            "scenario_integrity_pass": not any(
                item["category"] == "scenario"
                for item in exceptions
            ),
            "feature_integrity_pass": (
                not recomputed_feature_mismatches
                and not any(
                    item["category"] == "feature"
                    for item in exceptions
                )
            ),
            "split_integrity_pass": (
                not split_overlaps
                and not binary_split_deficiencies
            ),
        },
    }

    report_path = BASE_DIR / "validation_report.json"
    report_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
