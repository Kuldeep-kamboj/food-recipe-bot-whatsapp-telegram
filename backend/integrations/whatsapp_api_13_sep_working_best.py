from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Response, Body, status
import requests
import os
import logging
from typing import Dict, Any, Optional, List
import json
import hmac
import hashlib
import traceback
import re

from ..services.recipe_service import recipe_service
from ..utils.helpers import sanitize_input

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# WhatsApp Cloud API configuration
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v17.0")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")

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
                
                # Check for special commands
                if body_lower in ["start", "hello", "hi", "hey"]:
                    return {"type": "start", "from_number": from_number}
                elif body_lower == "help":
                    return {"type": "help", "from_number": from_number}
                elif body_lower == "more":
                    return {"type": "more_options", "from_number": from_number}
                
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

✨ *Examples:*
• `chicken, rice, vegetables`
• `pasta, tomato | Italian | vegetarian | 30`
• `eggs, cheese | | gluten-free`

💡 *Quick commands:*
• *help* - Show detailed instructions
• *more* - Get additional options after a recipe

Send your ingredients now to get started! 🥘"""

def get_help_message() -> str:
    return """📖 *Food Recipe Bot Help*

🥕 *Format your message:*
`ingredients | cuisine | dietary restrictions | cooking time`

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

async def process_recipe_request(from_number: str, recipe_data: Dict[str, Any]):
    try:
        # Send processing message
        whatsapp_api.send_text_message(from_number, get_processing_message())
        
        # Generate recipe
        recipe = await recipe_service.generate_recipe(recipe_data)
        message = format_recipe_for_whatsapp(recipe)
        whatsapp_api.send_text_message(from_number, message)
    except Exception as e:
        logger.error(f"Error in process_recipe_request: {e}")
        whatsapp_api.send_text_message(from_number, get_error_message())

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