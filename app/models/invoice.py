from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from app.core.database import Base
from datetime import datetime


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    fileName = Column(String(512), nullable=False)
    filePath = Column(String(1024), nullable=False)
    fileType = Column(String(128))
    uploadStatus = Column(String(64))
    processingStatus = Column(String(64))
    uploadedBy = Column(Integer, ForeignKey(
        "users.id", ondelete="SET NULL", onupdate="CASCADE"))
    uploadedAt = Column(DateTime)
    processedAt = Column(DateTime)
    reviewedAt = Column(DateTime)
    rawText = Column(Text)
    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, default=datetime.utcnow)
