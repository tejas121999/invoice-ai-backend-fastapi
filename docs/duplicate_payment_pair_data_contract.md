# Duplicate Payment Pair Data Contract

## Purpose

This contract defines the minimum pair-level fields required to construct,
adjudicate and feature-engineer duplicate-payment candidates in the thesis
project.

The contract describes a logical data exchange. It does not require database
tables, migrations or API changes.

## Prediction unit

Each pair represents:

```text
Two invoice-payment allocations that may settle the same underlying
invoice obligation.
```

The pair must retain references to both invoices and, where available,
both associated payments and allocations.

## Identifier and provenance fields

| Field | Type | Availability | Required | Notes |
|---|---|---|---|---|
| `pair_id` | string/UUID | Derived | Yes | Stable pair identifier |
| `invoice_id_a` | integer/UUID | Available: `Invoice.id` | Yes | First invoice |
| `invoice_id_b` | integer/UUID | Available/Generated | Yes | Second invoice |
| `extraction_id_a` | integer | Available: `ExtractedInvoiceData.id` | If available | First extraction |
| `extraction_id_b` | integer | Available/Generated | If available | Second extraction |
| `payment_id_a` | string/UUID | New/Synthetic | Required for a non-uncertain adjudication | First payment |
| `payment_id_b` | string/UUID | New/Synthetic | Required for a non-uncertain adjudication | Second payment |
| `allocation_id_a` | string/UUID | New/Synthetic | Required for a non-uncertain adjudication | First allocation |
| `allocation_id_b` | string/UUID | New/Synthetic | Required for a non-uncertain adjudication | Second allocation |
| `dataset_version` | string | New/Synthetic | Yes | Reproducibility |
| `pair_created_at` | timestamp | Derived | Yes | Candidate construction time |

Existing invoice and extraction identifiers already provide stable linkage
for invoice pairs. Payment identifiers are absent and must be supplied or
generated. A candidate with missing payment or allocation identifiers may
exist for construction and OCR review, but it should be labelled
`uncertain` until payment evidence is sufficient.

## Supplier fields

| Field | Type | Availability | Required | Notes |
|---|---|---|---|---|
| `supplier_id_a` | string/UUID | New/Synthetic | Yes | Stable supplier ID |
| `supplier_id_b` | string/UUID | New/Synthetic | Yes | Stable supplier ID |
| `vendor_name_a` | string | Available: `vendorName` | Yes | Extracted/reviewed vendor |
| `vendor_name_b` | string | Available: `vendorName` | Yes | Extracted/reviewed vendor |
| `vendor_name_reviewed_a` | string, nullable | Available: `reviewedFieldsJson.vendorName` | No | Human-corrected vendor |
| `vendor_name_reviewed_b` | string, nullable | Available: `reviewedFieldsJson.vendorName` | No | Human-corrected vendor |

For synthetic or anonymised data, `supplier_id_a` and `supplier_id_b` are
the primary identity fields. Vendor names are text features and must not
replace a stable supplier ID. The supplier ID must be used only as an
entity-linking and candidate-blocking field, not as the label shortcut:
two invoices sharing a supplier are not duplicate without settlement and
adjudication evidence.

## Invoice fields

