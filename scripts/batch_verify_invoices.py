"""Read-only batch verification for invoice records and their uploaded PDFs."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import bindparam, text

from app.core.config import settings
from app.core.database import engine
from app.utils.invoice_paths import (
    InvalidInvoicePathError,
    InvoiceFileAccessError,
    InvoiceFileNotFoundError,
    resolve_invoice_path,
)


MANDATORY_FIELDS = {
    "invoiceNumber": "invoice_number",
    "vendorName": "vendor_name",
    "invoiceDate": "invoice_date",
    "subtotal": "subtotal",
    "taxAmount": "tax_amount",
    "totalAmount": "total_amount",
    "currency": "currency",
}
OPTIONAL_FIELDS = {
    "paymentTerms": "payment_terms",
    "poNumber": "po_number",
    "vendorGst": "vendor_gst",
    "shippingCharges": "shipping_charges",
    "discount": "discount",
    "vendorAddress": "vendor_address",
    "paymentReference": "payment_reference",
}
SUCCESS_STATUSES = {"processed", "reviewed"}
AMOUNT_TOLERANCE = Decimal("0.01")
CSV_FIELDS = [
    "invoice_id",
    "file_name",
    "file_path",
    "processing_status",
    "processed_at",
    "extraction_record_exists",
    "extraction_record_count",
    "pdf_exists",
    "pdf_check",
    "invoice_number",
    "vendor_name",
    "invoice_date",
    "due_date",
    "subtotal",
    "tax_amount",
    "total_amount",
    "amount_difference",
    "currency",
    "payment_terms",
    "po_number",
    "vendor_gst",
    "shipping_charges",
    "discount",
    "vendor_address",
    "payment_reference",
    "confidence_score",
    "field_confidence_json",
    "is_reviewed",
    "missing_mandatory_fields",
    "low_confidence_fields",
    "optional_field_statuses",
    "duplicate_invoice_number_candidate",
    "duplicate_candidate_invoice_ids",
    "verification_status",
    "exception_count",
    "exception_types",
]
EXCEPTION_FIELDS = [
    "invoice_id",
    "file_name",
    "exception_type",
    "field",
    "details",
]


QUERY = """
WITH ranked_extractions AS (
    SELECT e.*,
           count(*) OVER (PARTITION BY e."invoiceId") AS extraction_record_count,
           row_number() OVER (
               PARTITION BY e."invoiceId"
               ORDER BY e."updatedAt" DESC NULLS LAST,
                        e."createdAt" DESC NULLS LAST,
                        e.id DESC
           ) AS extraction_rank
    FROM public.extracted_invoice_data AS e
),
latest_extractions AS (
    SELECT *
    FROM ranked_extractions
    WHERE extraction_rank = 1
),
duplicate_numbers AS (
    SELECT lower(btrim(e."invoiceNumber")) AS normalized_invoice_number,
           count(*) AS duplicate_count,
           array_agg(e."invoiceId" ORDER BY e."invoiceId") AS candidate_invoice_ids
    FROM latest_extractions AS e
    WHERE nullif(btrim(e."invoiceNumber"), '') IS NOT NULL
    GROUP BY lower(btrim(e."invoiceNumber"))
    HAVING count(*) > 1
)
SELECT i.id AS invoice_id,
       i."fileName" AS file_name,
       i."filePath" AS file_path,
       i."processingStatus" AS processing_status,
       i."processedAt" AS processed_at,
       e.id AS extraction_id,
       coalesce(e.extraction_record_count, 0) AS extraction_record_count,
       e."invoiceNumber" AS invoice_number,
       e."vendorName" AS vendor_name,
       e."invoiceDate" AS invoice_date,
       e."dueDate" AS due_date,
       e.subtotal,
       e."taxAmount" AS tax_amount,
       e."totalAmount" AS total_amount,
       e.currency,
       e."extractedFieldsJson" AS extracted_fields_json,
       e."confidenceJson" AS confidence_json,
       e."confidenceScore" AS confidence_score,
       e."isReviewed" AS is_reviewed,
       d.duplicate_count AS duplicate_invoice_number_count,
       d.candidate_invoice_ids AS duplicate_candidate_invoice_ids
FROM public.invoices AS i
LEFT JOIN latest_extractions AS e
       ON e."invoiceId" = i.id
