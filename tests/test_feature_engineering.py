import unittest
import re
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.models.extracted_invoice import ExtractedInvoiceData
from app.models.invoice import Invoice
from app.models.user import User
from app.repositories.invoice_repository import get_duplicate_frequency_counts
from app.schemas.feature_schema import InvoiceComparisonFeatures
from app.services.feature_engineering_service import (
    generate_invoice_features_service,
    generate_pair_features
)
from app.utils.similarity_utils import (
    calculate_amount_similarity,
    calculate_currency_match,
    calculate_date_difference_days,
    calculate_text_similarity
)


class TextSimilarityTests(unittest.TestCase):
    def test_vendor_similarity_exact_case_insensitive_and_similar_names(self):
        self.assertEqual(
            calculate_text_similarity(
                "Acme Supplies Ltd.",
                "Acme Supplies Ltd."
            ),
            1.0
        )
        self.assertEqual(
            calculate_text_similarity("ACME Supplies", "acme supplies"),
            1.0
        )

        similar_score = calculate_text_similarity(
            "Acme Supplies",
            "Acme Supply"
        )
        self.assertGreater(similar_score, 0.0)
        self.assertLess(similar_score, 1.0)

    def test_vendor_similarity_different_and_missing_names(self):
        self.assertEqual(
            calculate_text_similarity("Acme", "ZZZZ"),
            0.0
        )
        self.assertEqual(calculate_text_similarity(None, "Acme"), 0.0)
        self.assertEqual(calculate_text_similarity(" ", "Acme"), 0.0)

    def test_invoice_number_similarity_exact_similar_and_different(self):
        exact_score = calculate_text_similarity(
            "INV-2025-001",
            "INV-2025-001"
        )
        similar_score = calculate_text_similarity(
            "INV-2025-001",
            "INV-2025-002"
        )
        different_score = calculate_text_similarity(
            "INV-100",
            "BILL-999"
        )

        self.assertEqual(exact_score, 1.0)
        self.assertGreater(similar_score, different_score)
        self.assertLess(similar_score, 1.0)
        self.assertGreaterEqual(different_score, 0.0)
        self.assertLess(different_score, 1.0)

    def test_invoice_number_similarity_ignores_case_and_formatting(self):
        self.assertEqual(
            calculate_text_similarity(
                " inv-2025/001 ",
                "INV2025001"
            ),
            1.0
        )

    def test_invoice_number_similarity_missing_value(self):
        self.assertEqual(
            calculate_text_similarity(None, "INV-2025-001"),
            0.0
        )


class AmountSimilarityTests(unittest.TestCase):
    def test_exact_and_different_amounts(self):
        self.assertEqual(calculate_amount_similarity(100, 100), 1.0)
        self.assertEqual(calculate_amount_similarity(0, 0), 1.0)
        self.assertEqual(calculate_amount_similarity(0, 10), 0.0)
        self.assertEqual(calculate_amount_similarity(100, 25), 0.25)

        small_difference = calculate_amount_similarity(100, 99)
        self.assertEqual(small_difference, 0.99)
        self.assertGreater(small_difference, 0.9)

    def test_decimal_amounts_and_missing_amounts(self):
        self.assertEqual(
            calculate_amount_similarity(
                Decimal("100.00"),
                Decimal("99.50")
            ),
            0.995
        )
        self.assertEqual(calculate_amount_similarity(None, 100), 0.0)
        self.assertEqual(calculate_amount_similarity("", 100), 0.0)


class DateDifferenceTests(unittest.TestCase):
    def test_same_date_one_day_and_large_differences(self):
        self.assertEqual(
            calculate_date_difference_days(
                date(2025, 1, 1),
                date(2025, 1, 1)
            ),
            0
        )
        self.assertEqual(
            calculate_date_difference_days(
                date(2025, 1, 1),
                date(2025, 1, 2)
            ),
            1
        )
        self.assertEqual(
            calculate_date_difference_days(
                date(2020, 1, 1),
                date(2025, 1, 1)
            ),
            1827
        )

    def test_datetime_and_iso_date_string_inputs(self):
        self.assertEqual(
            calculate_date_difference_days(
                datetime(2025, 1, 1, 23, 59),
                datetime(2025, 1, 2, 0, 1)
            ),
            1
        )
        self.assertEqual(
            calculate_date_difference_days(
                "2025-01-01",
                "2025-01-04"
            ),
            3
        )

    def test_missing_and_invalid_dates_return_none(self):
        self.assertIsNone(
            calculate_date_difference_days(None, date(2025, 1, 1))
        )
        self.assertIsNone(
            calculate_date_difference_days("01/01/2025", "2025-01-04")
        )
        self.assertIsNone(
            calculate_date_difference_days("not-a-date", "also-invalid")
        )


