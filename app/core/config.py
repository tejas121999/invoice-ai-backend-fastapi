from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET_KEY: SecretStr | None = None
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    UPLOAD_DIR: str = str(BASE_DIR / "uploads" / "invoices")
    MAX_FILE_SIZE_MB: int = 10

    @field_validator("JWT_SECRET_KEY", mode="after")
    @classmethod
    def validate_jwt_secret_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value().encode()) < 32:
            raise ValueError("JWT_SECRET_KEY must contain at least 32 bytes")
        return value

    @field_validator("JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    @classmethod
    def validate_jwt_expiration(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("JWT_ACCESS_TOKEN_EXPIRE_MINUTES must be positive")
        return value

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