| Field | Type | Availability | Required | Notes |
|---|---|---|---|---|
| `invoice_number_a` | string | Available: `invoiceNumber` | Yes | OCR/review value |
| `invoice_number_b` | string | Available: `invoiceNumber` | Yes | OCR/review value |
| `invoice_date_a` | date | Available: `invoiceDate` | If supported | Source invoice date |
| `invoice_date_b` | date | Available: `invoiceDate` | If supported | Source invoice date |
| `due_date_a` | date | Available: `dueDate` | No | Existing dynamic/scalar field |
| `due_date_b` | date | Available: `dueDate` | No | Existing dynamic/scalar field |
| `subtotal_a` | decimal(14,2) | Available: `subtotal` | No | Existing extraction |
| `subtotal_b` | decimal(14,2) | Available: `subtotal` | No | Existing extraction |
| `tax_amount_a` | decimal(14,2) | Available: `taxAmount` | No | Existing extraction |
| `tax_amount_b` | decimal(14,2) | Available: `taxAmount` | No | Existing extraction |
| `total_amount_a` | decimal(14,2) | Available: `totalAmount` | Yes | Primary amount |
| `total_amount_b` | decimal(14,2) | Available: `totalAmount` | Yes | Primary amount |
| `currency_a` | ISO-style string | Available: `currency` | Yes | Existing currency |
| `currency_b` | ISO-style string | Available: `currency` | Yes | Existing currency |
| `payment_terms_a` | string | Available: `extractedFieldsJson.paymentTerms` | No | Dynamic extraction |
| `payment_terms_b` | string | Available: `extractedFieldsJson.paymentTerms` | No | Dynamic extraction |
| `po_number_a` | string | Available: `extractedFieldsJson.poNumber` | No | Optional reference |
| `po_number_b` | string | Available: `extractedFieldsJson.poNumber` | No | Optional reference |
| `vendor_gst_a` | string | Available: `extractedFieldsJson.vendorGst` | No | Optional masked identity |
| `vendor_gst_b` | string | Available: `extractedFieldsJson.vendorGst` | No | Optional masked identity |
| `raw_text_a` | text | Available: `Invoice.rawText` | No | Adjudication evidence |
| `raw_text_b` | text | Available: `Invoice.rawText` | No | Adjudication evidence |
| `source_file_a` | string | Available: `fileName`/`filePath` | Yes | Document provenance |
| `source_file_b` | string | Available/Generated | Yes | Document provenance |

For human adjudication, raw text and source documents are evidence fields,
not predictive features.

## Review and OCR quality fields

| Field | Type | Availability | Required | Notes |
|---|---|---|---|---|
| `is_reviewed_a` | boolean | Available: `isReviewed` | Yes | Extraction review state |
| `is_reviewed_b` | boolean | Available/Generated | Yes | Extraction review state |
| `reviewed_fields_a` | JSON | Available: `reviewedFieldsJson` | No | Human corrections |
| `reviewed_fields_b` | JSON | Available/Generated | No | Human corrections |
| `confidence_json_a` | JSON | Available: `confidenceJson` | No | Field confidences |
| `confidence_json_b` | JSON | Available/Generated | No | Field confidences |
| `average_confidence_a` | float 0–1 | Derived | No | Optional quality feature |
| `average_confidence_b` | float 0–1 | Derived | No | Optional quality feature |
| `ocr_error_profile_a` | string/JSON | Generated/New | No | Synthetic corruption metadata |
| `ocr_error_profile_b` | string/JSON | Generated/New | No | Synthetic corruption metadata |

OCR confidence can be used as a data-quality feature. It must not be used
as a duplicate-payment label.

## Payment and allocation fields

| Field | Type | Availability | Required | Notes |
|---|---|---|---|---|
| `payment_date_a` | date | New/Synthetic | Conditional | First payment date |
| `payment_date_b` | date | New/Synthetic | Conditional | Second payment date |
| `paid_amount_a` | decimal(14,2) | New/Synthetic | Conditional | Actual payment amount |
| `paid_amount_b` | decimal(14,2) | New/Synthetic | Conditional | Actual payment amount |
| `payment_currency_a` | string | New/Synthetic | Conditional | Payment currency |
| `payment_currency_b` | string | New/Synthetic | Conditional | Payment currency |
| `payment_reference_a` | string | New/Synthetic | Conditional | Transaction/reference |
| `payment_reference_b` | string | New/Synthetic | Conditional | Transaction/reference |
| `bank_transaction_id_masked_a` | string | New/Synthetic | No | Masked identifier |
| `bank_transaction_id_masked_b` | string | New/Synthetic | No | Masked identifier |
| `payment_status_a` | enum | New/Synthetic | Conditional | `paid`, `cancelled`, `reversed`, `refunded`, `pending` |
| `payment_status_b` | enum | New/Synthetic | Conditional | `paid`, `cancelled`, `reversed`, `refunded`, `pending` |
| `payment_run_id_a` | string | New/Synthetic | No | Payment batch |
| `payment_run_id_b` | string | New/Synthetic | No | Payment batch |
| `allocated_amount_a` | decimal(14,2) | New/Synthetic | Conditional | Amount assigned to invoice |
| `allocated_amount_b` | decimal(14,2) | New/Synthetic | Conditional | Amount assigned to invoice |
| `allocation_status_a` | enum | New/Synthetic | Conditional | `confirmed_paid`, `cancelled`, `reversed`, `refunded`, `pending` |
| `allocation_status_b` | enum | New/Synthetic | Conditional | `confirmed_paid`, `cancelled`, `reversed`, `refunded`, `pending` |
| `settlement_event_a` | enum | New/Synthetic | Conditional | `settled`, `cancelled_before_settlement`, `reversed_after_settlement`, `refunded_after_settlement` |
| `settlement_event_b` | enum | New/Synthetic | Conditional | `settled`, `cancelled_before_settlement`, `reversed_after_settlement`, `refunded_after_settlement` |
| `historical_settlement_count` | integer | Derived | No | Number of successful historical settlements for the underlying obligation |

