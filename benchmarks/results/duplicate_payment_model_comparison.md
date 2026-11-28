# Duplicate-Payment Model Comparison

## Scope

This report compares the saved Logistic Regression and Random Forest experiments for the synthetic duplicate-payment pilot. It is generated from the existing result JSON files and inspected model artifacts without retraining, changing hyperparameters, or re-evaluating the test split for model selection.

All reported precision, recall, F1, and ROC-AUC values use `duplicate` as the positive class.

## 1. Models and selected configurations

### Logistic Regression

- Pipeline: median imputer → standard scaler → regularized Logistic Regression.
- Solver: `liblinear`.
- Random seed: 42.
- Candidate `C`: 0.01, 0.1, 1, and 10.
- Selected `C`: **0.01**.
- Selection metric: validation duplicate-class F1.
- All four candidates had F1 `0.8000`; the documented tie-break selected the smallest C, providing the strongest regularization.

Logistic Regression is a simple, interpretable linear baseline whose coefficients directly represent an additive decision model after scaling.

### Random Forest

- Pipeline: median imputer → Random Forest classifier.
- Selected parameters: `max_depth=2`, `min_samples_leaf=3`, `class_weight=None`.
- Fixed configuration: `n_estimators=100`, `min_samples_split=4`, `max_features="sqrt"`, `bootstrap=True`, `random_state=42`, `n_jobs=1`.
- Selection metric: validation duplicate-class F1 across exactly eight configurations.
- Search dimensions: depth 2/3, minimum leaf size 2/3, and class weight `None`/`"balanced"`.
- All candidates had identical threshold metrics; the deterministic tie-break favored shallower depth, larger minimum leaf size, then no class weighting.

## 2. Dataset

Both models use the same unchanged split files and the same 13 approved predictive features.

| Split | Records | Duplicate | Not duplicate |
|---|---:|---:|---:|
| Train | 9 | 5 | 4 |
| Validation | 10 | 4 | 6 |
| Test | 7 | 4 | 3 |

Four `uncertain` records were excluded from binary training and evaluation. `pair_id`, `label`, and `split_name` were excluded from the predictive matrix.

## 3. Validation comparison

| Model | Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| Majority-class baseline | 0.4000 | 0.4000 | 1.0000 | 0.5714 | — |
| Logistic Regression | 0.8000 | 0.6667 | 1.0000 | 0.8000 | 0.8333 |
| Random Forest | 0.8000 | 0.6667 | 1.0000 | 0.8000 | 0.8958 |

Both learned models produce the same validation predictions and therefore the same threshold-dependent metrics. Random Forest has a higher validation ROC-AUC because its probability ranking differs, not because it makes different hard classifications at the current threshold.

### Validation confusion matrices

Rows are actual labels and columns are predicted labels, ordered `[not_duplicate, duplicate]`.

Both models: `[[4, 2], [0, 4]]`

- True negatives: 4
- False positives: 2
- False negatives: 0
- True positives: 4

Majority-class baseline: `[[0, 6], [0, 4]]`

## 4. Test comparison

| Model | Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| Majority-class baseline | 0.5714 | 0.5714 | 1.0000 | 0.7273 | — |
| Logistic Regression | 0.8571 | 0.8000 | 1.0000 | 0.8889 | **0.6667** |
| Random Forest | 0.8571 | 0.8000 | 1.0000 | 0.8889 | **0.7917** |

Both learned models again produce identical test predictions and threshold metrics. Random Forest's higher ROC-AUC reflects different probability ordering, but the difference cannot establish statistical superiority with only seven test records.

### Test confusion matrices

Both models: `[[2, 1], [0, 4]]`

- True negatives: 2
- False positives: 1
- False negatives: 0
- True positives: 4

Majority-class baseline: `[[0, 3], [0, 4]]`

## 5. Classification reports

### Logistic Regression: validation

| Class/average | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| `not_duplicate` | 1.0000 | 0.6667 | 0.8000 | 6 |
| `duplicate` | 0.6667 | 1.0000 | 0.8000 | 4 |
| Macro average | 0.8333 | 0.8333 | 0.8000 | 10 |
| Weighted average | 0.8667 | 0.8000 | 0.8000 | 10 |

### Logistic Regression: test

| Class/average | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| `not_duplicate` | 1.0000 | 0.6667 | 0.8000 | 3 |
| `duplicate` | 0.8000 | 1.0000 | 0.8889 | 4 |
| Macro average | 0.9000 | 0.8333 | 0.8444 | 7 |
| Weighted average | 0.8857 | 0.8571 | 0.8508 | 7 |

