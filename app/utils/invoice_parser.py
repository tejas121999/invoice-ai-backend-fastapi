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

DATE_TOKEN_PATTERN = (
    r"\b(?:"
    r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|"
    r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|"
    r"\d{1,2}[-/ ](?:[A-Za-z]{3,9}|\d{1,2})[-/ ,]+\d{2,4}|"
    r"[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}"
    r")\b"
)

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

INLINE_TOTAL_PATTERN = (
    r"^\s*(?:grand\s+)?total\s*[:\-]?\s*"
    r"(?:(?:INR|USD|EUR|GBP|Rs\.?|[$€£₹])\s*)?"
    r"([\d,]+(?:\.\d{1,2})?)"
    r"(?:\s*(?:INR|USD|EUR|GBP))?\s*$"
)

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
        r"\b(?:vendor\s*)?(?:gstin|gst\s*(?:number|no\.?|#)?)"
        r"\s*(?:[:\-]\s*)?"
        r"([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z])"
    )
]

PO_NUMBER_LABEL_PATTERNS = (
    r"purchase\s+order(?:\s+(?:number|no\.?))?",
    r"p\.?\s*o\.?\s*(?:number|no\.?|#)",
)

PAYMENT_TERMS_LABEL_PATTERNS = (
    r"payment\s+terms?",
    r"terms\s+of\s+payment",
    r"payment\s+due",
)

SHIPPING_CHARGES_LABEL_PATTERNS = (
    r"shipping\s+(?:charges?|costs?)",
    r"delivery\s+charges?",
    r"freight\s+charges?",
    r"carriage\s+charges?",
)

DISCOUNT_LABEL_PATTERNS = (
    r"(?:total\s+)?discount(?:\s+amount)?",
    r"less\s+discount",
    r"cash\s+discount",
    r"trade\s+discount",
)

VENDOR_ADDRESS_LABEL_PATTERNS = (
    r"vendor\s+address",
    r"supplier\s+address",
    r"company\s+address",
)

PAYMENT_REFERENCE_LABEL_PATTERNS = (
    r"payment\s+reference",
    r"payment\s+ref\.?",
    r"transaction\s+(?:reference|ref\.?|id)",
    r"reference\s+(?:number|no\.?|#)",
    r"utr\s+(?:number|no\.?|#)?",
)

ADDITIONAL_FIELD_LABEL_PATTERNS = (
    *PO_NUMBER_LABEL_PATTERNS,
    *PAYMENT_TERMS_LABEL_PATTERNS,
    *SHIPPING_CHARGES_LABEL_PATTERNS,
    *DISCOUNT_LABEL_PATTERNS,
    *VENDOR_ADDRESS_LABEL_PATTERNS,
    *PAYMENT_REFERENCE_LABEL_PATTERNS,
    r"vendor\s+gst",
    r"gstin",
    r"gst\s*(?:number|no\.?|#)?",
    r"invoice\s*(?:number|no\.?|#|date)",
    r"bill\s*(?:number|no\.?|date)",
    r"due\s+date",
    r"subtotal",
    r"sub\s+total",
    r"tax\s+amount",
    r"total\s+tax",
    r"total\s+amount",
    r"grand\s+total",
    r"currency",
    r"bill\s+to",
    r"ship\s+to",
    r"customer(?:\s+(?:name|address|details|information))?",
    r"buyer(?:\s+(?:name|address|details|information))?",
)

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

GENERIC_VENDOR_TITLES = {
    "invoice",
    "freelance invoice",
    "tax invoice",
    "two page test invoice",
    "bill"
}

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


