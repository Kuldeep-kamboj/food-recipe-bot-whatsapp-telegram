from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Response, Body, status
import requests
import os
import logging
from logging.handlers import RotatingFileHandler
from typing import Dict, Any, Optional, List
from pathlib import Path
import json
import hmac
import hashlib
import traceback
import re
from datetime import datetime
import base64

from ..services.recipe_service import recipe_service
from ..services.payment_service import payment_service
from ..utils.helpers import sanitize_input
from ..config.settings import settings
from ..database.db import db_instance
from ..models.payment_model import PaymentStatus

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Add file handler directly to this logger
if not logger.handlers:
    file_handler = RotatingFileHandler(
        'logs/whatsapp.log', 
        maxBytes=10485760,
        backupCount=5
    )
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.setLevel(logging.DEBUG)

# WhatsApp Cloud API configuration
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v23.0")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")

if not all([WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID]):
    logger.warning("WhatsApp credentials not fully set - WhatsApp integration disabled")

router = APIRouter()

class WhatsAppCloudAPI:
    """WhatsApp Cloud API handler class"""
    def __init__(self):
        self.access_token = WHATSAPP_ACCESS_TOKEN
        self.phone_number_id = WHATSAPP_PHONE_NUMBER_ID
        self.api_url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{self.phone_number_id}/messages"
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    def send_text_message(self, to: str, message: str) -> bool:
        if not self.access_token:
            logger.error("WhatsApp access token not configured")
            return False
        try:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": message
                }
            }
            response = requests.post(self.api_url, json=payload, headers=self.headers, timeout=10)
            response.raise_for_status()
            logger.info(f"Message sent to {to}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send message: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response content: {e.response.text}")
            return False

    def send_image_message(self, to: str, image_url: str, caption: str = "") -> bool:
        """Send image message via WhatsApp"""
        if not self.access_token:
            logger.error("WhatsApp access token not configured")
            return False
        try:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "image",
                "image": {
                    #"link": image_url,
                    "id": image_url,  # Use the uploaded media ID
                    "caption": caption
                }
            }
            logger.info(f"Attempting to send image with media ID: {image_url} to {to}")
            logger.debug(f"Request payload: {payload}")
            response = requests.post(self.api_url, json=payload, headers=self.headers, timeout=10)
            response.raise_for_status()
            logger.info(f"Image message sent to {to}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send image message: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response content: {e.response.text}")
            return False

whatsapp_api = WhatsAppCloudAPI()

def verify_whatsapp_webhook(request: Request, body: bytes) -> bool:
    """Verify WhatsApp webhook signature"""
    if not WHATSAPP_APP_SECRET:
        logger.warning("WHATSAPP_APP_SECRET not set, skipping verification")
        return True  # Only for testing

    signature = request.headers.get("X-Hub-Signature-256", "")
    logger.info(f"Received signature: {signature}")

    if not signature.startswith("sha256="):
        logger.error("Malformed signature header")
        return False

    expected_signature = hmac.new(
        WHATSAPP_APP_SECRET.encode("utf-8"),
        body,
        hashlib.sha256
    ).hexdigest()
    logger.info(f"Expected signature: sha256={expected_signature}")

    match = hmac.compare_digest(f"sha256={expected_signature}", signature)
    if not match:
        logger.error("Webhook signature mismatch!")
    return match