Existing `paymentReference` must not be copied into these fields unless the
source document is evidence that it is a real payment transaction reference.

## Candidate construction fields

| Field | Type | Availability | Required | Notes |
|---|---|---|---|---|
| `candidate_block_method` | enum | Derived | Yes | Exact identifier, supplier/amount window, or payment-run block |
| `candidate_window_days` | integer | Derived | Yes | Temporal candidate radius |
| `invoice_number_match_key` | string | Derived | Yes | Normalised invoice number |
| `supplier_match_key` | string | Derived | Yes | Normalised supplier/cluster key |
| `candidate_rank` | integer | Derived | No | Candidate order before review |

Candidate construction fields are not labels.

## Adjudication fields

| Field | Type | Availability | Required | Notes |
|---|---|---|---|---|
| `label` | enum | Adjudicated/Synthetic | Yes | `duplicate`, `not_duplicate`, `uncertain` |
| `label_status` | enum | Adjudicated/Synthetic | Yes | `adjudicated`, `synthetic`, `pending`, `uncertain` |
| `rationale_code` | enum | Adjudicated/Synthetic | Yes | Controlled label rationale |
| `rationale_text` | string | Adjudicated/Synthetic | No | Optional reviewer explanation |
| `reviewer_id_masked` | string | New/Synthetic | Conditional | Reviewer pseudonym |
| `review_confidence` | float 0–1 | Adjudicated/Synthetic | No | Reviewer certainty |
| `evidence_source` | enum | Adjudicated/Synthetic | Yes | `erp_allocation`, `payment_record`, `reviewer_adjudication`, `invoice_document`, `synthetic_ground_truth`, `combined_evidence` |
| `adjudicated_at` | timestamp | Adjudicated/Synthetic | Conditional | When the decision was made |
| `protocol_version` | string | New | Yes | Label protocol version |
| `second_reviewer_id_masked` | string | New | No | For adjudication quality |
| `adjudication_resolution` | enum | New | No | Accepted, resolved, unresolved |

The protocol document in
[duplicate_payment_label_protocol.md](./duplicate_payment_label_protocol.md)
is the source for valid labels and rationale codes.

## Duplicate-pair feature fields

These fields may be exported to a feature table or in-memory feature vector.
They must be derived only from pre-adjudication fields.

### Already implemented

| Feature | Type | Existing source |
|---|---|---|
| `vendorSimilarity` | float 0–1 | `vendorName` pair comparison |
| `invoiceNumberSimilarity` | float 0–1 | `invoiceNumber` pair comparison |
| `exactAmountMatch` | boolean | `totalAmount` equality |
| `amountDifference` | float or null | Absolute `totalAmount` difference |
| `amountSimilarity` | float 0–1 | Relative `totalAmount` similarity |
| `dateDifferenceDays` | integer or null | Absolute `invoiceDate` difference |
| `currencyMatch` | boolean | Normalized `currency` equality |
| `paymentTermsSimilarity` | float or null | Dynamic `paymentTerms` similarity |
| `vendorOccurrenceCount` | integer | Supplier frequency |
| `invoiceNumberOccurrenceCount` | integer | Invoice-number frequency |
| `vendorInvoiceOccurrenceCount` | integer | Supplier/invoice-number frequency |

The current implementation is in
[feature_engineering_service.py](<D:/Invoice Data Extraction/invoice-ai-backend-fastapi/app/services/feature_engineering_service.py>)
and [similarity_utils.py](<D:/Invoice Data Extraction/invoice-ai-backend-fastapi/app/utils/similarity_utils.py>).

### New derived fields

| Feature | Type | Required source |
|---|---|---|
| `paymentReferenceSimilarity` | float 0–1 | `payment_reference_a/b` |
| `samePaymentRun` | boolean | `payment_run_id_a/b` |
| `allocationOverlapRatio` | float 0–1 | Allocated invoice/payment overlap |
| `partialPaymentRatio` | float 0–1 | Allocated amount and invoice total |
| `reversalStatusMatch` | enum/boolean | Payment or allocation status |
| `supplierIdMatch` | boolean | Stable supplier ID |

