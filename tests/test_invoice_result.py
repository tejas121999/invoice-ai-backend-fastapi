import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.routers.invoice_router import get_invoice_result


class InvoiceResultReviewedFieldsTests(unittest.TestCase):
    def setUp(self):
        self.invoice = SimpleNamespace(
            id=65,
            processingStatus="reviewed",
            fileName="invoice.pdf",
            filePath="uploads/invoices/invoice.pdf",
            uploadedAt=None,
            rawText="Invoice text"
        )
        self.extracted_fields = {
            "invoiceNumber": "INV-ORIGINAL",
            "vendorName": "Original Vendor",
            "subtotal": 100.0
        }
        self.reviewed_fields = {
            "invoiceNumber": "INV-CORRECTED",
            "vendorName": "Reviewed Vendor",
            "subtotal": 125.0
        }

    def make_extracted_data(self, reviewed_fields):
        return SimpleNamespace(
            updatedAt=None,
            extractedFieldsJson=self.extracted_fields,
            reviewedFieldsJson=reviewed_fields,
            confidenceJson={},
            isReviewed=True
        )

    @patch("app.routers.invoice_router.get_invoice_result_services")
    def test_returns_extracted_and_reviewed_fields_separately(
        self,
        result_service
    ):
        result_service.return_value = {
            "invoice": self.invoice,
            "extracted_data": self.make_extracted_data(
                self.reviewed_fields
            )
        }

        response = get_invoice_result(invoice_id=65, db=object())

        self.assertEqual(
            response["data"]["fields"],
            self.extracted_fields
        )
        self.assertEqual(
            response["data"]["reviewedFieldsJson"],
            self.reviewed_fields
        )
        self.assertNotEqual(
            response["data"]["fields"],
            response["data"]["reviewedFieldsJson"]
        )

    @patch("app.routers.invoice_router.get_invoice_result_services")
    def test_returns_empty_reviewed_fields_when_none_are_stored(
        self,
        result_service
    ):
        result_service.return_value = {
            "invoice": self.invoice,
            "extracted_data": self.make_extracted_data(None)
        }

        response = get_invoice_result(invoice_id=65, db=object())

        self.assertEqual(
            response["data"]["fields"],
            self.extracted_fields
        )
        self.assertEqual(
            response["data"]["reviewedFieldsJson"],
            {}
        )


if __name__ == "__main__":
    unittest.main()
