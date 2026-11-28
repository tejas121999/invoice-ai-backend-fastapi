# Duplicate Payment Label Protocol

## Purpose

This document defines a reproducible protocol for assigning `duplicate`,
`not_duplicate`, or `uncertain` labels to candidate invoice-payment pairs.
It applies to this project before any synthetic dataset generation or ML
training.

The protocol is designed to preserve the existing FastAPI, SQLAlchemy,
invoice extraction, review and pair-feature architecture.

## Terminology

### Invoice

An invoice is a claim for payment represented by:

- an invoice number;
- supplier or vendor identity;
- invoice date;
- financial fields; and
- optional line items or invoice references.

The current project stores these values in `invoices` and
`extracted_invoice_data`. OCR text is retained in `invoices.rawText`.
Human-corrected values are stored in
`extracted_invoice_data.reviewedFieldsJson`.

### Payment

A payment is a settlement event with:

- a payment identifier;
- a payment date;
- a paid amount;
- a payment currency;
- a payment reference; and
- a payment status.

The current project has no payment transaction entity or payment table.
Consequently, invoice due dates, payment terms and `paymentReference`
extracted from invoice text must not be assumed to be payment records.

### Invoice-payment allocation

An invoice-payment allocation links an invoice to a payment and records:

- the amount allocated to that invoice;
- whether the allocation is confirmed, cancelled or reversed; and
- the source of the allocation.

An allocation is required because a payment may cover several invoices,
and an invoice may receive partial payments.

### Duplicate invoice document

A duplicate invoice document means that two document or record instances
represent the same invoice obligation.

A duplicate invoice document is not automatically a duplicate payment.
The duplicate-document case is positive only when the two documents also
lead to or result in a duplicate settlement.

### Duplicate payment

A duplicate payment is positive when two distinct invoice-payment allocations
represent the same underlying invoice obligation and one allocation is
settled without being a legitimate:

- partial payment;
- instalment;
- credit note;
- cancellation;
- reversal;
- corrected invoice process; or
- separate contractual obligation.

The required unit of prediction is:

```text
Invoice A + Allocation A
+ Invoice B + Allocation B
+ Supplier context
=> duplicate / not_duplicate / uncertain
```

A label must be based on evidence. It must not be based only on:

- invoice-number similarity;
- vendor-name similarity;
- equal amounts;
- equal dates;
- payment lifecycle status;
- a duplicate candidate count; or
- OCR confidence.

## Label classes

### `duplicate`

Assign `duplicate` when the evidence establishes that two settlements are
for the same underlying invoice obligation and one settlement is duplicate.

The evidence should be drawn from at least one strong source:

- invoice-payment allocation records;
- confirmed double payment or overpayment;
- ERP/reconciliation reversal or recovery;
- independent reviewer adjudication;
- controlled synthetic ground-truth metadata.

### `not_duplicate`

Assign `not_duplicate` when the pair represents separate legitimate
obligations or one of the specified legitimate payment patterns.

Examples include:

- ordinary repeated invoices;
- distinct invoice numbers;
- different suppliers;
- partial payments;
- instalments;
- credit notes;
- cancelled or pending payments;
- reversed payments that contain no second settlement;
- corrected invoices that replace, rather than duplicate, an original.

### `uncertain`

Assign `uncertain` when:

- the supplier or invoice identity cannot be established;
- allocation evidence is missing or contradictory;
- OCR corrections are not sufficiently reliable;
- a credit or reversal status is unclear;
- payment timing or amount evidence is incomplete;
- reviewers disagree or require more evidence.

`uncertain` pairs are excluded from the initial binary training set. They
remain available for adjudication review and may be relabelled later.

## Handling special cases

### Legitimate partial payments

Do not label a pair as duplicate if each allocation is part of a confirmed
payment plan for the same invoice and the sum does not exceed the invoice
amount.

The pair should be `not_duplicate` if the relevant allocations are both
legitimate and no second settlement exists.

### Instalments

Separate invoice obligations or instalment obligations are
`not_duplicate` when:

- the invoices are under one agreement or multiple instalments;
- all payment allocations are valid; and
- no repeated invoice obligation was paid twice.

