import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from dateutil import parser as date_parser


INVOICE_NUMBER_PATTERNS = [
    r"\binvoice\s*(?:number|no\.?|#)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-\/]+)",
    r"\binv\s*(?:number|no\.?|#)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-\/]+)",
    r"\bbill\s*(?:number|no\.?|#)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-\/]+)"
]

INVOICE_DATE_PATTERNS = [
    r"\binvoice\s*date\s*[:\-]?\s*([0-9A-Za-z,\-\/ ]{6,25})",
    r"\bbill\s*date\s*[:\-]?\s*([0-9A-Za-z,\-\/ ]{6,25})",
    r"\bdate\s*of\s*invoice\s*[:\-]?\s*([0-9A-Za-z,\-\/ ]{6,25})"
]

DUE_DATE_PATTERNS = [
    r"\bdue\s*date\s*[:\-]?\s*([0-9A-Za-z,\-\/ ]{6,25})",
    r"\bpayment\s*due\s*[:\-]?\s*([0-9A-Za-z,\-\/ ]{6,25})"
]

SUBTOTAL_PATTERNS = [
    r"\bsub\s*total\s*[:\-]?\s*(?:INR|USD|EUR|Rs\.?|₹|\$|€)?\s*([\d,]+(?:\.\d{1,2})?)"
]

TOTAL_AMOUNT_PATTERNS = [
    (
        r"\bnet\s+amount\s*[:\-]?\s*"
        r"(?:INR|USD|EUR|GBP|Rs\.?|₹|\$|€|£)?\s*"
        r"([\d,]+(?:\.\d{1,2})?)"
    ),
    (
        r"\bbill\s+amount\s*[:\-]?\s*"
        r"(?:INR|USD|EUR|GBP|Rs\.?|₹|\$|€|£)?\s*"
        r"([\d,]+(?:\.\d{1,2})?)"
    ),
    (
        r"\btotal\s+amount\s+due\s*[:\-]?\s*"
        r"(?:INR|USD|EUR|GBP|Rs\.?|₹|\$|€|£)?\s*"
        r"([\d,]+(?:\.\d{1,2})?)"
    ),
    (
        r"\bgrand\s+total\s*[:\-]?\s*"
        r"(?:INR|USD|EUR|GBP|Rs\.?|₹|\$|€|£)?\s*"
        r"([\d,]+(?:\.\d{1,2})?)"
    ),
    (
        r"\bamount\s+payable\s*[:\-]?\s*"
        r"(?:INR|USD|EUR|GBP|Rs\.?|₹|\$|€|£)?\s*"
        r"([\d,]+(?:\.\d{1,2})?)"
    ),
    (
        r"\bdue\s+amount\s*[:\-]?\s*"
        r"(?:INR|USD|EUR|GBP|Rs\.?|₹|\$|€|£)?\s*"
        r"([\d,]+(?:\.\d{1,2})?)"
    ),
    (
        r"\bbalance\s+due\s*[:\-]?\s*"
        r"(?:INR|USD|EUR|GBP|Rs\.?|₹|\$|€|£)?\s*"
        r"([\d,]+(?:\.\d{1,2})?)"
    ),
    (
        r"\btotal\s+amount\s*[:\-]?\s*"
        r"(?:INR|USD|EUR|GBP|Rs\.?|₹|\$|€|£)?\s*"
        r"([\d,]+(?:\.\d{1,2})?)"
    ),
    (
        r"(?im)^\s*total\s*[:\-]\s*"
        r"(?:INR|USD|EUR|GBP|Rs\.?|₹|\$|€|£)?\s*"
        r"([\d,]+(?:\.\d{1,2})?)\s*$"
    )
]

VENDOR_LABEL_PATTERNS = [
    r"\bvendor\s+name\s*(?:[:\-]\s*)?(.+)",
    r"\bsupplier\s+name\s*(?:[:\-]\s*)?(.+)",
    r"\bseller\s+name\s*(?:[:\-]\s*)?(.+)",
    r"\bvendor\s*(?:[:\-]\s*)?(.+)",
    r"\bsupplier\s*(?:[:\-]\s*)?(.+)",
    r"\bseller\s*(?:[:\-]\s*)?(.+)",
    r"\bfrom\s*(?:[:\-]\s*)?(.+)"
]

