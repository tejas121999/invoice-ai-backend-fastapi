import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.adapters.synthetic_csv_adapter import (
    AllocationRecord,
    InvoiceRecord,
    PaymentRecord,
    SupplierRecord,
    SyntheticPilotData,
    SyntheticPairRecord,
    load_synthetic_pilot,
)
from app.services.pair_feature_engineering_service import (
    INVOICE_FEATURE_NAMES,
    PAYMENT_FEATURE_NAMES,
    generate_invoice_pair_features,
    generate_payment_pair_features,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PILOT_DIR = (
    PROJECT_ROOT
    / "data"
    / "synthetic"
    / "duplicate_payment_pilot"
)


def make_supplier(supplier_id: str = "SUP-TEST") -> SupplierRecord:
    return SupplierRecord(
        supplier_id=supplier_id,
        supplier_name="Test Supplier",
        supplier_name_normalized="testsupplier",
        supplier_country="IN",
        supplier_tax_id_masked="TAX-TEST",
        supplier_bank_id_masked="BANK-TEST",
    )


def make_payment(**overrides) -> PaymentRecord:
    values = {
        "payment_id": "PAY-TEST",
        "supplier_id": "SUP-TEST",
        "payment_date": date(2026, 2, 1),
        "paid_amount": Decimal("1000.00"),
        "payment_currency": "INR",
        "payment_reference": "TXN-TEST",
        "bank_transaction_id_masked": "MASK-TEST",
        "payment_status": "paid",
        "payment_run_id": "RUN-TEST",
        "payment_posted_at": date(2026, 2, 1),
        "settlement_event": "settled",
    }
    values.update(overrides)
    return PaymentRecord(**values)


def make_allocation(**overrides) -> AllocationRecord:
    values = {
        "allocation_id": "ALLOC-TEST",
        "invoice_id": "TEST-A",
        "payment_id": "PAY-TEST",
        "allocated_amount": Decimal("1000.00"),
        "allocation_status": "confirmed_paid",
        "allocation_source": "test",
        "settlement_event": "settled",
    }
    values.update(overrides)
    return AllocationRecord(**values)


def make_pilot(
    pair: SyntheticPairRecord,
    payments: dict[str, PaymentRecord] | None = None,
    allocations: dict[str, AllocationRecord] | None = None,
) -> SyntheticPilotData:
    supplier = make_supplier()
    return SyntheticPilotData(
        suppliers={supplier.supplier_id: supplier},
        invoices={
            pair.invoice_a.invoice_id: pair.invoice_a,
            pair.invoice_b.invoice_id: pair.invoice_b,
        },
        payments=payments or {},
        allocations=allocations or {},
        pairs={pair.pair_id: pair},
        pair_labels={},
        pair_features={},
        manifest={},
        validation_report={},
    )


def make_invoice(**overrides) -> InvoiceRecord:
    values = {
        "invoice_id": "TEST-A",
        "supplier_id": "SUP-TEST",
        "source_document_id": "test.pdf",
        "invoice_number": "INV-2026-001",
        "vendor_name": "Acme Supplies",
        "vendor_name_reviewed": "Acme Supplies Limited",
        "invoice_date": date(2026, 1, 1),
        "due_date": date(2026, 1, 16),
        "subtotal": Decimal("900.00"),
        "tax_amount": Decimal("100.00"),
        "total_amount": Decimal("1000.00"),
        "currency": "INR",
        "payment_terms": "Net 30",
        "po_number": "PO-001",
        "is_reviewed": True,
        "ocr_confidence": 0.95,
        "invoice_status": "Reviewed",
    }
    values.update(overrides)
    return InvoiceRecord(**values)


def make_pair(
    invoice_a=None,
    invoice_b=None,
    payment_a=None,
    payment_b=None,
    allocation_a=None,
    allocation_b=None,
    pair_decision_timestamp=None,
) -> SyntheticPairRecord:
    supplier = make_supplier()
    return SyntheticPairRecord(
        pair_id="PAIR-TEST",
        invoice_a=invoice_a or make_invoice(),
        invoice_b=invoice_b or make_invoice(
            invoice_id="TEST-B",
            invoice_number="INV-2026-002",
        ),
        supplier_a=supplier,
        supplier_b=supplier,
        payment_a=payment_a,
        payment_b=payment_b,
        allocation_a=allocation_a,
        allocation_b=allocation_b,
        extraction_id_a="1",
        extraction_id_b="2",
        pair_decision_timestamp=pair_decision_timestamp,
        dataset_version="test",
        split_name="test",
    )


class InvoicePairFeatureTests(unittest.TestCase):
    def test_exact_and_similar_vendor_names(self):
        pair = make_pair(
            make_invoice(
                vendor_name="OCR Vendor",
                vendor_name_reviewed="Acme Supplies Limited",
            ),
            make_invoice(
                vendor_name="Other OCR",
                vendor_name_reviewed="Acme Supplies Ltd",
            ),
        )
        features = generate_invoice_pair_features(pair)
        self.assertGreater(features["vendorSimilarity"], 0.0)
        self.assertLessEqual(features["vendorSimilarity"], 1.0)

        pair = make_pair(
            make_invoice(vendor_name_reviewed="Acme Supplies"),
            make_invoice(vendor_name_reviewed="acme supplies"),
        )
        self.assertEqual(
            generate_invoice_pair_features(pair)["vendorSimilarity"],
            1.0,
        )

    def test_reviewed_vendor_name_is_preferred(self):
        pair = make_pair(
            make_invoice(
                vendor_name="Completely Different OCR",
                vendor_name_reviewed="Acme Supplies",
            ),
            make_invoice(
                vendor_name="Completely Different Candidate",
                vendor_name_reviewed="Acme Supplies",
            ),
        )
        self.assertEqual(
            generate_invoice_pair_features(pair)["vendorSimilarity"],
            1.0,
        )

    def test_missing_vendor_names_fall_back_to_documented_zero(self):
        pair = make_pair(
            make_invoice(vendor_name=None, vendor_name_reviewed=None),
            make_invoice(vendor_name="Acme", vendor_name_reviewed=None),
        )
        self.assertEqual(
            generate_invoice_pair_features(pair)["vendorSimilarity"],
            0.0,
        )

    def test_invoice_number_normalization_and_missing_values(self):
        exact = make_pair(
            make_invoice(invoice_number=" inv-2026/001 "),
            make_invoice(invoice_number="INV2026001"),
        )
        self.assertEqual(
            generate_invoice_pair_features(exact)["invoiceNumberSimilarity"],
            1.0,
        )

        missing = make_pair(
            make_invoice(invoice_number=None),
            make_invoice(invoice_number="INV-2026-001"),
        )
        self.assertEqual(
            generate_invoice_pair_features(missing)["invoiceNumberSimilarity"],
            0.0,
        )

    def test_exact_and_different_amounts(self):
        exact = make_pair(
            make_invoice(total_amount=Decimal("100.00"), currency="INR"),
            make_invoice(total_amount=Decimal("100.00"), currency="inr"),
        )
        features = generate_invoice_pair_features(exact)
        self.assertTrue(features["exactAmountMatch"])
        self.assertEqual(features["amountDifference"], Decimal("0.00"))
        self.assertEqual(features["amountSimilarity"], 1.0)

        different = make_pair(
            make_invoice(total_amount=Decimal("100.00"), currency="INR"),
            make_invoice(total_amount=Decimal("99.00"), currency="INR"),
        )
        features = generate_invoice_pair_features(different)
        self.assertFalse(features["exactAmountMatch"])
        self.assertEqual(features["amountDifference"], Decimal("1.00"))
        self.assertGreaterEqual(features["amountSimilarity"], 0.99)

    def test_cross_currency_and_missing_amounts_return_null(self):
        cross_currency = make_pair(
            make_invoice(total_amount=Decimal("100.00"), currency="INR"),
            make_invoice(total_amount=Decimal("100.00"), currency="USD"),
        )
        features = generate_invoice_pair_features(cross_currency)
        self.assertFalse(features["exactAmountMatch"])
        self.assertIsNone(features["amountDifference"])
        self.assertIsNone(features["amountSimilarity"])

        missing = make_pair(
            make_invoice(total_amount=None, currency="INR"),
            make_invoice(total_amount=Decimal("100.00"), currency="INR"),
        )
        features = generate_invoice_pair_features(missing)
        self.assertFalse(features["exactAmountMatch"])
        self.assertIsNone(features["amountDifference"])
        self.assertIsNone(features["amountSimilarity"])

    def test_zero_and_nonzero_amount_similarity(self):
        both_zero = make_pair(
            make_invoice(total_amount=Decimal("0"), currency="INR"),
            make_invoice(total_amount=Decimal("0"), currency="INR"),
        )
        self.assertEqual(
            generate_invoice_pair_features(both_zero)["amountSimilarity"],
            1.0,
        )

        one_zero = make_pair(
            make_invoice(total_amount=Decimal("0"), currency="INR"),
            make_invoice(total_amount=Decimal("100"), currency="INR"),
        )
        self.assertEqual(
            generate_invoice_pair_features(one_zero)["amountSimilarity"],
            0.0,
        )

    def test_invalid_and_nonfinite_amounts_return_null(self):
        for invalid_amount in (
            "not-a-amount",
            Decimal("NaN"),
            Decimal("Infinity"),
            "-Infinity",
        ):
            with self.subTest(invalid_amount=invalid_amount):
                pair = make_pair(
                    make_invoice(
                        total_amount=invalid_amount,
                        currency="INR",
                    ),
                    make_invoice(
                        total_amount=Decimal("100"),
                        currency="INR",
                    ),
                )
                features = generate_invoice_pair_features(pair)
                self.assertFalse(features["exactAmountMatch"])
                self.assertIsNone(features["amountDifference"])
                self.assertIsNone(features["amountSimilarity"])

    def test_equal_and_different_invoice_dates(self):
        equal = make_pair(
            make_invoice(invoice_date=date(2026, 1, 1)),
            make_invoice(invoice_date=date(2026, 1, 1)),
        )
        self.assertEqual(
            generate_invoice_pair_features(equal)["dateDifferenceDays"],
            0,
        )

        different = make_pair(
            make_invoice(invoice_date=date(2026, 1, 1)),
            make_invoice(invoice_date=date(2026, 1, 3)),
        )
        self.assertEqual(
            generate_invoice_pair_features(different)["dateDifferenceDays"],
            2,
        )

    def test_missing_and_invalid_dates_return_null(self):
        for invalid_date in (None, "not-a-date", ""):
            with self.subTest(invalid_date=invalid_date):
                pair = make_pair(
                    make_invoice(invoice_date=invalid_date),
                    make_invoice(invoice_date=date(2026, 1, 1)),
                )
                self.assertIsNone(
                    generate_invoice_pair_features(pair)["dateDifferenceDays"]
                )

    def test_currency_normalization_and_missing_currency(self):
        normalized = make_pair(
            make_invoice(currency=" inr "),
            make_invoice(currency="INR"),
        )
        self.assertTrue(
            generate_invoice_pair_features(normalized)["currencyMatch"]
        )

        missing = make_pair(
            make_invoice(currency=None),
            make_invoice(currency="INR"),
        )
        self.assertFalse(
            generate_invoice_pair_features(missing)["currencyMatch"]
        )

    def test_payment_terms_missing_similar_and_different(self):
        missing = make_pair(
            make_invoice(payment_terms=None),
            make_invoice(payment_terms="Net 30"),
        )
        self.assertIsNone(
            generate_invoice_pair_features(missing)["paymentTermsSimilarity"]
        )

        similar = make_pair(
            make_invoice(payment_terms=" NET   30 DAYS "),
            make_invoice(payment_terms="net30days"),
        )
        self.assertEqual(
            generate_invoice_pair_features(similar)["paymentTermsSimilarity"],
            1.0,
        )

        different = make_pair(
            make_invoice(payment_terms="Net 30"),
            make_invoice(payment_terms="Due on receipt"),
        )
        score = generate_invoice_pair_features(
            different
        )["paymentTermsSimilarity"]
        self.assertGreaterEqual(score, 0.0)
        self.assertLess(score, 1.0)

    def test_output_is_deterministic_and_has_exact_feature_names(self):
        pair = make_pair()
        first = generate_invoice_pair_features(pair)
        second = generate_invoice_pair_features(pair)
        self.assertEqual(first, second)
        self.assertEqual(set(first), set(INVOICE_FEATURE_NAMES))
        self.assertEqual(len(first), 8)

        for forbidden in (
            "label",
            "rationale",
            "hidden_obligation_id",
            "scenario",
            "reviewer",
            "split_name",
        ):
            self.assertNotIn(forbidden, first)

    def test_all_30_synthetic_pilot_pairs(self):
        pilot = load_synthetic_pilot(PILOT_DIR)
        self.assertEqual(len(pilot.pairs), 30)

        for pair in pilot.pairs.values():
            features = generate_invoice_pair_features(pair)
            self.assertEqual(set(features), set(INVOICE_FEATURE_NAMES))
            self.assertIsInstance(features["vendorSimilarity"], float)
            self.assertIsInstance(
                features["invoiceNumberSimilarity"],
                float,
            )
            self.assertIsInstance(features["exactAmountMatch"], bool)
            self.assertTrue(
                features["amountDifference"] is None
                or isinstance(features["amountDifference"], Decimal)
            )
            self.assertTrue(
                features["amountSimilarity"] is None
                or isinstance(features["amountSimilarity"], float)
            )
            self.assertIsInstance(features["currencyMatch"], bool)


class PaymentPairFeatureTests(unittest.TestCase):
    def test_matching_and_different_paid_amounts(self):
        payment_a = make_payment(
            payment_id="PAY-A",
            payment_reference="TXN-100",
            payment_run_id="RUN-100",
        )
        payment_b = make_payment(
            payment_id="PAY-B",
            payment_reference="TXN-101",
            payment_run_id="RUN-101",
        )
        pair = make_pair(
            payment_a=payment_a,
            payment_b=payment_b,
        )
        allocation_a = make_allocation(
            allocation_id="ALLOC-A",
            invoice_id="TEST-A",
            payment_id="PAY-A",
            allocated_amount=Decimal("100.00"),
        )
        allocation_b = make_allocation(
            allocation_id="ALLOC-B",
            invoice_id="TEST-B",
            payment_id="PAY-B",
            allocated_amount=Decimal("100.00"),
        )
        pilot = make_pilot(
            pair,
            payments={"PAY-A": payment_a, "PAY-B": payment_b},
            allocations={
                "ALLOC-A": allocation_a,
                "ALLOC-B": allocation_b,
            },
        )
        features = generate_payment_pair_features(pair, pilot)
        self.assertTrue(features["paidAmountMatch"])
        self.assertEqual(features["paidAmountSimilarity"], 1.0)

        allocation_b = make_allocation(
            allocation_id="ALLOC-B",
            invoice_id="TEST-B",
            payment_id="PAY-B",
            allocated_amount=Decimal("80.00"),
        )
        pilot = make_pilot(
            pair,
            payments={"PAY-A": payment_a, "PAY-B": payment_b},
            allocations={
                "ALLOC-A": allocation_a,
                "ALLOC-B": allocation_b,
            },
        )
        features = generate_payment_pair_features(pair, pilot)
        self.assertFalse(features["paidAmountMatch"])
        self.assertEqual(features["paidAmountSimilarity"], 0.8)

    def test_missing_payment_evidence_returns_null(self):
        pair = make_pair(
            payment_a=None,
            payment_b=make_payment(payment_id="PAY-B"),
        )
        pilot = make_pilot(pair)
        features = generate_payment_pair_features(pair, pilot)
        self.assertIsNone(features["paidAmountMatch"])
        self.assertIsNone(features["paidAmountSimilarity"])
        self.assertIsNone(features["paymentReferenceSimilarity"])
        self.assertIsNone(features["samePaymentRun"])
        self.assertIsNone(features["partialPaymentRatio"])

    def test_currency_mismatch_returns_null_paid_amount_features(self):
        payment_a = make_payment(
            payment_id="PAY-A",
            payment_currency="INR",
        )
        payment_b = make_payment(
            payment_id="PAY-B",
            payment_currency="USD",
        )
        pair = make_pair(
            payment_a=payment_a,
            payment_b=payment_b,
        )
        allocation_a = make_allocation(
            allocation_id="ALLOC-A",
            invoice_id="TEST-A",
            payment_id="PAY-A",
            allocated_amount=Decimal("100.00"),
        )
        allocation_b = make_allocation(
            allocation_id="ALLOC-B",
            invoice_id="TEST-B",
            payment_id="PAY-B",
            allocated_amount=Decimal("100.00"),
        )
        pilot = make_pilot(
            pair,
            payments={"PAY-A": payment_a, "PAY-B": payment_b},
            allocations={
                "ALLOC-A": allocation_a,
                "ALLOC-B": allocation_b,
            },
        )
        features = generate_payment_pair_features(pair, pilot)
        self.assertIsNone(features["paidAmountMatch"])
        self.assertIsNone(features["paidAmountSimilarity"])
        self.assertIsNone(features["partialPaymentRatio"])

    def test_zero_paid_amount_similarity(self):
        payment_a = make_payment(payment_id="PAY-A")
        payment_b = make_payment(payment_id="PAY-B")
        pair = make_pair(
            payment_a=payment_a,
            payment_b=payment_b,
        )
        allocation_a = make_allocation(
            allocation_id="ALLOC-A",
            invoice_id="TEST-A",
            payment_id="PAY-A",
            allocated_amount=Decimal("0"),
        )
        allocation_b = make_allocation(
            allocation_id="ALLOC-B",
            invoice_id="TEST-B",
            payment_id="PAY-B",
            allocated_amount=Decimal("100"),
        )
        pilot = make_pilot(
            pair,
            payments={"PAY-A": payment_a, "PAY-B": payment_b},
            allocations={
                "ALLOC-A": allocation_a,
                "ALLOC-B": allocation_b,
            },
        )
        features = generate_payment_pair_features(pair, pilot)
        self.assertFalse(features["paidAmountMatch"])
        self.assertEqual(features["paidAmountSimilarity"], 0.0)

    def test_multiple_allocations_for_one_invoice_are_aggregated(self):
        payment_a = make_payment(payment_id="PAY-A")
        payment_b = make_payment(payment_id="PAY-B")
        pair = make_pair(
            payment_a=payment_a,
            payment_b=payment_b,
        )
        allocations = {
            "ALLOC-A1": make_allocation(
                allocation_id="ALLOC-A1",
                invoice_id="TEST-A",
                payment_id="PAY-A",
                allocated_amount=Decimal("300.00"),
            ),
            "ALLOC-A2": make_allocation(
                allocation_id="ALLOC-A2",
                invoice_id="TEST-A",
                payment_id="PAY-A",
                allocated_amount=Decimal("700.00"),
            ),
            "ALLOC-B": make_allocation(
                allocation_id="ALLOC-B",
                invoice_id="TEST-B",
                payment_id="PAY-B",
                allocated_amount=Decimal("1000.00"),
            ),
        }
        pilot = make_pilot(
            pair,
            payments={"PAY-A": payment_a, "PAY-B": payment_b},
            allocations=allocations,
        )
        features = generate_payment_pair_features(pair, pilot)
        self.assertTrue(features["paidAmountMatch"])
        self.assertEqual(features["paidAmountSimilarity"], 1.0)
        self.assertEqual(features["partialPaymentRatio"], 1.0)

    def test_multiple_payments_for_one_invoice_are_aggregated(self):
        payment_a1 = make_payment(payment_id="PAY-A1")
        payment_a2 = make_payment(payment_id="PAY-A2")
        payment_b = make_payment(payment_id="PAY-B")
        pair = make_pair(
            payment_a=payment_a1,
            payment_b=payment_b,
        )
        allocations = {
            "ALLOC-A1": make_allocation(
                allocation_id="ALLOC-A1",
                invoice_id="TEST-A",
                payment_id="PAY-A1",
                allocated_amount=Decimal("400.00"),
            ),
            "ALLOC-A2": make_allocation(
                allocation_id="ALLOC-A2",
                invoice_id="TEST-A",
                payment_id="PAY-A2",
                allocated_amount=Decimal("600.00"),
            ),
            "ALLOC-B": make_allocation(
                allocation_id="ALLOC-B",
                invoice_id="TEST-B",
                payment_id="PAY-B",
                allocated_amount=Decimal("1000.00"),
            ),
        }
        pilot = make_pilot(
            pair,
            payments={
                "PAY-A1": payment_a1,
                "PAY-A2": payment_a2,
                "PAY-B": payment_b,
            },
            allocations=allocations,
        )
        features = generate_payment_pair_features(pair, pilot)
        self.assertTrue(features["paidAmountMatch"])
        self.assertEqual(features["paidAmountSimilarity"], 1.0)
        self.assertEqual(features["partialPaymentRatio"], 1.0)

    def test_shared_payment_uses_invoice_allocation_not_full_payment(self):
        payment_a = make_payment(
            payment_id="PAY-SHARED",
            paid_amount=Decimal("1500.00"),
        )
        payment_b = make_payment(
            payment_id="PAY-B",
            paid_amount=Decimal("500.00"),
        )
        pair = make_pair(
            payment_a=payment_a,
            payment_b=payment_b,
        )
        allocations = {
            "ALLOC-A": make_allocation(
                allocation_id="ALLOC-A",
                invoice_id="TEST-A",
                payment_id="PAY-SHARED",
                allocated_amount=Decimal("500.00"),
            ),
            "ALLOC-OTHER": make_allocation(
                allocation_id="ALLOC-OTHER",
                invoice_id="TEST-OTHER",
                payment_id="PAY-SHARED",
                allocated_amount=Decimal("1000.00"),
            ),
            "ALLOC-B": make_allocation(
                allocation_id="ALLOC-B",
                invoice_id="TEST-B",
                payment_id="PAY-B",
                allocated_amount=Decimal("500.00"),
            ),
        }
        pilot = make_pilot(
            pair,
            payments={"PAY-SHARED": payment_a, "PAY-B": payment_b},
            allocations=allocations,
        )
        features = generate_payment_pair_features(pair, pilot)
        self.assertTrue(features["paidAmountMatch"])
        self.assertEqual(features["paidAmountSimilarity"], 1.0)
        self.assertEqual(features["partialPaymentRatio"], 0.5)

    def test_cancelled_and_pending_allocations_have_no_paid_evidence(self):
        payment_a = make_payment(payment_id="PAY-A")
        payment_b = make_payment(payment_id="PAY-B")
        pair = make_pair(payment_a=payment_a, payment_b=payment_b)
        allocations = {
            "ALLOC-A": make_allocation(
                allocation_id="ALLOC-A",
                invoice_id="TEST-A",
                payment_id="PAY-A",
                allocation_status="cancelled",
                settlement_event="cancelled_before_settlement",
            ),
            "ALLOC-B": make_allocation(
                allocation_id="ALLOC-B",
                invoice_id="TEST-B",
                payment_id="PAY-B",
                allocation_status="pending",
                settlement_event="pending",
            ),
        }
        pilot = make_pilot(
            pair,
            payments={"PAY-A": payment_a, "PAY-B": payment_b},
            allocations=allocations,
        )
        features = generate_payment_pair_features(pair, pilot)
        self.assertIsNone(features["paidAmountMatch"])
        self.assertIsNone(features["paidAmountSimilarity"])
        self.assertIsNone(features["partialPaymentRatio"])

    def test_reversed_allocation_without_effective_timestamp_is_not_eligible(self):
        payment_a = make_payment(
            payment_id="PAY-A",
            payment_status="reversed",
            payment_posted_at=date(2026, 2, 1),
            settlement_event="reversed_after_settlement",
        )
        payment_b = make_payment(
            payment_id="PAY-B",
            payment_status="paid",
            settlement_event="settled",
        )
        pair = make_pair(
            payment_a=payment_a,
            payment_b=payment_b,
            pair_decision_timestamp=date(2026, 3, 1),
        )
        allocations = {
            "ALLOC-A": make_allocation(
                allocation_id="ALLOC-A",
                invoice_id="TEST-A",
                payment_id="PAY-A",
                allocated_amount=Decimal("100.00"),
                allocation_status="reversed",
                settlement_event="reversed_after_settlement",
            ),
            "ALLOC-B": make_allocation(
                allocation_id="ALLOC-B",
                invoice_id="TEST-B",
                payment_id="PAY-B",
                allocated_amount=Decimal("100.00"),
            ),
        }
        pilot = make_pilot(
            pair,
            payments={"PAY-A": payment_a, "PAY-B": payment_b},
            allocations=allocations,
        )
        features = generate_payment_pair_features(pair, pilot)
        self.assertIsNone(features["paidAmountMatch"])
        self.assertIsNone(features["paidAmountSimilarity"])
        self.assertIsNone(features["partialPaymentRatio"])

    def test_refunded_allocation_without_effective_timestamp_is_not_eligible(self):
        payment_a = make_payment(
            payment_id="PAY-A",
            payment_status="refunded",
            payment_posted_at=date(2026, 2, 1),
            settlement_event="refunded_after_settlement",
        )
        payment_b = make_payment(
            payment_id="PAY-B",
            payment_status="paid",
            settlement_event="settled",
        )
        pair = make_pair(payment_a=payment_a, payment_b=payment_b)
        allocations = {
            "ALLOC-A": make_allocation(
                allocation_id="ALLOC-A",
                invoice_id="TEST-A",
                payment_id="PAY-A",
                allocated_amount=Decimal("100.00"),
                allocation_status="refunded",
                settlement_event="refunded_after_settlement",
            ),
            "ALLOC-B": make_allocation(
                allocation_id="ALLOC-B",
                invoice_id="TEST-B",
                payment_id="PAY-B",
                allocated_amount=Decimal("100.00"),
            ),
        }
        pilot = make_pilot(
            pair,
            payments={"PAY-A": payment_a, "PAY-B": payment_b},
            allocations=allocations,
        )
        features = generate_payment_pair_features(pair, pilot)
        self.assertIsNone(features["paidAmountMatch"])
        self.assertIsNone(features["paidAmountSimilarity"])
        self.assertIsNone(features["partialPaymentRatio"])

    def test_confirmed_settled_allocations_remain_eligible(self):
        payment_a = make_payment(payment_id="PAY-A")
        payment_b = make_payment(payment_id="PAY-B")
        pair = make_pair(payment_a=payment_a, payment_b=payment_b)
        allocations = {
            "ALLOC-A": make_allocation(
                allocation_id="ALLOC-A",
                invoice_id="TEST-A",
                payment_id="PAY-A",
                allocated_amount=Decimal("100.00"),
            ),
            "ALLOC-B": make_allocation(
                allocation_id="ALLOC-B",
                invoice_id="TEST-B",
                payment_id="PAY-B",
                allocated_amount=Decimal("100.00"),
            ),
        }
        pilot = make_pilot(
            pair,
            payments={"PAY-A": payment_a, "PAY-B": payment_b},
            allocations=allocations,
        )
        features = generate_payment_pair_features(pair, pilot)
        self.assertTrue(features["paidAmountMatch"])
        self.assertEqual(features["paidAmountSimilarity"], 1.0)
        self.assertEqual(features["partialPaymentRatio"], 0.1)

    def test_payment_references_and_run_ids(self):
        payment_a = make_payment(
            payment_id="PAY-A",
            payment_reference="TXN-001",
            payment_run_id="RUN-1",
        )
        payment_b = make_payment(
            payment_id="PAY-B",
            payment_reference="txn001",
            payment_run_id="RUN-1",
        )
        pair = make_pair(payment_a=payment_a, payment_b=payment_b)
        pilot = make_pilot(
            pair,
            payments={"PAY-A": payment_a, "PAY-B": payment_b},
        )
        features = generate_payment_pair_features(pair, pilot)
        self.assertEqual(features["paymentReferenceSimilarity"], 1.0)
        self.assertTrue(features["samePaymentRun"])

        payment_b = make_payment(
            payment_id="PAY-B",
            payment_reference=None,
            payment_run_id="RUN-2",
        )
        pair = make_pair(payment_a=payment_a, payment_b=payment_b)
        pilot = make_pilot(
            pair,
            payments={"PAY-A": payment_a, "PAY-B": payment_b},
        )
        features = generate_payment_pair_features(pair, pilot)
        self.assertIsNone(features["paymentReferenceSimilarity"])
        self.assertFalse(features["samePaymentRun"])

    def test_missing_payment_runs_return_null(self):
        payment_a = make_payment(payment_id="PAY-A", payment_run_id=None)
        payment_b = make_payment(payment_id="PAY-B", payment_run_id="RUN-2")
        pair = make_pair(payment_a=payment_a, payment_b=payment_b)
        pilot = make_pilot(
            pair,
            payments={"PAY-A": payment_a, "PAY-B": payment_b},
        )
        features = generate_payment_pair_features(pair, pilot)
        self.assertIsNone(features["samePaymentRun"])

    def test_partial_payment_ratio_for_full_and_partial_coverage(self):
        payment_a = make_payment(payment_id="PAY-A")
        payment_b = make_payment(payment_id="PAY-B")
        scenarios = (
            (Decimal("1000.00"), Decimal("1000.00"), 1.0),
            (Decimal("500.00"), Decimal("250.00"), 0.25),
            (Decimal("1000.00"), Decimal("400.00"), 0.4),
        )

        for amount_a, amount_b, expected in scenarios:
            with self.subTest(amount_a=amount_a, amount_b=amount_b):
                pair = make_pair(payment_a=payment_a, payment_b=payment_b)
                pilot = make_pilot(
                    pair,
                    payments={"PAY-A": payment_a, "PAY-B": payment_b},
                    allocations={
                        "ALLOC-A": make_allocation(
                            allocation_id="ALLOC-A",
                            invoice_id="TEST-A",
                            payment_id="PAY-A",
                            allocated_amount=amount_a,
                        ),
                        "ALLOC-B": make_allocation(
                            allocation_id="ALLOC-B",
                            invoice_id="TEST-B",
                            payment_id="PAY-B",
                            allocated_amount=amount_b,
                        ),
                    },
                )
                features = generate_payment_pair_features(pair, pilot)
                self.assertEqual(features["partialPaymentRatio"], expected)

    def test_partial_payment_ratio_caps_coverage_at_one(self):
        payment_a = make_payment(payment_id="PAY-A")
        payment_b = make_payment(payment_id="PAY-B")
        pair = make_pair(payment_a=payment_a, payment_b=payment_b)
        pilot = make_pilot(
            pair,
            payments={"PAY-A": payment_a, "PAY-B": payment_b},
            allocations={
                "ALLOC-A": make_allocation(
                    allocation_id="ALLOC-A",
                    invoice_id="TEST-A",
                    payment_id="PAY-A",
                    allocated_amount=Decimal("1500.00"),
                ),
                "ALLOC-B": make_allocation(
                    allocation_id="ALLOC-B",
                    invoice_id="TEST-B",
                    payment_id="PAY-B",
                    allocated_amount=Decimal("2000.00"),
                ),
            },
        )

        features = generate_payment_pair_features(pair, pilot)
        self.assertEqual(features["partialPaymentRatio"], 1.0)

    def test_partial_payment_ratio_requires_valid_positive_totals(self):
        payment_a = make_payment(payment_id="PAY-A")
        payment_b = make_payment(payment_id="PAY-B")
        invalid_totals = (
            None,
            Decimal("0"),
            Decimal("-1"),
            Decimal("NaN"),
            Decimal("Infinity"),
        )

        for invoice_total in invalid_totals:
            with self.subTest(invoice_total=invoice_total):
                pair = make_pair(
                    invoice_a=make_invoice(total_amount=invoice_total),
                    payment_a=payment_a,
                    payment_b=payment_b,
                )
                pilot = make_pilot(
                    pair,
                    payments={"PAY-A": payment_a, "PAY-B": payment_b},
                    allocations={
                        "ALLOC-A": make_allocation(
                            allocation_id="ALLOC-A",
                            invoice_id="TEST-A",
                            payment_id="PAY-A",
                        ),
                        "ALLOC-B": make_allocation(
                            allocation_id="ALLOC-B",
                            invoice_id="TEST-B",
                            payment_id="PAY-B",
                        ),
                    },
                )
                features = generate_payment_pair_features(pair, pilot)
                self.assertIsNone(features["partialPaymentRatio"])

    def test_partial_payment_ratio_requires_matching_currency(self):
        payment_a = make_payment(payment_id="PAY-A")
        payment_b = make_payment(payment_id="PAY-B")
        pair = make_pair(
            invoice_a=make_invoice(currency=None),
            payment_a=payment_a,
            payment_b=payment_b,
        )
        pilot = make_pilot(
            pair,
            payments={"PAY-A": payment_a, "PAY-B": payment_b},
            allocations={
                "ALLOC-A": make_allocation(
                    allocation_id="ALLOC-A",
                    invoice_id="TEST-A",
                    payment_id="PAY-A",
                ),
                "ALLOC-B": make_allocation(
                    allocation_id="ALLOC-B",
                    invoice_id="TEST-B",
                    payment_id="PAY-B",
                ),
            },
        )
        self.assertIsNone(
            generate_payment_pair_features(pair, pilot)[
                "partialPaymentRatio"
            ]
        )

    def test_partial_payment_ratio_rejects_invalid_allocated_amounts(self):
        payment_a = make_payment(payment_id="PAY-A")
        payment_b = make_payment(payment_id="PAY-B")
        invalid_amounts = (
            None,
            Decimal("-1"),
            Decimal("NaN"),
            Decimal("Infinity"),
            Decimal("-Infinity"),
            "not-a-number",
        )

        for allocated_amount in invalid_amounts:
            with self.subTest(allocated_amount=allocated_amount):
                pair = make_pair(payment_a=payment_a, payment_b=payment_b)
                pilot = make_pilot(
                    pair,
                    payments={"PAY-A": payment_a, "PAY-B": payment_b},
                    allocations={
                        "ALLOC-A": make_allocation(
                            allocation_id="ALLOC-A",
                            invoice_id="TEST-A",
                            payment_id="PAY-A",
                            allocated_amount=allocated_amount,
                        ),
                        "ALLOC-B": make_allocation(
                            allocation_id="ALLOC-B",
                            invoice_id="TEST-B",
                            payment_id="PAY-B",
                        ),
                    },
                )
                features = generate_payment_pair_features(pair, pilot)
                self.assertIsNone(features["partialPaymentRatio"])

    def test_partial_payment_ratio_matches_verified_pilot_aggregation(self):
        pilot = load_synthetic_pilot(PILOT_DIR)
        for pair_id in ("PAIR-0014", "PAIR-0024"):
            features = generate_payment_pair_features(
                pilot.pairs[pair_id],
                pilot,
            )
            self.assertEqual(features["partialPaymentRatio"], 1.0)

    def test_payment_feature_output_is_deterministic_and_exact(self):
        payment_a = make_payment(payment_id="PAY-A")
        payment_b = make_payment(payment_id="PAY-B")
        pair = make_pair(payment_a=payment_a, payment_b=payment_b)
        pilot = make_pilot(
            pair,
            payments={"PAY-A": payment_a, "PAY-B": payment_b},
        )
        first = generate_payment_pair_features(pair, pilot)
        second = generate_payment_pair_features(pair, pilot)
        self.assertEqual(first, second)
        self.assertEqual(set(first), set(PAYMENT_FEATURE_NAMES))
        self.assertEqual(len(first), 5)
        for forbidden in (
            "label",
            "rationale",
            "underlying_obligation_id",
            "scenario",
            "reviewer",
            "split_name",
        ):
            self.assertNotIn(forbidden, first)

    def test_all_30_synthetic_pilot_pairs_generate_payment_features(self):
        pilot = load_synthetic_pilot(PILOT_DIR)
        for pair in pilot.pairs.values():
            features = generate_payment_pair_features(pair, pilot)
            self.assertEqual(set(features), set(PAYMENT_FEATURE_NAMES))
            self.assertTrue(
                features["paidAmountMatch"] is None
                or isinstance(features["paidAmountMatch"], bool)
            )
            self.assertTrue(
                features["paidAmountSimilarity"] is None
                or isinstance(features["paidAmountSimilarity"], float)
            )
            self.assertTrue(
                features["partialPaymentRatio"] is None
                or (
                    isinstance(features["partialPaymentRatio"], float)
                    and 0.0 <= features["partialPaymentRatio"] <= 1.0
                )
            )


if __name__ == "__main__":
    unittest.main()
