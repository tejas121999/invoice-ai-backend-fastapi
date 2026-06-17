from sqlalchemy import Column, Integer, String, DateTime
from app.core.database import Base
from datetime import datetime


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    passwordHash = Column("passwordHash", String(255), nullable=False)
    role = Column(String(64))
    createdAt = Column("createdAt", DateTime, default=datetime.utcnow)
    updatedAt = Column("updatedAt", DateTime, default=datetime.utcnow)