VENDOR_GST_PATTERNS = [
    (
        r"\b(?:vendor\s*)?(?:gst|gstin|gst\s*number)"
        r"\s*(?:[:\-]\s*)?"
        r"([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z])"
    )
]

COMPANY_KEYWORDS = (
    "private limited",
    "pvt ltd",
    "pvt. ltd",
    "limited",
    "ltd",
    "llp",
    "inc",
    "corporation",
    "corp",
    "company"
)

VENDOR_LABELS = (
    "vendor name",
    "supplier name",
    "seller name",
    "company name",
    "vendor",
    "supplier",
    "seller",
    "from"
)

VENDOR_STOP_LABELS = (
    "vendor gst",
    "gstin",
    "gst number",
    "po number",
    "purchase order",
    "invoice number",
    "invoice no",
    "invoice date",
    "due date",
    "currency",
    "payment terms",
    "subtotal",
    "sub total",
    "tax amount",
    "total tax",
    "total amount",
    "grand total",
    "amount payable"
)

COMPANY_SUFFIX_LINES = {
    "ltd",
    "ltd.",
    "limited",
    "pvt ltd",
    "pvt. ltd",
    "pvt. ltd.",
    "private limited",
    "llp",
    "inc",
    "inc."
}

TAX_PATTERNS = [
    (
        r"\btax\s*\(\s*\d+(?:\.\d+)?%\s*\)\s*"
        r"[:\-]?\s*"
        r"(?:INR|USD|EUR|GBP|Rs\.?|₹|\$|€|£)?\s*"
        r"([\d,]+(?:\.\d{1,2})?)"
    ),
    (
        r"\b(?:tax\s+amount|total\s+tax|"
        r"total\s+gst|gst\s+amount|vat\s+amount)"
        r"\s*[:\-]?\s*"
        r"(?:INR|USD|EUR|GBP|Rs\.?|₹|\$|€|£)?\s*"
        r"([\d,]+(?:\.\d{1,2})?)"
    )
]

INVOICE_NUMBER_LABELS = (
    "invoice number",
    "invoice no",
    "invoice #",
    "bill number",
    "bill no"
)

INVALID_INVOICE_NUMBER_VALUES = {
    "n/a",
    "na",
    "none",
    "nil",
    "-",
    "customer"
}

INVOICE_DATE_LABELS = (
    "invoice date",
    "bill date",
    "date of invoice",
)

DUE_DATE_LABELS = (
    "due date",
    "payment due",
    "payment due date",
)


def get_clean_lines(text: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", line).strip()
        for line in text.splitlines()
        if line.strip()
    ]


def find_value_after_label(
    lines: list[str],
    labels: tuple[str, ...]
) -> tuple[str | None, float]:

    for index, line in enumerate(lines):
        normalized = line.lower()

        for label in labels:
            label_lower = label.lower()

            if label_lower not in normalized:
                continue

            position = normalized.find(label_lower)

            value = line[
                position + len(label):
            ].strip(" :-")

            if value:
                return value, 0.95

            if index + 1 < len(lines):
                next_line = lines[index + 1].strip()

                if next_line:
                    return next_line, 0.90

    return None, 0.0


def extract_vendor_gst(
    text: str
) -> tuple[str | None, float]:
    return find_first_pattern(
        text,
        VENDOR_GST_PATTERNS
    )


def clean_vendor_name(value: str) -> str:
    cleaned = re.sub(
        r"\s+",
        " ",
        value
    ).strip()

    # Remove fields accidentally appended after vendor name.
    cleaned = re.split(
        r"\b(?:invoice\s*(?:number|no|#)|"
        r"invoice\s+date|due\s+date|"
        r"gstin|vendor\s+gst|po\s+number)\b",
        cleaned,
        maxsplit=1,
        flags=re.IGNORECASE
    )[0]

    return cleaned.strip(" :-\t")


