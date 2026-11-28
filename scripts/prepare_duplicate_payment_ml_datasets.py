"""Prepare binary train, validation and test CSVs from the synthetic pilot."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PILOT_DIR = (
    PROJECT_ROOT
    / "data"
    / "synthetic"
    / "duplicate_payment_pilot"
)
FEATURES_PATH = PILOT_DIR / "predictive_pair_features.csv"
PAIRS_PATH = PILOT_DIR / "pairs.csv"
OUTPUT_DIR = PILOT_DIR / "prepared"

FEATURE_COLUMNS = (
    "vendorSimilarity",
    "invoiceNumberSimilarity",
    "exactAmountMatch",
    "amountDifference",
    "amountSimilarity",
    "dateDifferenceDays",
    "currencyMatch",
    "paymentTermsSimilarity",
    "paidAmountMatch",
    "paidAmountSimilarity",
    "paymentReferenceSimilarity",
    "samePaymentRun",
    "partialPaymentRatio",
)
INPUT_COLUMNS = ("pair_id", *FEATURE_COLUMNS)
OUTPUT_COLUMNS = ("pair_id", "label", "split_name", *FEATURE_COLUMNS)
BINARY_LABELS = {"duplicate", "not_duplicate"}
VALID_LABELS = BINARY_LABELS | {"uncertain"}
SPLITS = ("train", "validation", "test")
FORBIDDEN_FEATURE_COLUMNS = {
    "label",
    "label_status",
    "rationale_code",
    "rationale_text",
    "reviewer_id_masked",
    "review_confidence",
    "evidence_source",
    "adjudicated_at",
    "protocol_version",
    "synthetic_scenario",
    "synthetic_ground_truth_label",
    "underlying_obligation_id",
    "underlying_obligation_id_a",
    "underlying_obligation_id_b",
    "split_name",
    "supplier_cluster_id",
    "generator_seed",
    "generator_metadata",
}


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        return list(reader.fieldnames), list(reader)


def _require_unique_pair_ids(
    rows: list[dict[str, str]],
    source_name: str,
) -> dict[str, dict[str, str]]:
    by_pair: dict[str, dict[str, str]] = {}
    for row in rows:
        pair_id = row.get("pair_id", "").strip()
        if not pair_id:
            raise ValueError(f"{source_name} contains a missing pair_id")
        if pair_id in by_pair:
            raise ValueError(f"{source_name} contains duplicate pair_id {pair_id}")
        by_pair[pair_id] = row
    return by_pair


def load_feature_rows(
    path: Path,
) -> tuple[list[str], dict[str, dict[str, str]]]:
    columns, rows = _read_csv(path)
    if columns != list(INPUT_COLUMNS):
        raise ValueError(
            "Predictive feature columns must exactly match the approved "
            f"14-column schema. Expected={list(INPUT_COLUMNS)}, actual={columns}"
        )
    forbidden = set(columns) & FORBIDDEN_FEATURE_COLUMNS
    if forbidden:
        raise ValueError(f"Predictive feature CSV has forbidden columns: {sorted(forbidden)}")
    return columns, _require_unique_pair_ids(rows, "predictive feature CSV")


def load_pair_targets(
    path: Path,
) -> dict[str, tuple[str, str]]:
    columns, rows = _read_csv(path)
    required_columns = {"pair_id", "label", "split_name"}
    missing_columns = required_columns - set(columns)
    if missing_columns:
        raise ValueError(
            f"Pair source is missing required columns: {sorted(missing_columns)}"
        )

    pair_rows = _require_unique_pair_ids(rows, "pair source CSV")
    targets: dict[str, tuple[str, str]] = {}
    for pair_id, row in pair_rows.items():
        label = row["label"].strip()
        split_name = row["split_name"].strip()
        if not label:
            raise ValueError(f"Pair {pair_id} has a missing label")
        if label not in VALID_LABELS:
            raise ValueError(f"Pair {pair_id} has unexpected label {label!r}")
        if split_name not in SPLITS:
            raise ValueError(
                f"Pair {pair_id} has unexpected split {split_name!r}"
            )
        targets[pair_id] = (label, split_name)
    return targets


def join_binary_features(
    feature_rows: dict[str, dict[str, str]],
    pair_targets: dict[str, tuple[str, str]],
) -> tuple[dict[str, list[dict[str, str]]], int]:
    feature_ids = set(feature_rows)
    target_ids = set(pair_targets)
    if feature_ids != target_ids:
        raise ValueError(
            "Feature and pair source IDs do not match: "
            f"missing_targets={sorted(feature_ids - target_ids)}, "
            f"missing_features={sorted(target_ids - feature_ids)}"
        )

    split_rows = {split_name: [] for split_name in SPLITS}
    uncertain_excluded = 0
    for pair_id in sorted(feature_ids):
        label, split_name = pair_targets[pair_id]
        if label == "uncertain":
            uncertain_excluded += 1
            continue
        if label not in BINARY_LABELS:
            raise ValueError(f"Pair {pair_id} has non-binary label {label!r}")

        source_features = feature_rows[pair_id]
        row = {
            "pair_id": pair_id,
            "label": label,
            "split_name": split_name,
            **{
                feature_name: source_features[feature_name]
                for feature_name in FEATURE_COLUMNS
            },
        }
        split_rows[split_name].append(row)
    return split_rows, uncertain_excluded


def _build_summary(
    split_rows: dict[str, list[dict[str, str]]],
    uncertain_excluded: int,
) -> dict[str, Any]:
    splits: dict[str, Any] = {}
    for split_name in SPLITS:
        rows = split_rows[split_name]
        label_counts = Counter(row["label"] for row in rows)
        splits[split_name] = {
            "binary_records": len(rows),
            "duplicate": label_counts["duplicate"],
            "not_duplicate": label_counts["not_duplicate"],
            "missing_values_by_feature": {
                feature_name: sum(row[feature_name] == "" for row in rows)
                for feature_name in FEATURE_COLUMNS
            },
        }

    all_binary_rows = [
        row
        for split_name in SPLITS
        for row in split_rows[split_name]
    ]
    return {
        "binary_records": len(all_binary_rows),
        "uncertain_records_excluded": uncertain_excluded,
        "feature_columns": list(FEATURE_COLUMNS),
        "splits": splits,
        "missing_values_by_feature": {
            feature_name: sum(
                row[feature_name] == "" for row in all_binary_rows
            )
            for feature_name in FEATURE_COLUMNS
        },
    }


def write_prepared_datasets(
    split_rows: dict[str, list[dict[str, str]]],
    summary: dict[str, Any],
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths: dict[str, Path] = {}
    for split_name in SPLITS:
        output_path = output_dir / f"binary_{split_name}.csv"
        with output_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=OUTPUT_COLUMNS,
                extrasaction="raise",
            )
            writer.writeheader()
            writer.writerows(split_rows[split_name])
        output_paths[split_name] = output_path

    summary_path = output_dir / "preparation_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    output_paths["summary"] = summary_path
    return output_paths


def prepare_datasets(
    features_path: Path = FEATURES_PATH,
    pairs_path: Path = PAIRS_PATH,
    output_dir: Path = OUTPUT_DIR,
) -> tuple[dict[str, Path], dict[str, Any]]:
    _, feature_rows = load_feature_rows(features_path)
    pair_targets = load_pair_targets(pairs_path)
    split_rows, uncertain_excluded = join_binary_features(
        feature_rows,
        pair_targets,
    )
    summary = _build_summary(split_rows, uncertain_excluded)
    output_paths = write_prepared_datasets(
        split_rows,
        summary,
        output_dir,
    )
    return output_paths, summary


def main() -> int:
    output_paths, summary = prepare_datasets()
    print(json.dumps({
        **summary,
        "output_paths": {
            name: str(path)
            for name, path in output_paths.items()
        },
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
