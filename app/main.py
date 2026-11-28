from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from app.core.database import engine, Base
from app.core.database import get_db
from app.routers import auth_router, invoice_router
from fastapi.middleware.cors import CORSMiddleware

from app.models import invoice
from app.models import extracted_invoice
from app.models import audit_log
from app.models import user
from app.models import invoice_line_item
from app.models import payment


Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Invoice AI Backend",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(invoice_router.router)


@app.get("/")
def home():
    return {"message": "Invoice AI Backend Running"}


@app.get("/test-db")
def test_db(db: Session = Depends(get_db)):
    return {"message": "Database connected"}
