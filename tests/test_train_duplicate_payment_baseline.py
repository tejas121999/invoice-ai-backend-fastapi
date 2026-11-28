import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.prepare_duplicate_payment_ml_datasets import FEATURE_COLUMNS
from scripts.train_duplicate_payment_baseline import (
    build_model,
    evaluate_majority_baseline,
    evaluate_model,
    load_split,
    prepare_features,
    select_model,
)


SPLIT_COLUMNS = ("pair_id", "label", "split_name", *FEATURE_COLUMNS)


class BaselineModelTests(unittest.TestCase):
    def make_frame(self, split_name: str, count: int = 6) -> pd.DataFrame:
        rows = []
        for index in range(count):
            rows.append({
                "pair_id": f"PAIR-{index:04d}",
                "label": "duplicate" if index % 2 == 0 else "not_duplicate",
                "split_name": split_name,
                **{
                    feature: float(index + feature_index)
                    for feature_index, feature in enumerate(FEATURE_COLUMNS)
                },
                "exactAmountMatch": index % 2 == 0,
                "currencyMatch": True,
                "paidAmountMatch": None if index == 0 else index % 2 == 0,
                "samePaymentRun": index % 2 == 0,
            })
        return pd.DataFrame(rows, columns=SPLIT_COLUMNS)

    def test_prepares_boolean_features_without_imputing(self):
        frame = self.make_frame("train")
        features, target = prepare_features(frame)

        self.assertEqual(tuple(features.columns), FEATURE_COLUMNS)
        self.assertEqual(features["exactAmountMatch"].tolist(), [1, 0, 1, 0, 1, 0])
        self.assertTrue(np.isnan(features.loc[0, "paidAmountMatch"]))
        self.assertEqual(target.tolist(), [1, 0, 1, 0, 1, 0])
        self.assertNotIn("pair_id", features)
        self.assertNotIn("label", features)
        self.assertNotIn("split_name", features)

    def test_pipeline_fits_imputer_on_training_data_only(self):
        train = self.make_frame("train")
        validation = self.make_frame("validation")
        x_train, y_train = prepare_features(train)
        x_validation, y_validation = prepare_features(validation)
        expected_median = x_train["paidAmountMatch"].median()

        model = build_model(1.0)
        model.fit(x_train, y_train)
        fitted_imputer = model.named_steps["imputer"]

        self.assertEqual(
            fitted_imputer.statistics_[FEATURE_COLUMNS.index("paidAmountMatch")],
            expected_median,
        )
        imputer_before = fitted_imputer.statistics_.copy()
        model.predict(x_validation)
        self.assertTrue(np.array_equal(fitted_imputer.statistics_, imputer_before))

    def test_model_selection_and_evaluation_are_deterministic(self):
        train = self.make_frame("train")
        validation = self.make_frame("validation")
        x_train, y_train = prepare_features(train)
        x_validation, y_validation = prepare_features(validation)

        first_model, first = select_model(
            x_train,
            y_train,
            x_validation,
            y_validation,
        )
        second_model, second = select_model(
            x_train,
            y_train,
            x_validation,
            y_validation,
        )

        self.assertEqual(first, second)
        self.assertEqual(
            first_model.named_steps["classifier"].C,
            second_model.named_steps["classifier"].C,
        )
        metrics = evaluate_model(first_model, x_validation, y_validation)
        self.assertEqual(metrics["confusion_matrix"], [[3, 0], [0, 3]])
        self.assertIn("classification_report", metrics)

    def test_majority_baseline_uses_training_label_only(self):
        train_target = pd.Series([1, 1, 1, 0])
        evaluation_target = pd.Series([0, 0, 1])

        metrics = evaluate_majority_baseline(train_target, evaluation_target)

        self.assertEqual(metrics["majority_class"], "duplicate")
        self.assertEqual(metrics["confusion_matrix"], [[0, 2], [0, 1]])

    def test_load_split_rejects_invalid_schema_and_split(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            path = Path(temp_directory) / "train.csv"
            frame = self.make_frame("test")
            frame.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "outside split"):
                load_split(path, "train")

            frame = self.make_frame("train")
            frame.drop(columns=["partialPaymentRatio"]).to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "columns differ"):
                load_split(path, "train")


if __name__ == "__main__":
    unittest.main()