def normalize_raw_text(raw_text: str) -> str:
    text = raw_text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def find_first_pattern(
    text: str,
    patterns: list[str]
) -> tuple[str | None, float]:
    for index, pattern in enumerate(patterns):
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        if match:
            value = match.group(1).strip()

            # Earlier patterns are normally more reliable.
            confidence = max(
                0.70,
                0.95 - (index * 0.05)
            )

            return value, round(confidence, 2)

    return None, 0.0


def parse_amount(value: str | None) -> float | None:
    if not value:
        return None

    # Reject values containing letters, except known currency labels
    # which should normally already be excluded by the regex.
    value_without_currency = re.sub(
        r"\b(?:INR|USD|EUR|GBP|RS)\b",
        "",
        value,
        flags=re.IGNORECASE
    )

    if re.search(r"[A-Za-z]", value_without_currency):
        return None

    cleaned = re.sub(
        r"[^\d.\-]",
        "",
        value_without_currency.replace(",", "")
    )

    if not cleaned or cleaned in {"-", ".", "-."}:
        return None

    try:
        return float(Decimal(cleaned))

    except (InvalidOperation, ValueError):
        return None


def parse_date_value(
    value: str | None
) -> str | None:
    if not value:
        return None

    try:
        parsed_date = date_parser.parse(
            value,
            fuzzy=True,
            dayfirst=True
        )

        return parsed_date.date().isoformat()

    except (ValueError, OverflowError):
        return None


def extract_invoice_number(
    text: str
) -> tuple[str | None, float]:

    lines = get_clean_lines(text)

    for index, line in enumerate(lines):
        normalized = line.lower()

        matched_label = next(
            (
                label
                for label in INVOICE_NUMBER_LABELS
                if label in normalized
            ),
            None
        )

        if not matched_label:
            continue

        position = normalized.find(matched_label)

        # Anything appearing after the label on the same line
        value = line[
            position + len(matched_label):
        ].strip(" :-")

        candidate_texts = []

        if value:
            candidate_texts.append(value)

        # Invoice value may appear on the next line.
        if index + 1 < len(lines):
            candidate_texts.append(
                lines[index + 1]
            )

        for candidate_text in candidate_texts:

            # Example:
            # "N/A RRSC21223308576"
            #
            # Find individual plausible invoice-number tokens.
            candidates = re.findall(
                r"\b[A-Z0-9][A-Z0-9\-\/]{3,}\b",
                candidate_text,
                flags=re.IGNORECASE
            )

            valid_candidates = [
                candidate
                for candidate in candidates
                if candidate.lower()
                not in INVALID_INVOICE_NUMBER_VALUES
            ]

            if valid_candidates:
                # Usually the actual invoice number is the
                # longest meaningful token.
                best_candidate = max(
                    valid_candidates,
                    key=len
                )

                return best_candidate, 0.95

    # Original regex fallback
    return find_first_pattern(
        text,
        INVOICE_NUMBER_PATTERNS
    )


def extract_indirect_tax_total(
    text: str
) -> tuple[float | None, float]:

    matches = re.findall(
        r"\b(?:CGST|SGST|IGST)"
        r"(?:@\d+(?:\.\d+)?%)?"
        r"\s*[:\-]?\s*"
        r"(?:INR|Rs\.?|₹)?\s*"
        r"([\d,]+(?:\.\d{1,2})?)",
        text,
        flags=re.IGNORECASE
    )

    amounts = []

    for value in matches:
        amount = parse_amount(value)

        if amount is not None:
            amounts.append(amount)

    if not amounts:
        return None, 0.0

    return round(sum(amounts), 2), 0.90


