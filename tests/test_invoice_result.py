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

    @patch("app.routers.invoice_router.get_invoice_result_services")
    def test_returns_dynamic_extracted_confidence_and_partial_reviewed_fields(
        self,
        result_service
    ):
        extracted_fields = {
            **self.extracted_fields,
            "poNumber": "PO-ORIGINAL",
            "vendorGst": "27ABCDE1234F1Z5",
            "paymentTerms": "Net 30",
            "shippingCharges": 10.5,
            "discount": 5.0,
            "vendorAddress": "10 Original Road",
            "paymentReference": "PAY-ORIGINAL"
        }
        confidence = {
            "invoiceNumber": 0.96,
            "poNumber": 0.95,
            "vendorGst": 0.98,
            "paymentTerms": 0.90,
            "shippingCharges": 0.88,
            "discount": 0.87,
            "vendorAddress": 0.84,
            "paymentReference": 0.86
        }
        reviewed_fields = {
            "poNumber": "PO-CORRECTED",
            "paymentTerms": "Due on receipt",
            "vendorAddress": "22 Reviewed Road"
        }
        extracted_data = SimpleNamespace(
            updatedAt=None,
            extractedFieldsJson=extracted_fields,
            reviewedFieldsJson=reviewed_fields,
            confidenceJson=confidence,
            isReviewed=True
        )
        result_service.return_value = {
            "invoice": self.invoice,
            "extracted_data": extracted_data
        }

        response = get_invoice_result(invoice_id=65, db=object())

        self.assertEqual(response["data"]["fields"], extracted_fields)
        self.assertEqual(response["data"]["confidence"], confidence)
        self.assertEqual(
            response["data"]["reviewedFieldsJson"],
            reviewed_fields
        )
        self.assertEqual(
            response["data"]["fields"]["poNumber"],
            "PO-ORIGINAL"
        )
        self.assertEqual(
            response["data"]["reviewedFieldsJson"]["poNumber"],
            "PO-CORRECTED"
        )
        self.assertEqual(
            response["data"]["fields"]["paymentTerms"],
            "Net 30"
        )
        self.assertEqual(
            response["data"]["reviewedFieldsJson"]["paymentTerms"],
            "Due on receipt"
        )
        self.assertEqual(response["data"]["fields"]["invoiceNumber"],
                         "INV-ORIGINAL")
        self.assertEqual(
            response["data"]["reviewedFieldsJson"]["vendorAddress"],
            "22 Reviewed Road"
        )

    @patch("app.routers.invoice_router.get_invoice_result_services")
    def test_empty_extracted_and_reviewed_json_are_returned_as_objects(
        self,
        result_service
    ):
        extracted_data = SimpleNamespace(
            updatedAt=None,
            extractedFieldsJson=None,
            reviewedFieldsJson=None,
            confidenceJson={},
            isReviewed=False
        )
        result_service.return_value = {
            "invoice": self.invoice,
            "extracted_data": extracted_data
        }

        response = get_invoice_result(invoice_id=65, db=object())

        self.assertEqual(response["data"]["fields"], {})
        self.assertEqual(response["data"]["reviewedFieldsJson"], {})
        self.assertEqual(response["data"]["confidence"], {})


if __name__ == "__main__":
    unittest.main()
