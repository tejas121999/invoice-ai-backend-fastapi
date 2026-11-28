import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_duplicate_payment_ml_datasets import (
    FEATURE_COLUMNS,
    INPUT_COLUMNS,
    OUTPUT_COLUMNS,
    join_binary_features,
    load_feature_rows,
    load_pair_targets,
    prepare_datasets,
)


PAIR_FIELDS = ("pair_id", "label", "split_name", "rationale_code")


def write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def feature_row(pair_id: str, **overrides) -> dict[str, str]:
    row = {
        "pair_id": pair_id,
        **{
            feature_name: str(index / 10)
            for index, feature_name in enumerate(FEATURE_COLUMNS)
        },
    }
    row.update(overrides)
    return row


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        return list(reader.fieldnames or []), list(reader)


class DuplicatePaymentPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_directory.name)
        self.features_path = self.base_dir / "predictive_pair_features.csv"
        self.pairs_path = self.base_dir / "pairs.csv"
        self.output_dir = self.base_dir / "prepared"

    def tearDown(self):
        self.temp_directory.cleanup()

    def write_sources(self) -> None:
        feature_rows = [
            feature_row("PAIR-0003", partialPaymentRatio=""),
            feature_row("PAIR-0001"),
            feature_row("PAIR-0004", paidAmountMatch=""),
            feature_row("PAIR-0002"),
        ]
        pair_rows = [
            {
                "pair_id": "PAIR-0003",
                "label": "uncertain",
                "split_name": "test",
                "rationale_code": "UNC_TEST",
            },
            {
                "pair_id": "PAIR-0001",
                "label": "duplicate",
                "split_name": "train",
                "rationale_code": "DUP_TEST",
            },
            {
                "pair_id": "PAIR-0004",
                "label": "not_duplicate",
                "split_name": "test",
                "rationale_code": "ND_TEST",
            },
            {
                "pair_id": "PAIR-0002",
                "label": "duplicate",
                "split_name": "validation",
                "rationale_code": "DUP_TEST",
            },
        ]
        write_csv(self.features_path, INPUT_COLUMNS, feature_rows)
        write_csv(self.pairs_path, PAIR_FIELDS, pair_rows)

    def test_prepares_binary_splits_without_mutating_feature_values(self):
        self.write_sources()

        output_paths, summary = prepare_datasets(
            self.features_path,
            self.pairs_path,
            self.output_dir,
        )

        self.assertEqual(summary["binary_records"], 3)
        self.assertEqual(summary["uncertain_records_excluded"], 1)
        self.assertEqual(summary["splits"]["train"]["duplicate"], 1)
        self.assertEqual(
            summary["splits"]["validation"]["duplicate"],
            1,
        )
        self.assertEqual(summary["splits"]["test"]["not_duplicate"], 1)

        train_columns, train_rows = read_csv(output_paths["train"])
        validation_rows = read_csv(output_paths["validation"])[1]
        test_rows = read_csv(output_paths["test"])[1]
        self.assertEqual(train_columns, list(OUTPUT_COLUMNS))
        self.assertEqual([row["pair_id"] for row in train_rows], ["PAIR-0001"])
        self.assertEqual(
            [row["pair_id"] for row in validation_rows],
            ["PAIR-0002"],
        )
        self.assertEqual([row["pair_id"] for row in test_rows], ["PAIR-0004"])
        self.assertNotIn("rationale_code", train_columns)
        self.assertEqual(test_rows[0]["paidAmountMatch"], "")
        self.assertEqual(
            summary["missing_values_by_feature"]["paidAmountMatch"],
            1,
        )

        summary_data = json.loads(
            output_paths["summary"].read_text(encoding="utf-8")
        )
        self.assertEqual(summary_data, summary)

    def test_preserves_source_csv_files(self):
        self.write_sources()
        feature_contents = self.features_path.read_bytes()
        pair_contents = self.pairs_path.read_bytes()

        prepare_datasets(
            self.features_path,
            self.pairs_path,
            self.output_dir,
        )

        self.assertEqual(self.features_path.read_bytes(), feature_contents)
        self.assertEqual(self.pairs_path.read_bytes(), pair_contents)

    def test_rejects_duplicate_feature_pair_ids(self):
        write_csv(
            self.features_path,
            INPUT_COLUMNS,
            [feature_row("PAIR-0001"), feature_row("PAIR-0001")],
        )

        with self.assertRaisesRegex(ValueError, "duplicate pair_id"):
            load_feature_rows(self.features_path)

    def test_rejects_missing_and_unexpected_labels(self):
        cases = ("", "maybe_duplicate")
        for label in cases:
            with self.subTest(label=label):
                write_csv(
                    self.pairs_path,
                    PAIR_FIELDS,
                    [{
                        "pair_id": "PAIR-0001",
                        "label": label,
                        "split_name": "train",
                        "rationale_code": "",
                    }],
                )
                with self.assertRaisesRegex(ValueError, "label"):
                    load_pair_targets(self.pairs_path)

    def test_rejects_unmatched_pair_ids(self):
        feature_rows = {"PAIR-0001": feature_row("PAIR-0001")}
        targets = {"PAIR-0002": ("duplicate", "train")}

        with self.assertRaisesRegex(ValueError, "do not match"):
            join_binary_features(feature_rows, targets)

    def test_uncertain_rows_are_excluded_without_becoming_negative(self):
        feature_rows = {
            "PAIR-0001": feature_row("PAIR-0001"),
            "PAIR-0002": feature_row("PAIR-0002"),
        }
        targets = {
            "PAIR-0001": ("duplicate", "train"),
            "PAIR-0002": ("uncertain", "train"),
        }

        split_rows, excluded = join_binary_features(feature_rows, targets)

        self.assertEqual(excluded, 1)
        self.assertEqual([row["pair_id"] for row in split_rows["train"]], ["PAIR-0001"])
        self.assertEqual(split_rows["train"][0]["label"], "duplicate")


if __name__ == "__main__":
    unittest.main()
