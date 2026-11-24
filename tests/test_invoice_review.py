import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pydantic import ValidationError

from app.repositories.invoice_repository import update_invoice_review
from app.routers.invoice_router import review_invoice
from app.schemas.invoice_schema import InvoiceReviewRequest


class InvoiceReviewDynamicFieldTests(unittest.TestCase):
    def test_review_schema_accepts_dynamic_and_fixed_fields(self):
        request = InvoiceReviewRequest.model_validate({
            "invoiceNumber": "INV-CORRECTED",
            "poNumber": "PO-2026-102",
            "vendorGst": "27ABCDE1234F1Z5",
            "paymentTerms": "Net 30",
            "shippingCharges": "10.50",
            "discount": "5.00",
            "vendorAddress": "10 Example Road",
            "paymentReference": "PAY-102"
        })

        payload = request.model_dump(exclude_unset=True)

        self.assertEqual(payload["invoiceNumber"], "INV-CORRECTED")
        self.assertEqual(payload["poNumber"], "PO-2026-102")
        self.assertEqual(payload["vendorGst"], "27ABCDE1234F1Z5")
        self.assertEqual(payload["paymentTerms"], "Net 30")
        self.assertEqual(payload["shippingCharges"], Decimal("10.50"))
        self.assertEqual(payload["discount"], Decimal("5.00"))
        self.assertEqual(payload["vendorAddress"], "10 Example Road")
        self.assertEqual(payload["paymentReference"], "PAY-102")
        self.assertNotIn("dueDate", payload)

        with self.assertRaises(ValidationError):
            InvoiceReviewRequest.model_validate({"subtotal": "-1"})

    def test_repository_saves_dynamic_values_without_changing_extracted_json(
        self
    ):
        extracted_fields = {
            "invoiceNumber": "INV-ORIGINAL",
            "poNumber": "PO-ORIGINAL"
        }
        extracted_data = SimpleNamespace(
            reviewedFieldsJson={},
            extractedFieldsJson=extracted_fields,
            reviewedData={},
            isReviewed=False,
            reviewedBy=None,
            invoiceNumber="INV-ORIGINAL",
            vendorName="Original Vendor",
            invoiceDate=None,
            dueDate=None,
            subtotal=Decimal("100.00"),
            taxAmount=Decimal("18.00"),
            totalAmount=Decimal("118.00"),
            currency="INR"
        )
        invoice = SimpleNamespace(id=12)
        db = Mock()
        review_data = {
            "invoiceNumber": "INV-CORRECTED",
            "poNumber": "PO-2026-102",
            "vendorGst": "27ABCDE1234F1Z5",
            "paymentTerms": "Net 30",
            "shippingCharges": Decimal("10.50"),
            "discount": Decimal("5.00"),
            "vendorAddress": "10 Example Road",
            "paymentReference": "PAY-102"
        }

        with (
            patch(
                "app.repositories.invoice_repository.get_invoice_by_id",
                return_value=invoice
            ),
            patch(
                "app.repositories.invoice_repository."
                "get_extracted_invoice_data_by_invoice_id",
                return_value=extracted_data
            )
        ):
            result = update_invoice_review(
                db=db,
                invoice_id=12,
                review_data=review_data,
                reviewed_by=7
            )

        self.assertEqual(result["extracted_data"], extracted_data)
        self.assertEqual(
            extracted_data.reviewedFieldsJson,
            {
                "invoiceNumber": "INV-CORRECTED",
                "vendorName": None,
                "invoiceDate": None,
                "dueDate": None,
                "subtotal": None,
                "taxAmount": None,
                "totalAmount": None,
                "currency": None,
                "poNumber": "PO-2026-102",
                "vendorGst": "27ABCDE1234F1Z5",
                "paymentTerms": "Net 30",
                "shippingCharges": 10.5,
                "discount": 5.0,
                "vendorAddress": "10 Example Road",
                "paymentReference": "PAY-102"
            }
        )
        self.assertEqual(extracted_data.extractedFieldsJson, extracted_fields)
        self.assertEqual(extracted_data.invoiceNumber, "INV-CORRECTED")
        self.assertEqual(extracted_data.totalAmount, None)
        db.flush.assert_called_once()

    def test_partial_dynamic_review_preserves_existing_dynamic_values(self):
        existing_reviewed_fields = {
            "invoiceNumber": "INV-REVIEWED",
            "poNumber": "PO-EXISTING",
            "vendorGst": "27ABCDE1234F1Z5",
            "paymentTerms": "Net 30",
            "vendorAddress": "10 Existing Road"
        }
        extracted_data = SimpleNamespace(
            reviewedFieldsJson=existing_reviewed_fields.copy(),
            extractedFieldsJson={"poNumber": "PO-EXTRACTED"},
            reviewedData=existing_reviewed_fields.copy(),
            isReviewed=True,
            reviewedBy=7,
            invoiceNumber="INV-REVIEWED",
            vendorName="Vendor",
            invoiceDate=None,
            dueDate=None,
            subtotal=None,
            taxAmount=None,
            totalAmount=None,
            currency=None
        )

        with (
            patch(
                "app.repositories.invoice_repository.get_invoice_by_id",
                return_value=SimpleNamespace(id=12)
            ),
            patch(
                "app.repositories.invoice_repository."
                "get_extracted_invoice_data_by_invoice_id",
                return_value=extracted_data
            )
        ):
            update_invoice_review(
                db=Mock(),
                invoice_id=12,
                review_data={"paymentTerms": "Due on receipt"},
                reviewed_by=7
            )

        self.assertEqual(
            extracted_data.reviewedFieldsJson["paymentTerms"],
            "Due on receipt"
        )
        self.assertEqual(
            extracted_data.reviewedFieldsJson["poNumber"],
            "PO-EXISTING"
        )
        self.assertEqual(
            extracted_data.reviewedFieldsJson["vendorGst"],
            "27ABCDE1234F1Z5"
        )
        self.assertEqual(
            extracted_data.reviewedFieldsJson["vendorAddress"],
            "10 Existing Road"
        )

    @patch("app.routers.invoice_router.review_invoice_service")
    def test_review_response_returns_saved_dynamic_values(self, service):
        reviewed_fields = {
            "poNumber": "PO-2026-102",
            "paymentTerms": "Net 30"
        }
        invoice = SimpleNamespace(id=12, processingStatus="reviewed")
        extracted_data = SimpleNamespace(
            reviewedFieldsJson=reviewed_fields,
            isReviewed=True,
            reviewedBy=7,
            updatedAt=None
        )
        service.return_value = {
            "invoice": invoice,
            "extracted_data": extracted_data
        }
        db = object()

        response = review_invoice(
            invoice_id=12,
            payload=InvoiceReviewRequest(
                poNumber="PO-2026-102",
                paymentTerms="Net 30"
            ),
            db=db
        )

        self.assertEqual(
            response["data"]["reviewedFieldsJson"],
            reviewed_fields
        )
        service.assert_called_once_with(
            db=db,
            invoice_id=12,
            review_data={
                "poNumber": "PO-2026-102",
                "paymentTerms": "Net 30"
            }
        )


if __name__ == "__main__":
    unittest.main()