def extract_labeled_text_field(
    text: str,
    label_patterns: tuple[str, ...],
    *,
    continuation_lines: int = 0
) -> tuple[str | None, float]:
    lines = get_clean_lines(text)
    labels = "|".join(label_patterns)
    label_pattern = re.compile(
        r"^\s*(?:" + labels
        + r")(?=\s|[:#\-]|$)\s*[:#\-]?\s*(.*?)\s*$",
        re.IGNORECASE
    )
    any_field_pattern = re.compile(
        r"^\s*(?:" + "|".join(ADDITIONAL_FIELD_LABEL_PATTERNS)
        + r")\b",
        re.IGNORECASE
    )

    for index, line in enumerate(lines):
        match = label_pattern.match(line)
        if not match:
            continue

        value = match.group(1).strip(" :-")
        if value:
            value = re.split(
                r"\s+(?=(?:" + "|".join(
                    ADDITIONAL_FIELD_LABEL_PATTERNS
                ) + r")\b\s*[:#\-])",
                value,
                maxsplit=1,
                flags=re.IGNORECASE
            )[0].strip(" :-")
            if value:
                return value, 0.95

        continuation: list[str] = []
        for next_line in lines[
            index + 1:index + 1 + continuation_lines
        ]:
            if any_field_pattern.match(next_line):
                break
            continuation.append(next_line)

        if continuation:
            return " ".join(continuation), 0.90

    return None, 0.0


def extract_labeled_amount(
    text: str,
    label_patterns: tuple[str, ...]
) -> tuple[float | None, float]:
    lines = get_clean_lines(text)
    labels = "|".join(label_patterns)
    label_pattern = re.compile(
        r"^\s*(?:" + labels
        + r")(?=\s|[:#\-]|$)\s*[:#\-]?\s*(.*?)\s*$",
        re.IGNORECASE
    )
    currency = r"(?:INR|USD|EUR|GBP|Rs\.?|₹|\$|€|£)?"
    amount_pattern = re.compile(
        r"^(?:(?:\(\s*\d+(?:\.\d+)?\s*%\)|"
        r"\d+(?:\.\d+)?\s*%)\s*[:\-]?\s*)?"
        + currency
        + r"\s*(-?\d[\d,]*(?:\.\d{1,2})?)"
        + r"(?:\s*(?:INR|USD|EUR|GBP))?\s*$",
        re.IGNORECASE
    )
    any_field_pattern = re.compile(
        r"^\s*(?:" + "|".join(ADDITIONAL_FIELD_LABEL_PATTERNS)
        + r")\b",
        re.IGNORECASE
    )

    for index, line in enumerate(lines):
        match = label_pattern.match(line)
        if not match:
            continue

        value_text = match.group(1).strip(" :-")
        amount_match = amount_pattern.fullmatch(value_text)
        if amount_match:
            amount = parse_amount(amount_match.group(1))
            if amount is not None:
                return amount, 0.95

        if not value_text and index + 1 < len(lines):
            next_line = lines[index + 1]
            if not any_field_pattern.match(next_line):
                amount_match = amount_pattern.fullmatch(next_line)
                if amount_match:
                    amount = parse_amount(amount_match.group(1))
                    if amount is not None:
                        return amount, 0.90

    return None, 0.0


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


def is_generic_vendor_title(value: str) -> bool:
    normalized = re.sub(
        r"[^a-z0-9]+",
        " ",
        value.lower()
    ).strip()
    return (
        normalized in GENERIC_VENDOR_TITLES
        or bool(re.fullmatch(
            r"(?:(?:two|multi) page )?(?:test )?(?:tax )?invoice",
            normalized
        ))
    )


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


def extract_date_token(value: str | None) -> str | None:
    if not value:
        return None

    match = re.search(DATE_TOKEN_PATTERN, value, flags=re.IGNORECASE)
    if not match:
        return None

    return parse_date_value(match.group(0))


