from pydantic import BaseModel


class InvoiceCreate(BaseModel):
    file_name: str
    original_name: str


class InvoiceResponse(BaseModel):
    id: int
    file_name: str
    status: str

    class Config:
        from_attributes = True