The pilot's 20-column predictive feature vector is an exact contract:
`pair_id` plus the 19 fields in the table below. It does not include
`paidAmountDifference`, `paymentDateDifferenceDays`, `paymentCurrencyMatch`,
PO similarity or line-item similarity.

## Final 19-predictive-feature contract

`pair_id` is an identifier and is never included in the predictive feature
vector.

| Feature | Input fields | Formula | Output type | Missing behavior | Prediction-time availability | Leakage risk | Initial decision |
|---|---|---|---|---|---|---|---|
| `vendorSimilarity` | Invoice A/B `vendor_name` | Normalize case/punctuation and calculate normalized text similarity | float 0–1 | `0.0` if either value is missing | Available if reviewed values are available by cutoff | Low | Retain |
| `invoiceNumberSimilarity` | Invoice A/B `invoice_number` | Normalize alphanumeric characters and calculate text similarity | float 0–1 | `0.0` if either value is missing | Available if OCR/reviewed values are available | Low | Retain |
| `exactAmountMatch` | Invoice A/B `total_amount` and matching currencies | `true` only when both currencies are present and equal and Decimal totals are exactly equal | boolean | `false` if either value or currency is missing or currencies differ | Available at pair construction | Low | Retain |
| `amountDifference` | Invoice A/B `total_amount` and matching currencies | `abs(total_amount_a - total_amount_b)` only when currencies match | decimal or null | `null` for missing, invalid or cross-currency amounts | Available at pair construction | Low | Retain |
| `amountSimilarity` | Invoice A/B `total_amount` and matching currencies | For equal currencies: `1 - abs(A-B)/max(abs(A),abs(B))`; if both amounts are zero, return `1.0`; if one amount is zero, return `1.0 - abs(A-B)/max(abs(A),abs(B)) = 0.0` | float 0–1 or null | `null` for cross-currency or missing/invalid amounts; `0.0` for invalid comparison values only if the documented missing-value policy is used | Available at pair construction | Low | Retain |
| `dateDifferenceDays` | Invoice A/B `invoice_date` | `abs(invoice_date_a - invoice_date_b).days` | integer or null | `null` if either date is missing/invalid | Available if invoice dates precede cutoff | Low | Retain |
| `currencyMatch` | Invoice A/B `currency` | Uppercase/trim and compare | boolean | `false` if either currency is missing | Available at pair construction | Low | Retain |
| `paymentTermsSimilarity` | Invoice A/B reviewed/extracted `payment_terms` | Reviewed value first; extracted value fallback; normalize and calculate text similarity | float 0–1 or null | `null` if either side is missing | Available only if terms are known before cutoff | Low to medium | Retain as a baseline |
| `vendorOccurrenceCount` | Training-corpus supplier/vendor matches | Count distinct training invoice IDs with the source normalized supplier | integer >= 0 | `0` if supplier or training count is missing | Requires a frozen training corpus | Medium; validation/test counts can leak | Retain with training-only counts |
| `invoiceNumberOccurrenceCount` | Training-corpus invoice-number matches | Count distinct training invoice IDs with the source normalized invoice number | integer >= 0 | `0` if number or training count is missing | Requires a frozen training corpus | Medium; validation/test counts can leak | Retain with training-only counts |
| `vendorInvoiceOccurrenceCount` | Training-corpus supplier and invoice-number matches | Count distinct training invoice IDs matching both | integer >= 0 | `0` if either source value is missing | Requires a frozen training corpus | Medium; validation/test counts can leak | Retain with training-only counts |
| `supplierIdMatch` | Invoice A/B stable `supplier_id` | `supplier_id_a == supplier_id_b` | boolean | `false` if either supplier ID is missing | Available before cutoff | High: supplier matching can shortcut the label | Test separately; exclude from the initial model unless supplier generalisation is studied |
| `paidAmountMatch` | Side-specific allocated amounts and payment currencies | Compare `allocated_amount_a` and `allocated_amount_b` only when currencies match; full payment amount is used only when no allocation is available and the relationship is unambiguously one-invoice/one-payment | boolean or null | `null` if allocation or currency is missing or currencies differ | Available when payment allocations are known before cutoff | Medium | Retain for feasibility testing |
| `paidAmountSimilarity` | Side-specific allocated amounts and payment currencies | For matching currencies, `1 - abs(A-B)/max(abs(A),abs(B))`, minimum 0; both zero is `1.0`; one zero is `0.0` | float 0–1 or null | `null` for missing or cross-currency amounts | Available when payment allocations are known before cutoff | Medium | Retain for feasibility testing |
| `paymentReferenceSimilarity` | Payment A/B `payment_reference` | Normalize and calculate text similarity | float 0–1 or null | `null` if either reference is missing | Available only before the prediction cutoff | Medium | Retain with cutoff validation |
| `samePaymentRun` | Payment A/B `payment_run_id` | Exact equality | boolean or null | `null` if either run ID is missing | Available if payment-run metadata precedes cutoff | Medium | Retain |
| `allocationOverlapRatio` | Invoice/payment allocation relationships | Initial pilot value: `1.0` when the pair uses the same invoice ID; `0.0` otherwise | float 0–1 or null | `null` if allocation evidence is missing | Available only after allocations exist | High: same-invoice identity can act as a duplicate shortcut | Defer/exclude from initial model |
| `partialPaymentRatio` | Invoice A/B invoice totals and all eligible completed allocations | `coverageA = min(1.0, sum(eligible allocations for invoice A) / invoice_total_a)`; `coverageB = min(1.0, sum(eligible allocations for invoice B) / invoice_total_b)`; pair value = `min(coverageA, coverageB)` | float 0–1 or null | `null` if an invoice total or eligible allocations are missing | Available only after allocations are reconciled | Medium | Retain |
| `reversalStatusMatch` | Payment/allocation `payment_status`, `settlement_event`, and reversal-effective timestamps | `-1` unknown, `0` no reversal at cutoff, `1` historical reversal/refund before cutoff | integer -1/0/1 | `-1` if evidence or timestamps are missing | Available only when original settlement and reversal timestamps are known | High if timestamps or cutoff are missing | Defer until timestamped reversal/refund data is available |

