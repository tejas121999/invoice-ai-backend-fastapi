import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Any


def normalize_text(value: str | None) -> str:
    """
    Normalize text before similarity comparison.

    Examples:
    'ABC Limited' -> 'abclimited'
    'INV-001'     -> 'inv001'
    """

    if not value:
        return ""

    normalized = value.strip().lower()

    # Remove spaces and non-alphanumeric characters.
    normalized = re.sub(r"[^a-z0-9]", "", normalized)

    return normalized


def calculate_text_similarity(
    first_value: str | None,
    second_value: str | None
) -> float:
    """
    Return similarity between 0 and 1.

    0 = completely different
    1 = exact match
    """

    first_normalized = normalize_text(first_value)
    second_normalized = normalize_text(second_value)

    if not first_normalized or not second_normalized:
        return 0.0

    score = SequenceMatcher(
        None,
        first_normalized,
        second_normalized
    ).ratio()

    return round(score, 4)


def to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def calculate_amount_difference(
    first_amount: Any,
    second_amount: Any
) -> float | None:
    first_decimal = to_decimal(first_amount)
    second_decimal = to_decimal(second_amount)

    if first_decimal is None or second_decimal is None:
        return None

    difference = abs(first_decimal - second_decimal)

    return round(float(difference), 2)


def calculate_amount_similarity(
    first_amount: Any,
    second_amount: Any
) -> float | None:
    """
   Return amount similarity between 0 and 1.

   Exact amount:
   45000 vs 45000 -> 1.0

   Small difference:
   45000 vs 44900 -> close to 1.0
   """
    first_decimal = to_decimal(first_amount)
    second_decimal = to_decimal(second_amount)

    if first_decimal is None or second_decimal is None:
        return 0.0

    if first_decimal == second_decimal:
        return 1.0

    maximum_amount = max(
        abs(first_decimal),
        abs(second_decimal)
    )

    if maximum_amount == 0:
        return 1.0

    difference = abs(first_decimal - second_decimal)

    similarity = Decimal("1") - (
        difference / maximum_amount
    )

    similarity = max(Decimal("0"), similarity)

    return round(float(similarity), 4)


def is_exact_amount_match(
    first_amount: Any,
    second_amount: Any
) -> bool:
    first_decimal = to_decimal(first_amount)
    second_decimal = to_decimal(second_amount)

    if first_decimal is None or second_decimal is None:
        return False

    return first_decimal == second_decimal


def to_date(value: Any) -> date | None:
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    return None


def calculate_date_difference_days(
    first_date: Any,
    second_date: Any
) -> int | None:
    first_parsed = to_date(first_date)
    second_parsed = to_date(second_date)

    if first_parsed is None or second_parsed is None:
        return None

    return abs((first_parsed - second_parsed).days)


def calculate_currency_match(
    first_currency: str | None,
    second_currency: str | None
) -> bool:
    if not first_currency or not second_currency:
        return False

    return (
        first_currency.strip().upper()
        == second_currency.strip().upper()
    )
