from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Response, Body, status
import requests
import os
import logging
from typing import Dict, Any, Optional
import json
import hmac
import hashlib
import traceback

from ..services.recipe_service import recipe_service
from ..utils.helpers import sanitize_input

logger = logging.getLogger(__name__)
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
                messages = value.get("messages", [])
                if not messages:
                    continue
                message = messages[0]
                message_type = message.get("type")
                from_number = message.get("from")
                if not from_number:
                    continue
                if message_type != "text":
                    return {"type": "unsupported", "from_number": from_number}
                body = message.get("text", {}).get("body", "").strip()
                if not body:
                    return {"type": "empty", "from_number": from_number}
                # Parse ingredients and options
                parts = body.split("|")
                ingredients = [sanitize_input(i.strip()) for i in parts[0].split(",") if i.strip()]
                if not ingredients:
                    return {"type": "no_ingredients", "from_number": from_number}
                cuisine = sanitize_input(parts[1].strip()) if len(parts) > 1 else None
                restrictions = [sanitize_input(r.strip()) for r in parts[2].split(",")] if len(parts) > 2 else []
                cooking_time = int(parts[3].strip()) if len(parts) > 3 and parts[3].strip().isdigit() else None
                return {
                    "type": "recipe_request",
                    "from_number": from_number,
                    "ingredients": ingredients,
                    "cuisine": cuisine,
                    "dietary_restrictions": restrictions,
                    "cooking_time": cooking_time
                }
        return None
    except Exception as e:
        logger.error(f"Failed to parse WhatsApp message: {e}")
        return None

def format_recipe_for_whatsapp(recipe: Dict[str, Any]) -> str:
    try:
        if not recipe['title'] or not recipe['title'].strip():
            return "Kindly provide the correct dish name or ingredients to proceed."

        return "\n".join([
            "🍳 *Recipe Generated* 🍳",
            f"*{recipe['title']}*",
            "*Ingredients:*",
            "\n".join(f"• {i}" for i in recipe['ingredients']),
            "*Instructions:*",
            "\n".join(f"{idx+1}. {step}" for idx, step in enumerate(recipe['instructions'])),
            f"*Cooking Time:* {recipe['cooking_time']} minutes",
            f"*Difficulty:* {recipe['difficulty']}",
            "Enjoy your meal! 🍽️",
            f"Recipe ID: {recipe['recipe_id']}"
        ])
    except Exception as e:
        logger.error(f"Error formatting recipe: {e}")
        return "Sorry, something went wrong formatting the recipe."

def get_welcome_message() -> str:
    return """👋 *Welcome to Food Recipe Bot!* 🍳

Send ingredients like:
`ingredient1, ingredient2 | cuisine | dietary restrictions | time`

Type 'help' for more options."""

def get_help_message() -> str:
    return """📖 *Food Recipe Bot Help*

Format:
`ingredients | cuisine | dietary restrictions | cooking time`

Example:
• `chicken, rice`
• `pasta, tomato | Italian | vegetarian | 20`"""

def get_no_ingredients_message() -> str:
    return """⚠ No ingredients detected.

Send like:
`ingredient1, ingredient2`

Example:
`chicken, rice, vegetables`"""

async def process_recipe_request(from_number: str, recipe_data: Dict[str, Any]):
    try:
        recipe = await recipe_service.generate_recipe(recipe_data)
        message = format_recipe_for_whatsapp(recipe)
        whatsapp_api.send_text_message(from_number, message)
    except Exception as e:
        logger.error(f"Error in process_recipe_request: {e}")
        whatsapp_api.send_text_message(from_number, "Sorry, something went wrong while generating the recipe.")

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
    
@router.post("/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    webhook_data: Dict[str, Any] = Body(...)
):
    if not WHATSAPP_ACCESS_TOKEN:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "WhatsApp integration not configured")
    try:
        body_bytes = await request.body()

        # Verify signature
        if not verify_whatsapp_webhook(request, body_bytes):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")

        logger.debug(f"Webhook data: {json.dumps(webhook_data, indent=2)}")

        parsed_message = parse_whatsapp_message(webhook_data)
        
        if not parsed_message or "from_number" not in parsed_message or not parsed_message["from_number"]:
            logger.warning("Invalid or unsupported message format")
            #whatsapp_api.send_text_message(from_number, "Please send some ingredients!")
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
            whatsapp_api.send_text_message(from_number, "Only text messages are supported.")
            return {"status": "success", "message": "Unsupported message handled"}

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
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
