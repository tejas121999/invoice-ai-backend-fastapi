import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app.core.config import BASE_DIR, settings
from app.schemas.invoice_schema import InvoiceResponse, InvoiceUploadResponse
from app.utils.document_reader import (
    read_document_text,
    read_image_text,
    read_pdf_text
)
from app.utils.invoice_paths import (
    InvoiceFileAccessError,
    InvalidInvoicePathError,
    InvoiceFileNotFoundError,
    invoice_path_for_response,
    resolve_invoice_path
)


class UploadDirectoryConfigurationTests(unittest.TestCase):
    def test_default_upload_directory_is_absolute_under_base_dir(self):
        expected = (BASE_DIR / "uploads" / "invoices").resolve()

        self.assertEqual(Path(settings.UPLOAD_DIR), expected)
        self.assertTrue(Path(settings.UPLOAD_DIR).is_absolute())
        self.assertEqual(
            settings.model_config["env_file"],
            BASE_DIR / ".env"
        )

    def test_custom_relative_upload_directory_is_anchored_to_base_dir(self):
        custom_settings = settings.__class__(
            DATABASE_URL=settings.DATABASE_URL,
            UPLOAD_DIR="var/custom-invoices"
        )

        self.assertEqual(
            Path(custom_settings.UPLOAD_DIR),
            (BASE_DIR / "var" / "custom-invoices").resolve()
        )

    def test_custom_absolute_upload_directory_is_preserved(self):
        with tempfile.TemporaryDirectory() as upload_dir:
            custom_settings = settings.__class__(
                DATABASE_URL=settings.DATABASE_URL,
                UPLOAD_DIR=upload_dir
            )

        self.assertEqual(
            Path(custom_settings.UPLOAD_DIR),
            Path(upload_dir).resolve()
        )


class InvoicePathResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.upload_dir = self.base_dir / "uploads" / "invoices"
        self.upload_dir.mkdir(parents=True)
        self.patches = (
            patch("app.utils.invoice_paths.BASE_DIR", self.base_dir),
            patch.object(settings, "UPLOAD_DIR", str(self.upload_dir))
        )
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.temp_dir.cleanup)

    def test_legacy_relative_path_resolves_from_base_dir(self):
        invoice_file = self.upload_dir / "example.pdf"
        invoice_file.write_bytes(b"%PDF-test")

        resolved = resolve_invoice_path(
            "uploads/invoices/example.pdf"
        )

        self.assertEqual(resolved, invoice_file.resolve())

    def test_windows_style_relative_path_resolves(self):
        invoice_file = self.upload_dir / "example.pdf"
        invoice_file.write_bytes(b"%PDF-test")

        resolved = resolve_invoice_path(
            r"uploads\invoices\example.pdf"
        )

        self.assertEqual(resolved, invoice_file.resolve())

    def test_absolute_path_inside_upload_directory_resolves(self):
        invoice_file = self.upload_dir / "example.pdf"
        invoice_file.write_bytes(b"%PDF-test")

        self.assertEqual(
            resolve_invoice_path(str(invoice_file)),
            invoice_file.resolve()
        )

    def test_path_traversal_is_rejected(self):
        outside_file = self.base_dir / "outside.pdf"
        outside_file.write_bytes(b"%PDF-test")

        with self.assertRaises(InvalidInvoicePathError):
            resolve_invoice_path("uploads/invoices/../../outside.pdf")

    def test_absolute_path_outside_upload_directory_is_rejected(self):
        outside_file = self.base_dir / "outside.pdf"
        outside_file.write_bytes(b"%PDF-test")

        with self.assertRaises(InvalidInvoicePathError):
            resolve_invoice_path(str(outside_file))

    def test_unc_path_is_rejected_without_accessing_network(self):
        def resolve_without_network(path, *args, **kwargs):
            return path

        with (
            patch(
                "app.utils.invoice_paths.Path.resolve",
                autospec=True,
                side_effect=resolve_without_network
            ),
            patch("app.utils.invoice_paths.Path.stat") as stat_mock
        ):
            with self.assertRaises(InvalidInvoicePathError):
                resolve_invoice_path(r"\\server\share\invoice.pdf")

        stat_mock.assert_not_called()

    def test_symlink_escape_is_rejected(self):
        outside_file = self.base_dir / "outside.pdf"
        outside_file.write_bytes(b"%PDF-test")
        link = self.upload_dir / "outside.pdf"

        try:
            link.symlink_to(outside_file)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"Symlink creation is unavailable: {exc}")

        with self.assertRaises(InvalidInvoicePathError):
            resolve_invoice_path(str(link))

    def test_symlink_escape_is_rejected_when_resolve_returns_target(self):
        link = self.upload_dir / "outside.pdf"
        outside_file = self.base_dir / "outside.pdf"

        def resolve_symlink(path, *args, **kwargs):
            if path == link:
                return outside_file
            return path

        with patch(
            "app.utils.invoice_paths.Path.resolve",
            autospec=True,
            side_effect=resolve_symlink
        ):
            with self.assertRaises(InvalidInvoicePathError):
                resolve_invoice_path(str(link))

    def test_missing_file_raises_clear_exception(self):
        with self.assertRaises(InvoiceFileNotFoundError):
            resolve_invoice_path("uploads/invoices/missing.pdf")

    def test_document_reader_reports_missing_file(self):
        with self.assertRaises(HTTPException) as context:
            read_document_text("uploads/invoices/missing.pdf")

        self.assertEqual(context.exception.status_code, 404)
        self.assertEqual(context.exception.detail, "Invoice file not found.")

    def test_pdf_disappearing_after_resolution_returns_404(self):
        invoice_file = self.upload_dir / "disappearing.pdf"

        with (
            patch(
                "app.utils.document_reader.resolve_invoice_path",
                return_value=invoice_file
            ),
            patch(
                "app.utils.document_reader.pymupdf.open",
                side_effect=FileNotFoundError(
                    "File disappeared at C:\\private\\disappearing.pdf"
                )
            )
        ):
            with self.assertRaises(HTTPException) as context:
                read_document_text(str(invoice_file))

        self.assertEqual(context.exception.status_code, 404)
        self.assertEqual(context.exception.detail, "Invoice file not found.")
        self.assertNotIn("C:\\private", context.exception.detail)

    def test_image_disappearing_after_resolution_returns_404(self):
        invoice_file = self.upload_dir / "disappearing.png"

        with (
            patch(
                "app.utils.document_reader.resolve_invoice_path",
                return_value=invoice_file
            ),
            patch(
                "app.utils.document_reader.Image.open",
                side_effect=FileNotFoundError(
                    "File disappeared at C:\\private\\disappearing.png"
                )
            )
        ):
            with self.assertRaises(HTTPException) as context:
                read_document_text(str(invoice_file))

        self.assertEqual(context.exception.status_code, 404)
        self.assertEqual(context.exception.detail, "Invoice file not found.")
        self.assertNotIn("C:\\private", context.exception.detail)

    def test_document_reader_reports_access_error(self):
        with patch(
            "app.utils.document_reader.resolve_invoice_path",
            side_effect=InvoiceFileAccessError(
                "Permission denied at C:\\private\\invoice.pdf"
            )
        ):
            with self.assertRaises(HTTPException) as context:
                read_document_text("uploads/invoices/example.pdf")

        self.assertEqual(context.exception.status_code, 500)
        self.assertEqual(
            context.exception.detail,
            "Invoice file cannot be accessed."
        )
        self.assertNotIn("C:\\private", context.exception.detail)

    def test_permission_error_during_path_resolution_is_wrapped(self):
        with patch(
            "pathlib.Path.resolve",
            side_effect=PermissionError(
                "Permission denied at C:\\private\\invoice.pdf"
            )
        ):
            with self.assertRaises(InvoiceFileAccessError) as context:
                resolve_invoice_path("uploads/invoices/example.pdf")

        self.assertEqual(
            str(context.exception),
            "Invoice file cannot be accessed."
        )

    def test_permission_error_during_stat_is_wrapped(self):
        invoice_file = self.upload_dir / "example.pdf"
        invoice_file.write_bytes(b"%PDF-test")

        with patch(
            "pathlib.Path.stat",
            side_effect=PermissionError(
                "Permission denied at C:\\private\\invoice.pdf"
            )
        ):
            with self.assertRaises(InvoiceFileAccessError) as context:
                resolve_invoice_path(str(invoice_file))

        self.assertEqual(
            str(context.exception),
            "Invoice file cannot be accessed."
        )

    def test_pdf_open_permission_error_has_stable_http_detail(self):
        with patch(
            "app.utils.document_reader.pymupdf.open",
            side_effect=PermissionError(
                "Permission denied at C:\\private\\invoice.pdf"
            )
        ):
            with self.assertRaises(HTTPException) as context:
                read_pdf_text(self.upload_dir / "example.pdf")

        self.assertEqual(context.exception.status_code, 500)
        self.assertEqual(
            context.exception.detail,
            "Invoice file cannot be accessed."
        )
        self.assertNotIn("C:\\private", context.exception.detail)

    def test_image_open_permission_error_has_stable_http_detail(self):
        with patch(
            "app.utils.document_reader.Image.open",
            side_effect=PermissionError(
                "Permission denied at C:\\private\\invoice.png"
            )
        ):
            with self.assertRaises(HTTPException) as context:
                read_image_text(self.upload_dir / "invoice.png")

        self.assertEqual(context.exception.status_code, 500)
        self.assertEqual(
            context.exception.detail,
            "Invoice file cannot be accessed."
        )
        self.assertNotIn("C:\\private", context.exception.detail)

    def test_document_reader_reads_valid_pdf_path(self):
        invoice_file = self.upload_dir / "example.pdf"
        invoice_file.write_bytes(b"%PDF-test")

        with patch(
            "app.utils.document_reader.read_pdf_text",
            return_value="invoice text"
        ):
            text = read_document_text(str(invoice_file))

        self.assertEqual(text, "invoice text")

    def test_non_file_path_is_rejected(self):
        with self.assertRaises(InvalidInvoicePathError):
            resolve_invoice_path(str(self.upload_dir))

    def test_absolute_paths_are_not_exposed_in_api_path_values(self):
        invoice_file = self.upload_dir / "example.pdf"

        self.assertEqual(
            invoice_path_for_response(str(invoice_file)),
            "uploads/invoices/example.pdf"
        )
        upload_response = InvoiceUploadResponse(
            success=True,
            message="Uploaded",
            invoiceId=1,
            fileName="example.pdf",
            filePath=str(invoice_file),
            uploadStatus="uploaded",
            processingStatus="uploaded"
        )
        invoice_response = InvoiceResponse(
            id=1,
            fileName="example.pdf",
            filePath=str(invoice_file),
            fileType="application/pdf",
            uploadStatus="uploaded",
            processingStatus="uploaded",
            uploadedAt=None
        )

        self.assertEqual(
            upload_response.model_dump()["filePath"],
            "uploads/invoices/example.pdf"
        )
        self.assertEqual(
            invoice_response.model_dump()["filePath"],
            "uploads/invoices/example.pdf"
        )


if __name__ == "__main__":
    unittest.main()