def extract_invoice_date(
    text: str
) -> tuple[str | None, float]:

    lines = get_clean_lines(text)

    raw_value, confidence = find_value_after_label(
        lines,
        INVOICE_DATE_LABELS
    )

    if raw_value:
        parsed = parse_date_value(raw_value)

        if parsed:
            return parsed, confidence

    # Fallback to regex
    raw_value, confidence = find_first_pattern(
        text,
        INVOICE_DATE_PATTERNS
    )

    parsed = parse_date_value(raw_value)

    if parsed:
        return parsed, confidence

    return None, 0.0


def extract_due_date(
    text: str
) -> tuple[str | None, float]:

    lines = get_clean_lines(text)

    raw_value, confidence = find_value_after_label(
        lines,
        DUE_DATE_LABELS
    )

    if raw_value:
        parsed = parse_date_value(raw_value)

        if parsed:
            return parsed, confidence

    raw_value, confidence = find_first_pattern(
        text,
        DUE_DATE_PATTERNS
    )

    parsed = parse_date_value(raw_value)

    if parsed:
        return parsed, confidence

    return None, 0.0


def extract_subtotal(
    text: str
) -> tuple[float | None, float]:

    matches = re.findall(
        r"\bsub\s*total\s*[:\-]?\s*"
        r"(?:INR|USD|EUR|GBP|Rs\.?|₹|\$|€|£)?\s*"
        r"([\d,]+(?:\.\d{1,2})?)",
        text,
        flags=re.IGNORECASE
    )

    if not matches:
        return None, 0.0

    # If there is exactly one subtotal,
    # it is reasonably safe to use it.
    if len(matches) == 1:
        amount = parse_amount(matches[0])

        if amount is not None:
            return amount, 0.90

    # Multiple subtotals usually mean
    # section-level totals, not invoice subtotal.
    return None, 0.0


def extract_amount_field(
    text: str,
    patterns: list[str]
) -> tuple[float | None, float]:
    raw_value, confidence = find_first_pattern(
        text,
        patterns
    )

    amount = parse_amount(raw_value)

    if raw_value and amount is None:
        return None, 0.0

    return amount, confidence


def extract_currency(
    text: str
) -> tuple[str | None, float]:
    normalized = text.upper()

    if "INR" in normalized or "₹" in text or re.search(
        r"\bRS\.?\s*\d",
        normalized
    ):
        return "INR", 0.90

    if "USD" in normalized or "$" in text:
        return "USD", 0.90

    if "EUR" in normalized or "€" in text:
        return "EUR", 0.90

    if "GBP" in normalized or "£" in text:
        return "GBP", 0.90

    return None, 0.0


def extract_vendor_name(
    text: str
) -> tuple[str | None, float]:
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    # Strategy 1:
    # Find an explicit Vendor/Supplier/Seller label.
    for index, line in enumerate(lines):
        normalized_line = line.lower()

        matched_label = next(
            (
                label
                for label in VENDOR_LABELS
                if normalized_line.startswith(label)
            ),
            None
        )

        if not matched_label:
            continue

        # Remove the matched label from the current line.
        current_value = line[len(matched_label):].strip(" :-")

        vendor_parts: list[str] = []

        if current_value:
            vendor_parts.append(current_value)

        next_index = index + 1

        # Join continuation lines such as:
        #
        # Vendor Name OOPO Office Supplies Pvt.
        # Ltd.
        while next_index < len(lines):
            next_line = lines[next_index].strip()
            next_normalized = next_line.lower()

            # Stop when another known invoice field starts.
            if any(
                next_normalized.startswith(stop_label)
                for stop_label in VENDOR_STOP_LABELS
            ):
                break

            # Do not collect too many unrelated lines.
            if len(vendor_parts) >= 3:
                break

            vendor_parts.append(next_line)

            joined_vendor = " ".join(vendor_parts).lower()

            # Once a legal company suffix is found,
            # vendor name is probably complete.
            if any(
                keyword in joined_vendor
                for keyword in COMPANY_KEYWORDS
            ):
                break

            next_index += 1

        vendor_name = clean_vendor_name(
            " ".join(vendor_parts)
        )

        if vendor_name:
            return vendor_name[:255], 0.95

    # Strategy 2:
    # Find company-like text near the top of the document.
    for index, line in enumerate(lines[:20]):
        combined_line = line

        if index + 1 < len(lines):
            next_line = lines[index + 1].strip()

            if next_line.lower() in COMPANY_SUFFIX_LINES:
                combined_line = f"{line} {next_line}"

        normalized_line = combined_line.lower()

        if any(
            keyword in normalized_line
            for keyword in COMPANY_KEYWORDS
        ):
            if not any(
                excluded in normalized_line
                for excluded in (
                    "bill to",
                    "ship to",
                    "customer",
                    "buyer"
                )
            ):
                return (
                    clean_vendor_name(combined_line)[:255],
                    0.65
                )

    return None, 0.0