### Currency comparison rules

Invoice, paid and allocation amount comparisons require matching currencies.
Different currencies must return `null` for amount difference and similarity
and must not contribute to `exactAmountMatch`, `paidAmountMatch` or
`paidAmountSimilarity`. A false boolean result must not be used to represent
an unknown cross-currency amount.

If documented exchange rates are available and frozen for the prediction
cutoff, both amounts may be normalized to the same reporting currency before
comparison. The exchange-rate source and timestamp must be retained as
metadata; the pilot has no exchange-rate mechanism.

The generic amount-similarity formula is:

```text
if A is null or B is null: null
if currencyA != currencyB: null
if A == 0 and B == 0: 1.0
if maximum(abs(A), abs(B)) == 0: 1.0
similarity = 1 - abs(A-B)/maximum(abs(A),abs(B))
```

If exactly one amount is zero:

```text
similarity = 0.0
```

The result is capped to `[0,1]` and rounded to 4 decimal places.

### Occurrence-feature split limits

Occurrence features must be calculated only from the frozen training corpus:

- `vendorOccurrenceCount`
- `invoiceNumberOccurrenceCount`
- `vendorInvoiceOccurrenceCount`

Validation and test suppliers absent from training will receive zero or
unseen-category behavior for supplier-dependent counts. This is not evidence
that the feature value is meaningful; it indicates an out-of-training
supplier population.

Candidate supplier groups should be used for ablation:

1. Baseline: text and amount features without supplier occurrence counts.
2. Supplier-aware: training-only occurrence counts.
3. Supplier-absent test: report performance separately for unseen suppliers.

The project should not silently import validation/test invoice rows into
training occurrence calculations.

### Paid amount rule

The primary feature source is the invoice-specific allocation amount:

```text
allocated_amount_a = allocation A allocated_amount
allocated_amount_b = allocation B allocated_amount
```

The full payment amount is used only as a fallback when allocation data is
not available and the pair has a one-invoice, one-payment relationship.
For a payment covering multiple invoices, the full payment amount must not
be compared directly because it is not attributable to either invoice.

### Partial-payment rule

For a pair:

```text
coverageA = min(
  1.0,
  sum(eligible_completed_allocations_for_invoice_a) / invoice_total_a
)

coverageB = min(
  1.0,
  sum(eligible_completed_allocations_for_invoice_b) / invoice_total_b
)

partialPaymentRatio = min(coverageA, coverageB)
```

