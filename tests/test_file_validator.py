import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.core.config import settings
from app.services.file_upload_service import save_invoice_file
from app.utils.file_validator import validate_invoice_file


def make_upload(filename: str, content_type: str, content: bytes = b"test"):
    return UploadFile(
        file=BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type})
    )


class FileValidatorTests(unittest.TestCase):
    def test_supported_extensions_are_accepted(self):
        cases = (
            ("invoice.pdf", "application/pdf", ".pdf"),
            ("invoice.jpg", "image/jpeg", ".jpg"),
            ("invoice.jpeg", "image/jpeg", ".jpeg"),
            ("invoice.png", "image/png", ".png"),
        )

        for filename, content_type, expected_extension in cases:
            with self.subTest(filename=filename):
                upload = make_upload(filename, content_type)
                self.assertEqual(
                    validate_invoice_file(upload),
                    expected_extension
                )

    def test_webp_is_rejected(self):
        upload = make_upload("invoice.webp", "image/webp")

        with self.assertRaises(HTTPException) as context:
            validate_invoice_file(upload)

        self.assertEqual(context.exception.status_code, 400)
        self.assertEqual(
            context.exception.detail,
            "Only PDF and image files are allowed"
        )

    def test_document_reader_only_formats_are_rejected_by_upload_validation(self):
        for filename, content_type in (
            ("invoice.bmp", "image/bmp"),
            ("invoice.tif", "image/tiff"),
            ("invoice.tiff", "image/tiff"),
        ):
            with self.subTest(filename=filename):
                upload = make_upload(filename, content_type)

                with self.assertRaises(HTTPException) as context:
                    validate_invoice_file(upload)

                self.assertEqual(context.exception.status_code, 400)
                self.assertEqual(
                    context.exception.detail,
                    "Only PDF and image files are allowed"
                )

    def test_unsupported_extension_returns_project_validation_error(self):
        upload = make_upload("invoice.txt", "text/plain")

        with self.assertRaises(HTTPException) as context:
            validate_invoice_file(upload)

        self.assertEqual(context.exception.status_code, 400)
        self.assertEqual(
            context.exception.detail,
            "Only PDF and image files are allowed"
        )

    def test_invalid_content_type_returns_project_validation_error(self):
        upload = make_upload("invoice.pdf", "text/plain")

        with self.assertRaises(HTTPException) as context:
            validate_invoice_file(upload)

        self.assertEqual(context.exception.status_code, 400)
        self.assertEqual(
            context.exception.detail,
            "Invalid file type"
        )


class FileUploadSizeTests(unittest.IsolatedAsyncioTestCase):
    async def test_file_within_limit_is_saved(self):
        with tempfile.TemporaryDirectory() as upload_dir:
            upload = make_upload(
                "invoice.pdf",
                "application/pdf",
                content=b"%PDF-test"
            )

            with (
                patch.object(settings, "UPLOAD_DIR", upload_dir),
                patch.object(settings, "MAX_FILE_SIZE_MB", 1)
            ):
                result = await save_invoice_file(upload)

            saved_file = Path(upload_dir) / result["fileName"]
            self.assertTrue(saved_file.exists())
            self.assertEqual(saved_file.read_bytes(), b"%PDF-test")
            self.assertEqual(result["fileType"], "application/pdf")
            self.assertEqual(result["file_size"], len(b"%PDF-test"))

    async def test_file_larger_than_configured_limit_is_rejected(self):
        with tempfile.TemporaryDirectory() as upload_dir:
            upload = make_upload(
                "large.pdf",
                "application/pdf",
                content=b"x" * (1024 * 1024 + 1)
            )

            with (
                patch.object(settings, "UPLOAD_DIR", upload_dir),
                patch.object(settings, "MAX_FILE_SIZE_MB", 1)
            ):
                with self.assertRaises(HTTPException) as context:
                    await save_invoice_file(upload)

            self.assertEqual(context.exception.status_code, 400)
            self.assertEqual(
                context.exception.detail,
                "File size must be less than 1 MB"
            )

            self.assertEqual(list(Path(upload_dir).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