### Credit notes

A credit note is a separate financial correction and is normally
`not_duplicate` because it does not itself create a duplicate settlement.
It is positive only if the adjudicated evidence shows that the credit is
recovering or correcting an independently confirmed duplicate payment.
The credit/reference amount must not be used as the sole reason to assign
`duplicate`.

### Refunds

A refund is a return of money after one or more payments. A refund does not
erase a historical duplicate event.

- A refund of one of two genuine duplicate settlements remains `duplicate`
  if both settlements occurred and the second settlement was not legitimate.
- A refund of only the second, extra payment can be evidence of a recovered
  duplicate and remains `duplicate`.
- A refund of a legitimate invoice payment with no second settlement remains
  `not_duplicate`.
- If refund, reversal and payment evidence are contradictory or incomplete,
  assign `uncertain`.

### Cancelled payments

A cancelled payment is `not_duplicate` if no settlement reached the
supplier and no additional valid payment was made for the same obligation.

If another payment validly settled the obligation, the cancelled allocation
must not be counted as evidence of a duplicate payment unless it also
settled and was later cancelled.

### Reversed payments

A reversal alone is not a duplicate payment.

A pair is positive only if:

- two settlements occurred; or
- a reversed allocation is combined with evidence of a second successful
  payment for the same obligation.

The default label is `not_duplicate` for one successful payment plus one
cancelled or reversed allocation that did not remain paid.

When a payment was successful and later reversed or refunded, evaluate the
historical settlement state:

- two successful settlements occurred and one was duplicate:
  retain `duplicate`;
- only one successful settlement occurred and the second allocation was
  cancelled or never settled:
  retain `not_duplicate`;
- the historical settlement evidence is ambiguous:
  assign `uncertain`.

For feature engineering, reversal status must describe the state known at
the prediction cutoff:

- `-1` if evidence is unknown or missing;
- `0` if no reversal/refund is confirmed; or
- `1` if a historical reversal/refund is confirmed before the cutoff.

This feature is historical settlement evidence, not a duplicate-payment
label. Reversals or refunds occurring after the prediction cutoff must not
be used as model inputs.

The implementation requires three timestamps:

- original settlement timestamp;
- reversal/refund effective timestamp; and
- pair prediction timestamp.

If any required timestamp is missing, reversal status must remain
unknown and must not enter the initial feature set.

The pilot does not contain reversal-effective timestamps. Therefore the
current synthetic reversal status is not sufficient to prove whether a
future reversal occurred before or after the prediction cutoff. Reversal
timing must remain deferred until timestamped historical settlement evidence
is available.

### Corrected invoices

A corrected invoice is `not_duplicate` if it replaces the original and only
the corrected invoice was paid.

It is `duplicate` only if:

- the original and corrected invoice both settled;
- both allocations are non-cancelled duplicate settlements; and
- evidence confirms that the original obligation was paid twice.

OCR variance within an invoice number or supplier name is not sufficient
evidence for a correction or duplicate.

## Rationale codes

### Duplicate codes

| Code | Meaning |
|---|---|
| `DUP_SAME_INVOICE_NUMBER` | Supplier and invoice number identify the same obligation, and two payments settled it |
| `DUP_EXACT_INVOICE_REPEAT` | Two invoice records and payments represent the same underlying invoice |
| `DUP_FORMAT_VARIANT` | OCR/formatting variations differ, but stable evidence identifies the same invoice |
| `DUP_RESUBMISSION` | Original and resubmitted/corrected invoice were both paid |
| `DUP_PAYMENT_RUN_REPEAT` | The same obligation was paid in separate runs or transactions |
| `DUP_RECOVERED_OR_REVERSED` | Historical evidence confirms a duplicate settlement or recovery |
| `DUP_OTHER_CONFIRMED` | Another documented evidence source confirms duplication |

### Not-duplicate codes

