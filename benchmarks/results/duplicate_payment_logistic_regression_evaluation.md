# Logistic Regression Baseline Evaluation

## Scope and reproducibility

This report describes the saved first baseline for the synthetic duplicate-payment pilot. It was produced from the existing saved results and model metadata without retraining or modifying the model, hyperparameters, datasets, or feature engineering.

Source artifacts:

- Model: `duplicate_payment_logistic_regression.joblib`
- Metrics: `duplicate_payment_logistic_regression_results.json`
- Training implementation: `scripts/train_duplicate_payment_baseline.py`
- Prepared data: `data/synthetic/duplicate_payment_pilot/prepared/`

Random seed: **42**.

## 1. Model overview

The baseline is regularized binary Logistic Regression with the `liblinear` solver. Logistic Regression is appropriate as a first baseline because it is simple, interpretable, regularized, and able to provide class probabilities from a small tabular feature set.

The target encoding is:

- `not_duplicate` = `0`
- `duplicate` = `1` (**positive class**)

Accordingly, all reported precision, recall, F1, and ROC-AUC values treat `duplicate` as the positive class.

This is a feasibility baseline, not a production-ready model or evidence of production-level accuracy.

## 2. Dataset overview

The binary pilot contains 26 records:

| Split | Records | Duplicate | Not duplicate |
|---|---:|---:|---:|
| Training | 9 | 5 | 4 |
| Validation | 10 | 4 | 6 |
| Test | 7 | 4 | 3 |

Four `uncertain` records were excluded from binary training and evaluation while remaining unchanged in the source data.

Exactly 13 predictive features were used:

1. `vendorSimilarity`
2. `invoiceNumberSimilarity`
3. `exactAmountMatch`
4. `amountDifference`
5. `amountSimilarity`
6. `dateDifferenceDays`
7. `currencyMatch`
8. `paymentTermsSimilarity`
9. `paidAmountMatch`
10. `paidAmountSimilarity`
11. `paymentReferenceSimilarity`
12. `samePaymentRun`
13. `partialPaymentRatio`

`pair_id`, `label`, and `split_name` are not model inputs. The label is used only as the target, while the pair ID and split assignment remain metadata.

## 3. Preprocessing

The saved artifact is a fitted scikit-learn `Pipeline` with these ordered steps:

1. **Boolean normalization:** `true`/`1` becomes `1.0`, `false`/`0` becomes `0.0`, and missing boolean evidence remains `NaN` until imputation.
2. **Median imputation:** `SimpleImputer(strategy="median", keep_empty_features=True)`.
3. **Standardization:** `StandardScaler`.
4. **Classification:** regularized `LogisticRegression`.

The imputer and scaler were fitted through pipeline fitting on the **9 training records only**. Validation and test records were transformed with the fitted training statistics and were not used to refit preprocessing. The saved pipeline contains the fitted imputer statistics, scaler means/scales, and classifier coefficients.

## 4. Hyperparameter selection

Candidate regularization values:

- `C = 0.01`
- `C = 0.1`
- `C = 1`
- `C = 10`

Selection metric: validation F1 for the positive class (`duplicate`). All four candidates produced the same validation F1 of `0.8000` and the same other reported validation metrics. The documented tie-break ranks candidates by F1 and then favors the smaller C through `-C`, selecting the strongest regularization:

**Selected C: `0.01`.**

The selected model was then evaluated on the test split. Test data was not used for C selection or preprocessing fitting.

## 5. Evaluation results

### Summary metrics

| Split | Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| Validation | 0.8000 | 0.6667 | 1.0000 | 0.8000 | 0.8333 |
| Test | 0.8571 | 0.8000 | 1.0000 | 0.8889 | **0.6667** |

The ROC-AUC values carry the saved warning that they are unstable because the evaluation splits are very small. In particular, test ROC-AUC uses only seven observations.

### Validation classification report

| Class / average | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| `not_duplicate` | 1.0000 | 0.6667 | 0.8000 | 6 |
| `duplicate` | 0.6667 | 1.0000 | 0.8000 | 4 |
| Macro average | 0.8333 | 0.8333 | 0.8000 | 10 |
| Weighted average | 0.8667 | 0.8000 | 0.8000 | 10 |

Validation accuracy: **0.8000**.

### Test classification report

| Class / average | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| `not_duplicate` | 1.0000 | 0.6667 | 0.8000 | 3 |
| `duplicate` | 0.8000 | 1.0000 | 0.8889 | 4 |
| Macro average | 0.9000 | 0.8333 | 0.8444 | 7 |
| Weighted average | 0.8857 | 0.8571 | 0.8508 | 7 |

Test accuracy: **0.8571**.

### Confusion matrices

Rows are actual labels and columns are predicted labels, ordered as `[not_duplicate, duplicate]`.

**Validation**

```text
                         Predicted
                    not_duplicate  duplicate
Actual not_duplicate       4           2
Actual duplicate           0           4
```

Matrix: `[[4, 2], [0, 4]]`

- True negatives: 4
- False positives: 2
- False negatives: 0
- True positives: 4

**Test**

```text
                         Predicted
                    not_duplicate  duplicate
Actual not_duplicate       2           1
Actual duplicate           0           4
```

Matrix: `[[2, 1], [0, 4]]`

- True negatives: 2
- False positives: 1
- False negatives: 0
- True positives: 4

## 6. Interpretation

### Validation

The model correctly classified 8 of 10 validation pairs. It identified all 4 duplicate pairs and did not miss any duplicate, producing recall of 1.0000. It incorrectly flagged 2 of 6 non-duplicate pairs as duplicates, which limits duplicate-class precision to 0.6667. The result favors duplicate detection sensitivity at the cost of additional false-positive review work.

### Test

The model correctly classified 6 of 7 test pairs. It again identified all 4 duplicate pairs with no false negatives. One of 3 non-duplicate pairs was incorrectly classified as duplicate. Test duplicate-class precision is therefore 0.8000, while recall remains 1.0000.

The lower test ROC-AUC of 0.6667 indicates that ranking/separation of probability scores is weaker than the final thresholded predictions suggest. Because the test set has only 7 records, one changed probability ranking can materially alter ROC-AUC.

### Majority-class comparison

The training majority class is `duplicate`.

| Split | Accuracy | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| Validation majority baseline | 0.4000 | 0.4000 | 1.0000 | 0.5714 |
| Test majority baseline | 0.5714 | 0.5714 | 1.0000 | 0.7273 |

The logistic model improves accuracy and F1 on both splits. However, the majority baseline's recall is also 1.0000 because it predicts every pair as duplicate; it provides no useful discrimination between classes. Its confusion matrices are `[[0, 6], [0, 4]]` for validation and `[[0, 3], [0, 4]]` for test.

## 7. Limitations

- The model was fitted with only **9 training records**.
- The held-out test set contains only **7 records**.
- There are **13 features**, a large feature count relative to the training sample.
- The pilot is synthetic rather than a representative real ERP/payment-history population.
- Validation and test class metrics have wide uncertainty due to sample size.
- Candidate C values produced identical validation results, so the observed preference for `C=0.01` is a deterministic tie-break rather than evidence of a meaningful performance difference.
- ROC-AUC is especially unstable for the small splits.
- These metrics are preliminary feasibility results and do not demonstrate generalization, robustness, calibration, or production-level performance.

## Verification statement

The report metrics, classification reports, confusion matrices, selected C, feature list, and record counts match the saved results JSON. The saved joblib artifact was inspected without retraining and contains one complete fitted pipeline with median imputation, scaling, and Logistic Regression.