### Random Forest: validation

| Class/average | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| `not_duplicate` | 1.0000 | 0.6667 | 0.8000 | 6 |
| `duplicate` | 0.6667 | 1.0000 | 0.8000 | 4 |
| Macro average | 0.8333 | 0.8333 | 0.8000 | 10 |
| Weighted average | 0.8667 | 0.8000 | 0.8000 | 10 |

### Random Forest: test

| Class/average | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| `not_duplicate` | 1.0000 | 0.6667 | 0.8000 | 3 |
| `duplicate` | 0.8000 | 1.0000 | 0.8889 | 4 |
| Macro average | 0.9000 | 0.8333 | 0.8444 | 7 |
| Weighted average | 0.8857 | 0.8571 | 0.8508 | 7 |

## 6. Error interpretation

A false positive is a `not_duplicate` pair flagged as `duplicate`. On the final test set, each model produced one false positive. In a review workflow, this means one valid/non-duplicate payment pair would require unnecessary duplicate-payment investigation.

A false negative is an actual `duplicate` pair predicted as `not_duplicate`. Neither model produced a false negative on validation or test. Missing duplicates is operationally important for this use case, so this sensitivity is encouraging, but it is based on only four positive test examples and cannot be generalized.

Both models improved accuracy and F1 over the training-majority baseline. The majority baseline predicts every record as duplicate, so its recall is perfect but its false-positive behavior and lack of discrimination make it unsuitable as a predictive model.

## 7. F1 versus ROC-AUC

F1 is threshold-dependent: it combines duplicate-class precision and recall at the classifier's current prediction threshold. Both models have the same F1 because they make the same hard predictions on validation and test.

ROC-AUC is threshold-independent and measures how consistently the model ranks positive examples above negative examples across thresholds. Random Forest ranks the tiny evaluation samples better than Logistic Regression in the saved results, producing higher ROC-AUC on validation and test despite identical hard classifications.

With seven test examples, one reordered prediction can substantially change ROC-AUC. Therefore, the ROC-AUC difference is a preliminary probability-ranking observation, not evidence of stable statistical superiority. The report does not use test metrics for model or hyperparameter selection.

## 8. Algorithm strengths and limitations

### Logistic Regression

**Strengths**

- Simple and interpretable additive decision model.
- Strong regularization is available with small sample sizes.
- Produces continuous probability scores.
- Computationally inexpensive and reproducible.

**Limitations**

- Primarily linear decision boundaries unless interactions are engineered.
- Sensitive to scaling and correlated features.
- Feature coefficients are unstable when samples are scarce.
- Lower saved ROC-AUC than Random Forest on the tiny test split, without a classification advantage.

### Random Forest

**Strengths**

- Can represent nonlinear relationships and interactions without explicit feature transformation.
- Does not require feature scaling.
- Shallow depth and larger leaves reduced model complexity for this experiment.
- Slightly higher ranking performance by validation and test ROC-AUC.

**Limitations**

- Easier to overfit than regularized Logistic Regression when data are scarce.
- More complex and less directly interpretable at the parameter level.
- Feature-importance estimates would be unreliable with nine training observations.
- All eight configurations produced identical threshold metrics, providing little evidence for selecting among its hyperparameters.
- Probability estimates and ROC-AUC can be unstable in a seven-record test set.

## 9. Cautious model-selection conclusion

Neither model has enough evidence to be declared statistically superior. They make identical validation and test classifications and therefore share the same accuracy, precision, recall, F1, and confusion matrices. Random Forest has higher ROC-AUC in the saved results, but the test split contains only seven observations.

For a simple operational baseline, regularized Logistic Regression remains the more parsimonious and interpretable default. Random Forest is a useful nonlinear comparison, but its ranking advantage should be treated as preliminary and unconfirmed. A future decision should require substantially more representative data, repeated or confidence-interval evaluation, and untouched real-world validation evidence.

These results demonstrate feasibility on a very small synthetic pilot only. They do not establish generalization, calibration, or production-level performance.

## Verification

All reported aggregate metrics, classification reports, confusion matrices, selected configurations, feature counts, and split counts were checked against:

- `duplicate_payment_logistic_regression_results.json`
- `duplicate_payment_random_forest_results.json`

The saved Logistic Regression test ROC-AUC is `0.6667`; the saved Random Forest test ROC-AUC is `0.7917`. Neither model nor either results file was modified or retrained for this report.
