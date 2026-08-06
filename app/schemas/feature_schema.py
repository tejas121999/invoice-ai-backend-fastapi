from pydantic import BaseModel, Field


class InvoiceComparisonFeatures(BaseModel):
    vendorSimilarity: float = Field(ge=0, le=1)
    invoiceNumberSimilarity: float = Field(ge=0, le=1)

    exactAmountMatch: bool
    amountDifference: float | None = None
    amountSimilarity: float = Field(ge=0, le=1)

    dateDifferenceDays: int | None = None
    currencyMatch: bool


class InvoiceFeatureComparison(BaseModel):
    sourceInvoiceId: int
    candidateInvoiceId: int

    sourceInvoiceNumber: str | None = None
    candidateInvoiceNumber: str | None = None

    sourceVendorName: str | None = None
    candidateVendorName: str | None = None

    features: InvoiceComparisonFeatures


class InvoiceFeatureData(BaseModel):
    invoiceId: int
    comparedInvoices: int
    comparisons: list[InvoiceFeatureComparison]


class InvoiceFeatureResponse(BaseModel):
    success: bool
    message: str
    data: InvoiceFeatureData
