import csv
import shutil
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from app.adapters.synthetic_csv_adapter import (
    CSVFileNotFoundError,
    CSVRelationshipError,
    CSVValueError,
    build_candidate_pairs,
    load_allocations,
    load_pair_features,
    load_invoices,
    load_pair_labels,
    load_payments,
    load_suppliers,
    load_synthetic_pilot,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PILOT_DIR = (
    PROJECT_ROOT
    / "data"
    / "synthetic"
    / "duplicate_payment_pilot"
)


def copy_pilot(temp_dir: Path) -> Path:
    destination = temp_dir / "pilot"
    shutil.copytree(PILOT_DIR, destination)
    return destination


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class SyntheticCSVAdapterTests(unittest.TestCase):
    def test_successful_dataset_loading(self):
        pilot = load_synthetic_pilot(PILOT_DIR)

        self.assertEqual(len(pilot.suppliers), 12)
        self.assertEqual(len(pilot.invoices), 36)
        self.assertEqual(len(pilot.payments), 37)
        self.assertEqual(len(pilot.allocations), 37)
        self.assertEqual(len(pilot.pairs), 30)
        self.assertEqual(len(pilot.pair_features), 30)
        self.assertEqual(len(pilot.pair_labels), 30)

    def test_correct_pair_construction(self):
        suppliers = load_suppliers(PILOT_DIR)
        invoices = load_invoices(PILOT_DIR)
        payments = load_payments(PILOT_DIR)
        allocations = load_allocations(PILOT_DIR)
        pairs = build_candidate_pairs(
            PILOT_DIR,
            invoices,
            suppliers,
            payments,
            allocations,
        )

        pair = pairs["PAIR-0001"]
        self.assertEqual(pair.pair_id, "PAIR-0001")
        self.assertEqual(pair.invoice_a.invoice_id, "1")
        self.assertEqual(pair.invoice_b.invoice_id, "2")
        self.assertEqual(pair.supplier_a.supplier_id, "SUP-001")
        self.assertEqual(pair.supplier_b.supplier_id, "SUP-001")
        self.assertIsNotNone(pair.payment_a)
        self.assertIsNotNone(pair.payment_b)
        self.assertIsNotNone(pair.allocation_a)
        self.assertIsNotNone(pair.allocation_b)

    def test_decimal_parsing(self):
        pilot = load_synthetic_pilot(PILOT_DIR)
        invoice = pilot.invoices["1"]
        payment = pilot.payments["PAY-0001"]
        allocation = pilot.allocations["ALLOC-0001"]

        self.assertIsInstance(invoice.total_amount, Decimal)
        self.assertEqual(invoice.total_amount, Decimal("100000.00"))
        self.assertIsInstance(payment.paid_amount, Decimal)
        self.assertEqual(payment.paid_amount, Decimal("100000.00"))
        self.assertIsInstance(allocation.allocated_amount, Decimal)
        self.assertEqual(
            allocation.allocated_amount,
            Decimal("100000.00"),
        )

    def test_missing_csv_file(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            pilot = copy_pilot(Path(temp_directory))
            (pilot / "suppliers.csv").unlink()

            with self.assertRaises(CSVFileNotFoundError) as context:
                load_suppliers(pilot)

            self.assertIn(
                "Required CSV file not found",
                str(context.exception),
            )

    def test_invalid_supplier_reference(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            pilot = copy_pilot(Path(temp_directory))
            path = pilot / "invoices.csv"
            rows = read_csv(path)
            for row in rows:
                if row["invoice_id"] == "1":
                    row["supplier_id"] = "SUP-MISSING"
                    break

            with path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=rows[0].keys(),
                )
                writer.writeheader()
                writer.writerows(rows)

            with self.assertRaises(CSVRelationshipError):
                load_synthetic_pilot(pilot)

    def test_invalid_invoice_reference(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            pilot = copy_pilot(Path(temp_directory))
            path = pilot / "pairs.csv"
            rows = read_csv(path)
            for row in rows:
                if row["pair_id"] == "PAIR-0001":
                    row["invoice_id_a"] = "999"
                    break

            with path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=rows[0].keys(),
                )
                writer.writeheader()
                writer.writerows(rows)

            with self.assertRaises(CSVRelationshipError) as context:
                suppliers = load_suppliers(pilot)
                invoices = load_invoices(pilot)
                payments = load_payments(pilot)
                allocations = load_allocations(pilot)
                build_candidate_pairs(
                    pilot,
                    invoices,
                    suppliers,
                    payments,
                    allocations,
                )

            self.assertIn("does not reference an invoice", str(context.exception))

    def test_invalid_payment_reference(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            pilot = copy_pilot(Path(temp_directory))
            path = pilot / "pairs.csv"
            rows = read_csv(path)
            for row in rows:
                if row["pair_id"] == "PAIR-0001":
                    row["payment_id_a"] = "PAY-MISSING"
                    break

            with path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=rows[0].keys(),
                )
                writer.writeheader()
                writer.writerows(rows)

            with self.assertRaises(CSVRelationshipError) as context:
                suppliers = load_suppliers(pilot)
                invoices = load_invoices(pilot)
                payments = load_payments(pilot)
                allocations = load_allocations(pilot)
                build_candidate_pairs(
                    pilot,
                    invoices,
                    suppliers,
                    payments,
                    allocations,
                )

            self.assertIn("does not reference a payment", str(context.exception))

    def test_missing_optional_payment_evidence(self):
        pilot = load_synthetic_pilot(PILOT_DIR)
        uncertain_pairs = [
            pair
            for pair in pilot.pairs.values()
            if pilot.pair_labels[pair.pair_id].label == "uncertain"
        ]
        self.assertGreater(len(uncertain_pairs), 0)

        missing_evidence_pair = next(
            pair
            for pair in uncertain_pairs
            if pair.payment_a is None
            or pair.payment_b is None
            or pair.allocation_a is None
            or pair.allocation_b is None
        )
        self.assertIsInstance(missing_evidence_pair, object)

    def test_duplicate_primary_identifiers(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            pilot = copy_pilot(Path(temp_directory))
            path = pilot / "suppliers.csv"
            rows = read_csv(path)
            duplicate_row = dict(rows[0])
            rows.append(duplicate_row)

            with path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=rows[0].keys(),
                )
                writer.writeheader()
                writer.writerows(rows)

            with self.assertRaises(CSVRelationshipError) as context:
                load_suppliers(pilot)

            self.assertIn("duplicate primary identifier", str(context.exception))

    def test_hidden_metadata_excluded_from_predictive_pair_records(self):
        pilot = load_synthetic_pilot(PILOT_DIR)
        pair = pilot.pairs["PAIR-0001"]
        pair_keys = set(vars(pair))
        forbidden = {
            "label",
            "rationale",
            "rationale_code",
            "synthetic_scenario",
            "underlying_obligation_id_a",
            "underlying_obligation_id_b",
            "hidden_supplier_cluster",
            "hidden_pair_overlap",
        }

        self.assertTrue(pair_keys.isdisjoint(forbidden))

    def test_multiple_allocations_for_one_invoice(self):
        pilot = load_synthetic_pilot(PILOT_DIR)
        allocations = [
            allocation
            for allocation in pilot.allocations.values()
            if allocation.invoice_id == "21"
        ]

        self.assertGreaterEqual(len(allocations), 2)
        self.assertEqual(
            sum(
                allocation.allocated_amount
                for allocation in allocations
                if allocation.allocated_amount is not None
            ),
            Decimal("600.00"),
        )

    def test_multiple_invoices_can_share_one_payment(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            pilot = copy_pilot(Path(temp_directory))
            path = pilot / "allocations.csv"
            rows = read_csv(path)
            for row in rows:
                if row["allocation_id"] == "ALLOC-0034":
                    row["payment_id"] = "PAY-0023"
                    break

            with path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=rows[0].keys(),
                )
                writer.writeheader()
                writer.writerows(rows)

            allocations = load_allocations(pilot)
            payment_invoice_ids = {}
            for allocation in allocations.values():
                payment_invoice_ids.setdefault(
                    allocation.payment_id,
                    set(),
                ).add(allocation.invoice_id)

            self.assertIn("PAY-0023", payment_invoice_ids)
            self.assertGreaterEqual(
                len(payment_invoice_ids["PAY-0023"]),
                2,
            )

    def test_negative_zero_nan_and_infinity_allocations(self):
        for value in ("-1.00", "0.00", "NaN", "Infinity"):
            with self.subTest(value=value):
                with tempfile.TemporaryDirectory() as temp_directory:
                    pilot = copy_pilot(Path(temp_directory))
                    path = pilot / "allocations.csv"
                    rows = read_csv(path)
                    for row in rows:
                        if row["allocation_id"] == "ALLOC-0001":
                            row["allocated_amount"] = value
                            break

                    with path.open("w", newline="", encoding="utf-8") as file:
                        writer = csv.DictWriter(
                            file,
                            fieldnames=rows[0].keys(),
                        )
                        writer.writeheader()
                        writer.writerows(rows)

                    with self.assertRaises((CSVValueError, CSVRelationshipError)):
                        load_allocations(pilot)

    def test_currency_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            pilot = copy_pilot(Path(temp_directory))
            path = pilot / "invoices.csv"
            rows = read_csv(path)
            for row in rows:
                if row["invoice_id"] == "1":
                    row["currency"] = "USD"
                    break

            with path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=rows[0].keys(),
                )
                writer.writeheader()
                writer.writerows(rows)

            with self.assertRaises(CSVRelationshipError):
                load_synthetic_pilot(pilot)

    def test_invalid_currency_value(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            pilot = copy_pilot(Path(temp_directory))
            path = pilot / "payments.csv"
            rows = read_csv(path)
            for row in rows:
                if row["payment_id"] == "PAY-0001":
                    row["payment_currency"] = "US"
                    break

            with path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=rows[0].keys(),
                )
                writer.writeheader()
                writer.writerows(rows)

            with self.assertRaises(CSVValueError):
                load_payments(pilot)

    def test_allocation_over_invoice_total(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            pilot = copy_pilot(Path(temp_directory))
            path = pilot / "allocations.csv"
            rows = read_csv(path)
            for row in rows:
                if row["allocation_id"] == "ALLOC-0001":
                    row["allocated_amount"] = "200000.00"
                    break

            with path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=rows[0].keys(),
                )
                writer.writeheader()
                writer.writerows(rows)

            with self.assertRaises(CSVRelationshipError) as context:
                load_synthetic_pilot(pilot)

            self.assertIn("exceed", str(context.exception))

    def test_allocation_over_payment_amount(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            pilot = copy_pilot(Path(temp_directory))
            path = pilot / "allocations.csv"
            rows = read_csv(path)
            for row in rows:
                if row["allocation_id"] == "ALLOC-0001":
                    row["allocated_amount"] = "200000.00"
                    break

            with path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=rows[0].keys(),
                )
                writer.writeheader()
                writer.writerows(rows)

            with self.assertRaises(CSVRelationshipError) as context:
                load_synthetic_pilot(pilot)

            self.assertIn("exceed", str(context.exception))

    def test_missing_pair_label_record(self):
        pilot = load_synthetic_pilot(PILOT_DIR)
        with tempfile.TemporaryDirectory() as temp_directory:
            temp_pilot = copy_pilot(Path(temp_directory))
            path = temp_pilot / "pairs.csv"
            rows = read_csv(path)
            for row in rows:
                if row["pair_id"] == "PAIR-0001":
                    row["label"] = ""
                    break

            with path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=rows[0].keys(),
                )
                writer.writeheader()
                writer.writerows(rows)

            with self.assertRaises(CSVValueError):
                load_pair_labels(temp_pilot)

    def test_feature_type_conversion(self):
        features = load_pair_features(PILOT_DIR)
        pair_feature = features["PAIR-0001"]
        values = pair_feature.values

        self.assertIsInstance(values["exactAmountMatch"], bool)
        self.assertIsInstance(values["dateDifferenceDays"], int)
        self.assertIsInstance(values["amountDifference"], Decimal)
        self.assertIsInstance(values["amountSimilarity"], float)
        self.assertIsInstance(values["partialPaymentRatio"], Decimal)

    def test_contradictory_allocation_status_event(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            pilot = copy_pilot(Path(temp_directory))
            path = pilot / "allocations.csv"
            rows = read_csv(path)
            for row in rows:
                if row["allocation_id"] == "ALLOC-0001":
                    row["allocation_status"] = "confirmed_paid"
                    row["settlement_event"] = "cancelled_before_settlement"
                    break

            with path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=rows[0].keys(),
                )
                writer.writeheader()
                writer.writerows(rows)

            with self.assertRaises(CSVValueError) as context:
                load_allocations(pilot)

            self.assertIn("contradictory", str(context.exception))


if __name__ == "__main__":
    unittest.main()
