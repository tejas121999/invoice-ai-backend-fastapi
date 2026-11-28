"""Train and evaluate a conservative Random Forest comparison model."""

from __future__ import annotations

import json
import sys
from itertools import product
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.prepare_duplicate_payment_ml_datasets import FEATURE_COLUMNS
from scripts.train_duplicate_payment_baseline import (
    RANDOM_SEED,
    evaluate_majority_baseline,
    evaluate_model,
    load_split,
    prepare_features,
)


PREPARED_DIR = (
    PROJECT_ROOT
    / "data"
    / "synthetic"
    / "duplicate_payment_pilot"
    / "prepared"
)
RESULTS_DIR = PROJECT_ROOT / "benchmarks" / "results"
MODEL_PATH = RESULTS_DIR / "duplicate_payment_random_forest.joblib"
RESULTS_PATH = RESULTS_DIR / "duplicate_payment_random_forest_results.json"
SEARCH_SPACE = tuple(product((2, 3), (2, 3), (None, "balanced")))


def candidate_rank(result: dict[str, Any]) -> tuple[float, int, int, int]:
    return (
        result["f1"],
        -result["max_depth"],
        result["min_samples_leaf"],
        1 if result["class_weight"] is None else 0,
    )


def build_model(
    max_depth: int,
    min_samples_leaf: int,
    class_weight: str | None,
) -> Pipeline:
    return Pipeline([
        (
            "imputer",
            SimpleImputer(strategy="median", keep_empty_features=True),
        ),
        (
            "classifier",
            RandomForestClassifier(
                n_estimators=100,
                min_samples_split=4,
                max_features="sqrt",
                bootstrap=True,
                random_state=RANDOM_SEED,
                n_jobs=1,
                max_depth=max_depth,
                min_samples_leaf=min_samples_leaf,
                class_weight=class_weight,
            ),
        ),
    ])


def select_model(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    x_validation: pd.DataFrame,
    y_validation: pd.Series,
) -> tuple[Pipeline, dict[str, Any]]:
    candidate_results: list[dict[str, Any]] = []
    selected_model: Pipeline | None = None
    selected_result: dict[str, Any] | None = None

    for max_depth, min_samples_leaf, class_weight in SEARCH_SPACE:
        model = build_model(
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            class_weight=class_weight,
        )
        model.fit(x_train, y_train)
        metrics = evaluate_model(model, x_validation, y_validation)
        result = {
            "max_depth": max_depth,
            "min_samples_leaf": min_samples_leaf,
            "class_weight": class_weight,
            **metrics,
        }
        candidate_results.append(result)
        if (
            selected_result is None
            or candidate_rank(result) > candidate_rank(selected_result)
        ):
            selected_model = model
            selected_result = result

    if selected_model is None or selected_result is None:
        raise RuntimeError("No Random Forest candidate was evaluated")
    return selected_model, {
        "selection_metric": "validation_duplicate_f1",
        "evaluated_candidates": len(candidate_results),
        "tie_break_order": [
            "shallower max_depth",
            "larger min_samples_leaf",
            "class_weight=None",
        ],
        "selected_parameters": {
            "max_depth": selected_result["max_depth"],
            "min_samples_leaf": selected_result["min_samples_leaf"],
            "class_weight": selected_result["class_weight"],
            "n_estimators": 100,
            "min_samples_split": 4,
            "max_features": "sqrt",
            "bootstrap": True,
            "random_state": RANDOM_SEED,
            "n_jobs": 1,
        },
        "candidates": candidate_results,
    }


def train_and_evaluate(
    train_path: Path = PREPARED_DIR / "binary_train.csv",
    validation_path: Path = PREPARED_DIR / "binary_validation.csv",
    test_path: Path = PREPARED_DIR / "binary_test.csv",
) -> tuple[Pipeline, dict[str, Any]]:
    train = load_split(train_path, "train")
    validation = load_split(validation_path, "validation")
    x_train, y_train = prepare_features(train)
    x_validation, y_validation = prepare_features(validation)

    model, selection = select_model(
        x_train,
        y_train,
        x_validation,
        y_validation,
    )
    validation_metrics = evaluate_model(model, x_validation, y_validation)
    validation_majority = evaluate_majority_baseline(y_train, y_validation)

    test = load_split(test_path, "test")
    x_test, y_test = prepare_features(test)
    test_metrics = evaluate_model(model, x_test, y_test)
    test_majority = evaluate_majority_baseline(y_train, y_test)

    results = {
        "random_seed": RANDOM_SEED,
        "feature_columns": list(FEATURE_COLUMNS),
        "train_records": len(train),
        "validation_records": len(validation),
        "test_records": len(test),
        "model_selection": selection,
        "majority_baseline": {
            "validation": validation_majority,
            "test": test_majority,
        },
        "random_forest": {
            "validation": validation_metrics,
            "test": test_metrics,
        },
        "limitations": [
            "The pilot contains only 26 binary examples across 13 features.",
            "Validation-based hyperparameter selection is unstable on 10 records.",
            "The test split contains only seven records; ROC-AUC is unstable.",
            "Metrics are descriptive and do not demonstrate production-level accuracy.",
        ],
    }
    return model, results


def save_artifacts(model: Pipeline, results: dict[str, Any]) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    RESULTS_PATH.write_text(
        json.dumps(results, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    model, results = train_and_evaluate()
    save_artifacts(model, results)
    print(json.dumps(results, indent=2))
    print(f"Model artifact: {MODEL_PATH}")
    print(f"Results artifact: {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