class CurrencyMatchTests(unittest.TestCase):
    def test_exact_and_case_insensitive_currency_matches(self):
        self.assertTrue(calculate_currency_match("USD", "USD"))
        self.assertTrue(calculate_currency_match(" inr ", "INR"))

    def test_different_and_missing_currencies_do_not_match(self):
        self.assertFalse(calculate_currency_match("USD", "EUR"))
        self.assertFalse(calculate_currency_match(None, "USD"))
        self.assertFalse(calculate_currency_match("USD", ""))


class PairFeatureTests(unittest.TestCase):
    def test_pair_features_have_expected_keys_types_and_ranges(self):
        source_invoice = SimpleNamespace(
            vendorName="Acme Supplies",
            invoiceNumber="INV-2025-001",
            totalAmount=Decimal("100.00"),
            invoiceDate=date(2025, 1, 1),
            currency="USD"
        )
        candidate_invoice = SimpleNamespace(
            vendorName="Acme Supply",
            invoiceNumber="INV-2025-002",
            totalAmount=Decimal("99.00"),
            invoiceDate=date(2025, 1, 2),
            currency="usd"
        )

        features = generate_pair_features(
            source_invoice=source_invoice,
            candidate_invoice=candidate_invoice
        )

        self.assertEqual(
            set(features),
            {
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
                "vendorInvoiceOccurrenceCount"
            }
        )
        self.assertIsInstance(features["vendorSimilarity"], float)
        self.assertIsInstance(features["invoiceNumberSimilarity"], float)
        self.assertIsInstance(features["exactAmountMatch"], bool)
        self.assertIsInstance(features["amountDifference"], float)
        self.assertIsInstance(features["amountSimilarity"], float)
        self.assertIsInstance(features["dateDifferenceDays"], int)
        self.assertIsInstance(features["currencyMatch"], bool)
        self.assertIsNone(features["paymentTermsSimilarity"])

        for field_name in (
            "vendorSimilarity",
            "invoiceNumberSimilarity",
            "amountSimilarity"
        ):
            with self.subTest(field=field_name):
                self.assertGreaterEqual(features[field_name], 0.0)
                self.assertLessEqual(features[field_name], 1.0)

        self.assertEqual(features["amountDifference"], 1.0)
        self.assertEqual(features["dateDifferenceDays"], 1)
        self.assertTrue(features["currencyMatch"])
        self.assertEqual(features["vendorOccurrenceCount"], 0)
        self.assertEqual(features["invoiceNumberOccurrenceCount"], 0)
        self.assertEqual(features["vendorInvoiceOccurrenceCount"], 0)
        self.assertIsInstance(features["vendorOccurrenceCount"], int)
        self.assertIsInstance(features["invoiceNumberOccurrenceCount"], int)
        self.assertIsInstance(features["vendorInvoiceOccurrenceCount"], int)
        InvoiceComparisonFeatures.model_validate(features)

    def test_pair_features_preserve_existing_missing_value_behavior(self):
        source_invoice = SimpleNamespace(
            vendorName=None,
            invoiceNumber=None,
            totalAmount=None,
            invoiceDate=None,
            currency=None
        )
        candidate_invoice = SimpleNamespace(
            vendorName="Acme",
            invoiceNumber="INV-2025-001",
            totalAmount=Decimal("12.50"),
            invoiceDate="invalid",
            currency="USD"
        )

        features = generate_pair_features(
            source_invoice=source_invoice,
            candidate_invoice=candidate_invoice
        )

        self.assertEqual(features["vendorSimilarity"], 0.0)
        self.assertEqual(features["invoiceNumberSimilarity"], 0.0)
        self.assertFalse(features["exactAmountMatch"])
        self.assertIsNone(features["amountDifference"])
        self.assertEqual(features["amountSimilarity"], 0.0)
        self.assertIsNone(features["dateDifferenceDays"])
        self.assertFalse(features["currencyMatch"])
        self.assertIsNone(features["paymentTermsSimilarity"])
        self.assertEqual(features["vendorOccurrenceCount"], 0)
        self.assertEqual(features["invoiceNumberOccurrenceCount"], 0)
        self.assertEqual(features["vendorInvoiceOccurrenceCount"], 0)
        InvoiceComparisonFeatures.model_validate(features)

    def make_invoice(
        self,
        *,
        reviewed_terms=None,
        extracted_terms=None
    ):
        return SimpleNamespace(
            vendorName="Acme",
            invoiceNumber="INV-100",
            totalAmount=Decimal("100.00"),
            invoiceDate=date(2025, 1, 1),
            currency="USD",
            reviewedFieldsJson=(
                {"paymentTerms": reviewed_terms}
                if reviewed_terms is not None
                else {}
            ),
            extractedFieldsJson=(
                {"paymentTerms": extracted_terms}
                if extracted_terms is not None
                else {}
            )
        )

    def get_payment_terms_similarity(self, source, candidate):
        return generate_pair_features(
            source_invoice=source,
            candidate_invoice=candidate
        )["paymentTermsSimilarity"]

    def test_exact_and_different_payment_terms(self):
        source = self.make_invoice(reviewed_terms="Net 30 days")
        exact_candidate = self.make_invoice(extracted_terms="Net 30 days")
        different_candidate = self.make_invoice(
            extracted_terms="Due on receipt"
        )

        self.assertEqual(
            self.get_payment_terms_similarity(source, exact_candidate),
            1.0
        )
        different_score = self.get_payment_terms_similarity(
            source,
            different_candidate
        )
        self.assertIsInstance(different_score, float)
        self.assertGreaterEqual(different_score, 0.0)
        self.assertLess(different_score, 1.0)

    def test_payment_terms_similarity_normalizes_case_and_whitespace(self):
        source = self.make_invoice(reviewed_terms="  NET   30 Days ")
        candidate = self.make_invoice(extracted_terms="net 30 days")

        self.assertEqual(
            self.get_payment_terms_similarity(source, candidate),
            1.0
        )

    def test_missing_source_candidate_or_both_payment_terms_return_none(self):
        available = self.make_invoice(extracted_terms="Net 30")
        missing = self.make_invoice()

        self.assertIsNone(
            self.get_payment_terms_similarity(missing, available)
        )
        self.assertIsNone(
            self.get_payment_terms_similarity(available, missing)
        )
        self.assertIsNone(
            self.get_payment_terms_similarity(missing, missing)
        )

    def test_reviewed_payment_terms_take_precedence_over_extracted(self):
        source = self.make_invoice(
            reviewed_terms="Net 30",
            extracted_terms="Due on receipt"
        )
        candidate = self.make_invoice(extracted_terms="Net 30")

        self.assertEqual(
            self.get_payment_terms_similarity(source, candidate),
            1.0
        )

    def test_extracted_payment_terms_are_fallback_without_reviewed_value(
        self
    ):
        source = self.make_invoice(
            reviewed_terms="   ",
            extracted_terms="Net 30"
        )
        candidate = self.make_invoice(extracted_terms="Net 30")

        self.assertEqual(
            self.get_payment_terms_similarity(source, candidate),
            1.0
        )


class DuplicateFrequencyRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")

        @event.listens_for(self.engine, "connect")
        def register_regexp_replace(connection, _record):
            connection.create_function(
                "regexp_replace",
                4,
                lambda value, pattern, replacement, _flags: re.sub(
                    pattern,
                    replacement,
                    value
                )
            )

        ExtractedInvoiceData.metadata.create_all(
            bind=self.engine,
            tables=[
                Invoice.__table__,
                User.__table__,
                ExtractedInvoiceData.__table__
            ]
        )
        self.session = sessionmaker(bind=self.engine)()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)

    def add_record(
        self,
        record_id,
        invoice_id,
        vendor_name,
        invoice_number,
        is_reviewed=True
    ):
        self.session.add(ExtractedInvoiceData(
            id=record_id,
            invoiceId=invoice_id,
            vendorName=vendor_name,
            invoiceNumber=invoice_number,
            isReviewed=is_reviewed
        ))
        self.session.flush()

    def count_for_source(
        self,
        vendor_name="Acme Ltd.",
        invoice_number="INV-100"
    ):
        return get_duplicate_frequency_counts(
            db=self.session,
            current_invoice_id=1,
            vendor_name=vendor_name,
            invoice_number=invoice_number
        )

    def test_no_matching_historical_records_returns_zero_counts(self):
        self.add_record(1, 1, "Acme Ltd.", "INV-100")
        self.add_record(2, 2, "Other Vendor", "INV-200")

        self.assertEqual(
            self.count_for_source(),
            {
                "vendorOccurrenceCount": 0,
                "invoiceNumberOccurrenceCount": 0,
                "vendorInvoiceOccurrenceCount": 0
            }
        )

    def test_matching_reviewed_vendor_is_counted(self):
        self.add_record(1, 1, "Acme Ltd.", "INV-100")
        self.add_record(2, 2, "Acme Ltd.", "INV-200")

        counts = self.count_for_source()

        self.assertEqual(counts["vendorOccurrenceCount"], 1)
        self.assertEqual(counts["invoiceNumberOccurrenceCount"], 0)
        self.assertEqual(counts["vendorInvoiceOccurrenceCount"], 0)

    def test_matching_reviewed_invoice_number_is_counted(self):
        self.add_record(1, 1, "Acme Ltd.", "INV-100")
        self.add_record(2, 2, "Other Vendor", "INV-100")

        counts = self.count_for_source()

        self.assertEqual(counts["vendorOccurrenceCount"], 0)
        self.assertEqual(counts["invoiceNumberOccurrenceCount"], 1)
        self.assertEqual(counts["vendorInvoiceOccurrenceCount"], 0)

    def test_matching_vendor_and_invoice_number_are_counted(self):
        self.add_record(1, 1, "Acme Ltd.", "INV-100")
        self.add_record(2, 2, "Acme Ltd.", "INV-100")

        counts = self.count_for_source()

        self.assertEqual(counts["vendorOccurrenceCount"], 1)
        self.assertEqual(counts["invoiceNumberOccurrenceCount"], 1)
        self.assertEqual(counts["vendorInvoiceOccurrenceCount"], 1)

    def test_case_and_punctuation_use_existing_text_normalization(self):
        self.add_record(1, 1, "Acme Ltd.", "INV-100")
        self.add_record(2, 2, " ACME-LTD ", "inv/100")

        counts = self.count_for_source()

        self.assertEqual(counts["vendorOccurrenceCount"], 1)
        self.assertEqual(counts["invoiceNumberOccurrenceCount"], 1)
        self.assertEqual(counts["vendorInvoiceOccurrenceCount"], 1)

    def test_both_missing_or_empty_source_values_return_zero_counts(self):
        self.add_record(1, 1, "", "")
        self.add_record(2, 2, None, None)

        zero_counts = {
                "vendorOccurrenceCount": 0,
                "invoiceNumberOccurrenceCount": 0,
                "vendorInvoiceOccurrenceCount": 0
        }
        cases = (
            (None, None),
            ("", ""),
            ("   ", " \t ")
        )

        for vendor_name, invoice_number in cases:
            with self.subTest(
                vendor_name=vendor_name,
                invoice_number=invoice_number
            ):
                self.assertEqual(
                    self.count_for_source(vendor_name, invoice_number),
                    zero_counts
                )

    def test_one_missing_source_value_preserves_other_count(self):
        self.add_record(1, 1, "Acme Ltd.", "INV-100")
        self.add_record(2, 2, "Acme Ltd.", "INV-200")
        self.add_record(3, 3, "Other Vendor", "INV-100")

        self.assertEqual(
            self.count_for_source(vendor_name=None),
            {
                "vendorOccurrenceCount": 0,
                "invoiceNumberOccurrenceCount": 1,
                "vendorInvoiceOccurrenceCount": 0
            }
        )
        self.assertEqual(
            self.count_for_source(invoice_number=None),
            {
                "vendorOccurrenceCount": 1,
                "invoiceNumberOccurrenceCount": 0,
                "vendorInvoiceOccurrenceCount": 0
            }
        )

    def test_source_invoice_is_excluded_from_all_counts(self):
        self.add_record(1, 1, "Acme Ltd.", "INV-100")

        self.assertEqual(
            self.count_for_source(),
            {
                "vendorOccurrenceCount": 0,
                "invoiceNumberOccurrenceCount": 0,
                "vendorInvoiceOccurrenceCount": 0
            }
        )

    def test_duplicate_extraction_rows_count_one_distinct_invoice(self):
        self.add_record(1, 1, "Acme Ltd.", "INV-100")
        self.add_record(2, 2, "Acme Ltd.", "INV-100")
        self.add_record(3, 2, "Acme Ltd.", "INV-100")

        self.assertEqual(
            self.count_for_source(),
            {
                "vendorOccurrenceCount": 1,
                "invoiceNumberOccurrenceCount": 1,
                "vendorInvoiceOccurrenceCount": 1
            }
        )

    def test_unreviewed_records_are_excluded(self):
        self.add_record(1, 1, "Acme Ltd.", "INV-100")
        self.add_record(2, 2, "Acme Ltd.", "INV-100", is_reviewed=False)

        self.assertEqual(
            self.count_for_source(),
            {
                "vendorOccurrenceCount": 0,
                "invoiceNumberOccurrenceCount": 0,
                "vendorInvoiceOccurrenceCount": 0
            }
        )