def extract_invoice_number(
    text: str
) -> tuple[str | None, float]:

    lines = get_clean_lines(text)
    found_invoice_number_label = False

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
        found_invoice_number_label = True

        position = normalized.find(matched_label)

        # Anything appearing after the label on the same line
        value = line[
            position + len(matched_label):
        ].strip(" :-")

        candidate_texts: list[tuple[str, bool]] = []

        if value:
            candidate_texts.append((value, True))

        # Invoice value may appear on the next line.
        if index + 1 < len(lines):
            candidate_texts.append(
                (lines[index + 1], False)
            )

        for candidate_text, is_inline_value in candidate_texts:
            if re.search(
                DATE_TOKEN_PATTERN,
                candidate_text,
                flags=re.IGNORECASE
            ):
                continue

            email_matches = re.findall(
                r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
                candidate_text,
                flags=re.IGNORECASE
            )
            text_without_emails = re.sub(
                r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
                " ",
                candidate_text,
                flags=re.IGNORECASE
            ).strip(" \t,:-")
            text_without_phones = re.sub(
                r"(?:\+?\d{1,3}\s*)?\(\d{2,4}\)\s*\d{3,4}[- ]\d{3,4}\b"
                r"|\b\d{3}[-.]\d{3}[-.]\d{4}\b",
                " ",
                text_without_emails
            ).strip(" \t,:-")

            numeric_candidate = None
            if re.fullmatch(
                r"\d{1,12}" if is_inline_value else r"\d{1,4}",
                text_without_phones
            ):
                if is_inline_value or email_matches:
                    numeric_candidate = text_without_phones

            # Example:
            # "N/A RRSC21223308576"
            #
            # Find individual plausible invoice-number tokens.
            candidates = re.findall(
                r"\b(?=[A-Z0-9][A-Z0-9\-\/]{3,}\b)"
                r"(?=[A-Z0-9\-\/]*[A-Z])"
                r"(?=[A-Z0-9\-\/]*\d)"
                r"[A-Z0-9][A-Z0-9\-\/]{3,}\b",
                text_without_phones,
                flags=re.IGNORECASE
            )

            candidates = [
                re.sub(
                    r"(?i)(?:invoice|date|due|currency)$",
                    "",
                    candidate
                )
                for candidate in candidates
            ]

            if numeric_candidate:
                candidates.append(numeric_candidate)

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

    if found_invoice_number_label:
        return None, 0.0

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


def extract_tax_amount(
    text: str
) -> tuple[float | None, float]:
    currency = r"(?:INR|USD|EUR|GBP|Rs\.?|₹|\$|€|£)?"
    amount = r"([\d,]+(?:\.\d{1,2})?)"
    percentage = r"(?:\s*\(\s*\d+(?:\.\d+)?\s*%\s*\))?"
    direct_patterns = (
        (
            re.compile(
                r"^(?:total\s+tax|tax\s+amount|total\s+gst|"
                r"gst\s+amount|vat\s+amount)\b"
                + percentage
                + r"\s*[:\-]?\s*"
                + currency
                + r"\s*"
                + amount
                + r"(?:\s*(?:INR|USD|EUR|GBP))?\s*$",
                re.IGNORECASE
            ),
            0.95
        ),
        (
            re.compile(
                r"^(?:tax\s*\(\s*\d+(?:\.\d+)?\s*%\s*\)|"
                r"tax)\s*[:\-]?\s*"
                + currency
                + r"\s*"
                + amount
                + r"(?:\s*(?:INR|USD|EUR|GBP))?\s*$",
                re.IGNORECASE
            ),
            0.90
        ),
        (
            re.compile(
                r"^(?:gst|vat)"
                + percentage
                + r"\s*[:\-]?\s*"
                + currency
                + r"\s*"
                + amount
                + r"(?:\s*(?:INR|USD|EUR|GBP))?\s*$",
                re.IGNORECASE
            ),
            0.85
        )
    )

    lines = get_clean_lines(text)
    for line in lines:
        for pattern, confidence in direct_patterns:
            match = pattern.match(line)
            if match:
                parsed_amount = parse_amount(match.group(1))
                if parsed_amount is not None:
                    return parsed_amount, confidence

    label_only_pattern = re.compile(
        r"^(?:total\s+tax|tax\s+amount|total\s+gst|gst\s+amount|"
        r"vat\s+amount|tax|gst|vat)"
        r"(?:\s*\(\s*\d+(?:\.\d+)?\s*%\s*\))?$",
        re.IGNORECASE
    )
    next_line_amount_pattern = re.compile(
        currency + r"\s*" + amount
        + r"(?:\s*(?:INR|USD|EUR|GBP))?",
        re.IGNORECASE
    )
    for index, line in enumerate(lines[:-1]):
        if not label_only_pattern.fullmatch(line):
            continue

        next_line = next_line_amount_pattern.fullmatch(lines[index + 1])
        if next_line:
            parsed_amount = parse_amount(next_line.group(1))
            if parsed_amount is not None:
                return parsed_amount, 0.85

    component_pattern = re.compile(
        r"^(?:cgst|sgst|igst)(?:\s*@?\s*\d+(?:\.\d+)?\s*%)?"
        r"\s*[:\-]?\s*"
        + currency
        + r"\s*"
        + amount
        + r"(?:\s*(?:INR|USD|EUR|GBP))?\s*$",
        re.IGNORECASE
    )
    component_amounts = []
    for line in lines:
        match = component_pattern.match(line)
        if match:
            parsed_amount = parse_amount(match.group(1))
            if parsed_amount is not None:
                component_amounts.append(parsed_amount)

    if component_amounts:
        return round(sum(component_amounts), 2), 0.90

    return None, 0.0