def validate_amount_fields(
    subtotal: float | None,
    tax_amount: float | None,
    total_amount: float | None
) -> list[dict[str, str]]:

    errors: list[dict[str, str]] = []

    if (
        subtotal is not None
        and tax_amount is not None
        and total_amount is not None
    ):
        expected = subtotal + tax_amount

        if abs(expected - total_amount) > 0.05:
            errors.append({
                "field": "totalAmount",
                "message": (
                    "Extracted subtotal plus tax does not "
                    "match extracted total amount."
                )
            })

    return errors


def parse_invoice_fields(raw_text: str) -> dict[str, Any]:
    text = normalize_raw_text(raw_text)

    invoice_number, invoice_number_confidence = (
        extract_invoice_number(text)
    )

    vendor_gst, vendor_gst_confidence = (
        extract_vendor_gst(text)
    )

    vendor_name, vendor_confidence = (
        extract_vendor_name(text)
    )

    invoice_date, invoice_date_confidence = (
        extract_invoice_date(text)
    )

    due_date, due_date_confidence = (
        extract_due_date(text)
    )

    subtotal, subtotal_confidence = extract_subtotal(text)

    total_amount, total_confidence = (
        extract_amount_field(
            text,
            TOTAL_AMOUNT_PATTERNS
        )
    )

    currency, currency_confidence = (
        extract_currency(text)
    )

    tax_amount, tax_confidence = extract_amount_field(
        text,
        TAX_PATTERNS
    )

    if tax_amount is None:
        tax_amount, tax_confidence = extract_indirect_tax_total(
            text
        )

    fields = {
        "invoiceNumber": invoice_number,
        "vendorName": vendor_name,
        "invoiceDate": invoice_date,
        "dueDate": due_date,
        "subtotal": subtotal,
        "taxAmount": tax_amount,
        "totalAmount": total_amount,
        "currency": currency,
        "vendorGst": vendor_gst
    }

    confidence = {
        "invoiceNumber": invoice_number_confidence,
        "vendorName": vendor_confidence,
        "invoiceDate": invoice_date_confidence,
        "dueDate": due_date_confidence,
        "subtotal": subtotal_confidence,
        "taxAmount": tax_confidence,
        "totalAmount": total_confidence,
        "currency": currency_confidence,
        "vendorGstConfidence": vendor_gst_confidence
    }

    errors: list[dict[str, str]] = []

    required_fields = {
        "invoiceNumber": invoice_number,
        "vendorName": vendor_name,
        "totalAmount": total_amount
    }

    for field_name, field_value in required_fields.items():
        if field_value is None:
            errors.append({
                "field": field_name,
                "message": (
                    f"{field_name} could not be extracted."
                )
            })

    if (
        invoice_date
        and due_date
        and date.fromisoformat(due_date)
        < date.fromisoformat(invoice_date)
    ):
        errors.append({
            "field": "dueDate",
            "message": (
                "Extracted due date is earlier than "
                "the invoice date."
            )
        })

    errors.extend(
        validate_amount_fields(
            subtotal=subtotal,
            tax_amount=tax_amount,
            total_amount=total_amount
        )
    )
    return {
        "fields": fields,
        "confidence": confidence,
        "errors": errors
    }