class DuplicateFrequencyServiceTests(unittest.TestCase):
    @patch(
        "app.services.feature_engineering_service."
        "get_feature_candidate_invoices"
    )
    @patch(
        "app.services.feature_engineering_service."
        "get_duplicate_frequency_counts"
    )
    @patch(
        "app.services.feature_engineering_service."
        "get_extracted_invoice_data_by_invoice_id"
    )
    def test_counts_are_calculated_once_and_added_to_each_comparison(
        self,
        get_source,
        get_counts,
        get_candidates
    ):
        source_invoice = SimpleNamespace(
            invoiceId=1,
            isReviewed=True,
            vendorName="Acme Ltd.",
            invoiceNumber="INV-100",
            totalAmount=Decimal("100.00"),
            invoiceDate=date(2025, 1, 1),
            currency="USD"
        )
        candidates = [
            SimpleNamespace(
                invoiceId=2,
                vendorName="Acme Ltd.",
                invoiceNumber="INV-200",
                totalAmount=Decimal("100.00"),
                invoiceDate=date(2025, 1, 1),
                currency="USD"
            ),
            SimpleNamespace(
                invoiceId=3,
                vendorName="Other Vendor",
                invoiceNumber="INV-300",
                totalAmount=Decimal("90.00"),
                invoiceDate=date(2025, 1, 2),
                currency="EUR"
            )
        ]
        occurrence_counts = {
            "vendorOccurrenceCount": 2,
            "invoiceNumberOccurrenceCount": 1,
            "vendorInvoiceOccurrenceCount": 1
        }
        db = Mock()
        get_source.return_value = source_invoice
        get_counts.return_value = occurrence_counts
        get_candidates.return_value = candidates

        result = generate_invoice_features_service(db=db, invoice_id=1)

        get_counts.assert_called_once_with(
            db=db,
            current_invoice_id=1,
            vendor_name="Acme Ltd.",
            invoice_number="INV-100"
        )
        self.assertEqual(result["comparedInvoices"], 2)
        self.assertEqual(len(result["comparisons"]), 2)
        for comparison in result["comparisons"]:
            self.assertEqual(
                comparison["features"]["vendorOccurrenceCount"],
                2
            )
            self.assertEqual(
                comparison["features"]["invoiceNumberOccurrenceCount"],
                1
            )
            self.assertEqual(
                comparison["features"]["vendorInvoiceOccurrenceCount"],
                1
            )
            self.assertIsInstance(
                comparison["features"]["vendorOccurrenceCount"],
                int
            )
            InvoiceComparisonFeatures.model_validate(comparison["features"])


if __name__ == "__main__":
    unittest.main()
