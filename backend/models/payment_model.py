from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum

class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"

class PaymentRequest(BaseModel):
    amount: float
    currency: str = "INR"
    description: str
    customer_phone: str
    upi_id: Optional[str] = None

class PaymentResponse(BaseModel):
    payment_id: str
    status: str
    upi_link: Optional[str] = None
    qr_code: Optional[str] = None
    amount: float
    currency: str

class PaymentStatusResponse(BaseModel):
    payment_id: str
    status: str
    amount: float
    currency: str
    timestamp: datetime
    upi_reference: Optional[str] = None

class UPIRequest(BaseModel):
    vpa: str
    amount: float
    note: str = "Recipe Payment"