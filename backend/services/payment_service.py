import razorpay
import qrcode
import base64
import io
import json
from typing import Optional, Dict, Any
from ..config.settings import settings
from ..models.payment_model import PaymentResponse, PaymentStatusResponse, PaymentStatus
from ..database.db import db_instance  # Import the db_instance

class PaymentService:
    def __init__(self):
        self.client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )
    
    def create_upi_payment_link(self, amount: float, description: str, 
                               customer_phone: str) -> PaymentResponse:
        """Create UPI payment link"""
        try:
            # Create Razorpay order
            order_data = {
                "amount": int(amount * 100),  # Convert to paise
                "currency": settings.PAYMENT_CURRENCY,
                "payment_capture": 1,
                "notes": {
                    "description": description,
                    "customer_phone": customer_phone
                }
            }
            
            order = self.client.order.create(order_data)
            
            # Generate UPI payment link
            upi_link = self._generate_upi_link(
                amount=amount,
                order_id=order['id'],
                description=description
            )
            
            # Generate QR code
            qr_code = self._generate_qr_code(upi_link)
            
            # Store payment in database using the DatabaseManager instance
            db_instance.save_payment({
                'payment_id': order['id'],
                'amount': amount,
                'currency': settings.PAYMENT_CURRENCY,
                'customer_phone': customer_phone,
                'status': PaymentStatus.PENDING.value,
                'description': description
            })
            
            return PaymentResponse(
                payment_id=order['id'],
                status="created",
                upi_link=upi_link,
                qr_code=qr_code,
                amount=amount,
                currency=settings.PAYMENT_CURRENCY
            )
            
        except Exception as e:
            raise Exception(f"Payment creation failed: {str(e)}")
    
    def _generate_upi_link(self, amount: float, order_id: str, description: str) -> str:
        """Generate UPI payment deep link"""
        upi_params = {
            "pa": settings.UPI_VPA,
            "pn": "Recipe Bot",
            "am": str(amount),
            "tn": description,
            "cu": settings.PAYMENT_CURRENCY,
            "tr": order_id
        }
        
        query_string = "&".join([f"{k}={v}" for k, v in upi_params.items()])
        return f"upi://pay?{query_string}"
    
    def _generate_qr_code(self, upi_link: str) -> str:
        """Generate base64 encoded QR code"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(upi_link)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return f"data:image/png;base64,{img_str}"
    
    def verify_payment(self, payment_id: str) -> PaymentStatusResponse:
        """Verify payment status"""
        try:
            payment = self.client.payment.fetch(payment_id)
            
            # Update database with payment status using the DatabaseManager instance
            db_instance.update_payment_status(
                payment_id=payment_id,
                status=payment['status'],
                upi_reference=payment.get('acquirer_data', {}).get('rrn')
            )
            
            return PaymentStatusResponse(
                payment_id=payment_id,
                status=payment['status'],
                amount=payment['amount'] / 100,  # Convert from paise to INR
                currency=payment['currency'],
                timestamp=payment['created_at'],
                upi_reference=payment.get('acquirer_data', {}).get('rrn')
            )
            
        except Exception as e:
            raise Exception(f"Payment verification failed: {str(e)}")

payment_service = PaymentService()