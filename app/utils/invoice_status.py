from enum import Enum


class InvoiceStatus(str, Enum):
    UPLOADED = "Uploaded"
    PROCESSING = "Processing"
    PROCESSED = "Processed"
    REVIEWED = "Reviewed"
    DUPLICATE_CHECKED = "DuplicateChecked"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    FAILED = "Failed"
