"""Generate the approved predictive feature dataset for the synthetic pilot."""

from __future__ import annotations

import csv
import math
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.adapters.synthetic_csv_adapter import load_synthetic_pilot
from app.services.pair_feature_engineering_service import (
    INVOICE_FEATURE_NAMES,
    PAYMENT_FEATURE_NAMES,
    generate_invoice_pair_features,
    generate_payment_pair_features,
)


PILOT_DIR = (
    PROJECT_ROOT
    / "data"
    / "synthetic"
    / "duplicate_payment_pilot"
)
OUTPUT_PATH = PILOT_DIR / "predictive_pair_features.csv"

COLUMNS = (
    "pair_id",
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
FEATURE_NAMES = COLUMNS[1:]
BOOLEAN_FEATURES = {
    "exactAmountMatch",
    "currencyMatch",
    "paidAmountMatch",
    "samePaymentRun",
}
INTEGER_FEATURES = {"dateDifferenceDays"}
DECIMAL_FEATURES = {"amountDifference", "partialPaymentRatio"}
FLOAT_FEATURES = {
    "vendorSimilarity",
    "invoiceNumberSimilarity",
    "amountSimilarity",
    "paymentTermsSimilarity",
    "paidAmountSimilarity",
    "paymentReferenceSimilarity",
}
FORBIDDEN_COLUMNS = {
    "label",
    "label_status",
    "rationale_code",
    "rationale_text",
    "reviewer_id_masked",
    "review_confidence",
    "evidence_source",
    "adjudicated_at",
    "protocol_version",
    "underlying_obligation_id",
    "underlying_obligation_id_a",
    "underlying_obligation_id_b",
    "synthetic_scenario",
    "split_name",
    "supplier_cluster_id",
    "generator_seed",
    "generator_metadata",
}


def _validate_feature_keys(
    invoice_features: dict[str, Any],
    payment_features: dict[str, Any],
) -> None:
    expected_invoice = set(INVOICE_FEATURE_NAMES)
    expected_payment = set(PAYMENT_FEATURE_NAMES)
    actual_invoice = set(invoice_features)
    actual_payment = set(payment_features)

    if actual_invoice != expected_invoice:
        raise ValueError(
            "Invoice feature keys differ from the approved contract: "
            f"missing={sorted(expected_invoice - actual_invoice)}, "
            f"unexpected={sorted(actual_invoice - expected_invoice)}"
        )
    if actual_payment != expected_payment:
        raise ValueError(
            "Payment feature keys differ from the approved contract: "
            f"missing={sorted(expected_payment - actual_payment)}, "
            f"unexpected={sorted(actual_payment - expected_payment)}"
        )
    overlap = actual_invoice & actual_payment
    if overlap:
        raise ValueError(f"Duplicate feature keys: {sorted(overlap)}")

    combined = actual_invoice | actual_payment
    expected_features = set(FEATURE_NAMES)
    if combined != expected_features:
        raise ValueError(
            "Combined feature keys differ from the approved 13-feature "
            f"contract: missing={sorted(expected_features - combined)}, "
            f"unexpected={sorted(combined - expected_features)}"
        )


def _serialize_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"Non-finite Decimal cannot be serialized: {value}")
        return format(value, "f")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Non-finite float cannot be serialized: {value}")
        return str(value)
    if isinstance(value, (int, str)):
        return str(value)
    raise TypeError(f"Unsupported feature value: {value!r}")


def _validate_rows(rows: list[dict[str, Any]]) -> None:
    if len(rows) != 30:
        raise ValueError(f"Expected 30 feature rows, generated {len(rows)}")

    pair_ids = [row["pair_id"] for row in rows]
    if len(set(pair_ids)) != len(pair_ids):
        duplicates = sorted(
            pair_id
            for pair_id, count in Counter(pair_ids).items()
            if count > 1
        )
        raise ValueError(f"Duplicate pair IDs: {duplicates}")

    expected_keys = set(COLUMNS)
    forbidden = expected_keys & FORBIDDEN_COLUMNS
    if forbidden:
        raise ValueError(f"Forbidden output columns: {sorted(forbidden)}")
    for row in rows:
        if set(row) != expected_keys:
            raise ValueError(
                f"Row {row.get('pair_id')} has invalid columns: "
                f"missing={sorted(expected_keys - set(row))}, "
                f"unexpected={sorted(set(row) - expected_keys)}"
            )

        for feature_name in FEATURE_NAMES:
            if feature_name in BOOLEAN_FEATURES:
                value = row[feature_name]
                if value is not None and not isinstance(value, bool):
                    raise TypeError(
                        f"{row['pair_id']}:{feature_name} must be bool or None"
                    )
            elif feature_name in INTEGER_FEATURES:
                value = row[feature_name]
                if value is not None and not isinstance(value, int):
                    raise TypeError(
                        f"{row['pair_id']}:{feature_name} must be int or None"
                    )