Use Decimal arithmetic. Aggregate every eligible completed allocation for
each invoice before dividing by that invoice's total. Eligible allocations
exclude cancelled-before-settlement and pending/unsettled allocations.

Eligible allocation statuses and events are:

- `allocation_status = confirmed_paid` and
  `settlement_event = settled`
- `allocation_status = reversed` or `refunded` and
  `settlement_event = reversed_after_settlement` or
  `refunded_after_settlement`, when the reversal/refund occurred on or before
  the pair decision cutoff and the original settlement remains historical
  evidence

Excluded:

- `allocation_status = cancelled`
- `settlement_event = cancelled_before_settlement`
- `allocation_status = pending`
- Any unsettled allocation without a completed settlement event

Reversed/refunded allocations must not be included after the prediction
cutoff. The pilot does not contain reversal-effective timestamps, so the
documented reversal status is deferred and must not be used as an initial
model feature.

For example, if invoice A has two completed allocations of 300.00 against a
600.00 invoice:

- Aggregated allocation amount = 600.00
- `coverageA = 600.00 / 600.00 = 1.0`

It would be incorrect to use only one referenced 300.00 allocation and
report `0.5`.

If required invoice or allocation evidence is missing, the pair-level
`partialPaymentRatio` is `null`.

### Allocation overlap decision

The current pilot implementation of `allocationOverlapRatio` only measures
whether both sides point to the same invoice ID:

```text
1.0 if invoice_id_a == invoice_id_b else 0.0
```

This can act as an invoice-identity shortcut and gives no meaningful overlap
for two different invoice records representing the same obligation. It
should be excluded from the initial model and retained only as a
diagnostic/validation feature.

### Reversal status decision

Use a numeric or enum output:

```text
-1 = unknown or evidence missing
0 = no reversal/refund confirmed at the cutoff
1 = historical reversal/refund before the prediction cutoff
```

Do not derive this feature from a synthetic scenario name or final label.
A reversal or refund occurring after the prediction cutoff must not be
included.

The pilot CSV does not contain reversal-effective timestamps. It is therefore
not possible to verify whether a reversal occurred before or after the
prediction cutoff independently. The historical reversal status is only a
documented pilot approximation until timestamped payment and allocation
history is available.

The `invoice_line_items` table already exists but is currently empty.
Payment statuses and reversal/refund fields must describe historical
settlement evidence. A later reversal or refund must not overwrite the
historical `settlement_event` or its positive/negative label.

## Feature count and initial model scope

The full research contract contains 19 predictive features:

- 11 retained baseline/invoice features
- 8 payment, supplier or allocation features

No claim is made that all 19 are implementation-ready from the current pilot.

Initial candidate feature set:

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

The initial set is recommended only as a pilot implementation baseline.

Deferred or excluded features:

- `supplierIdMatch`: exclude from the initial model; study separately as an ablation.
- `allocationOverlapRatio`: defer because same-invoice ID behavior can be an identity shortcut.
- `reversalStatusMatch`: defer until settlement, reversal and prediction timestamps exist.
- `vendorOccurrenceCount`: defer until a frozen supplier-aware training corpus and unseen-supplier policy exist.
- `invoiceNumberOccurrenceCount`: defer or use cautiously; stable invoice numbers may encode duplicate labels.
- `vendorInvoiceOccurrenceCount`: defer until a frozen training corpus and supplier-disjoint design are implemented.

## Pilot consistency findings

The current pilot was checked against its source invoice, payment and
allocation CSV files:

- The pilot's `paidAmountMatch` and `paidAmountSimilarity` values agree with
  the full-payment and allocated-payment interpretations for the current
  rows. There is no multi-invoice payment in the pilot, so allocated
  amounts are identical to full payment amounts for the rows checked.
- `partialPaymentRatio` must use all eligible allocations for each invoice.
- PAIR-0014 uses two 300.00 allocations for invoice 21, whose total is
  600.00. The aggregate coverage is `1.0`, so PAIR-0014 is verified at
  `1.0`.
- PAIR-0024 compares invoice 19 and invoice 21. Invoice 19 has 600.00
  coverage and invoice 21 has 600.00 aggregate coverage, so PAIR-0024 is
  also verified at `1.0`.
- `allocationOverlapRatio` matches a same-invoice-ID comparison in every
  pilot row, but remains an identity shortcut and is deferred.
