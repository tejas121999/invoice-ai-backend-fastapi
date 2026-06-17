from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from app.core.database import engine, Base
from app.core.database import get_db

from app.models import invoice
from app.models import extracted_invoice
from app.models import audit_log
from app.models import user


Base.metadata.create_all(bind=engine)

app = FastAPI()


@app.get("/")
def home():
    return {"message": "Invoice AI Backend Running"}


@app.get("/test-db")
def test_db(db: Session = Depends(get_db)):
    return {"message": "Database connected"}
