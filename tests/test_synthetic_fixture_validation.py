import csv
import importlib
import shutil
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = (
    PROJECT_ROOT
    / "data"
    / "synthetic"
    / "duplicate_payment_pilot"
)


def read_csv(path: Path) -> list[dict]:
    with path.open("r", newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


class PartialPaymentRatioTests(unittest.TestCase):
    def setUp(self):
        self.invoices = {
            row["invoice_id"]: row
            for row in read_csv(DATA_DIR / "invoices.csv")
        }
        self.allocations = read_csv(DATA_DIR / "allocations.csv")
        self.allocations_for_generator = [
            {
                **row,
                "invoice_id": int(row["invoice_id"]),
            }
            for row in self.allocations
        ]
        self.invoices_for_generator = {
            int(invoice_id): row
            for invoice_id, row in {
                key: value
                for key, value in self.invoices.items()
            }.items()
        }

    def test_partial_ratio_aggregates_invoice_21_allocations(self):
        generator = importlib.import_module(
            "scripts.generate_duplicate_payment_fixture"
        )
        validator = importlib.import_module(
            "scripts.validate_duplicate_payment_fixture"
        )

        expected = Decimal("1")
        generator_ratio = generator.calculate_partial_payment_ratio(
            21,
            self.invoices_for_generator,
            self.allocations_for_generator,
        )
        validator_ratio = validator.calculate_partial_payment_ratio(
            "21",
            self.invoices,
            self.allocations,
        )

        self.assertEqual(generator_ratio, expected)
        self.assertEqual(validator_ratio, expected)

    def test_paired_coverage_is_one_for_pair_0024(self):
        generator = importlib.import_module(
            "scripts.generate_duplicate_payment_fixture"
        )
        validator = importlib.import_module(
            "scripts.validate_duplicate_payment_fixture"
        )

        generator_a = generator.calculate_partial_payment_ratio(
            19,
            self.invoices_for_generator,
            self.allocations_for_generator,
        )
        generator_b = generator.calculate_partial_payment_ratio(
            21,
            self.invoices_for_generator,
            self.allocations_for_generator,
        )
        validator_a = validator.calculate_partial_payment_ratio(
            "19",
            self.invoices,
            self.allocations,
        )
        validator_b = validator.calculate_partial_payment_ratio(
            "21",
            self.invoices,
            self.allocations,
        )

        self.assertEqual(generator_a, Decimal("1"))
        self.assertEqual(generator_b, Decimal("1"))
        self.assertEqual(validator_a, Decimal("1"))
        self.assertEqual(validator_b, Decimal("1"))


class TemporaryMismatchValidatorTests(unittest.TestCase):
    def test_validator_detects_intentionally_incorrect_feature(self):
        validator = importlib.import_module(
            "scripts.validate_duplicate_payment_fixture"
        )

        with tempfile.TemporaryDirectory() as temp_directory:
            temp_dir = Path(temp_directory)
            for source in DATA_DIR.iterdir():
                if source.is_file():
                    shutil.copy2(source, temp_dir / source.name)

            feature_path = temp_dir / "pair_features.csv"
            rows = read_csv(feature_path)
            for row in rows:
                if row["pair_id"] == "PAIR-0014":
                    row["partialPaymentRatio"] = "0.5"
                    break

            with feature_path.open(
                "w",
                newline="",
                encoding="utf-8",
            ) as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=rows[0].keys(),
                )
                writer.writeheader()
                writer.writerows(rows)

            original_base_dir = validator.BASE_DIR
            validator.BASE_DIR = temp_dir
            try:
                result = validator.main()
            finally:
                validator.BASE_DIR = original_base_dir

            self.assertEqual(result, 1)

            report = temp_dir / "validation_report.json"
            report_data = __import__("json").loads(
                report.read_text(encoding="utf-8")
            )
            feature_mismatches = report_data[
                "recomputed_feature_mismatches"
            ]
            pair_mismatch = next(
                item
                for item in feature_mismatches
                if item["pair_id"] == "PAIR-0014"
            )
            mismatch = pair_mismatch["mismatches"]["partialPaymentRatio"]
            self.assertEqual(mismatch["actual"], "0.5")
            self.assertEqual(mismatch["expected"], "1.0")


if __name__ == "__main__":
    unittest.main()