def parse_whatsapp_message(webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse incoming WhatsApp message safely"""
    try:
        entries = webhook_data.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                
                # Extract messages from the correct location in the webhook data
                messages = value.get("messages", [])
                if not messages:
                    continue
                    
                message = messages[0]
                message_type = message.get("type")
                from_number = message.get("from")
                
                if not from_number:
                    continue
                
                # Handle interactive messages (buttons, lists)
                if message_type == "interactive":
                    interactive_type = message.get("interactive", {}).get("type")
                    if interactive_type == "button_reply":
                        button_id = message.get("interactive", {}).get("button_reply", {}).get("id")
                        return {
                            "type": "button_interaction",
                            "from_number": from_number,
                            "button_id": button_id
                        }
                    elif interactive_type == "list_reply":
                        list_id = message.get("interactive", {}).get("list_reply", {}).get("id")
                        return {
                            "type": "list_interaction",
                            "from_number": from_number,
                            "list_id": list_id
                        }
                
                # Handle text messages
                if message_type != "text":
                    return {"type": "unsupported", "from_number": from_number}
                
                body_text = message.get("text", {}).get("body", "").strip()
                if not body_text:
                    return {"type": "empty", "from_number": from_number}
                
                # Convert to lowercase for command matching but keep original for processing
                body_lower = body_text.lower()
                
                # Check for payment-related commands first
                if any(word in body_lower for word in ["pay", "payment", "premium", "upgrade", "subscribe", "buy"]):
                    return {"type": "payment_request", "from_number": from_number}
                elif any(word in body_lower for word in ["payment status", "status of payment", "payment info", "my payments"]):
                    return {"type": "payment_status", "from_number": from_number}
                elif any(word in body_lower for word in ["confirm payment", "paid", "payment done", "i paid"]):
                    return {"type": "payment_confirmation", "from_number": from_number}
                elif any(word in body_lower for word in ["my account", "account info", "premium status"]):
                    return {"type": "account_info", "from_number": from_number}
                
                # Check for other special commands and conversational messages
                if any(word in body_lower for word in ["start", "hello", "hi", "hey", "good morning", "good evening"]):
                    return {"type": "start", "from_number": from_number}
                elif any(word in body_lower for word in ["help", "support", "assistance", "issue", "complaint"]):
                    return {"type": "help", "from_number": from_number}
                elif any(word in body_lower for word in ["more"]):    
                    return {"type": "more_options", "from_number": from_number}
                elif any(word in body_lower for word in ["thank", "thanks", "appreciate", "grateful"]):
                    return {"type": "thank_you", "from_number": from_number}
                elif any(word in body_lower for word in ["bye", "goodbye", "see you", "farewell"]):
                    return {"type": "goodbye", "from_number": from_number}
                elif any(word in body_lower for word in ["how are you", "how do you do", "how's it going"]):
                    return {"type": "how_are_you", "from_number": from_number}
                elif any(word in body_lower for word in ["what can you do", "capabilities", "features"]):
                    return {"type": "capabilities", "from_number": from_number}
                
                # Parse ingredients and options
                parts = body_text.split("|")
                ingredients = [sanitize_input(i.strip()) for i in parts[0].split(",") if i.strip()]
                if not ingredients:
                    return {"type": "no_ingredients", "from_number": from_number}
                
                cuisine = sanitize_input(parts[1].strip()) if len(parts) > 1 and parts[1].strip() else None
                restrictions = [sanitize_input(r.strip()) for r in parts[2].split(",")] if len(parts) > 2 and parts[2].strip() else []
                
                # Improved cooking time parsing
                cooking_time = None
                if len(parts) > 3 and parts[3].strip():
                    time_match = re.search(r'(\d+)', parts[3].strip())
                    if time_match:
                        cooking_time = int(time_match.group(1))
                
                return {
                    "type": "recipe_request",
                    "from_number": from_number,
                    "ingredients": ingredients,
                    "cuisine": cuisine,
                    "dietary_restrictions": restrictions,
                    "cooking_time": cooking_time,
                    "original_text": body_text  # Keep original text for debugging
                }
        return None
    except Exception as e:
        logger.error(f"Failed to parse WhatsApp message: {e}")
        logger.error(f"Webhook data that caused error: {json.dumps(webhook_data, indent=2)}")
        return None

def format_recipe_for_whatsapp(recipe: Dict[str, Any]) -> str:
    try:
        if not recipe.get('title') or not recipe['title'].strip():
            return "❌ I couldn't generate a recipe with those ingredients. Please try different ingredients or check your formatting."
        
        message = [
            "🍳 *Recipe Generated* 🍳",
            f"*{recipe['title']}*",
            "",
            "*Ingredients:*",
            "\n".join(f"• {i}" for i in recipe['ingredients']),
            "",
            "*Instructions:*",
            "\n".join(f"{idx+1}. {step}" for idx, step in enumerate(recipe['instructions'])),
            "",
            f"*Cooking Time:* {recipe.get('cooking_time', 'N/A')} minutes",
            f"*Difficulty:* {recipe.get('difficulty', 'N/A')}",
            "",
            "Enjoy your meal! 🍽️",
            "",
            "Type 'more' for additional options or send new ingredients for another recipe."
        ]
        
        return "\n".join(message)
    except Exception as e:
        logger.error(f"Error formatting recipe: {e}")
        return "❌ Sorry, something went wrong while formatting the recipe. Please try again."

def get_welcome_message() -> str:
    return """👋 *Welcome to Food Recipe Bot!* 🍳

I can help you discover delicious recipes based on ingredients you have.

📋 *How to use:*
Send your ingredients in this format:
`ingredient1, ingredient2 | cuisine | dietary restrictions | cooking time`

💰 *Premium Features:*
Type 'premium' to upgrade for:
• Exclusive recipes from top chefs
• Step-by-step video guides
• Nutritional information
• Meal planning features

✨ *Examples:*
• `chicken, rice, vegetables`
• `pasta, tomato | Italian | vegetarian | 30`
• `eggs, cheese | | gluten-free`

💡 *Quick commands:*
• *help* - Show detailed instructions
• *more* - Get additional options after a recipe
• *premium* - Upgrade to premium features

Send your ingredients now to get started! 🥘"""

def get_help_message() -> str:
    return """📖 *Food Recipe Bot Help*

🥕 *Format your message:*
`ingredients | cuisine | dietary restrictions | cooking time`

💰 *Premium Features:*
Type 'premium' to unlock:
• Exclusive chef recipes
• Video cooking guides
• Nutritional analysis
• Meal planning tools

🍝 *Examples:*
• Basic: `chicken, rice, vegetables`
• With cuisine: `pasta, tomato | Italian`
• With restrictions: `beans, corn | Mexican | vegan`
• With time: `eggs, cheese | | | 15`

🌱 *Supported dietary restrictions:*
vegetarian, vegan, gluten-free, dairy-free, nut-free

🌍 *Supported cuisines:*
Italian, Mexican, Chinese, Indian, Thai, Mediterranean, American

⏱️ *Cooking time:*
Specify maximum preparation time in minutes

Type 'start' to begin or send your ingredients now!"""

def get_no_ingredients_message() -> str:
    return """❌ No ingredients detected.

Please send your ingredients in this format:
`ingredient1, ingredient2, ingredient3`

Examples:
• `chicken, rice, vegetables`
• `pasta, tomato, basil`
• `eggs, cheese, milk`

Type 'help' for more detailed instructions."""

def get_processing_message() -> str:
    return """⏳ *Processing your request...*

I'm generating a recipe based on your ingredients. This may take a few moments.

In the meantime, you can:
• Type 'help' for instructions
• Send 'more' after receiving your recipe for additional options"""

def get_more_options_message(recipe_id: str) -> str:
    return f"""🔍 *Additional Options for Recipe*

What would you like to do next?
• Get similar recipes
• Save this recipe
• Convert measurements
• Get nutritional information
• Start over with new ingredients

Reply with your choice or send new ingredients for another recipe.

Recipe ID: {recipe_id}"""

def get_error_message() -> str:
    return """❌ *Sorry, something went wrong.*

Please try again in a moment. If the problem persists, try rephrasing your request.

Examples:
• `chicken, rice`
• `pasta, tomato | Italian`

Type 'help' for more instructions."""

def get_unsupported_message() -> str:
    return """❌ *Unsupported message type*

I can only process text messages at this time. Please send your ingredients as text.

Examples:
• `chicken, rice, vegetables`
• `pasta, tomato | Italian`

Type 'help' for more instructions."""

def get_thank_you_message() -> str:
    return """🙏 You're welcome!

I'm glad I could help you with your recipe needs.

If you enjoyed the recipe or have any feedback, please let me know!

What would you like to do next?
• Get another recipe with different ingredients
• Type 'help' for instructions
• Type 'more' for additional options on your last recipe"""

def get_goodbye_message() -> str:
    return """👋 Goodbye!

Thank you for using the Food Recipe Bot. I hope you enjoyed your cooking experience!

Feel free to come back anytime you need recipe ideas or cooking inspiration.

Happy cooking! 🍳"""

def get_how_are_you_message() -> str:
    return """🤖 I'm doing great, thank you for asking!

I'm always here and ready to help you discover delicious recipes based on whatever ingredients you have available.

What can I help you cook today?"""

def get_capabilities_message() -> str:
    return """🌟 *What I Can Do*

I'm your personal recipe assistant! Here's what I can help you with:

🍳 *Recipe Generation*
- Create recipes based on ingredients you have
- Suggest cuisine styles (Italian, Mexican, etc.)
- Accommodate dietary restrictions (vegan, gluten-free, etc.)
- Adjust for cooking time constraints

💰 *Premium Features*
- Exclusive recipes from top chefs
- Step-by-step video cooking guides
- Detailed nutritional information
- Personalized meal planning

📋 *Additional Features*
- Provide step-by-step cooking instructions
- Offer recipe variations and alternatives
- Give cooking tips and techniques

💡 *How to Use*
Just send me your ingredients in this format:
`ingredient1, ingredient2 | cuisine | restrictions | time`

Examples:
• `chicken, rice, vegetables`
• `pasta, tomato | Italian | vegetarian | 30`

Type 'help' for more detailed instructions!"""

# Payment-related messages
def get_payment_message() -> str:
    return """💰 *Premium Recipe Access Payment* 💰

Upgrade to premium for:
• Exclusive recipes from top chefs
• Step-by-step video guides
• Nutritional information
• Meal planning features
• Priority support

Reply with 'pay' to continue with payment."""

def get_payment_processing_message() -> str:
    return """⏳ *Processing your payment request...*

We're setting up a secure payment link for you. This will only take a moment."""

def get_payment_success_message() -> str:
    return """🎉 *Payment Successful!* 🎉

Thank you for upgrading to premium! You now have access to:

• Exclusive premium recipes
• Step-by-step video guides
• Nutritional information
• Meal planning features
• Priority support

Enjoy your enhanced cooking experience! 🍳"""

def get_payment_failed_message() -> str:
    return """❌ *Payment Failed*

We couldn't process your payment. This could be due to:
• Insufficient funds
• Network issues
• Payment cancellation

Please try again or contact support if the issue persists."""

def get_payment_instructions_message(upi_link: str, payment_id: str) -> str:
    return f"""📋 *Payment Instructions*

Please complete your payment using one of these methods:

1. *Scan QR Code*: Open any UPI app and scan the QR code we'll send you
2. *Click Link*: {upi_link}
3. *Manual UPI*: Send ₹{settings.PAYMENT_AMOUNT} to {settings.UPI_VPA} with note: {payment_id}

Your Payment ID: {payment_id}

After payment, you'll get instant access to premium recipes! 🎉"""

def get_payment_status_message(payments: List[Dict[str, Any]]) -> str:
    if not payments:
        return "No payments found for your account."
    
    message = ["📊 *Your Payment History*"]
    
    for payment in payments:
        status_emoji = "✅" if payment['status'] == 'captured' else "⏳" if payment['status'] == 'created' else "❌"
        message.append(f"\n{status_emoji} *Payment ID:* {payment['payment_id']}")
        message.append(f"*Amount:* ₹{payment['amount']}")
        message.append(f"*Status:* {payment['status']}")
        message.append(f"*Date:* {payment['created_at']}")
        message.append("─" * 20)
    
    message.append("\nType 'premium' to upgrade or 'help' for more options.")
    return "\n".join(message)

def get_account_info_message(user_data: Dict[str, Any]) -> str:
    if not user_data:
        return "No account information found. Please start by sending a message to create your account."
    
    premium_status = "✅ Premium User" if user_data.get('is_premium') else "❌ Free Account"
    expiry_info = f"\n*Premium Expires:* {user_data.get('premium_expiry')}" if user_data.get('premium_expiry') else ""
    
    return f"""👤 *Your Account Information*

*Phone:* {user_data.get('phone_number', 'N/A')}
*Status:* {premium_status}{expiry_info}
*Member Since:* {user_data.get('created_at', 'N/A')}

Type 'premium' to upgrade your account or 'payment status' to view your payment history."""

async def process_recipe_request(from_number: str, recipe_data: Dict[str, Any]):
    try:
        # Send processing message
        whatsapp_api.send_text_message(from_number, get_processing_message())
        
        # Generate recipe
        recipe = await recipe_service.generate_recipe(recipe_data)
        message = format_recipe_for_whatsapp(recipe)
        whatsapp_api.send_text_message(from_number, message)
        
        # Save user if not exists
        user_data = db_instance.get_user(from_number)
        if not user_data:
            db_instance.save_user({
                'phone_number': from_number,
                'name': None,
                'is_premium': False
            })
            
    except Exception as e:
        logger.error(f"Error in process_recipe_request: {e}")
        whatsapp_api.send_text_message(from_number, get_error_message())

async def process_payment_request(from_number: str):
    """Process payment request from user"""
    try:
        # Send processing message
        whatsapp_api.send_text_message(from_number, get_payment_processing_message())
        
        # Create payment
        payment = payment_service.create_upi_payment_link(
            amount=settings.PAYMENT_AMOUNT,
            description=settings.PAYMENT_DESCRIPTION,
            customer_phone=from_number
        )
        
        # Save payment to database
        db_instance.save_payment({
            'payment_id': payment.payment_id,
            'amount': payment.amount,
            'currency': payment.currency,
            'customer_phone': from_number,
            'status': PaymentStatus.PENDING,
            'description': settings.PAYMENT_DESCRIPTION
        })
        
        # Send payment instructions
        whatsapp_api.send_text_message(
            from_number, 
            get_payment_instructions_message(payment.upi_link, payment.payment_id)
        )
        
        # Send QR code as image if available
        if payment.qr_code:
            whatsapp_api.send_text_message(
                from_number,
                "Scan this QR code with any UPI app to complete your payment:"
            )
            # Note: WhatsApp Cloud API might need special handling for images
            # For now, we'll just send the QR code as a link
            
            #whatsapp_api.send_text_message(
            #    from_number,
            #    f"QR Code URL: {payment.qr_code}"
            #)

            whatsapp_api.send_image_message(
                from_number,  
                save_qrcode_image(payment.qr_code)
            )
        
        return {"status": "success", "payment_id": payment.payment_id}
    except Exception as e:
        logger.error(f"Error in process_payment_request: {e}")
        whatsapp_api.send_text_message(from_number, get_payment_failed_message())
        return {"status": "error", "message": str(e)}

async def process_payment_status_request(from_number: str):
    """Process payment status request from user"""
    try:
        # Get user's payment history
        payments = db_instance.get_user_payments(from_number, limit=5)
        status_message = get_payment_status_message(payments)
        whatsapp_api.send_text_message(from_number, status_message)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error in process_payment_status_request: {e}")
        whatsapp_api.send_text_message(from_number, "Sorry, I couldn't retrieve your payment status. Please try again later.")
        return {"status": "error", "message": str(e)}

async def process_account_info_request(from_number: str):
    """Process account information request"""
    try:
        # Get user account information
        user_data = db_instance.get_user(from_number)
        account_message = get_account_info_message(user_data)
        whatsapp_api.send_text_message(from_number, account_message)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error in process_account_info_request: {e}")
        whatsapp_api.send_text_message(from_number, "Sorry, I couldn't retrieve your account information. Please try again later.")
        return {"status": "error", "message": str(e)}

@router.get("/webhook/whatsapp")
async def verify_whatsapp_webhook_endpoint(request: Request):
    """Webhook verification endpoint for WhatsApp"""
    query_params = request.query_params
    hub_mode = query_params.get("hub.mode")
    hub_verify_token = query_params.get("hub.verify_token")
    hub_challenge = query_params.get("hub.challenge")

    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        logger.info("WhatsApp webhook verified successfully")
        # Return the challenge as plain text, not JSON
        return Response(content=hub_challenge, media_type="text/plain")
    else:
        logger.warning("WhatsApp webhook verification failed")
        raise HTTPException(status_code=403, detail="Verification failed")
    
@router.post("/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    if not WHATSAPP_ACCESS_TOKEN:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "WhatsApp integration not configured")
    
    try:
        body_bytes = await request.body()
        webhook_data = await request.json()

        # Verify signature
        if not verify_whatsapp_webhook(request, body_bytes):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")

        logger.debug(f"Webhook data: {json.dumps(webhook_data, indent=2)}")

        parsed_message = parse_whatsapp_message(webhook_data)
        
        if not parsed_message or "from_number" not in parsed_message or not parsed_message["from_number"]:
            logger.warning("Invalid or unsupported message format")
            return {"status": "ignored", "message": "Non-text or empty message ignored"}

        from_number = parsed_message["from_number"]

        # Handle different message types
        if parsed_message["type"] == "start":
            whatsapp_api.send_text_message(from_number, get_welcome_message())
            return {"status": "success", "message": "Welcome message sent"}

        elif parsed_message["type"] == "help":
            whatsapp_api.send_text_message(from_number, get_help_message())
            return {"status": "success", "message": "Help message sent"}

        elif parsed_message["type"] == "empty":
            whatsapp_api.send_text_message(from_number, "Please send some ingredients!")
            return {"status": "success", "message": "Empty message handled"}

        elif parsed_message["type"] == "no_ingredients":
            whatsapp_api.send_text_message(from_number, get_no_ingredients_message())
            return {"status": "success", "message": "No ingredients message handled"}

        elif parsed_message["type"] == "unsupported":
            whatsapp_api.send_text_message(from_number, get_unsupported_message())
            return {"status": "success", "message": "Unsupported message handled"}
            
        elif parsed_message["type"] == "more_options":
            # This would need the recipe_id from context, which would require session management
            # For now, we'll send a generic message
            whatsapp_api.send_text_message(from_number, "Type 'help' for options or send new ingredients for another recipe.")
            return {"status": "success", "message": "More options message sent"}
            
        elif parsed_message["type"] == "thank_you":
            whatsapp_api.send_text_message(from_number, get_thank_you_message())
            return {"status": "success", "message": "Thank you message sent"}
            
        elif parsed_message["type"] == "goodbye":
            whatsapp_api.send_text_message(from_number, get_goodbye_message())
            return {"status": "success", "message": "Goodbye message sent"}
            
        elif parsed_message["type"] == "how_are_you":
            whatsapp_api.send_text_message(from_number, get_how_are_you_message())
            return {"status": "success", "message": "How are you response sent"}
            
        elif parsed_message["type"] == "capabilities":
            whatsapp_api.send_text_message(from_number, get_capabilities_message())
            return {"status": "success", "message": "Capabilities message sent"}
            
        # Payment-related handlers
        elif parsed_message["type"] == "payment_request":
            background_tasks.add_task(process_payment_request, from_number)
            return {"status": "processing", "message": "Payment processing started"}
            
        elif parsed_message["type"] == "payment_status":
            background_tasks.add_task(process_payment_status_request, from_number)
            return {"status": "processing", "message": "Payment status request processing"}
            
        elif parsed_message["type"] == "payment_confirmation":
            whatsapp_api.send_text_message(from_number, "Thank you for confirming your payment. We'll verify it and update your account shortly.")
            return {"status": "success", "message": "Payment confirmation received"}
            
        elif parsed_message["type"] == "account_info":
            background_tasks.add_task(process_account_info_request, from_number)
            return {"status": "processing", "message": "Account info request processing"}

        elif parsed_message["type"] == "recipe_request":
            recipe_request = {
                "ingredients": parsed_message["ingredients"],
                "cuisine": parsed_message["cuisine"],
                "dietary_restrictions": parsed_message["dietary_restrictions"],
                "cooking_time": parsed_message["cooking_time"]
            }
            background_tasks.add_task(process_recipe_request, from_number, recipe_request)
            return {"status": "processing", "message": "Recipe generation started"}

    except Exception as e:
        logger.error(f"Webhook processing error: {traceback.format_exc()}")
        # Try to send error message to user if we have their number
        try:
            if 'from_number' in locals():
                whatsapp_api.send_text_message(from_number, get_error_message())
        except:
            pass
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
    
def save_qrcode_image(qrcode):
    data_url = qrcode
    # Extract the base64 part
    base64_data = data_url.split(",")[1]

    # Decode and save as PNG
    current_dir = Path(__file__).parent
    # Go up one level and into qrcodes folder
    qr_dir = current_dir.parent / "qrcodes"
    qr_path = qr_dir / "qrcode.jpg"
    with open(qr_path, "wb") as f:
        f.write(base64.b64decode(base64_data))
    
    return upload_qrcode_image(qr_path)
    #return qr_path    

def upload_qrcode_image(imagepath):
    access_token = WHATSAPP_ACCESS_TOKEN
    phone_number_id = WHATSAPP_PHONE_NUMBER_ID
    api_version = "v23.0"
    
    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/media"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        imagepath_str = str(imagepath)
        
        # Verify file exists and has content
        if not os.path.exists(imagepath_str):
            logger.error(f"File does not exist: {imagepath_str}")
            return None
            
        file_size = os.path.getsize(imagepath_str)
        if file_size == 0:
            logger.error(f"File is empty: {imagepath_str}")
            return None
            
        logger.info(f"Uploading file: {imagepath_str}, size: {file_size} bytes")

        with open(imagepath_str, 'rb') as image_file:
            # Read the file content to verify it's not empty
            file_content = image_file.read()
            if len(file_content) == 0:
                logger.error("File content is empty after reading")
                return None
                
            # Reset file pointer
            image_file.seek(0)
            
            files = {
                'file': ('image.jpg', image_file, 'image/jpeg'),
            }
            data = {
                'messaging_product': 'whatsapp'
            }

            response = requests.post(url, headers=headers, files=files, data=data, timeout=30)
            
            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Response text: {response.text}")
            
            response.raise_for_status()
            
            response_data = response.json()
            if 'id' in response_data:
                media_id = response_data['id']
                logger.info(f"Media uploaded successfully with ID: {media_id}")
                return media_id
            else:
                logger.error(f"No media ID in response: {response_data}")
                return None
                
    except Exception as e:
        logger.error(f"Error uploading media: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response content: {e.response.text}")
        return None