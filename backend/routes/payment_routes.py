from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from ..models.payment_model import PaymentRequest, PaymentResponse, PaymentStatusResponse
from ..services.payment_service import payment_service
from ..config.settings import settings

router = APIRouter(prefix="/payments", tags=["payments"])

@router.post("/create", response_model=PaymentResponse)
async def create_payment(payment_request: PaymentRequest):
    """Create a new UPI payment"""
    try:
        payment = payment_service.create_upi_payment_link(
            amount=payment_request.amount,
            description=payment_request.description,
            customer_phone=payment_request.customer_phone
        )
        return payment
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/status/{payment_id}", response_model=PaymentStatusResponse)
async def get_payment_status(payment_id: str):
    """Get payment status"""
    try:
        status = payment_service.verify_payment(payment_id)
        return status
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/webhook/razorpay")
async def razorpay_webhook(request: Request):
    """Handle Razorpay webhook for payment status updates"""
    try:
        payload = await request.json()
        
        # Verify webhook signature (important for security)
        # Implement signature verification based on Razorpay docs
        
        # Process webhook event
        event = payload.get('event')
        if event == 'payment.captured':
            payment_id = payload['payload']['payment']['entity']['id']
            # Update your database with successful payment
            # Send WhatsApp message to user
            
        return JSONResponse(content={"status": "success"})
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))