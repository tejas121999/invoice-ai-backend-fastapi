from sqlalchemy import Column, Integer, String, DateTime
from app.core.database import Base
from datetime import datetime


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String(255), nullable=False)
    original_name = Column(String(255))
    file_path = Column(String(500))
    status = Column(String(50), default="uploaded")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
