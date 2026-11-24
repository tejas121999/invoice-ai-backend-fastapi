import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.repositories.invoice_repository import save_extract_result
from app.schemas.extraction_schema import (
    ExtractionConfidence,
    ExtractionFields,
    ExtractionRequest
)
from app.services.extraction_service import extract_invoice


class DynamicFieldSchemaTests(unittest.TestCase):
    def test_dynamic_fields_and_confidence_survive_alias_serialization(self):
        fields = ExtractionFields.model_validate({
            "invoiceNumber": "INV-2026-102",
            "totalAmount": 118.0,
            "poNumber": "PO-2026-102",
            "vendorGst": "27ABCDE1234F1Z5",
            "paymentTerms": "Net 30",
            "shippingCharges": 10.0,
            "discount": 5.0,
            "vendorAddress": "10 Example Road",
            "paymentReference": "PAY-102"
        }).model_dump(by_alias=True)
        confidence = ExtractionConfidence.model_validate({
            "invoiceNumber": 0.96,
            "totalAmount": 0.93,
            "poNumber": 0.95,
            "vendorGst": 0.98,
            "paymentTerms": 0.90,
            "shippingCharges": 0.88,
            "discount": 0.87,
            "vendorAddress": 0.84,
            "paymentReference": 0.86
        }).model_dump(by_alias=True)

        self.assertEqual(fields["invoiceNumber"], "INV-2026-102")
        self.assertEqual(fields["totalAmount"], 118.0)
        self.assertEqual(fields["poNumber"], "PO-2026-102")
        self.assertEqual(fields["vendorGst"], "27ABCDE1234F1Z5")
        self.assertEqual(fields["paymentTerms"], "Net 30")
        self.assertEqual(fields["shippingCharges"], 10.0)
        self.assertEqual(fields["discount"], 5.0)
        self.assertEqual(fields["vendorAddress"], "10 Example Road")
        self.assertEqual(fields["paymentReference"], "PAY-102")
        self.assertEqual(confidence["poNumber"], 0.95)
        self.assertEqual(confidence["vendorGst"], 0.98)
        self.assertEqual(confidence["paymentTerms"], 0.90)
        self.assertEqual(confidence["shippingCharges"], 0.88)
        self.assertEqual(confidence["discount"], 0.87)
        self.assertEqual(confidence["vendorAddress"], 0.84)
        self.assertEqual(confidence["paymentReference"], 0.86)


class DynamicFieldPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_extraction_service_fields_reach_repository_json(self):
        extracted_fields = {
            "invoiceNumber": "INV-2026-102",
            "vendorName": "Example Vendor Ltd.",
            "invoiceDate": "2026-01-15",
            "dueDate": "2026-01-30",
            "subtotal": 100.0,
            "taxAmount": 18.0,
            "totalAmount": 118.0,
            "currency": "INR",
            "poNumber": "PO-2026-102",
            "vendorGst": "27ABCDE1234F1Z5",
            "paymentTerms": "Net 30",
            "shippingCharges": 10.0,
            "discount": 5.0,
            "vendorAddress": "10 Example Road",
            "paymentReference": "PAY-102"
        }
        confidence = {
            "invoiceNumber": 0.96,
            "vendorName": 0.90,
            "invoiceDate": 0.95,
            "dueDate": 0.95,
            "subtotal": 0.92,
            "taxAmount": 0.91,
            "totalAmount": 0.93,
            "currency": 0.90,
            "poNumber": 0.95,
            "vendorGst": 0.98,
            "paymentTerms": 0.90,
            "shippingCharges": 0.88,
            "discount": 0.87,
            "vendorAddress": 0.84,
            "paymentReference": 0.86
        }
        invoice = SimpleNamespace(rawText=None)
        db = Mock()

        with (
            patch(
                "app.services.extraction_service.read_document_text",
                return_value="invoice text"
            ),
            patch(
                "app.services.extraction_service.parse_invoice_fields",
                return_value={
                    "fields": extracted_fields,
                    "confidence": confidence,
                    "errors": []
                }
            ),
            patch(
                "app.repositories.invoice_repository.get_invoice_by_id",
                return_value=invoice
            ),
            patch(
                "app.repositories.invoice_repository."
                "get_extracted_invoice_data_by_invoice_id",
                return_value=None
            )
        ):
            response = await extract_invoice(
                ExtractionRequest(
                    invoice_id=7,
                    file_path="uploads/invoices/sample.pdf"
                )
            )
            persisted = save_extract_result(
                db=db,
                invoice_id=7,
                extraction_data=response.model_dump(by_alias=True)
            )

        stored_data = persisted["extracted_data"]
        self.assertEqual(
            stored_data.extractedFieldsJson["poNumber"],
            "PO-2026-102"
        )
        self.assertEqual(
            stored_data.extractedFieldsJson["vendorGst"],
            "27ABCDE1234F1Z5"
        )
        self.assertEqual(
            stored_data.extractedFieldsJson["paymentTerms"],
            "Net 30"
        )
        self.assertEqual(
            stored_data.extractedFieldsJson["shippingCharges"],
            10.0
        )
        self.assertEqual(stored_data.extractedFieldsJson["discount"], 5.0)
        self.assertEqual(
            stored_data.extractedFieldsJson["vendorAddress"],
            "10 Example Road"
        )
        self.assertEqual(
            stored_data.extractedFieldsJson["paymentReference"],
            "PAY-102"
        )
        self.assertEqual(stored_data.confidenceJson, confidence)
        self.assertEqual(stored_data.invoiceNumber, "INV-2026-102")
        self.assertEqual(stored_data.totalAmount, 118.0)
        db.flush.assert_called_once()


if __name__ == "__main__":
    unittest.main()