def extract_invoice_date(
    text: str
) -> tuple[str | None, float]:

    lines = get_clean_lines(text)

    raw_value, confidence = find_value_after_label(
        lines,
        INVOICE_DATE_LABELS
    )

    if raw_value:
        parsed = extract_date_token(raw_value)

        if parsed:
            return parsed, confidence

    for index, line in enumerate(lines):
        normalized_line = line.lower()

        if re.search(r"\b(?:due\s+date|payment\s+due)\b", normalized_line):
            break

        if re.search(r"\bdate\s*$", normalized_line):
            if index + 1 < len(lines):
                parsed = extract_date_token(lines[index + 1])
                if parsed:
                    return parsed, 0.90

    # Fallback to regex
    raw_value, confidence = find_first_pattern(
        text,
        INVOICE_DATE_PATTERNS
    )

    parsed = extract_date_token(raw_value)

    if parsed:
        return parsed, confidence

    if any(label in text.lower() for label in INVOICE_DATE_LABELS):
        date_matches = re.finditer(
            DATE_TOKEN_PATTERN,
            text,
            flags=re.IGNORECASE
        )
        for match in date_matches:
            parsed = parse_date_value(match.group(0))
            if parsed:
                return parsed, 0.80

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
        parsed = extract_date_token(raw_value)

        if parsed:
            return parsed, confidence

    raw_value, confidence = find_first_pattern(
        text,
        DUE_DATE_PATTERNS
    )

    parsed = extract_date_token(raw_value)

    if parsed:
        return parsed, confidence

    if any(label in text.lower() for label in DUE_DATE_LABELS):
        date_matches = list(re.finditer(
            DATE_TOKEN_PATTERN,
            text,
            flags=re.IGNORECASE
        ))

        if date_matches:
            date_index = 1 if (
                any(
                    label in text.lower()
                    for label in INVOICE_DATE_LABELS
                )
                and len(date_matches) > 1
            ) else 0
            parsed = parse_date_value(
                date_matches[date_index].group(0)
            )
            if parsed:
                return parsed, 0.80

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


