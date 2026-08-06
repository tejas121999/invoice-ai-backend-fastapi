from fastapi import HTTPException
from sqlalchemy.orm import Session
from starlette import status

from app.repositories.invoice_repository import (
    get_extracted_invoice_data_by_invoice_id,
    get_feature_candidate_invoices
)
from app.utils.similarity_utils import (
    calculate_amount_difference,
    calculate_amount_similarity,
    calculate_currency_match,
    calculate_date_difference_days,
    calculate_text_similarity,
    is_exact_amount_match
)


def generate_pair_features(
    source_invoice,
    candidate_invoice
) -> dict:
    """
    Compare two extracted invoice database records and generate
    an ML-ready feature vector.
    """

    return {
        "vendorSimilarity": calculate_text_similarity(
            source_invoice.vendorName,
            candidate_invoice.vendorName
        ),
        "invoiceNumberSimilarity": calculate_text_similarity(
            source_invoice.invoiceNumber,
            candidate_invoice.invoiceNumber
        ),
        "exactAmountMatch": is_exact_amount_match(
            source_invoice.totalAmount,
            candidate_invoice.totalAmount
        ),
        "amountDifference": calculate_amount_difference(
            source_invoice.totalAmount,
            candidate_invoice.totalAmount
        ),
        "amountSimilarity": calculate_amount_similarity(
            source_invoice.totalAmount,
            candidate_invoice.totalAmount
        ),
        "dateDifferenceDays": calculate_date_difference_days(
            source_invoice.invoiceDate,
            candidate_invoice.invoiceDate
        ),
        "currencyMatch": calculate_currency_match(
            source_invoice.currency,
            candidate_invoice.currency
        )
    }


def generate_invoice_features_service(
    db: Session,
    invoice_id: int
) -> dict:
    source_invoice = get_extracted_invoice_data_by_invoice_id(
        db=db,
        invoice_id=invoice_id
    )

    if not source_invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Extracted invoice data not found. "
                "Process and review the invoice first."
            )
        )

    if not source_invoice.isReviewed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Invoice must be reviewed before "
                "feature engineering can be executed."
            )
        )

    candidate_invoices = get_feature_candidate_invoices(
        db=db,
        current_invoice_id=invoice_id
    )

    comparisons: list[dict] = []

    for candidate in candidate_invoices:
        features = generate_pair_features(
            source_invoice=source_invoice,
            candidate_invoice=candidate
        )

        comparisons.append({
            "sourceInvoiceId": source_invoice.invoiceId,
            "candidateInvoiceId": candidate.invoiceId,

            "sourceInvoiceNumber": source_invoice.invoiceNumber,
            "candidateInvoiceNumber": candidate.invoiceNumber,

            "sourceVendorName": source_invoice.vendorName,
            "candidateVendorName": candidate.vendorName,

            "features": features
        })

    return {
        "invoiceId": source_invoice.invoiceId,
        "comparedInvoices": len(comparisons),
        "comparisons": comparisons
    }
