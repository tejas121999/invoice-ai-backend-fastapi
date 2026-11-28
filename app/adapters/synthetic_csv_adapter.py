"""CSV adapter for the synthetic duplicate-payment pilot fixture."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable


REQUIRED_DATA_FILES = (
    "suppliers.csv",
    "invoices.csv",
    "payments.csv",
    "allocations.csv",
    "pairs.csv",
)

FEATURE_CSV_FIELDS = (
    "pair_id",
    "vendorSimilarity",
    "invoiceNumberSimilarity",
    "exactAmountMatch",
    "amountDifference",
    "amountSimilarity",
    "dateDifferenceDays",
    "currencyMatch",
    "paymentTermsSimilarity",
    "vendorOccurrenceCount",
    "invoiceNumberOccurrenceCount",
    "vendorInvoiceOccurrenceCount",
    "supplierIdMatch",
    "paidAmountMatch",
    "paidAmountSimilarity",
    "paymentReferenceSimilarity",
    "samePaymentRun",
    "allocationOverlapRatio",
    "partialPaymentRatio",
    "reversalStatusMatch",
)


class SyntheticCSVAdapterError(ValueError):
    """Base error for synthetic pilot CSV loading and validation."""


class CSVFileNotFoundError(SyntheticCSVAdapterError):
    """Raised when a required pilot CSV file is missing."""


class CSVSchemaError(SyntheticCSVAdapterError):
    """Raised when a CSV header or required field is invalid."""


class CSVValueError(SyntheticCSVAdapterError):
    """Raised when a CSV value cannot be parsed."""


class CSVRelationshipError(SyntheticCSVAdapterError):
    """Raised when synthetic CSV relationships are inconsistent."""


@dataclass(frozen=True)
class SupplierRecord:
    supplier_id: str
    supplier_name: str
    supplier_name_normalized: str
    supplier_country: str | None
    supplier_tax_id_masked: str | None
    supplier_bank_id_masked: str | None


@dataclass(frozen=True)
class InvoiceRecord:
    invoice_id: str
    supplier_id: str
    source_document_id: str
    invoice_number: str | None
    vendor_name: str | None
    vendor_name_reviewed: str | None
    invoice_date: date | None
    due_date: date | None
    subtotal: Decimal | None
    tax_amount: Decimal | None
    total_amount: Decimal | None
    currency: str | None
    payment_terms: str | None
    po_number: str | None
    is_reviewed: bool
    ocr_confidence: float | None
    invoice_status: str | None


@dataclass(frozen=True)
class PaymentRecord:
    payment_id: str
    supplier_id: str
    payment_date: date | None
    paid_amount: Decimal | None
    payment_currency: str | None
    payment_reference: str | None
    bank_transaction_id_masked: str | None
    payment_status: str | None
    payment_run_id: str | None
    payment_posted_at: date | None
    settlement_event: str | None


@dataclass(frozen=True)
class AllocationRecord:
    allocation_id: str
    invoice_id: str
    payment_id: str
    allocated_amount: Decimal | None
    allocation_status: str | None
    allocation_source: str | None
    settlement_event: str | None


@dataclass(frozen=True)
class PairLabelRecord:
    pair_id: str
    label: str
    label_status: str | None
    rationale_code: str | None
    evidence_source: str | None
    split_name: str | None
    dataset_version: str | None


@dataclass(frozen=True)
class SyntheticPairRecord:
    pair_id: str
    invoice_a: InvoiceRecord
    invoice_b: InvoiceRecord
    supplier_a: SupplierRecord
    supplier_b: SupplierRecord
    payment_a: PaymentRecord | None
    payment_b: PaymentRecord | None
    allocation_a: AllocationRecord | None
    allocation_b: AllocationRecord | None
    extraction_id_a: str | None
    extraction_id_b: str | None
    pair_decision_timestamp: date | None
    dataset_version: str | None
    split_name: str | None


@dataclass(frozen=True)
class PairFeatureRecord:
    pair_id: str
    values: dict[str, str | int | float | bool | None]


@dataclass(frozen=True)
class SyntheticPilotData:
    suppliers: dict[str, SupplierRecord]
    invoices: dict[str, InvoiceRecord]
    payments: dict[str, PaymentRecord]
    allocations: dict[str, AllocationRecord]
    pairs: dict[str, SyntheticPairRecord]
    pair_labels: dict[str, PairLabelRecord]
    pair_features: dict[str, PairFeatureRecord]
    manifest: dict
    validation_report: dict


def _required_text(row: dict[str, str], field: str, record_id: str) -> str:
    value = row.get(field)
    if value is None or not value.strip():
        raise CSVValueError(
            f"{record_id}: missing required field '{field}'"
        )
    return value.strip()


def _optional_text(row: dict[str, str], field: str) -> str | None:
    value = row.get(field)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_decimal(
    row: dict[str, str],
    field: str,
    record_id: str,
) -> Decimal | None:
    value = _optional_text(row, field)
    if value is None:
        return None
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise CSVValueError(
            f"{record_id}: field '{field}' has invalid Decimal value '{value}'"
        ) from exc
    if not parsed.is_finite():
        raise CSVValueError(
            f"{record_id}: field '{field}' must be finite, got '{value}'"
        )
    return parsed


def _parse_allocation_amount(
    row: dict[str, str],
    record_id: str,
) -> Decimal:
    amount = _parse_decimal(row, "allocated_amount", record_id)
    if amount is None:
        raise CSVValueError(
            f"{record_id}: missing required allocation amount"
        )
    if amount <= 0:
        raise CSVValueError(
            f"{record_id}: allocated_amount must be greater than zero"
        )
    return amount


def _validate_currency(
    value: str | None,
    record_id: str,
    field: str,
    *,
    required: bool = False,
) -> str | None:
    if value is None or not value.strip():
        if required:
            raise CSVValueError(
                f"{record_id}: missing required currency field '{field}'"
            )
        return None
    normalized = value.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", normalized):
        raise CSVValueError(
            f"{record_id}: invalid currency '{value}' in '{field}'"
        )
    return normalized


def _parse_date(
    row: dict[str, str],
    field: str,
    record_id: str,
) -> date | None:
    value = _optional_text(row, field)
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CSVValueError(
            f"{record_id}: field '{field}' has invalid date '{value}'"
        ) from exc


def _parse_bool(
    row: dict[str, str],
    field: str,
    record_id: str,
    default: bool = False,
) -> bool:
    value = _optional_text(row, field)
    if value is None:
        return default
    normalized = value.lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise CSVValueError(
        f"{record_id}: field '{field}' has invalid boolean '{value}'"
    )


def _parse_float(
    row: dict[str, str],
    field: str,
    record_id: str,
) -> float | None:
    value = _optional_text(row, field)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise CSVValueError(
            f"{record_id}: field '{field}' has invalid float '{value}'"
        ) from exc


def _read_csv(
    base_dir: Path,
    filename: str,
    required_fields: Iterable[str],
) -> list[dict[str, str]]:
    path = base_dir / filename
    if not path.is_file():
        raise CSVFileNotFoundError(
            f"Required CSV file not found: {path}"
        )

    with path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise CSVSchemaError(
                f"{filename}: CSV header is missing"
            )
        missing = [
            field
            for field in required_fields
            if field not in reader.fieldnames
        ]
        if missing:
            raise CSVSchemaError(
                f"{filename}: missing required columns {missing}"
            )
        return list(reader)


def _add_unique(
    items: dict,
    identifier: str,
    record,
    record_type: str,
) -> None:
    if identifier in items:
        raise CSVRelationshipError(
            f"{record_type}:{identifier}: duplicate primary identifier"
        )
    items[identifier] = record


def load_suppliers(base_dir: str | Path) -> dict[str, SupplierRecord]:
    base = Path(base_dir)
    rows = _read_csv(
        base,
        "suppliers.csv",
        (
            "supplier_id",
            "supplier_name",
            "supplier_name_normalized",
        ),
    )
    suppliers: dict[str, SupplierRecord] = {}
    for row in rows:
        record_id = _required_text(row, "supplier_id", "supplier")
        record = SupplierRecord(
            supplier_id=record_id,
            supplier_name=_required_text(row, "supplier_name", record_id),
            supplier_name_normalized=_required_text(
                row,
                "supplier_name_normalized",
                record_id,
            ),
            supplier_country=_optional_text(row, "supplier_country"),
            supplier_tax_id_masked=_optional_text(
                row,
                "supplier_tax_id_masked",
            ),
            supplier_bank_id_masked=_optional_text(
                row,
                "supplier_bank_id_masked",
            ),
        )
        _add_unique(suppliers, record_id, record, "supplier")
    return suppliers


def load_invoices(
    base_dir: str | Path,
) -> dict[str, InvoiceRecord]:
    base = Path(base_dir)
    rows = _read_csv(
        base,
        "invoices.csv",
        (
            "invoice_id",
            "supplier_id",
            "source_document_id",
            "invoice_number",
            "vendor_name",
        ),
    )
    invoices: dict[str, InvoiceRecord] = {}
    for row in rows:
        record_id = _required_text(row, "invoice_id", "invoice")
        record = InvoiceRecord(
            invoice_id=record_id,
            supplier_id=_required_text(row, "supplier_id", record_id),
            source_document_id=_required_text(
                row,
                "source_document_id",
                record_id,
            ),
            invoice_number=_optional_text(row, "invoice_number"),
            vendor_name=_optional_text(row, "vendor_name"),
            vendor_name_reviewed=_optional_text(
                row,
                "vendor_name_reviewed",
            ),
            invoice_date=_parse_date(row, "invoice_date", record_id),
            due_date=_parse_date(row, "due_date", record_id),
            subtotal=_parse_decimal(row, "subtotal", record_id),
            tax_amount=_parse_decimal(row, "tax_amount", record_id),
            total_amount=_parse_decimal(row, "total_amount", record_id),
            currency=_validate_currency(
                _optional_text(row, "currency"),
                record_id,
                "currency",
                required=True,
            ),
            payment_terms=_optional_text(row, "payment_terms"),
            po_number=_optional_text(row, "po_number"),
            is_reviewed=_parse_bool(row, "is_reviewed", record_id),
            ocr_confidence=_parse_float(
                row,
                "ocr_confidence",
                record_id,
            ),
            invoice_status=_optional_text(row, "invoice_status"),
        )
        for field_name, value in (
            ("subtotal", record.subtotal),
            ("tax_amount", record.tax_amount),
            ("total_amount", record.total_amount),
        ):
            if value is not None and value < 0:
                raise CSVValueError(
                    f"{record_id}: {field_name} must not be negative"
                )
        _add_unique(invoices, record_id, record, "invoice")
    return invoices


def load_payments(
    base_dir: str | Path,
) -> dict[str, PaymentRecord]:
    base = Path(base_dir)
    rows = _read_csv(
        base,
        "payments.csv",
        (
            "payment_id",
            "supplier_id",
            "payment_date",
            "paid_amount",
            "payment_currency",
        ),
    )
    payments: dict[str, PaymentRecord] = {}
    for row in rows:
        record_id = _required_text(row, "payment_id", "payment")
        record = PaymentRecord(
            payment_id=record_id,
            supplier_id=_required_text(row, "supplier_id", record_id),
            payment_date=_parse_date(row, "payment_date", record_id),
            paid_amount=_parse_decimal(row, "paid_amount", record_id),
            payment_currency=_validate_currency(
                _optional_text(row, "payment_currency"),
                record_id,
                "payment_currency",
                required=True,
            ),
            payment_reference=_optional_text(row, "payment_reference"),
            bank_transaction_id_masked=_optional_text(
                row,
                "bank_transaction_id_masked",
            ),
            payment_status=_optional_text(row, "payment_status"),
            payment_run_id=_optional_text(row, "payment_run_id"),
            payment_posted_at=_parse_date(
                row,
                "payment_posted_at",
                record_id,
            ),
            settlement_event=_optional_text(row, "settlement_event"),
        )
        if record.paid_amount is not None and record.paid_amount < 0:
            raise CSVValueError(
                f"{record_id}: paid_amount must not be negative"
            )
        _add_unique(payments, record_id, record, "payment")
    return payments


def load_allocations(
    base_dir: str | Path,
) -> dict[str, AllocationRecord]:
    base = Path(base_dir)
    rows = _read_csv(
        base,
        "allocations.csv",
        (
            "allocation_id",
            "invoice_id",
            "payment_id",
            "allocated_amount",
            "allocation_status",
            "allocation_source",
        ),
    )
    allocations: dict[str, AllocationRecord] = {}
    for row in rows:
        record_id = _required_text(row, "allocation_id", "allocation")
        allocation_status = _optional_text(row, "allocation_status")
        settlement_event = _optional_text(row, "settlement_event")
        valid_statuses = {
            "confirmed_paid",
            "cancelled",
            "reversed",
            "refunded",
            "pending",
        }
        valid_events = {
            "settled",
            "cancelled_before_settlement",
            "reversed_after_settlement",
            "refunded_after_settlement",
            "pending",
        }
        if allocation_status not in valid_statuses:
            raise CSVValueError(
                f"{record_id}: invalid allocation_status "
                f"'{allocation_status}'"
            )
        if settlement_event is not None and settlement_event not in valid_events:
            raise CSVValueError(
                f"{record_id}: invalid settlement_event "
                f"'{settlement_event}'"
            )
        if settlement_event is None:
            raise CSVValueError(
                f"{record_id}: missing settlement_event"
            )

        status_event_pairs = {
            ("confirmed_paid", "settled"),
            ("cancelled", "cancelled_before_settlement"),
            ("reversed", "reversed_after_settlement"),
            ("refunded", "refunded_after_settlement"),
            ("pending", "pending"),
        }
        if (
            settlement_event is not None
            and (allocation_status, settlement_event)
            not in status_event_pairs
        ):
            raise CSVValueError(
                f"{record_id}: contradictory allocation_status "
                f"'{allocation_status}' and settlement_event "
                f"'{settlement_event}'"
            )

        record = AllocationRecord(
            allocation_id=record_id,
            invoice_id=_required_text(row, "invoice_id", record_id),
            payment_id=_required_text(row, "payment_id", record_id),
            allocated_amount=_parse_allocation_amount(row, record_id),
            allocation_status=allocation_status,
            allocation_source=_optional_text(row, "allocation_source"),
            settlement_event=settlement_event,
        )
        _add_unique(
            allocations,
            record_id,
            record,
            "allocation",
        )
    return allocations


def load_pair_labels(
    base_dir: str | Path,
) -> dict[str, PairLabelRecord]:
    base = Path(base_dir)
    rows = _read_csv(
        base,
        "pairs.csv",
        (
            "pair_id",
            "label",
            "label_status",
            "rationale_code",
            "evidence_source",
        ),
    )
    labels: dict[str, PairLabelRecord] = {}
    for row in rows:
        record_id = _required_text(row, "pair_id", "pair")
        label = _required_text(row, "label", record_id)
        if label not in {"duplicate", "not_duplicate", "uncertain"}:
            raise CSVValueError(
                f"{record_id}: invalid label '{label}'"
            )
        record = PairLabelRecord(
            pair_id=record_id,
            label=label,
            label_status=_optional_text(row, "label_status"),
            rationale_code=_optional_text(row, "rationale_code"),
            evidence_source=_optional_text(row, "evidence_source"),
            split_name=_optional_text(row, "split_name"),
            dataset_version=_optional_text(row, "dataset_version"),
        )
        _add_unique(labels, record_id, record, "pair_label")
    return labels


def load_pair_features(
    base_dir: str | Path,
) -> dict[str, PairFeatureRecord]:
    base = Path(base_dir)
    rows = _read_csv(
        base,
        "pair_features.csv",
        FEATURE_CSV_FIELDS,
    )
    features: dict[str, PairFeatureRecord] = {}
    for row in rows:
        record_id = _required_text(row, "pair_id", "pair_feature")
        values: dict[str, str | int | float | bool | None] = {}
        for field in FEATURE_CSV_FIELDS:
            if field == "pair_id":
                continue
            raw = _optional_text(row, field)
            if raw is None:
                values[field] = None
            elif field in {
                "exactAmountMatch",
                "currencyMatch",
                "supplierIdMatch",
                "paidAmountMatch",
                "samePaymentRun",
            }:
                normalized = raw.lower()
                if normalized in {"true", "1", "yes"}:
                    values[field] = True
                elif normalized in {"false", "0", "no"}:
                    values[field] = False
                else:
                    values[field] = None
            elif field in {
                "dateDifferenceDays",
                "vendorOccurrenceCount",
                "invoiceNumberOccurrenceCount",
                "vendorInvoiceOccurrenceCount",
            }:
                try:
                    values[field] = int(raw)
                except ValueError:
                    values[field] = None
            elif field in {
                "amountDifference",
                "partialPaymentRatio",
            }:
                try:
                    parsed = Decimal(raw)
                    values[field] = (
                        parsed
                        if parsed.is_finite()
                        else None
                    )
                except (InvalidOperation, ValueError):
                    values[field] = None
            elif field == "reversalStatusMatch":
                if raw == "reversed_or_refunded":
                    values[field] = 1
                elif raw == "":
                    values[field] = -1
                else:
                    try:
                        values[field] = int(raw)
                    except ValueError:
                        values[field] = -1
            else:
                try:
                    parsed = float(raw)
                    values[field] = (
                        parsed
                        if -float("inf") < parsed < float("inf")
                        else None
                    )
                except ValueError:
                    values[field] = None
        record = PairFeatureRecord(
            pair_id=record_id,
            values=values,
        )
        _add_unique(features, record_id, record, "pair_feature")
    return features


def load_manifest(
    base_dir: str | Path,
) -> dict:
    path = Path(base_dir) / "manifest.json"
    if not path.is_file():
        raise CSVFileNotFoundError(
            f"Required JSON file not found: {path}"
        )
    try:
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
    except json.JSONDecodeError as exc:
        raise CSVValueError(
            f"manifest.json: invalid JSON: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise CSVSchemaError(
            "manifest.json: root value must be an object"
        )
    return value


def load_validation_report(
    base_dir: str | Path,
) -> dict:
    path = Path(base_dir) / "validation_report.json"
    if not path.is_file():
        raise CSVFileNotFoundError(
            f"Required JSON file not found: {path}"
        )
    try:
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
    except json.JSONDecodeError as exc:
        raise CSVValueError(
            f"validation_report.json: invalid JSON: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise CSVSchemaError(
            "validation_report.json: root value must be an object"
        )
    return value


def build_candidate_pairs(
    base_dir: str | Path,
    invoices: dict[str, InvoiceRecord],
    suppliers: dict[str, SupplierRecord],
    payments: dict[str, PaymentRecord],
    allocations: dict[str, AllocationRecord],
) -> dict[str, SyntheticPairRecord]:
    base = Path(base_dir)
    rows = _read_csv(
        base,
        "pairs.csv",
        (
            "pair_id",
            "invoice_id_a",
            "invoice_id_b",
            "supplier_id_a",
            "supplier_id_b",
        ),
    )
    pairs: dict[str, SyntheticPairRecord] = {}
    allocation_by_relationship = {
        (allocation.invoice_id, allocation.payment_id): allocation
        for allocation in allocations.values()
    }

    for row in rows:
        record_id = _required_text(row, "pair_id", "pair")
        invoice_id_a = _required_text(
            row,
            "invoice_id_a",
            record_id,
        )
        invoice_id_b = _required_text(
            row,
            "invoice_id_b",
            record_id,
        )

        invoice_a = invoices.get(invoice_id_a)
        invoice_b = invoices.get(invoice_id_b)
        if invoice_a is None:
            raise CSVRelationshipError(
                f"{record_id}: invoice_id_a '{invoice_id_a}' "
                "does not reference an invoice"
            )
        if invoice_b is None:
            raise CSVRelationshipError(
                f"{record_id}: invoice_id_b '{invoice_id_b}' "
                "does not reference an invoice"
            )

        supplier_id_a = _required_text(
            row,
            "supplier_id_a",
            record_id,
        )
        supplier_id_b = _required_text(
            row,
            "supplier_id_b",
            record_id,
        )
        supplier_a = suppliers.get(supplier_id_a)
        supplier_b = suppliers.get(supplier_id_b)
        if supplier_a is None:
            raise CSVRelationshipError(
                f"{record_id}: supplier_id_a '{supplier_id_a}' "
                "does not reference a supplier"
            )
        if supplier_b is None:
            raise CSVRelationshipError(
                f"{record_id}: supplier_id_b '{supplier_id_b}' "
                "does not reference a supplier"
            )
        if invoice_a.supplier_id != supplier_id_a:
            raise CSVRelationshipError(
                f"{record_id}: invoice_id_a '{invoice_id_a}' "
                f"belongs to '{invoice_a.supplier_id}', "
                f"not pair supplier '{supplier_id_a}'"
            )
        if invoice_b.supplier_id != supplier_id_b:
            raise CSVRelationshipError(
                f"{record_id}: invoice_id_b '{invoice_id_b}' "
                f"belongs to '{invoice_b.supplier_id}', "
                f"not pair supplier '{supplier_id_b}'"
            )

        payment_id_a = _optional_text(row, "payment_id_a")
        payment_id_b = _optional_text(row, "payment_id_b")
        allocation_id_a = _optional_text(row, "allocation_id_a")
        allocation_id_b = _optional_text(row, "allocation_id_b")

        payment_a = (
            payments.get(payment_id_a)
            if payment_id_a
            else None
        )
        payment_b = (
            payments.get(payment_id_b)
            if payment_id_b
            else None
        )
        if payment_id_a and payment_a is None:
            raise CSVRelationshipError(
                f"{record_id}: payment_id_a '{payment_id_a}' "
                "does not reference a payment"
            )
        if payment_id_b and payment_b is None:
            raise CSVRelationshipError(
                f"{record_id}: payment_id_b '{payment_id_b}' "
                "does not reference a payment"
            )

        allocation_a = (
            allocations.get(allocation_id_a)
            if allocation_id_a
            else None
        )
        allocation_b = (
            allocations.get(allocation_id_b)
            if allocation_id_b
            else None
        )
        if allocation_id_a and allocation_a is None:
            raise CSVRelationshipError(
                f"{record_id}: allocation_id_a '{allocation_id_a}' "
                "does not reference an allocation"
            )
        if allocation_id_b and allocation_b is None:
            raise CSVRelationshipError(
                f"{record_id}: allocation_id_b '{allocation_id_b}' "
                "does not reference an allocation"
            )

        if allocation_a is not None:
            relationship = allocation_by_relationship.get(
                (allocation_a.invoice_id, allocation_a.payment_id)
            )
            if relationship is None:
                raise CSVRelationshipError(
                    f"{record_id}: allocation_id_a "
                    f"'{allocation_a.allocation_id}' has no valid "
                    "invoice/payment relationship"
                )
            if (
                allocation_a.invoice_id != invoice_id_a
                or allocation_a.payment_id != payment_id_a
            ):
                raise CSVRelationshipError(
                    f"{record_id}: allocation_id_a "
                    f"'{allocation_a.allocation_id}' does not reference "
                    f"invoice '{invoice_id_a}' and payment "
                    f"'{payment_id_a}'"
                )
        if allocation_b is not None:
            relationship = allocation_by_relationship.get(
                (allocation_b.invoice_id, allocation_b.payment_id)
            )
            if relationship is None:
                raise CSVRelationshipError(
                    f"{record_id}: allocation_id_b "
                    f"'{allocation_b.allocation_id}' has no valid "
                    "invoice/payment relationship"
                )
            if (
                allocation_b.invoice_id != invoice_id_b
                or allocation_b.payment_id != payment_id_b
            ):
                raise CSVRelationshipError(
                    f"{record_id}: allocation_id_b "
                    f"'{allocation_b.allocation_id}' does not reference "
                    f"invoice '{invoice_id_b}' and payment "
                    f"'{payment_id_b}'"
                )

        record = SyntheticPairRecord(
            pair_id=record_id,
            invoice_a=invoice_a,
            invoice_b=invoice_b,
            supplier_a=supplier_a,
            supplier_b=supplier_b,
            payment_a=payment_a,
            payment_b=payment_b,
            allocation_a=allocation_a,
            allocation_b=allocation_b,
            extraction_id_a=_optional_text(row, "extraction_id_a"),
            extraction_id_b=_optional_text(row, "extraction_id_b"),
            pair_decision_timestamp=_parse_date(
                row,
                "pair_decision_timestamp",
                record_id,
            ),
            dataset_version=_optional_text(row, "dataset_version"),
            split_name=_optional_text(row, "split_name"),
        )
        _add_unique(pairs, record_id, record, "pair")
    return pairs


def validate_relationships(
    suppliers: dict[str, SupplierRecord],
    invoices: dict[str, InvoiceRecord],
    payments: dict[str, PaymentRecord],
    allocations: dict[str, AllocationRecord],
    pairs: dict[str, SyntheticPairRecord],
    pair_labels: dict[str, PairLabelRecord],
) -> list[str]:
    errors: list[str] = []

    for invoice in invoices.values():
        if invoice.supplier_id not in suppliers:
            errors.append(
                f"invoice:{invoice.invoice_id}: supplier "
                f"{invoice.supplier_id} does not exist"
            )
        if (
            invoice.subtotal is not None
            and invoice.tax_amount is not None
            and invoice.total_amount is not None
            and invoice.subtotal + invoice.tax_amount
            != invoice.total_amount
        ):
            errors.append(
                f"invoice:{invoice.invoice_id}: subtotal + tax "
                f"{invoice.subtotal + invoice.tax_amount} != "
                f"total {invoice.total_amount}"
            )

    for payment in payments.values():
        if payment.supplier_id not in suppliers:
            errors.append(
                f"payment:{payment.payment_id}: supplier "
                f"{payment.supplier_id} does not exist"
            )

    allocations_by_payment: dict[str, list[AllocationRecord]] = {}
    for allocation in allocations.values():
        invoice = invoices.get(allocation.invoice_id)
        if invoice is None:
            errors.append(
                f"allocation:{allocation.allocation_id}: invoice "
                f"{allocation.invoice_id} does not exist"
            )
        payment = payments.get(allocation.payment_id)
        if payment is None:
            errors.append(
                f"allocation:{allocation.allocation_id}: payment "
                f"{allocation.payment_id} does not exist"
            )
        if invoice is not None and payment is not None:
            if invoice.supplier_id != payment.supplier_id:
                errors.append(
                    f"allocation:{allocation.allocation_id}: invoice "
                    f"supplier {invoice.supplier_id} != payment "
                    f"supplier {payment.supplier_id}"
                )
            if (
                invoice.currency is not None
                and payment.payment_currency is not None
                and invoice.currency != payment.payment_currency
            ):
                errors.append(
                    f"allocation:{allocation.allocation_id}: invoice "
                    f"currency {invoice.currency} != payment "
                    f"currency {payment.payment_currency}"
                )
            if allocation.allocated_amount is not None:
                if allocation.allocated_amount <= 0:
                    errors.append(
                        f"allocation:{allocation.allocation_id}: "
                        "allocated_amount must be greater than zero"
                    )

        status_event_pairs = {
            ("confirmed_paid", "settled"),
            ("cancelled", "cancelled_before_settlement"),
            ("reversed", "reversed_after_settlement"),
            ("refunded", "refunded_after_settlement"),
            ("pending", "pending"),
        }
        if (
            allocation.allocation_status is not None
            and allocation.settlement_event is not None
            and (
                allocation.allocation_status,
                allocation.settlement_event,
            )
            not in status_event_pairs
        ):
            errors.append(
                f"allocation:{allocation.allocation_id}: contradictory "
                f"status '{allocation.allocation_status}' and "
                f"settlement event '{allocation.settlement_event}'"
            )
        allocations_by_payment.setdefault(
            allocation.payment_id,
            [],
        ).append(allocation)

    allocations_by_invoice: dict[str, list[AllocationRecord]] = {}
    for allocation in allocations.values():
        allocations_by_invoice.setdefault(
            allocation.invoice_id,
            [],
        ).append(allocation)

    for invoice in invoices.values():
        if invoice.total_amount is None:
            continue
        eligible_allocated_total = Decimal("0")
        for allocation in allocations_by_invoice.get(
            invoice.invoice_id,
            [],
        ):
            if (
                allocation.allocated_amount is not None
                and allocation.allocation_status
                in {"confirmed_paid", "reversed", "refunded"}
            ):
                eligible_allocated_total += allocation.allocated_amount
        if eligible_allocated_total > invoice.total_amount:
            errors.append(
                f"invoice:{invoice.invoice_id}: allocations "
                f"{eligible_allocated_total} exceed invoice total "
                f"{invoice.total_amount}"
            )

    for payment in payments.values():
        if payment.paid_amount is None:
            continue
        allocated_total = Decimal("0")
        for allocation in allocations_by_payment.get(
            payment.payment_id,
            [],
        ):
            if (
                allocation.allocated_amount is not None
                and allocation.allocation_status
                in {"confirmed_paid", "reversed", "refunded"}
            ):
                allocated_total += allocation.allocated_amount
        if allocated_total > payment.paid_amount:
            errors.append(
                f"payment:{payment.payment_id}: allocations "
                f"{allocated_total} exceed paid amount "
                f"{payment.paid_amount}"
            )

    for pair_id, pair in pairs.items():
        label = pair_labels.get(pair_id)
        if label is None:
            errors.append(
                f"pair:{pair_id}: missing pair label"
            )
        elif label.label not in {
            "duplicate",
            "not_duplicate",
            "uncertain",
        }:
            errors.append(
                f"pair:{pair_id}: invalid label '{label.label}'"
            )

        if pair.supplier_a.supplier_id != pair.invoice_a.supplier_id:
            errors.append(
                f"pair:{pair_id}: supplier A "
                f"{pair.supplier_a.supplier_id} != invoice A "
                f"supplier {pair.invoice_a.supplier_id}"
            )
        if pair.supplier_b.supplier_id != pair.invoice_b.supplier_id:
            errors.append(
                f"pair:{pair_id}: supplier B "
                f"{pair.supplier_b.supplier_id} != invoice B "
                f"supplier {pair.invoice_b.supplier_id}"
            )

        if pair.payment_a is not None:
            if pair.payment_a.supplier_id != pair.invoice_a.supplier_id:
                errors.append(
                    f"pair:{pair_id}: payment A "
                    f"{pair.payment_a.payment_id} supplier "
                    f"{pair.payment_a.supplier_id} != invoice A "
                    f"supplier {pair.invoice_a.supplier_id}"
                )
        if pair.payment_b is not None:
            if pair.payment_b.supplier_id != pair.invoice_b.supplier_id:
                errors.append(
                    f"pair:{pair_id}: payment B "
                    f"{pair.payment_b.payment_id} supplier "
                    f"{pair.payment_b.supplier_id} != invoice B "
                    f"supplier {pair.invoice_b.supplier_id}"
                )

        label_value = label.label if label is not None else None
        if label_value != "uncertain":
            if pair.payment_a is None or pair.payment_b is None:
                errors.append(
                    f"pair:{pair_id}: binary pair missing payment evidence"
                )
            if pair.allocation_a is None or pair.allocation_b is None:
                errors.append(
                    f"pair:{pair_id}: binary pair missing allocation evidence"
                )

    return errors


def load_synthetic_pilot(
    base_dir: str | Path,
) -> SyntheticPilotData:
    base = Path(base_dir)
    if not base.is_dir():
        raise CSVFileNotFoundError(
            f"Pilot dataset directory not found: {base}"
        )

    suppliers = load_suppliers(base)
    invoices = load_invoices(base)
    payments = load_payments(base)
    allocations = load_allocations(base)
    pair_labels = load_pair_labels(base)
    pairs = build_candidate_pairs(
        base,
        invoices,
        suppliers,
        payments,
        allocations,
    )
    pair_features = load_pair_features(base)

    try:
        manifest = load_manifest(base)
    except CSVFileNotFoundError:
        manifest = {}
    try:
        validation_report = load_validation_report(base)
    except CSVFileNotFoundError:
        validation_report = {}

    relationship_errors = validate_relationships(
        suppliers,
        invoices,
        payments,
        allocations,
        pairs,
        pair_labels,
    )
    if relationship_errors:
        raise CSVRelationshipError(
            "Synthetic pilot relationship validation failed:\n"
            + "\n".join(relationship_errors)
        )

    for pair_id in pair_features:
        if pair_id not in pairs:
            raise CSVRelationshipError(
                f"pair_feature:{pair_id}: pair does not exist"
            )

    return SyntheticPilotData(
        suppliers=suppliers,
        invoices=invoices,
        payments=payments,
        allocations=allocations,
        pairs=pairs,
        pair_labels=pair_labels,
        pair_features=pair_features,
        manifest=manifest,
        validation_report=validation_report,
    )
