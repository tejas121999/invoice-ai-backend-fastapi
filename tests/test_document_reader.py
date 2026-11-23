import gc
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pymupdf
from fastapi import HTTPException

from app.utils.document_reader import read_pdf_text


class PdfDocumentReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_path = Path(self.temp_dir.name)

    def create_pdf(
        self,
        filename: str,
        page_texts: tuple[str, ...],
        *,
        owner_password: str = "",
        user_password: str = ""
    ) -> Path:
        pdf_path = self.temp_path / filename
        document = pymupdf.open()

        try:
            for text in page_texts:
                page = document.new_page()
                if text:
                    page.insert_text((72, 72), text)

            save_options = {}
            if owner_password or user_password:
                save_options = {
                    "encryption": pymupdf.PDF_ENCRYPT_AES_256,
                    "owner_pw": owner_password,
                    "user_pw": user_password
                }

            document.save(pdf_path, **save_options)
        finally:
            document.close()

        return pdf_path

    def test_reads_one_page_and_includes_page_marker(self):
        pdf_path = self.create_pdf(
            "one-page.pdf",
            ("Invoice Number: INV-1001\nVendor: Example Supplies",)
        )

        text = read_pdf_text(pdf_path)

        self.assertIn("[Page 1]", text)
        self.assertIn("Invoice Number: INV-1001", text)
        self.assertNotIn("[Page 2]", text)

    def test_reads_digital_and_scanned_style_pages_in_order(self):
        pdf_path = self.create_pdf(
            "mixed-pages.pdf",
            (
                "Digital invoice page with enough embedded text.",
                ""
            )
        )

        with patch(
            "app.utils.document_reader.run_ocr_on_image",
            return_value="Scanned invoice OCR text."
        ) as ocr_mock:
            text = read_pdf_text(pdf_path)

        self.assertIn("[Page 1]\nDigital invoice page", text)
        self.assertIn("[Page 2]\nScanned invoice OCR text.", text)
        self.assertLess(text.index("[Page 1]"), text.index("[Page 2]"))
        ocr_mock.assert_called_once()

    def test_zero_page_pdf_returns_empty_document_error_and_closes(self):
        document = Mock()
        document.needs_pass = False
        document.page_count = 0

        with patch(
            "app.utils.document_reader.pymupdf.open",
            return_value=document
        ):
            with self.assertRaises(HTTPException) as context:
                read_pdf_text(self.temp_path / "empty.pdf")

        self.assertEqual(context.exception.status_code, 422)
        self.assertEqual(
            context.exception.detail,
            "No readable text was found in the invoice."
        )
        document.close.assert_called_once()

    def test_password_protected_pdf_returns_clear_bad_request_and_closes(self):
        pdf_path = self.create_pdf(
            "password-protected.pdf",
            ("Protected invoice text.",),
            owner_password="owner",
            user_password="secret"
        )

        with self.assertRaises(HTTPException) as context:
            read_pdf_text(pdf_path)

        self.assertEqual(context.exception.status_code, 400)
        self.assertEqual(
            context.exception.detail,
            "The uploaded PDF is password-protected."
        )
        self.assertNotIn("secret", context.exception.detail)

    def test_corrupt_pdf_returns_clear_bad_request(self):
        pdf_path = self.temp_path / "corrupt.pdf"
        pdf_path.write_bytes(b"not a valid PDF")

        with self.assertRaises(HTTPException) as context:
            read_pdf_text(pdf_path)

        self.assertEqual(context.exception.status_code, 400)
        self.assertEqual(
            context.exception.detail,
            "The uploaded PDF could not be opened."
        )
        self.assertNotIn("valid PDF", context.exception.detail)
        context.exception.__cause__ = None
        context.exception.__context__ = None
        context.exception.__traceback__ = None
        del context
        gc.collect()

    def test_page_retrieval_failure_is_marked_and_later_page_is_processed(self):
        first_page = Mock()
        first_page.get_text.return_value = (
            "First page contains enough digital invoice text."
        )
        last_page = Mock()
        last_page.get_text.return_value = (
            "Last page contains enough digital invoice text."
        )

        document = Mock()
        document.needs_pass = False
        document.page_count = 3
        document.load_page.side_effect = (
            first_page,
            RuntimeError("sensitive internal failure"),
            last_page
        )

        with patch(
            "app.utils.document_reader.pymupdf.open",
            return_value=document
        ):
            text = read_pdf_text(self.temp_path / "multi-page.pdf")

        self.assertIn("[Page 1]\nFirst page", text)
        self.assertIn("[Page 2: processing failed]", text)
        self.assertIn("[Page 3]\nLast page", text)
        self.assertLess(text.index("[Page 2"), text.index("[Page 3]"))
        self.assertNotIn("sensitive internal failure", text)
        document.close.assert_called_once()

    def test_ocr_failure_adds_page_specific_marker_and_closes_resources(self):
        pdf_path = self.create_pdf("ocr-failure.pdf", ("",))

        with patch(
            "app.utils.document_reader.run_ocr_on_image",
            side_effect=RuntimeError("sensitive OCR failure")
        ):
            text = read_pdf_text(pdf_path)

        self.assertEqual(text, "[Page 1: processing failed]")
        self.assertNotIn("sensitive OCR failure", text)

    def test_pages_are_combined_in_original_order(self):
        pdf_path = self.create_pdf(
            "ordered-pages.pdf",
            (
                "First page has sufficient text for digital extraction.",
                "Second page has sufficient text for digital extraction.",
                "Third page has sufficient text for digital extraction."
            )
        )

        text = read_pdf_text(pdf_path)

        self.assertLess(text.index("[Page 1]"), text.index("[Page 2]"))
        self.assertLess(text.index("[Page 2]"), text.index("[Page 3]"))
        self.assertLess(text.index("First page"), text.index("Second page"))
        self.assertLess(text.index("Second page"), text.index("Third page"))

    def test_missing_pdf_behavior_remains_404(self):
        with self.assertRaises(HTTPException) as context:
            read_pdf_text(self.temp_path / "missing.pdf")

        self.assertEqual(context.exception.status_code, 404)
        self.assertEqual(context.exception.detail, "Invoice file not found.")

    def test_permission_error_behavior_remains_500(self):
        with patch(
            "app.utils.document_reader.pymupdf.open",
            side_effect=PermissionError("private path")
        ):
            with self.assertRaises(HTTPException) as context:
                read_pdf_text(self.temp_path / "unavailable.pdf")

        self.assertEqual(context.exception.status_code, 500)
        self.assertEqual(
            context.exception.detail,
            "Invoice file cannot be accessed."
        )
        self.assertNotIn("private path", context.exception.detail)


if __name__ == "__main__":
    unittest.main()
