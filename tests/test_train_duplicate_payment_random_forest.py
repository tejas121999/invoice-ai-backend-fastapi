import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd

from scripts.prepare_duplicate_payment_ml_datasets import FEATURE_COLUMNS
from scripts.train_duplicate_payment_random_forest import (
    SEARCH_SPACE,
    build_model,
    candidate_rank,
    select_model,
)
from scripts.train_duplicate_payment_baseline import prepare_features


class RandomForestBaselineTests(unittest.TestCase):
    def make_frame(self, split_name: str, count: int = 8) -> pd.DataFrame:
        rows = []
        for index in range(count):
            rows.append({
                "pair_id": f"PAIR-{index:04d}",
                "label": "duplicate" if index < count // 2 else "not_duplicate",
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
        return pd.DataFrame(rows)

    def test_uses_exactly_thirteen_features_and_handles_missing_booleans(self):
        features, target = prepare_features(self.make_frame("train"))

        self.assertEqual(tuple(features.columns), FEATURE_COLUMNS)
        self.assertEqual(len(features.columns), 13)
        self.assertNotIn("pair_id", features)
        self.assertNotIn("label", features)
        self.assertNotIn("split_name", features)
        self.assertTrue(np.isnan(features.loc[0, "paidAmountMatch"]))
        self.assertEqual(features.loc[0, "exactAmountMatch"], 1.0)
        self.assertEqual(set(target), {0, 1})

    def test_pipeline_has_imputer_and_forest_without_scaler(self):
        model = build_model(2, 2, None)

        self.assertEqual(list(model.named_steps), ["imputer", "classifier"])
        classifier = model.named_steps["classifier"]
        self.assertEqual(classifier.n_estimators, 100)
        self.assertEqual(classifier.min_samples_split, 4)
        self.assertEqual(classifier.max_features, "sqrt")
        self.assertTrue(classifier.bootstrap)
        self.assertEqual(classifier.random_state, 42)
        self.assertEqual(classifier.n_jobs, 1)

    def test_imputer_is_fitted_on_training_and_not_refitted_on_validation(self):
        train = self.make_frame("train")
        validation = self.make_frame("validation")
        x_train, y_train = prepare_features(train)
        x_validation, _ = prepare_features(validation)
        expected_median = x_train["paidAmountMatch"].median()
        model = build_model(2, 2, None)
        model.fit(x_train, y_train)
        imputer = model.named_steps["imputer"]

        self.assertEqual(
            imputer.statistics_[FEATURE_COLUMNS.index("paidAmountMatch")],
            expected_median,
        )
        statistics_before = imputer.statistics_.copy()
        model.predict(x_validation)
        self.assertTrue(np.array_equal(imputer.statistics_, statistics_before))

    def test_evaluates_exactly_eight_configurations_deterministically(self):
        train = self.make_frame("train")
        validation = self.make_frame("validation")
        x_train, y_train = prepare_features(train)
        x_validation, y_validation = prepare_features(validation)

        with patch(
            "scripts.train_duplicate_payment_random_forest.evaluate_model",
            wraps=__import__(
                "scripts.train_duplicate_payment_random_forest",
                fromlist=["evaluate_model"],
            ).evaluate_model,
        ) as evaluate:
            first_model, first = select_model(
                x_train,
                y_train,
                x_validation,
                y_validation,
            )
        self.assertEqual(len(SEARCH_SPACE), 8)
        self.assertEqual(evaluate.call_count, 8)
        self.assertEqual(first["evaluated_candidates"], 8)

        second_model, second = select_model(
            x_train,
            y_train,
            x_validation,
            y_validation,
        )
        self.assertEqual(first, second)
        self.assertEqual(
            first_model.named_steps["classifier"].get_params(),
            second_model.named_steps["classifier"].get_params(),
        )

    def test_tie_break_prefers_shallow_leafy_unweighted_model(self):
        worse_depth = {
            "f1": 0.8,
            "max_depth": 3,
            "min_samples_leaf": 3,
            "class_weight": None,
        }
        shallower = {
            "f1": 0.8,
            "max_depth": 2,
            "min_samples_leaf": 2,
            "class_weight": "balanced",
        }
        larger_leaf = {
            "f1": 0.8,
            "max_depth": 2,
            "min_samples_leaf": 3,
            "class_weight": "balanced",
        }
        unweighted = {
            "f1": 0.8,
            "max_depth": 2,
            "min_samples_leaf": 3,
            "class_weight": None,
        }

        self.assertGreater(candidate_rank(shallower), candidate_rank(worse_depth))
        self.assertGreater(candidate_rank(larger_leaf), candidate_rank(shallower))
        self.assertGreater(candidate_rank(unweighted), candidate_rank(larger_leaf))

    def test_saved_artifact_contains_complete_fitted_pipeline(self):
        train = self.make_frame("train")
        x_train, y_train = prepare_features(train)
        model = build_model(2, 3, None).fit(x_train, y_train)

        with tempfile.TemporaryDirectory() as temp_directory:
            model_path = Path(temp_directory) / "model.joblib"
            joblib.dump(model, model_path)
            restored = joblib.load(model_path)

        self.assertEqual(list(restored.named_steps), ["imputer", "classifier"])
        self.assertTrue(hasattr(restored.named_steps["imputer"], "statistics_"))
        self.assertTrue(hasattr(restored.named_steps["classifier"], "estimators_"))
        self.assertEqual(len(restored.feature_names_in_), 13)

    def test_test_data_is_not_available_to_selection(self):
        train = self.make_frame("train")
        validation = self.make_frame("validation")
        x_train, y_train = prepare_features(train)
        x_validation, y_validation = prepare_features(validation)

        _, selection = select_model(
            x_train,
            y_train,
            x_validation,
            y_validation,
        )

        self.assertEqual(set(selection), {
            "selection_metric",
            "evaluated_candidates",
            "tie_break_order",
            "selected_parameters",
            "candidates",
        })
        for candidate in selection["candidates"]:
            self.assertNotIn("test_accuracy", candidate)
            self.assertNotIn("test_f1", candidate)


if __name__ == "__main__":
    unittest.main()