def _write_csv(rows: list[dict[str, Any]]) -> None:
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                column: _serialize_value(row[column])
                for column in COLUMNS
            })


def _validate_written_csv(expected_rows: list[dict[str, Any]]) -> dict[str, int]:
    with OUTPUT_PATH.open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != list(COLUMNS):
            raise ValueError(
                f"CSV columns differ from the approved order: {reader.fieldnames}"
            )
        read_rows = list(reader)

    if len(read_rows) != 30:
        raise ValueError(f"CSV contains {len(read_rows)} rows instead of 30")
    if len({row["pair_id"] for row in read_rows}) != 30:
        raise ValueError("CSV pair IDs are not unique")
    if any(set(row) & FORBIDDEN_COLUMNS for row in read_rows):
        raise ValueError("CSV contains forbidden label or metadata columns")

    expected_by_pair = {
        row["pair_id"]: {
            column: _serialize_value(row[column])
            for column in COLUMNS
        }
        for row in expected_rows
    }
    for row in read_rows:
        pair_id = row["pair_id"]
        if row != expected_by_pair[pair_id]:
            raise ValueError(f"CSV round-trip mismatch for {pair_id}")
        for feature_name in BOOLEAN_FEATURES:
            if row[feature_name] not in {"", "true", "false"}:
                raise ValueError(
                    f"Invalid boolean serialization for "
                    f"{pair_id}:{feature_name}: {row[feature_name]!r}"
                )
        for feature_name in INTEGER_FEATURES:
            if row[feature_name]:
                try:
                    int(row[feature_name])
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid integer for {pair_id}:{feature_name}"
                    ) from exc
        for feature_name in DECIMAL_FEATURES:
            if row[feature_name]:
                try:
                    parsed = Decimal(row[feature_name])
                except InvalidOperation as exc:
                    raise ValueError(
                        f"Invalid Decimal for {pair_id}:{feature_name}"
                    ) from exc
                if not parsed.is_finite():
                    raise ValueError(
                        f"Non-finite Decimal for {pair_id}:{feature_name}"
                    )
        for feature_name in FLOAT_FEATURES:
            if row[feature_name]:
                try:
                    parsed = float(row[feature_name])
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid float for {pair_id}:{feature_name}"
                    ) from exc
                if not math.isfinite(parsed):
                    raise ValueError(
                        f"Non-finite float for {pair_id}:{feature_name}"
                    )

    missing_counts = {
        feature_name: sum(
            row[feature_name] == ""
            for row in read_rows
        )
        for feature_name in FEATURE_NAMES
    }
    return missing_counts


def generate_predictive_pair_features() -> tuple[int, dict[str, int]]:
    pilot = load_synthetic_pilot(PILOT_DIR)
    rows: list[dict[str, Any]] = []

    for pair_id in sorted(pilot.pairs):
        pair = pilot.pairs[pair_id]
        invoice_features = generate_invoice_pair_features(pair)
        payment_features = generate_payment_pair_features(pair, pilot)
        _validate_feature_keys(invoice_features, payment_features)
        rows.append({
            "pair_id": pair.pair_id,
            **invoice_features,
            **payment_features,
        })

    if {row["pair_id"] for row in rows} != set(pilot.pairs):
        raise ValueError("Generated rows do not cover all loaded pilot pairs")
    _validate_rows(rows)
    _write_csv(rows)
    missing_counts = _validate_written_csv(rows)
    return len(rows), missing_counts


def main() -> int:
    row_count, missing_counts = generate_predictive_pair_features()
    print(f"Generated {row_count} rows at {OUTPUT_PATH}")
    print("Missing values:")
    for feature_name in FEATURE_NAMES:
        print(f"  {feature_name}: {missing_counts[feature_name]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
