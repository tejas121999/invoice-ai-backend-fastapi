"""Train and evaluate a logistic-regression baseline on the prepared pilot."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.base import ClassifierMixin
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.prepare_duplicate_payment_ml_datasets import FEATURE_COLUMNS
PREPARED_DIR = (
    PROJECT_ROOT
    / "data"
    / "synthetic"
    / "duplicate_payment_pilot"
    / "prepared"
)
RESULTS_DIR = PROJECT_ROOT / "benchmarks" / "results"
MODEL_PATH = RESULTS_DIR / "duplicate_payment_logistic_regression.joblib"
RESULTS_PATH = RESULTS_DIR / "duplicate_payment_logistic_regression_results.json"
RANDOM_SEED = 42
C_VALUES = (0.01, 0.1, 1.0, 10.0)
SPLIT_COLUMNS = ("pair_id", "label", "split_name", *FEATURE_COLUMNS)
BOOLEAN_FEATURES = {
    "exactAmountMatch",
    "currencyMatch",
    "paidAmountMatch",
    "samePaymentRun",
}


def load_split(path: Path, expected_split: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if tuple(frame.columns) != SPLIT_COLUMNS:
        raise ValueError(
            f"{path} columns differ from the approved prepared schema: "
            f"expected={list(SPLIT_COLUMNS)}, actual={list(frame.columns)}"
        )
    if not frame["pair_id"].is_unique:
        raise ValueError(f"{path} contains duplicate pair_id values")
    if frame["split_name"].ne(expected_split).any():
        raise ValueError(
            f"{path} contains rows outside split {expected_split!r}"
        )
    invalid_labels = set(frame["label"].dropna()) - {
        "duplicate",
        "not_duplicate",
    }
    if invalid_labels:
        raise ValueError(f"{path} contains invalid labels: {sorted(invalid_labels)}")
    if frame["label"].isna().any():
        raise ValueError(f"{path} contains missing labels")
    return frame


def prepare_features(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    feature_frame = frame.loc[:, FEATURE_COLUMNS].copy()
    for feature_name in BOOLEAN_FEATURES:
        normalized = feature_frame[feature_name].astype("string").str.lower()
        feature_frame[feature_name] = normalized.map({
            "true": 1.0,
            "false": 0.0,
            "1": 1.0,
            "0": 0.0,
        }).astype("float64")

    numeric_columns = [
        feature_name
        for feature_name in FEATURE_COLUMNS
        if feature_name not in BOOLEAN_FEATURES
    ]
    feature_frame[numeric_columns] = feature_frame[numeric_columns].apply(
        pd.to_numeric,
        errors="raise",
    )
    target = frame["label"].map({
        "not_duplicate": 0,
        "duplicate": 1,
    }).astype("int64")
    return feature_frame, target


def build_model(c_value: float) -> Pipeline:
    return Pipeline([
        (
            "imputer",
            SimpleImputer(strategy="median", keep_empty_features=True),
        ),
        ("scaler", StandardScaler()),
        (
            "classifier",
            LogisticRegression(
                C=c_value,
                max_iter=1000,
                random_state=RANDOM_SEED,
                solver="liblinear",
            ),
        ),
    ])


def evaluate_model(
    model: ClassifierMixin,
    x: pd.DataFrame,
    y: pd.Series,
) -> dict[str, Any]:
    predictions = model.predict(x)
    metrics: dict[str, Any] = {
        "accuracy": float(accuracy_score(y, predictions)),
        "precision": float(precision_score(y, predictions, zero_division=0)),
        "recall": float(recall_score(y, predictions, zero_division=0)),
        "f1": float(f1_score(y, predictions, zero_division=0)),
        "confusion_matrix": confusion_matrix(
            y,
            predictions,
            labels=[0, 1],
        ).tolist(),
        "classification_report": classification_report(
            y,
            predictions,
            labels=[0, 1],
            target_names=["not_duplicate", "duplicate"],
            output_dict=True,
            zero_division=0,
        ),
    }

    if hasattr(model, "predict_proba") and y.nunique() == 2:
        metrics["roc_auc"] = float(
            roc_auc_score(y, model.predict_proba(x)[:, 1])
        )
        metrics["roc_auc_warning"] = (
            "ROC-AUC is unstable for this very small evaluation split."
        )
    else:
        metrics["roc_auc"] = None
        metrics["roc_auc_warning"] = (
            "ROC-AUC unavailable because probability scores or both "
            "classes are missing."
        )
    return metrics


def select_model(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    x_validation: pd.DataFrame,
    y_validation: pd.Series,
) -> tuple[Pipeline, dict[str, Any]]:
    candidate_results = []
    selected_model: Pipeline | None = None
    selected_result: dict[str, Any] | None = None
    for c_value in C_VALUES:
        model = build_model(c_value)
        model.fit(x_train, y_train)
        metrics = evaluate_model(model, x_validation, y_validation)
        result = {"C": c_value, **metrics}
        candidate_results.append(result)
        candidate_rank = (result["f1"], -c_value)
        selected_rank = (
            (selected_result["f1"], -selected_result["C"])
            if selected_result is not None
            else (-1.0, -float("inf"))
        )
        if candidate_rank > selected_rank:
            selected_model = model
            selected_result = result

    if selected_model is None:
        raise RuntimeError("No logistic regression candidate was evaluated")
    return selected_model, {
        "selection_metric": "validation_f1",
        "selected_C": selected_model.named_steps["classifier"].C,
        "candidates": candidate_results,
    }


def evaluate_majority_baseline(
    y_train: pd.Series,
    y: pd.Series,
) -> dict[str, Any]:
    majority_class = int(y_train.value_counts().idxmax())
    class MajorityClassifier:
        def predict(self, x: pd.DataFrame) -> list[int]:
            return [majority_class] * len(x)

    predictions = MajorityClassifier().predict(pd.DataFrame(index=y.index))
    return {
        "strategy": "training_majority_class",
        "majority_class": (
            "duplicate" if majority_class == 1 else "not_duplicate"
        ),
        "accuracy": float(accuracy_score(y, predictions)),
        "precision": float(precision_score(y, predictions, zero_division=0)),
        "recall": float(recall_score(y, predictions, zero_division=0)),
        "f1": float(f1_score(y, predictions, zero_division=0)),
        "confusion_matrix": confusion_matrix(
            y,
            predictions,
            labels=[0, 1],
        ).tolist(),
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
        "logistic_regression": {
            "validation": validation_metrics,
            "test": test_metrics,
        },
        "limitations": [
            "The pilot contains only 26 binary examples across 13 features.",
            "Metrics are descriptive and do not demonstrate production-level accuracy.",
            "The test split is very small; ROC-AUC is unstable.",
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
