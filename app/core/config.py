from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    DATABASE_URL: str

    UPLOAD_DIR: str = str(BASE_DIR / "uploads" / "invoices")
    MAX_FILE_SIZE_MB: int = 10

    @field_validator("UPLOAD_DIR", mode="before")
    @classmethod
    def resolve_upload_dir(cls, value: str | Path) -> str:
        path = Path(value)
        if not path.is_absolute():
            path = BASE_DIR / path
        return str(path.resolve())

    # OCR configuration
    TESSERACT_CMD: str | None = None
    OCR_LANGUAGE: str = "eng"
    OCR_PDF_DPI: int = 300

    class Config:
        env_file = BASE_DIR / ".env"
        extra = "ignore"


settings = Settings()