| Code | Meaning |
|---|---|
| `ND_DISTINCT_INVOICE` | Separate invoice numbers and obligations |
| `ND_DIFFERENT_SUPPLIER` | Similar records belong to different suppliers |
| `ND_PARTIAL_PAYMENT` | Allocations are valid partial payments of one invoice |
| `ND_INSTALMENT` | Obligations are legitimate instalments or agreed stages |
| `ND_CREDIT_NOTE` | Credit or adjustment, not a second settlement |
| `ND_CANCELLED_PAYMENT` | Cancelled/pending allocation was not paid |
| `ND_REVERSED_NO_DOUBLE_SETTLEMENT` | Reversal does not indicate a second successful payment |
| `ND_REFUND_NO_DOUBLE_SETTLEMENT` | Refund is not evidence of a second settlement |
| `ND_CORRECTED_INVOICE_ONLY` | Only corrected invoice was settled |
| `ND_HARD_NEGATIVE` | Similar identifiers or amounts but separate verified obligations |
| `ND_RANDOM_NEGATIVE` | Deliberately unrelated candidate pair |

### Uncertain codes

| Code | Meaning |
|---|---|
| `UNC_SUPPLIER_UNKNOWN` | Supplier identity cannot be established |
| `UNC_INVOICE_UNKNOWN` | Invoice identity is incomplete or contradictory |
| `UNC_PAYMENT_EVIDENCE_MISSING` | Payment or allocation evidence is unavailable |
| `UNC_REVIEWER_DISAGREEMENT` | Reviewers disagree and no resolution exists |
| `UNC_CREDIT_REVERSAL_AMBIGUITY` | Credit/reversal status is unclear |
| `UNC_OCR_UNRELIABLE` | OCR evidence is too uncertain for adjudication |
| `UNC_OTHER_INSUFFICIENT` | Insufficient evidence for a binary decision |

Free-text rationale is optional and must not substitute for the controlled
rationale code.

## Positive and negative examples

### Positive examples

1. Invoice A and Invoice B have the same supplier and invoice number,
   but two separate, successful payment references settle the full amount.
   Label: `duplicate`; code: `DUP_SAME_INVOICE_NUMBER`.

2. The OCR text shows `INV-2026/010` and `INV2026010`; after human
   verification they identify the same supplier and invoice. Two successful
   payments exist. Label: `duplicate`; code:
   `DUP_FORMAT_VARIANT`.

3. An invoice is submitted as `INV-1001`, corrected to `INV-1001-C`,
   and both corrected and original records are settled. Label:
   `duplicate`; code: `DUP_RESUBMISSION`.

4. The ERP allocation table records one payment and a later duplicate
   payment for the same invoice. Label: `duplicate`; code:
   `DUP_EXACT_INVOICE_REPEAT`.

5. A confirmed reversed refund record identifies one payment plus a
   second successful payment for the same obligation. Label: `duplicate`;
   code: `DUP_RECOVERED_OR_REVERSED`.

6. One supplier is paid twice through separate payment runs for the same
   invoice number and amount. Label: `duplicate`; code:
   `DUP_PAYMENT_RUN_REPEAT`.

7. Two payments were originally successful for the same invoice obligation;
   one payment was later refunded. Historical evidence confirms both
   settlements occurred, so the pair remains `duplicate`; code:
   `DUP_RECOVERED_OR_REVERSED`.

### Negative examples

1. Two invoices have identical totals but different suppliers and invoice
   numbers. Label: `not_duplicate`; code: `ND_DIFFERENT_SUPPLIER`.

2. A supplier issues `INV-200` and `INV-201` in the same month and each
   is paid once. Label: `not_duplicate`; code: `ND_DISTINCT_INVOICE`.

3. One invoice is paid in two allocations, with both amounts totalling the
   confirmed invoice amount. Label: `not_duplicate`; code:
   `ND_PARTIAL_PAYMENT`.

4. Three separate invoices are instalment charges under different dates.
   Label: `not_duplicate`; code: `ND_INSTALMENT`.

5. An invoice is paid once and a later credit note reverses part of the
   obligation. Label: `not_duplicate`; code: `ND_CREDIT_NOTE`.

6. The invoice number differs by one character but belongs to two verified
   supplier obligations. Label: `not_duplicate`; code: `ND_HARD_NEGATIVE`.

