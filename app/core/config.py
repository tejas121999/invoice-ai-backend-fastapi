from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    UPLOAD_DIR: str = "uploads/invoices"
    MAX_FILE_SIZE_MB: int = 10
    PYTHON_OCR_SERVICE_URL: str = "http://localhost:5000"

    class Config:
        env_file = ".env"


settings = Settings()
