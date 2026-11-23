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

PDF_SIGNATURE = b"%PDF-"
JPEG_SIGNATURE = b"\xff\xd8\xff"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class FileValidatorTests(unittest.TestCase):
    def test_supported_extensions_are_accepted(self):
        cases = (
            ("invoice.pdf", "application/pdf", ".pdf", PDF_SIGNATURE),
            ("invoice.jpg", "image/jpeg", ".jpg", JPEG_SIGNATURE),
            ("invoice.jpeg", "image/jpeg", ".jpeg", JPEG_SIGNATURE),
            ("invoice.png", "image/png", ".png", PNG_SIGNATURE),
        )

        for filename, content_type, expected_extension, signature in cases:
            with self.subTest(filename=filename):
                upload = make_upload(
                    filename,
                    content_type,
                    content=signature + b"valid content"
                )
                self.assertEqual(
                    validate_invoice_file(upload),
                    expected_extension
                )
                self.assertEqual(upload.file.tell(), 0)

    def test_pdf_extension_with_non_pdf_content_is_rejected(self):
        self.assert_signature_mismatch(
            "invoice.pdf", "application/pdf", b"not a PDF"
        )

    def test_jpg_extension_with_pdf_content_is_rejected(self):
        self.assert_signature_mismatch(
            "invoice.jpg", "image/jpeg", PDF_SIGNATURE + b"data"
        )

    def test_png_extension_with_invalid_content_is_rejected(self):
        self.assert_signature_mismatch(
            "invoice.png", "image/png", b"invalid PNG"
        )

    def test_correct_extension_with_incorrect_content_type_is_rejected(self):
        self.assert_signature_mismatch(
            "invoice.pdf", "image/jpeg", PDF_SIGNATURE + b"data"
        )

    def assert_signature_mismatch(
        self,
        filename: str,
        content_type: str,
        content: bytes
    ):
        upload = make_upload(filename, content_type, content=content)

        with self.assertRaises(HTTPException) as context:
            validate_invoice_file(upload)

        self.assertEqual(context.exception.status_code, 400)
        self.assertEqual(
            context.exception.detail,
            "File extension, content type, and file content do not match"
        )
        self.assertEqual(upload.file.tell(), 0)

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
            "File extension, content type, and file content do not match"
        )


class FileUploadSizeTests(unittest.IsolatedAsyncioTestCase):
    async def assert_upload_permission_error_is_sanitized(
        self,
        upload: UploadFile,
        upload_dir: str,
        patcher
    ):
        with (
            patch.object(settings, "UPLOAD_DIR", upload_dir),
            patcher
        ):
            with self.assertRaises(HTTPException) as context:
                await save_invoice_file(upload)

        self.assertEqual(context.exception.status_code, 500)
        self.assertEqual(
            context.exception.detail,
            "Invoice file could not be uploaded."
        )
        self.assertNotIn("C:\\private", context.exception.detail)
        self.assertTrue(upload.file.closed)

    async def test_permission_error_creating_upload_directory_is_sanitized(self):
        with tempfile.TemporaryDirectory() as upload_dir:
            upload = make_upload(
                "invoice.pdf",
                "application/pdf",
                content=PDF_SIGNATURE + b"test"
            )

            await self.assert_upload_permission_error_is_sanitized(
                upload,
                upload_dir,
                patch(
                    "app.services.file_upload_service.Path.mkdir",
                    side_effect=PermissionError(
                        "Permission denied at C:\\private\\uploads"
                    )
                )
            )

    async def test_permission_error_writing_upload_is_sanitized(self):
        with tempfile.TemporaryDirectory() as upload_dir:
            upload = make_upload(
                "invoice.pdf",
                "application/pdf",
                content=PDF_SIGNATURE + b"test"
            )

            await self.assert_upload_permission_error_is_sanitized(
                upload,
                upload_dir,
                patch(
                    "app.services.file_upload_service.aiofiles.open",
                    side_effect=PermissionError(
                        "Permission denied at C:\\private\\invoice.pdf"
                    )
                )
            )

    async def test_file_within_limit_is_saved(self):
        with tempfile.TemporaryDirectory() as upload_dir:
            upload = make_upload(
                "invoice.pdf",
                "application/pdf",
                content=PDF_SIGNATURE + b"test"
            )

            with (
                patch.object(settings, "UPLOAD_DIR", upload_dir),
                patch.object(settings, "MAX_FILE_SIZE_MB", 1)
            ):
                result = await save_invoice_file(upload)

            saved_file = Path(upload_dir) / result["fileName"]
            self.assertTrue(saved_file.exists())
            self.assertTrue(Path(result["filePath"]).is_absolute())
            self.assertEqual(
                Path(result["filePath"]),
                saved_file.resolve()
            )
            self.assertEqual(
                saved_file.read_bytes(),
                PDF_SIGNATURE + b"test"
            )
            self.assertEqual(result["fileType"], "application/pdf")
            self.assertEqual(
                result["file_size"],
                len(PDF_SIGNATURE + b"test")
            )

    async def test_file_larger_than_configured_limit_is_rejected(self):
        with tempfile.TemporaryDirectory() as upload_dir:
            upload = make_upload(
                "large.pdf",
                "application/pdf",
                content=PDF_SIGNATURE + b"x" * (
                    1024 * 1024 + 1 - len(PDF_SIGNATURE)
                )
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
