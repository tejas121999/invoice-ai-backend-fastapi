import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.repositories.invoice_repository import save_extract_result
from app.routers.invoice_router import get_invoice_result, review_invoice
from app.schemas.invoice_schema import InvoiceReviewRequest
from app.schemas.extraction_schema import ExtractionRequest
from app.services.extraction_service import extract_invoice
from app.utils.invoice_status import InvoiceStatus


INVOICE_TEXT = """TAX INVOICE
Vendor Name: NovaTech Solutions Pvt. Ltd.
Vendor GSTIN: 27ABCDE1234F1Z5
Vendor Address:
12 Market Street
Springfield
Invoice Number: NT-2026-2045
Invoice Date: 18 November 2026
Due Date: 03 December 2026
Currency: INR
Purchase Order Number: PO-2026-102
Payment Terms: Net 30 days
Payment Reference: PAY-2026-2045
Shipping Charges: INR 1,000.00
Discount: INR 500.00
Bill To: Global Retail Technologies Pvt. Ltd.
Subtotal: 70,000.00
Tax Amount (18%): 12,600.00
Total Amount: 82,600.00"""

DYNAMIC_FIELD_NAMES = (
    "poNumber",
    "vendorGst",
    "paymentTerms",
    "shippingCharges",
    "discount",
    "vendorAddress",
    "paymentReference"
)


class DynamicInvoiceWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_extract_review_and_result_workflow(self):
        invoice = SimpleNamespace(
            id=901,
            processingStatus=InvoiceStatus.PROCESSED.value,
            fileName="isolated-dynamic-invoice.pdf",
            filePath="uploads/invoices/isolated-dynamic-invoice.pdf",
            uploadedAt=None,
            processedAt=None,
            rawText=None
        )
        db = Mock()

        with (
            patch(
                "app.services.extraction_service.read_document_text",
                return_value=INVOICE_TEXT
            ),
            patch("app.services.extraction_service.log_performance"),
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
            extraction_response = await extract_invoice(
                ExtractionRequest(
                    invoiceId=901,
                    filePath=invoice.filePath
                )
            )
            persisted_result = save_extract_result(
                db=db,
                invoice_id=901,
                extraction_data=extraction_response.model_dump(
                    by_alias=True
                )
            )

        extracted_data = persisted_result["extracted_data"]
        original_fields = dict(extracted_data.extractedFieldsJson)
        original_confidence = dict(extracted_data.confidenceJson)

        self.assertEqual(original_fields["invoiceNumber"], "NT-2026-2045")
        self.assertEqual(
            original_fields["vendorName"],
            "NovaTech Solutions Pvt. Ltd."
        )
        self.assertEqual(original_fields["invoiceDate"], "2026-11-18")
        self.assertEqual(original_fields["dueDate"], "2026-12-03")
        self.assertEqual(original_fields["subtotal"], 70000.0)
        self.assertEqual(original_fields["taxAmount"], 12600.0)
        self.assertEqual(original_fields["totalAmount"], 82600.0)
        self.assertEqual(original_fields["currency"], "INR")
        self.assertEqual(original_fields["poNumber"], "PO-2026-102")
        self.assertEqual(original_fields["vendorGst"], "27ABCDE1234F1Z5")
        self.assertEqual(original_fields["paymentTerms"], "Net 30 days")
        self.assertEqual(original_fields["shippingCharges"], 1000.0)
        self.assertEqual(original_fields["discount"], 500.0)
        self.assertEqual(
            original_fields["vendorAddress"],
            "12 Market Street Springfield"
        )
        self.assertEqual(
            original_fields["paymentReference"],
            "PAY-2026-2045"
        )
        for field_name in DYNAMIC_FIELD_NAMES:
            with self.subTest(confidence_field=field_name):
                self.assertGreater(original_confidence[field_name], 0.0)
        self.assertEqual(extracted_data.reviewedFieldsJson, {})

        invoice_by_id = lambda _db, _invoice_id: invoice
        extracted_by_invoice_id = lambda db, invoice_id: extracted_data

        def transition_to_reviewed(
            db,
            invoice,
            new_status,
            user_id=None,
            reason=None
        ):
            invoice.processingStatus = new_status.value
            return invoice

        with (
            patch(
                "app.services.invoice_service.get_invoice_by_id",
                side_effect=invoice_by_id
            ),
            patch(
                "app.services.invoice_service."
                "get_extracted_invoice_data_by_invoice_id",
                side_effect=extracted_by_invoice_id
            ),
            patch(
                "app.repositories.invoice_repository.get_invoice_by_id",
                side_effect=invoice_by_id
            ),
            patch(
                "app.repositories.invoice_repository."
                "get_extracted_invoice_data_by_invoice_id",
                side_effect=extracted_by_invoice_id
            ),
            patch(
                "app.services.invoice_service.change_invoice_status",
                side_effect=transition_to_reviewed
            ),
            patch("app.services.invoice_service.save_audit_log")
        ):
            first_review = review_invoice(
                invoice_id=901,
                payload=InvoiceReviewRequest(
                    poNumber="PO-CORRECTED-102",
                    vendorGst="27ABCDE1234F1Z9",
                    reviewedBy=7
                ),
                db=db
            )
            self.assertEqual(
                first_review["data"]["reviewedFieldsJson"]["poNumber"],
                "PO-CORRECTED-102"
            )
            self.assertEqual(
                first_review["data"]["reviewedFieldsJson"]["vendorGst"],
                "27ABCDE1234F1Z9"
            )

            second_review = review_invoice(
                invoice_id=901,
                payload=InvoiceReviewRequest(
                    paymentTerms="Due on receipt",
                    reviewedBy=7
                ),
                db=db
            )

        reviewed_fields = extracted_data.reviewedFieldsJson
        self.assertEqual(reviewed_fields["poNumber"], "PO-CORRECTED-102")
        self.assertEqual(reviewed_fields["vendorGst"], "27ABCDE1234F1Z9")
        self.assertEqual(
            reviewed_fields["paymentTerms"],
            "Due on receipt"
        )
        self.assertEqual(
            extracted_data.extractedFieldsJson,
            original_fields
        )
        self.assertEqual(
            extracted_data.confidenceJson,
            original_confidence
        )
        self.assertEqual(
            second_review["data"]["reviewedFieldsJson"],
            reviewed_fields
        )

        with patch(
            "app.routers.invoice_router.get_invoice_result_services",
            return_value={
                "invoice": invoice,
                "extracted_data": extracted_data
            }
        ):
            result_response = get_invoice_result(
                invoice_id=901,
                db=db
            )

        self.assertEqual(result_response["data"]["fields"], original_fields)
        self.assertEqual(
            result_response["data"]["confidence"],
            original_confidence
        )
        self.assertEqual(
            result_response["data"]["reviewedFieldsJson"],
            reviewed_fields
        )
        self.assertEqual(
            result_response["data"]["fields"]["poNumber"],
            "PO-2026-102"
        )
        self.assertEqual(
            result_response["data"]["reviewedFieldsJson"]["poNumber"],
            "PO-CORRECTED-102"
        )


if __name__ == "__main__":
    unittest.main()