7. A legitimate payment is refunded and no other successful payment settled
   the same obligation. Label: `not_duplicate`; code:
   `ND_REFUND_NO_DOUBLE_SETTLEMENT`.

### Uncertain examples

1. OCR reads two possible invoice numbers and no allocation confirms
   whether they are the same obligation. Label: `uncertain`; code:
   `UNC_OCR_UNRELIABLE`.

2. Two payments match the amount and supplier, but invoice or payment
   references are absent. Label: `uncertain`; code:
   `UNC_PAYMENT_EVIDENCE_MISSING`.

3. Two reviewers disagree on whether a reversed payment constitutes a
   duplicate settlement. Label: `uncertain`; code:
   `UNC_REVIEWER_DISAGREEMENT`.

4. Refund records exist but do not establish whether both payments settled
   successfully. Label: `uncertain`; code:
   `UNC_CREDIT_REVERSAL_AMBIGUITY`.

## Evidence precedence and label preservation

Evidence must be evaluated in this order:

1. confirmed invoice-payment allocations and settlement records;
2. payment status and historical settlement evidence;
3. credit, reversal or refund evidence;
4. reviewer adjudication;
5. OCR and invoice similarity evidence.

Evidence precedence does not mean that lower-precedence similarity evidence
can override a confirmed binary event. It means that candidate similarity
alone cannot change a final allocation-based adjudication.

For every positive or negative decision, record the strongest evidence
source in `evidence_source`. If sources conflict, assign `uncertain` unless
the protocol can identify a confirmed original settlement separately from
its later reversal or refund.

## Reviewer decision recording

Every adjudication should record:

- `pair_id`
- two invoice IDs
- associated payment and allocation IDs, if available
- final label
- rationale code
- optional free-text rationale
- evidence source
- reviewer pseudonym or ID
- reviewer confidence
- adjudication timestamp
- dataset/generation version

A review should display:

- source invoice fields;
- reviewed invoice fields;
- invoice image/PDF;
- OCR raw text;
- payment evidence;
- allocation evidence;
- existing similarity features;
- credit/reversal/cancellation state.

The model label must not be visible while initial ground truth is created.

## Synthetic ground-truth separation

Synthetic generators may create hidden ground-truth metadata, but predictive
features must be generated only from fields available before adjudication.

The following must be separate from the pair feature vector:

- synthetic generator rule;
- target label;
- duplicate subtype;
- reviewer decision;
- rationale text;
- final adjudication status;
- hidden supplier cluster;
- hidden pair-generation scenario;
- payment reversal/credit outcome that reveals the label;
- train/validation/test assignment.

Synthetic samples should include hidden provenance metadata for research
reproducibility, but it must not be written to model feature columns.

## Dataset split protocol

### Supplier-disjoint split

No supplier may appear with different pair records in multiple splits.

Where stable supplier IDs are unavailable:

1. use reviewed, normalized vendor identity;
2. create a supplier-cluster key;
3. assign the entire cluster to one split;
4. document that vendor identity may still require correction.

### Time-aware split

Assign pairs by the latest available invoice/payment decision timestamp:

- training: earlier period;
- validation: subsequent period;
- test: latest period.

Do not place later invoices or payments in training data.

### Entity-disjoint split

No invoice should occur in both training and test pairs.
No payment should occur in both training and test pairs.
No source PDF/document should occur in both splits.

### Split assignment

The split must be assigned after candidate pair construction and only after
labels are complete. The label must not influence split assignment except
when balancing is performed as a documented stratification step.

The final split metadata should include:

- `supplier_cluster_id`
- `split_name`
- `invoice_ids`
- `payment_ids`
- `time_cutoff`
- `split_reason`

## Adjudication quality controls

For real or anonymised data:

- use at least two independent reviewers for a pilot subset;
- calculate inter-rater agreement;
- use a third reviewer for disagreement;
- preserve the original evidence;
- version the label protocol;
- audit a random sample of labels;
- audit all uncertain and rare duplicate examples;
- retain OCR confidence and extraction provenance.

Synthetic data should include an exact generator provenance field and should
be evaluated separately from any real/peer-reviewed dataset.
