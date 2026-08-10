from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str

    UPLOAD_DIR: str = "uploads/invoices"
    MAX_FILE_SIZE_MB: int = 10

    # OCR configuration
    TESSERACT_CMD: str | None = None
    OCR_LANGUAGE: str = "eng"
    OCR_PDF_DPI: int = 300

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
