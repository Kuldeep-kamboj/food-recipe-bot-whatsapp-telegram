from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Response, Body
import requests
import os
import logging
from typing import Dict, Any, Optional
import json
import hmac
import hashlib

from ..services.recipe_service import recipe_service
from ..utils.helpers import sanitize_input

logger = logging.getLogger(__name__)

# WhatsApp Cloud API configuration
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v23.0")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
#WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "recipe-bot-verify")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")

# Validate configuration
if not all([WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID]):
    logger.warning("WhatsApp Cloud API credentials not set - WhatsApp integration will be disabled")

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
        """Send text message via WhatsApp Cloud API"""
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
            logger.error(f"Failed to send WhatsApp message: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response content: {e.response.text}")
            return False

# Global WhatsApp instance
whatsapp_api = WhatsAppCloudAPI()

def verify_whatsapp_webhook(request: Request, body: bytes) -> bool:
    """Verify WhatsApp webhook signature"""
    if not WHATSAPP_APP_SECRET:
        return True  # No verification if no secret is set
    
    try:
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not signature or not signature.startswith("sha256="):
            return False
        
        # Calculate expected signature
        expected_signature = hmac.new(
            WHATSAPP_APP_SECRET.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures
        return hmac.compare_digest(f"sha256={expected_signature}", signature)
        
    except Exception as e:
        logger.error(f"Error verifying webhook signature: {e}")
        return False

def parse_whatsapp_message(webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Parse recipe request from WhatsApp message.
    Expected format: "ingredient1, ingredient2, ... | cuisine | restrictions | time"
    """
    try:
        # 1. Check if this is a message event and has the right structure
        entries = webhook_data.get("entry", [])
        if not entries:
            logger.debug("No entries found in webhook")
            return None

        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                
                # Check if this change contains messages
                if "messages" in value:
                    messages = value.get("messages", [])
                    if not messages:
                        continue
                    
                    message = messages[0]
                    message_type = message.get("type")
                    from_number = message.get("from")
                    
                    if not from_number:
                        continue
                    
                    # Handle only text messages for now
                    if message_type != "text":
                        return {
                            "type": "unsupported",
                            "from_number": from_number,
                            "message_type": message_type
                        }
                    
                    message_text = message.get("text", {}).get("body", "").strip()
                    
                    if not message_text:
                        return {
                            "type": "empty",
                            "from_number": from_number
                        }
                    
                    # Check for help command
                    if message_text.lower() in ["help", "menu", "options"]:
                        return {
                            "type": "help",
                            "from_number": from_number
                        }
                    
                    # Check for start command
                    if message_text.lower() in ["start", "hi", "hello", "hey"]:
                        return {
                            "type": "start",
                            "from_number": from_number
                        }
                    
                    # Parse ingredients and options
                    parts = message_text.split('|')
                    ingredients = [sanitize_input(ing.strip()) for ing in parts[0].split(',') if ing.strip()]
                    
                    if not ingredients:
                        return {
                            "type": "no_ingredients",
                            "from_number": from_number,
                            "message": message_text
                        }
                    
                    cuisine = sanitize_input(parts[1].strip()) if len(parts) > 1 and parts[1].strip() else None
                    
                    restrictions = []
                    if len(parts) > 2 and parts[2].strip():
                        restrictions = [sanitize_input(restr.strip()) for restr in parts[2].split(',') if restr.strip()]
                    
                    cooking_time = None
                    if len(parts) > 3 and parts[3].strip():
                        try:
                            cooking_time = int(parts[3].strip())
                        except ValueError:
                            pass
                    
                    return {
                        "type": "recipe_request",
                        "from_number": from_number,
                        "ingredients": ingredients,
                        "cuisine": cuisine,
                        "dietary_restrictions": restrictions,
                        "cooking_time": cooking_time
                    }
        
        # If we get here, no message was found in the webhook (e.g., it was a status update)
        logger.debug("Webhook received, but no message data found (might be a status update)")
        return None
        
    except Exception as e:
        logger.error(f"Failed to parse WhatsApp message: {e}")
        return None

def format_recipe_for_whatsapp(recipe: Dict[str, Any]) -> str:
    """Format recipe response for WhatsApp message"""
    try:
        message = [
            "🍳 *Recipe Generated* 🍳",
            "",
            f"*{recipe['title']}*",
            "",
            "*Ingredients:*",
            "\n".join([f"• {ing}" for ing in recipe['ingredients']]),
            "",
            "*Instructions:*",
            "\n".join([f"{i+1}. {step}" for i, step in enumerate(recipe['instructions'])]),
            "",
            f"*Cooking Time:* {recipe['cooking_time']} minutes",
            f"*Difficulty:* {recipe['difficulty']}",
            "",
            "Enjoy your meal! 🍽️",
            "",
            f"Recipe ID: {recipe['recipe_id']}"
        ]
        
        return "\n".join(message)
    except Exception as e:
        logger.error(f"Failed to format recipe for WhatsApp: {e}")
        return "Sorry, I couldn't format the recipe properly."

def get_welcome_message() -> str:
    """Get welcome message for new users"""
    return """👋 *Welcome to Food Recipe Bot!* 🍳

I can create delicious recipes from ingredients you have available.

*How to use:*
Send me your ingredients in this format:
`ingredient1, ingredient2, ingredient3 | cuisine | restrictions | time`

*Examples:*
• `chicken, rice, vegetables`
• `pasta, tomatoes, cheese | Italian`
• `tofu, vegetables | | vegan, gluten-free | 30`

Type *help* for more options or just send your ingredients to get started!"""

def get_help_message() -> str:
    """Get help message"""
    return """📖 *Food Recipe Bot Help*

*Format your message:*
`ingredients | cuisine | dietary restrictions | cooking time`

*All fields except ingredients are optional!*

*Cuisine options:* Italian, Mexican, Chinese, Indian, Thai, American, Mediterranean

*Dietary restrictions:* vegetarian, vegan, gluten-free, dairy-free, nut-free

*Cooking time:* Maximum time in minutes (e.g., 30, 60)

*Quick examples:*
• `chicken, rice, broccoli`
• `pasta, tomatoes, basil | Italian | vegetarian`
• `tofu, vegetables | Chinese | vegan, gluten-free | 30`

Just send your ingredients and I'll create something delicious! 🍳"""

def get_no_ingredients_message() -> str:
    """Get message when no ingredients are found"""
    return """🔄 Message received, but no ingredients found.

*Possible issues:*
• Only emojis were used 🍅🥕 (please use text)
• Too vague: "some stuff from fridge"
• Formatting issues

*Try:* `ingredient1, ingredient2, ingredient3`

*Example:* `chicken, rice, vegetables`"""

async def process_recipe_request(from_number: str, recipe_data: Dict[str, Any]):
    """Process recipe request and send response"""
    try:
        # Generate recipe
        recipe = await recipe_service.generate_recipe(recipe_data)
        
        # Format and send response
        response_message = format_recipe_for_whatsapp(recipe)
        whatsapp_api.send_text_message(from_number, response_message)
        
    except Exception as e:
        logger.error(f"Error processing recipe request: {e}")
        error_message = "Sorry, I encountered an error generating your recipe. Please try again with different ingredients or format."
        whatsapp_api.send_text_message(from_number, error_message)

@router.get("/webhook/whatsapp")
async def verify_whatsapp_webhook_endpoint(request: Request):
    query_params = request.query_params
    hub_mode = query_params.get("hub.mode")
    hub_verify_token = query_params.get("hub.verify_token")
    hub_challenge = query_params.get("hub.challenge")

    """Webhook verification endpoint for WhatsApp"""
    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        logger.info("WhatsApp webhook verified successfully")
        # Return the challenge as plain text, not JSON
        return Response(content=hub_challenge, media_type="text/plain")
    else:
        logger.warning("WhatsApp webhook verification failed")
        raise HTTPException(status_code=403, detail="Verification failed")
    
@router.get("/webhook/whatsapp1")
async def verify_whatsapp_webhook_endpoint(
    hub_mode: str,
    hub_verify_token: str,
    hub_challenge: str
):
    """Webhook verification endpoint for WhatsApp"""
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
    background_tasks: BackgroundTasks,
    body_bytes: bytes = Body(...)  # Get raw bytes directly for signature verification
):
    """Webhook endpoint for WhatsApp messages"""
    if not WHATSAPP_ACCESS_TOKEN:
        raise HTTPException(status_code=501, detail="WhatsApp integration not configured")
    
    try:
        # Verify webhook signature if secret is set
        if not verify_whatsapp_webhook(request, body_bytes):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        
        # Parse the JSON from the verified bytes
        webhook_data = json.loads(body_bytes.decode('utf-8'))
        logger.debug(f"Received WhatsApp webhook: {json.dumps(webhook_data, indent=2)}")
        
        # Parse the message
        parsed_message = parse_whatsapp_message(webhook_data)
        if not parsed_message:
            return {"status": "ignored", "message": "No parsable message found in webhook (could be a status update)"}
        
        from_number = parsed_message["from_number"]
        
        # Handle different message types
        if parsed_message["type"] == "start":
            welcome_msg = get_welcome_message()
            whatsapp_api.send_text_message(from_number, welcome_msg)
            return {"status": "success", "message": "Welcome message sent"}
        
        elif parsed_message["type"] == "help":
            help_msg = get_help_message()
            whatsapp_api.send_text_message(from_number, help_msg)
            return {"status": "success", "message": "Help message sent"}
        
        elif parsed_message["type"] == "empty":
            empty_msg = "Please send me some ingredients to get started! Type 'help' for instructions."
            whatsapp_api.send_text_message(from_number, empty_msg)
            return {"status": "success", "message": "Empty message handled"}
        
        elif parsed_message["type"] == "no_ingredients":
            no_ingredients_msg = get_no_ingredients_message()
            whatsapp_api.send_text_message(from_number, no_ingredients_msg)
            return {"status": "success", "message": "No ingredients message handled"}
        
        elif parsed_message["type"] == "unsupported":
            unsupported_msg = "I currently only support text messages. Please send your ingredients as text."
            whatsapp_api.send_text_message(from_number, unsupported_msg)
            return {"status": "success", "message": "Unsupported message type handled"}
        
        elif parsed_message["type"] == "recipe_request":
            # Process recipe request in background
            recipe_request = {
                'ingredients': parsed_message['ingredients'],
                'cuisine': parsed_message['cuisine'],
                'dietary_restrictions': parsed_message['dietary_restrictions'],
                'cooking_time': parsed_message['cooking_time']
            }
            
            background_tasks.add_task(process_recipe_request, from_number, recipe_request)
            return {"status": "processing", "message": "Recipe generation started"}
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    except Exception as e:
        logger.error(f"Error in WhatsApp webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/webhook/whatsapp/info")
async def get_whatsapp_info():
    """Get information about the WhatsApp business account"""
    if not WHATSAPP_ACCESS_TOKEN:
        raise HTTPException(status_code=501, detail="WhatsApp integration not configured")
    
    try:
        url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}"
        params = {
            "fields": "display_phone_number,quality_rating,status",
            "access_token": WHATSAPP_ACCESS_TOKEN
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code != 200:
            error_data = response.json()
            logger.error(f"Failed to fetch WhatsApp info: {error_data}")
            
            if 'error' in error_data and error_data['error'].get('code') == 190:
                raise HTTPException(
                    status_code=400,
                    detail="WhatsApp access token has expired. Please renew it."
                )
            
            response.raise_for_status()
        
        data = response.json()
        return {"status": "success", "data": data}
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Exception while fetching WhatsApp info: {e}")
        
        if hasattr(e, 'response') and e.response:
            error_data = e.response.json()
            if 'error' in error_data and error_data['error'].get('code') == 190:
                raise HTTPException(
                    status_code=400,
                    detail="WhatsApp access token expired. Please renew it."
                )
        
        raise HTTPException(status_code=500, detail="Failed to fetch WhatsApp information")

@router.get("/webhook/whatsapp/test")
async def test_whatsapp_integration(phone_number: str):
    """Test endpoint to send a message to WhatsApp"""
    if not WHATSAPP_ACCESS_TOKEN:
        raise HTTPException(status_code=501, detail="WhatsApp integration not configured")
    
    test_message = "🚀 WhatsApp integration test successful!\n\nThis is a test message from your Food Recipe Bot. Send your ingredients to get started!"
    
    success = whatsapp_api.send_text_message(phone_number, test_message)
    
    if success:
        return {"status": "success", "message": "Test message sent"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send test message")