def extract_total_amount(
    text: str
) -> tuple[float | None, float]:
    amount, confidence = extract_amount_field(
        text,
        TOTAL_AMOUNT_PATTERNS
    )
    if amount is not None:
        return amount, confidence

    for line in get_clean_lines(text):
        match = re.match(
            INLINE_TOTAL_PATTERN,
            line,
            flags=re.IGNORECASE
        )
        if match:
            amount = parse_amount(match.group(1))
            if amount is not None:
                return amount, 0.70

    currency_amount_pattern = (
        r"(?:[$€£₹]\s*|(?:INR|USD|EUR|GBP|Rs\.?)\s*)"
        r"([\d,]+(?:\.\d{1,2})?)"
    )

    lines = get_clean_lines(text)
    for index, line in enumerate(lines):
        if re.search(
            r"\b(?:items?|description|quantity|qty|price|tax|amount)\b",
            line,
            flags=re.IGNORECASE
        ):
            continue

        if not re.search(
            r"(?:^|[\s:])total\s*:?\s*$",
            line,
            flags=re.IGNORECASE
        ):
            continue

        for nearby_line in lines[index + 1:index + 3]:
            matches = re.findall(
                currency_amount_pattern,
                nearby_line,
                flags=re.IGNORECASE
            )
            if len(matches) == 1:
                parsed_amount = parse_amount(matches[0])
                if parsed_amount is not None:
                    return parsed_amount, 0.70

    return None, 0.0


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

        if vendor_name and not is_generic_vendor_title(vendor_name):
            return vendor_name[:255], 0.95

    # Strategy 2:
    # Prefer the first plausible company line in the header, before customer
    # and address sections.
    header_lines: list[str] = []
    for line in lines[:20]:
        if re.match(
            r"^(?:bill\s+to|ship\s+to|customer|buyer|"
            r"client\s+information|client\s+details|"
            r"customer\s+information|customer\s+details)\b",
            line,
            flags=re.IGNORECASE
        ):
            break
        header_lines.append(line)

    for index, line in enumerate(header_lines):
        if is_generic_vendor_title(line):
            continue

        if re.search(
            r"\b(?:inv(?:oice)?[\s\-/#]*\d[A-Z0-9\-\/]*|"
            r"invoice\s*(?:number|no\.?)\b)",
            line,
            flags=re.IGNORECASE
        ):
            continue

        if re.search(
            r"\b(?:invoice\s*(?:number|no\.?|date)|due\s*date|"
            r"total\s*amount|grand\s*total|sub\s*total|subtotal|"
            r"tax\s*amount|gst(?:in)?|bill\s+to|ship\s+to|"
            r"payment\s+terms)\b",
            line,
            flags=re.IGNORECASE
        ):
            continue

        if re.match(
            r"^(?:vendor|supplier|seller)\s+name\b",
            line,
            flags=re.IGNORECASE
        ):
            continue

        if re.match(r"^\d", line):
            break

        if re.match(
            r"^(?:invoice|date|due date|payment due|items|description)\b",
            line,
            flags=re.IGNORECASE
        ):
            continue

        if re.search(
            r"\b(?:street|st\.|avenue|ave\.|road|rd\.|boulevard|"
            r"blvd|lane|ln\.|drive|dr\.|suite|unit)\b",
            line,
            flags=re.IGNORECASE
        ):
            break

        if (
            index + 1 < len(header_lines)
            and header_lines[index + 1].lower() in COMPANY_SUFFIX_LINES
        ):
            line = f"{line} {header_lines[index + 1]}"

        candidate = re.split(
            r"\s+(?:\d{1,6}\s+|\d{5}(?:-\d{4})?$|"
            r"[A-Z]{1,5}[-/]\d[A-Z0-9/-]*\b|"
            r"street\b|st\.|avenue\b|ave\.|road\b|rd\.|"
            r"boulevard\b|blvd\.|lane\b|ln\.|drive\b|dr\.|"
            r"suite\b|unit\b)",
            line,
            maxsplit=1,
            flags=re.IGNORECASE
        )[0]

        candidate = clean_vendor_name(candidate)
        if candidate and re.search(r"[A-Za-z]", candidate):
            confidence = (
                0.85
                if any(
                    keyword in candidate.lower()
                    for keyword in COMPANY_KEYWORDS
                )
                else 0.70
            )
            return candidate[:255], confidence

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
    text = re.sub(
        r"(?im)^\s*\[(?:page\s+\d+"
        r"(?::\s*(?:processing failed|no text detected))?"
        r"|no text detected)\]\s*$",
        "",
        text
    )

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

    total_amount, total_confidence = extract_total_amount(text)

    currency, currency_confidence = (
        extract_currency(text)
    )

    tax_amount, tax_confidence = extract_tax_amount(text)
    if tax_amount is None:
        tax_amount, tax_confidence = extract_indirect_tax_total(text)

    po_number, po_number_confidence = extract_labeled_text_field(
        text,
        PO_NUMBER_LABEL_PATTERNS
    )
    payment_terms, payment_terms_confidence = extract_labeled_text_field(
        text,
        PAYMENT_TERMS_LABEL_PATTERNS,
        continuation_lines=1
    )
    shipping_charges, shipping_charges_confidence = (
        extract_labeled_amount(text, SHIPPING_CHARGES_LABEL_PATTERNS)
    )
    discount, discount_confidence = extract_labeled_amount(
        text,
        DISCOUNT_LABEL_PATTERNS
    )
    vendor_address, vendor_address_confidence = (
        extract_labeled_text_field(
            text,
            VENDOR_ADDRESS_LABEL_PATTERNS,
            continuation_lines=3
        )
    )
    payment_reference, payment_reference_confidence = (
        extract_labeled_text_field(
            text,
            PAYMENT_REFERENCE_LABEL_PATTERNS
        )
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
        "vendorGst": vendor_gst,
        "poNumber": po_number,
        "paymentTerms": payment_terms,
        "shippingCharges": shipping_charges,
        "discount": discount,
        "vendorAddress": vendor_address,
        "paymentReference": payment_reference
    }

    confidence = {
        "invoiceNumber": invoice_number_confidence,
        "vendorName": vendor_confidence,
        "invoiceDate": invoice_date_confidence,
        "dueDate": due_date_confidence,
        "subtotal": subtotal_confidence,
        "taxAmount": tax_confidence,
        "totalAmount": total_confidence,
        "currency": currency_confidence
    }
    dynamic_confidences = {
        "poNumber": (po_number, po_number_confidence),
        "vendorGst": (vendor_gst, vendor_gst_confidence),
        "paymentTerms": (payment_terms, payment_terms_confidence),
        "shippingCharges": (
            shipping_charges,
            shipping_charges_confidence
        ),
        "discount": (discount, discount_confidence),
        "vendorAddress": (vendor_address, vendor_address_confidence),
        "paymentReference": (
            payment_reference,
            payment_reference_confidence
        )
    }
    confidence.update({
        field_name: field_confidence
        for field_name, (field_value, field_confidence)
        in dynamic_confidences.items()
        if field_value is not None
    })

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

    financial_errors = validate_amount_fields(
        subtotal=subtotal,
        tax_amount=tax_amount,
        total_amount=total_amount
    )
    errors.extend(financial_errors)

    if (
        subtotal is not None
        and tax_amount is not None
        and total_amount is not None
    ):
        if financial_errors:
            subtotal_confidence = min(subtotal_confidence, 0.60)
            tax_confidence = min(tax_confidence, 0.60)
            total_confidence = min(total_confidence, 0.60)
        else:
            subtotal_confidence = min(subtotal_confidence + 0.03, 0.98)
            tax_confidence = min(tax_confidence + 0.03, 0.98)
            total_confidence = min(total_confidence + 0.03, 0.98)

        confidence.update({
            "subtotal": subtotal_confidence,
            "taxAmount": tax_confidence,
            "totalAmount": total_confidence
        })

    return {
        "fields": fields,
        "confidence": confidence,
        "errors": errors
    }