LEFT JOIN duplicate_numbers AS d
       ON d.normalized_invoice_number = lower(btrim(e."invoiceNumber"))
"""


def _parse_invoice_ids(values: list[str] | None) -> list[int] | None:
    if not values:
        return None

    parsed: set[int] = set()
    try:
        for value in values:
            for item in value.split(","):
                invoice_id = int(item.strip())
                if invoice_id <= 0:
                    raise ValueError("Invoice IDs must be positive integers.")
                parsed.add(invoice_id)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Invoice IDs must be positive integers, separated by spaces or commas."
        ) from exc

    if not parsed:
        raise argparse.ArgumentTypeError("Provide at least one invoice ID.")
    return sorted(parsed)


def _json_object(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        decoded = json.loads(value)
        if isinstance(decoded, dict):
            return decoded
    raise ValueError("Expected a JSON object or null.")


def _is_present(value: Any) -> bool:
    return value is not None and not (
        isinstance(value, str) and not value.strip()
    )


def _format_value(value: Any) -> Any:
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if hasattr(value, "isoformat") and callable(value.isoformat):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    return value


def _exception(
    exceptions: list[dict[str, Any]],
    row: dict[str, Any],
    exception_type: str,
    details: str,
    field: str = "",
) -> None:
    exceptions.append(
        {
            "invoice_id": row["invoice_id"],
            "file_name": row["file_name"] or "",
            "exception_type": exception_type,
            "field": field,
            "details": details,
        }
    )


def _check_pdf(row: dict[str, Any], exceptions: list[dict[str, Any]]) -> tuple[bool, str]:
    try:
        resolve_invoice_path(row["file_path"])
        return True, "present"
    except InvoiceFileNotFoundError:
        _exception(exceptions, row, "missing_pdf", "PDF file does not exist.")
        return False, "missing"
    except InvalidInvoicePathError as exc:
        _exception(exceptions, row, "invalid_pdf_path", str(exc))
        return False, "invalid_path"
    except InvoiceFileAccessError as exc:
        _exception(exceptions, row, "pdf_access_error", str(exc))
        return False, "access_error"


def _verify_row(
    row: dict[str, Any],
    confidence_threshold: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    exceptions: list[dict[str, Any]] = []
    extraction_exists = row["extraction_id"] is not None
    pdf_exists, pdf_check = _check_pdf(row, exceptions)

    status = (row["processing_status"] or "").strip()
    if status.lower() not in SUCCESS_STATUSES:
        _exception(
            exceptions,
            row,
            "processing_status",
            f"Processing status is {status or 'missing'}, not Processed or Reviewed.",
            "processingStatus",
        )

    if not extraction_exists:
        _exception(
            exceptions,
            row,
            "missing_extraction",
            "No extracted_invoice_data row exists for this invoice.",
        )
    elif row["extraction_record_count"] > 1:
        _exception(
            exceptions,
            row,
            "multiple_extractions",
            f'{row["extraction_record_count"]} extraction rows exist; the latest was selected.',
        )

    missing_fields: list[str] = []
    field_values = {
        "invoiceNumber": row["invoice_number"],
        "vendorName": row["vendor_name"],
        "invoiceDate": row["invoice_date"],
        "dueDate": row["due_date"],
        "subtotal": row["subtotal"],
        "taxAmount": row["tax_amount"],
        "totalAmount": row["total_amount"],
        "currency": row["currency"],
    }
    for field_name, column_name in MANDATORY_FIELDS.items():
        if not _is_present(field_values[field_name]):
            missing_fields.append(field_name)
            _exception(
                exceptions,
                row,
                "missing_mandatory_field",
                f"Mandatory field {field_name} is missing.",
                column_name,
            )

    amount_difference: Decimal | None = None
    amounts = (row["subtotal"], row["tax_amount"], row["total_amount"])
    if all(amount is not None for amount in amounts):
        amount_difference = amounts[0] + amounts[1] - amounts[2]
        if abs(amount_difference) > AMOUNT_TOLERANCE:
            _exception(
                exceptions,
                row,
                "financial_mismatch",
                "Subtotal plus tax does not equal total "
                f"(difference: {amount_difference}).",
                "subtotal,taxAmount,totalAmount",
            )

    try:
        extracted_fields = _json_object(row["extracted_fields_json"])
    except (json.JSONDecodeError, ValueError) as exc:
        extracted_fields = {}
        _exception(
            exceptions,
            row,
            "invalid_extracted_fields_json",
            f"Could not read extractedFieldsJson as an object: {exc}",
            "extractedFieldsJson",
        )
    try:
        confidence = _json_object(row["confidence_json"])
    except (json.JSONDecodeError, ValueError) as exc:
        confidence = {}
        _exception(
            exceptions,
            row,
            "invalid_confidence_json",
            f"Could not read confidenceJson as an object: {exc}",
            "confidenceJson",
        )

    low_confidence: list[str] = []
    for field_name, value in confidence.items():
        extracted_value = field_values.get(field_name)
        if not _is_present(extracted_value):
            extracted_value = extracted_fields.get(field_name)
        if not _is_present(extracted_value):
            continue
        try:
            score = float(value)
        except (TypeError, ValueError):
            _exception(
                exceptions,
                row,
                "invalid_confidence_score",
                f"Confidence score {value!r} is not numeric.",
                str(field_name),
            )
            continue
        if score < confidence_threshold:
            low_confidence.append(str(field_name))
            _exception(
                exceptions,
                row,
                "low_confidence",
                f"Confidence {score:.3f} is below threshold {confidence_threshold:.3f}.",
                str(field_name),
            )

    for field_name in MANDATORY_FIELDS:
        if _is_present(field_values[field_name]) and field_name not in confidence:
            _exception(
                exceptions,
                row,
                "missing_confidence",
                f"No field-level confidence score exists for {field_name}.",
                field_name,
            )

    duplicate_count = row["duplicate_invoice_number_count"] or 0
    duplicate_ids = row["duplicate_candidate_invoice_ids"] or []
    if duplicate_count > 1:
        _exception(
            exceptions,
            row,
            "duplicate_invoice_number_candidate",
            "Invoice number repeats across invoice records; this is a candidate, "
            "not a confirmed duplicate payment.",
            "invoiceNumber",
        )

    optional_field_statuses = {
        field_name: (
            "Present" if _is_present(extracted_fields.get(field_name)) else "Not Present"
        )
        for field_name in OPTIONAL_FIELDS
    }

    row_exceptions = [item["exception_type"] for item in exceptions]
    output = {
        "invoice_id": row["invoice_id"],
        "file_name": row["file_name"],
        "file_path": row["file_path"],
        "processing_status": status,
        "processed_at": _format_value(row["processed_at"]),
        "extraction_record_exists": extraction_exists,
        "extraction_record_count": row["extraction_record_count"],
        "pdf_exists": pdf_exists,
        "pdf_check": pdf_check,
        "invoice_number": row["invoice_number"],
        "vendor_name": row["vendor_name"],
        "invoice_date": _format_value(row["invoice_date"]),
        "due_date": _format_value(row["due_date"]),
        "subtotal": _format_value(row["subtotal"]),
        "tax_amount": _format_value(row["tax_amount"]),
        "total_amount": _format_value(row["total_amount"]),
        "amount_difference": _format_value(amount_difference),
        "currency": row["currency"],
        "payment_terms": extracted_fields.get("paymentTerms"),
        "po_number": extracted_fields.get("poNumber"),
        "vendor_gst": extracted_fields.get("vendorGst"),
        "shipping_charges": extracted_fields.get("shippingCharges"),
        "discount": extracted_fields.get("discount"),
        "vendor_address": extracted_fields.get("vendorAddress"),
        "payment_reference": extracted_fields.get("paymentReference"),
        "confidence_score": row["confidence_score"],
        "field_confidence_json": confidence,
        "is_reviewed": row["is_reviewed"],
        "missing_mandatory_fields": missing_fields,
        "low_confidence_fields": low_confidence,
        "optional_field_statuses": optional_field_statuses,
        "duplicate_invoice_number_candidate": duplicate_count > 1,
        "duplicate_candidate_invoice_ids": duplicate_ids,
        "verification_status": "REVIEW" if exceptions else "PASS",
        "exception_count": len(exceptions),
        "exception_types": sorted(set(row_exceptions)),
    }
    return output, exceptions


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: _format_value(value)
                    for key, value in row.items()
                }
            )


def _build_summary(
    report_rows: list[dict[str, Any]],
    exceptions: list[dict[str, Any]],
    confidence_threshold: float,
    report_path: Path,
    exceptions_path: Path,
) -> dict[str, Any]:
    counts = Counter(item["exception_type"] for item in exceptions)
    duplicate_groups = {
        tuple(row["duplicate_candidate_invoice_ids"])
        for row in report_rows
        if row["duplicate_invoice_number_candidate"]
    }
    return {
        "total_invoices_checked": len(report_rows),
        "successfully_processed_invoices": sum(
            (row["processing_status"] or "").lower() in SUCCESS_STATUSES
            for row in report_rows
        ),
        "missing_extraction_records": counts["missing_extraction"],
        "missing_pdf_files": counts["missing_pdf"],
        "invoices_with_missing_mandatory_fields": len(
            {
                item["invoice_id"]
                for item in exceptions
                if item["exception_type"] == "missing_mandatory_field"
            }
        ),
        "missing_mandatory_field_count": counts["missing_mandatory_field"],
        "financial_mismatch_invoices": counts["financial_mismatch"],
        "duplicate_invoice_number_candidate_groups": len(duplicate_groups),
        "duplicate_candidate_invoice_records": counts[
            "duplicate_invoice_number_candidate"
        ],
        "low_confidence_fields": counts["low_confidence"],
        "populated_low_confidence_fields": counts["low_confidence"],
        "optional_fields_not_present": sum(
            status == "Not Present"
            for row in report_rows
            for status in row["optional_field_statuses"].values()
        ),
        "missing_field_confidence_scores": counts["missing_confidence"],
        "other_exceptions": {
            key: value
            for key, value in sorted(counts.items())
            if key
            not in {
                "missing_extraction",
                "missing_pdf",
                "missing_mandatory_field",
                "financial_mismatch",
                "duplicate_invoice_number_candidate",
                "low_confidence",
                "missing_confidence",
            }
        },
        "confidence_threshold": confidence_threshold,
        "amount_tolerance": str(AMOUNT_TOLERANCE),
        "upload_directory": settings.UPLOAD_DIR,
        "report_csv": str(report_path),
        "exceptions_csv": str(exceptions_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only verification of invoice database rows and uploaded PDFs."
    )
    parser.add_argument(
        "--invoice-ids",
        nargs="+",
        help="Optional IDs to report (space- or comma-separated, e.g. 66 67 or 66,67).",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.70,
        help="Field-confidence scores below this value are flagged (default: 0.70).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Main CSV path. Defaults to reports/invoice_batch_verification_<timestamp>.csv.",
    )
    args = parser.parse_args()

    if not 0 <= args.confidence_threshold <= 1:
        parser.error("--confidence-threshold must be between 0 and 1.")
    try:
        invoice_ids = _parse_invoice_ids(args.invoice_ids)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    if engine.dialect.name != "postgresql":
        parser.error(
            f"Expected PostgreSQL for read-only transaction enforcement; found {engine.dialect.name}."
        )

    query = QUERY
    parameters: dict[str, Any] = {}
    statement = text(query)
    if invoice_ids is not None:
        query += '\nWHERE i.id IN :invoice_ids'
        statement = text(query).bindparams(bindparam("invoice_ids", expanding=True))
        parameters["invoice_ids"] = invoice_ids
    statement = statement.columns()

    with engine.connect() as connection:
        with connection.begin():
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            source_rows = [
                dict(row)
                for row in connection.execute(statement, parameters).mappings().all()
            ]

    verified_rows: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []
    for row in source_rows:
        report_row, row_exceptions = _verify_row(row, args.confidence_threshold)
        verified_rows.append(report_row)
        exceptions.extend(row_exceptions)

    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    report_path = (
        args.output.resolve()
        if args.output
        else (PROJECT_ROOT / "reports" / f"invoice_batch_verification_{timestamp}.csv")
    )
    exceptions_path = report_path.with_name(f"{report_path.stem}_exceptions.csv")
    summary_path = report_path.with_name(f"{report_path.stem}_summary.json")

    _write_csv(report_path, CSV_FIELDS, verified_rows)
    _write_csv(exceptions_path, EXCEPTION_FIELDS, exceptions)
    summary = _build_summary(
        verified_rows,
        exceptions,
        args.confidence_threshold,
        report_path,
        exceptions_path,
    )
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Summary JSON: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