- `reversalStatusMatch` uses legacy string values in the pilot:
  an empty string means no reversal information encoded in the current CSV,
  and `reversed_or_refunded` marks the historical reversal. Implementation
  must normalize these values to `-1/0/1` only after verifying cutoff
  evidence.
- The pilot does not contain reversal-effective timestamps. Future
  reversals occurring after the prediction cutoff must not be assumed to be
  safely excluded until timestamped status evidence is added.
- `supplierIdMatch` is `true` for 29 of 30 pilot pairs and `false` for one
  pair. It is highly concentrated and must be tested as an ablation feature,
  not treated as a label proxy.

No pilot CSV was changed during this review.

## Split fields

| Field | Type | Availability | Required | Notes |
|---|---|---|---|---|
| `supplier_cluster_id` | string | Derived | Yes | Supplier-disjoint cluster key |
| `supplier_split_key` | string | Derived | Yes | Stable hash or cluster key |
| `time_split_key` | string | Derived | Yes | `train`, `validation`, or `test` |
| `pair_decision_timestamp` | timestamp | Derived | Yes | Latest invoice/payment evidence time |
| `time_cutoff` | timestamp | Derived | Yes | Split generation cutoff |
| `split_reason` | string | Derived | Yes | Document split assignment |

Split fields must be metadata rather than predictive features.

## Hidden synthetic ground-truth fields

Synthetic records may contain these fields outside the feature export:

| Field | Type | Purpose |
|---|---|---|
| `generator_version` | string | Synthetic generation provenance |
| `generator_seed` | integer | Reproduction |
| `synthetic_scenario` | enum | Hidden label-generation scenario |
| `synthetic_duplicate_type` | enum | Positive transformation subtype |
| `synthetic_negative_type` | enum | Negative transformation subtype |
| `synthetic_ground_truth_label` | enum | Generator gold label |
| `underlying_obligation_id_a` | string | Validation-only obligation for invoice A |
| `underlying_obligation_id_b` | string | Validation-only obligation for invoice B |
| `hidden_supplier_cluster` | string | Split assignment |
| `hidden_pair_overlap` | boolean | Leakage audit |

These fields must not be included in:

- pair feature vectors;
- training samples;
- validation samples;
- test samples;
- model serialisation;
- reviewer label-generation inputs.

## Label consistency rules

1. Labels must use one of:
   - `duplicate`
   - `not_duplicate`
   - `uncertain`
2. `uncertain` pairs must not enter binary training.
3. `duplicate` requires actual or synthetic evidence of a second settlement.
4. Similarity scores are candidate features, not labels.
5. Existing lifecycle statuses are not labels.
6. Existing invoice review state is not a duplicate label.
7. One pair must have exactly one active `pair_id`.
8. One pair must have exactly one final label.
9. Audit metadata must preserve label changes and rationale history.

## Minimum export shape

The first data export should contain three groups:

```text
Pair identity
Evidence fields
Label metadata
```

```json
{
  "pair_id": "pair-example-001",
  "invoice_id_a": 70,
  "invoice_id_b": 71,
  "supplier_id_a": "supplier-synthetic-001",
  "supplier_id_b": "supplier-synthetic-001",
  "invoice_number_a": "MOS/2026/552",
  "invoice_number_b": "MOS/2026/552",
  "total_amount_a": 56640.00,
  "total_amount_b": 56640.00,
  "currency_a": "INR",
  "currency_b": "INR",
  "payment_id_a": null,
  "payment_id_b": null,
  "paid_amount_a": null,
  "paid_amount_b": null,
  "label": "uncertain",
  "rationale_code": "UNC_PAYMENT_EVIDENCE_MISSING",
  "evidence_source": "invoice_document",
  "dataset_version": "draft-v1"
}
```

The example is illustrative. It does not invent or assert real payment
evidence and must not be treated as a synthetic or real dataset record.

## Split contract

Before pair export:

1. Assign supplier clusters.
2. Assign time cutoffs.
3. Remove split-overlapping invoices.
4. Remove split-overlapping payments.
5. Remove duplicate source documents.
6. Confirm no pair shares one invoice across splits.
7. Confirm no pair shares one payment across splits.
8. Record split assignment provenance.

For supplier-disjoint and time-aware splits:

- training: earlier date, a disjoint supplier subset;
- validation: later date, a disjoint supplier subset;
- test: latest date, a disjoint supplier subset.

No predictive feature may include split metadata or dataset assignment.
