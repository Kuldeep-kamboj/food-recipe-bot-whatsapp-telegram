from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
import requests
import logging
import os
from typing import Dict, Any, Optional
import json
import hmac
import hashlib

from ..services.recipe_service import recipe_service
from ..utils.helpers import sanitize_input, generate_recipe_id
from ..database.db import db_instance

logger = logging.getLogger(__name__)

# Telegram Bot configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Validate required configuration
if not TELEGRAM_BOT_TOKEN:
    logger.warning("TELEGRAM_BOT_TOKEN environment variable not set - Telegram integration will be disabled")

router = APIRouter()

class TelegramBot:
    """Telegram Bot handler class"""
    
    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        self.api_url = f"https://api.telegram.org/bot{self.token}"
    
    def send_message(self, chat_id: int, text: str, parse_mode: str = "Markdown") -> bool:
        """Send message to Telegram chat"""
        if not self.token:
            logger.error("Telegram bot token not configured")
            return False
        
        try:
            url = f"{self.api_url}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }
            
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    def set_webhook(self, webhook_url: str) -> bool:
        """Set Telegram webhook URL"""
        if not self.token:
            return False
        
        try:
            url = f"{self.api_url}/setWebhook"
            payload = {
                "url": webhook_url,
                "drop_pending_updates": True
            }
            
            if TELEGRAM_WEBHOOK_SECRET:
                payload["secret_token"] = TELEGRAM_WEBHOOK_SECRET
            
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info(f"Telegram webhook set to: {webhook_url}")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to set Telegram webhook: {e}")
            return False

# Global Telegram bot instance
telegram_bot = TelegramBot()

def verify_telegram_webhook(request: Request) -> bool:
    """Verify Telegram webhook signature if secret is set"""
    if not TELEGRAM_WEBHOOK_SECRET:
        return True  # No verification required if no secret is set
    
    try:
        signature = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        return hmac.compare_digest(signature, TELEGRAM_WEBHOOK_SECRET)
    except Exception as e:
        logger.error(f"Error verifying webhook signature: {e}")
        return False

def parse_telegram_message(update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Parse recipe request from Telegram message.
    Expected format: "/recipe ingredient1, ingredient2, ... | cuisine | restrictions | time"
    or just "ingredient1, ingredient2, ..."
    """
    try:
        if "message" not in update or "text" not in update["message"]:
            return None
        
        message_text = update["message"]["text"].strip()
        chat_id = update["message"]["chat"]["id"]
        
        # Remove command if present
        if message_text.startswith("/recipe"):
            message_text = message_text.replace("/recipe", "", 1).strip()
        elif message_text.startswith("/start"):
            return {
                "type": "start",
                "chat_id": chat_id,
                "message": message_text
            }
        elif message_text.startswith("/help"):
            return {
                "type": "help",
                "chat_id": chat_id,
                "message": message_text
            }
        
        if not message_text:
            return {
                "type": "empty",
                "chat_id": chat_id,
                "message": message_text
            }
        
        # Parse ingredients and options
        parts = message_text.split('|')
        ingredients = [sanitize_input(ing.strip()) for ing in parts[0].split(',') if ing.strip()]
        
        if not ingredients:
            return {
                "type": "error",
                "chat_id": chat_id,
                "error": "No ingredients provided"
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
            "chat_id": chat_id,
            "ingredients": ingredients,
            "cuisine": cuisine,
            "dietary_restrictions": restrictions,
            "cooking_time": cooking_time
        }
        
    except Exception as e:
        logger.error(f"Failed to parse Telegram message: {e}")
        return None

def format_recipe_for_telegram(recipe: Dict[str, Any]) -> str:
    """Format recipe response for Telegram message using Markdown"""
    try:
        if recipe.get('ingredients'):
            message = [
                f"*🍳 {recipe['title']} 🍳*",
                "",
                "*📋 Ingredients:*",
                "\n".join([f"• {ing}" for ing in recipe['ingredients']]),
                "",
                "*👩‍🍳 Instructions:*",
                "\n".join([f"{i+1}\\. {step}" for i, step in enumerate(recipe['instructions'])]),
                "",
                f"*⏰ Cooking Time:* {recipe['cooking_time']} minutes",
                f"*📊 Difficulty:* {recipe['difficulty']}",
                "",
                "*Enjoy your meal!* 🍽️",
                "",
                f"*Recipe ID:* `{recipe['recipe_id']}`"
            ]
        else:
            #return "No ingredients found"
            return get_no_ingredients_message()
    
        return "\n".join(message)
    except Exception as e:
        logger.error(f"Failed to format recipe for Telegram: {e}")
        return "Sorry, I couldn't format the recipe properly."

def get_welcome_message() -> str:
    """Get welcome message for /start command"""
    return """*Welcome to Food Recipe Bot!* 🍳

I can help you create delicious recipes from ingredients you have available.

*How to use:*
• Send me a list of ingredients like: `chicken, rice, vegetables`
• Or use the format: `ingredient1, ingredient2 | cuisine | restrictions | time`

*Examples:*
• `tomatoes, pasta, basil | Italian | vegetarian | 30`
• `chicken, potatoes, carrots | | gluten-free | 60`
• `eggs, flour, sugar, chocolate`

*Available commands:*
/start - Show this welcome message
/help - Show help information
/recipe - Generate a recipe (you can also just send ingredients)

*Bon appétit!* 🍽️"""

def get_help_message() -> str:
    """Get help message for /help command"""
    return """*Food Recipe Bot Help* 🆘

*Format your request:*
`ingredient1, ingredient2, ingredient3 | cuisine | dietary restrictions | cooking time`

*All fields except ingredients are optional!*

*Cuisine options:* Italian, Mexican, Chinese, Indian, Thai, American, Mediterranean, Japanese, French

*Dietary restrictions:* vegetarian, vegan, gluten-free, dairy-free, nut-free, keto, paleo, low-carb

*Cooking time:* Maximum time in minutes (e.g., 30, 60, 120)

*Examples:*
• `chicken, rice, broccoli | Chinese | | 45`
• `tofu, bell peppers, onions | | vegan, gluten-free | 30`
• `flour, eggs, milk, sugar` (simple format)

*Need more help?* Just send your ingredients and I'll create something delicious! 🍳"""

async def process_recipe_request(chat_id: int, recipe_data: Dict[str, Any]):
    """Process recipe request and send response"""
    try:
        # Send typing action
        telegram_bot.send_message(chat_id, "⌨️")
        
        # Generate recipe
        recipe = await recipe_service.generate_recipe(recipe_data)
        
        # Format and send response
        response_message = format_recipe_for_telegram(recipe)
        telegram_bot.send_message(chat_id, response_message)
        
    except Exception as e:
        logger.error(f"Error processing recipe request: {e}")
        error_message = "Sorry, I encountered an error generating your recipe. Please try again with different ingredients or format."
        telegram_bot.send_message(chat_id, error_message)

@router.post("/webhook/telegram")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """Webhook endpoint for Telegram bot messages"""
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=501, detail="Telegram integration not configured")
    
    # Verify webhook signature if secret is set
    if not verify_telegram_webhook(request):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    try:
        update = await request.json()
        logger.debug(f"Received Telegram update: {update}")
        
        # Parse the message
        parsed_message = parse_telegram_message(update)
        if not parsed_message:
            return {"status": "ignored", "message": "Invalid message format"}
        
        chat_id = parsed_message["chat_id"]
        
        # Handle different message types
        if parsed_message["type"] == "start":
            welcome_msg = get_welcome_message()
            telegram_bot.send_message(chat_id, welcome_msg)
            return {"status": "success", "message": "Welcome message sent"}
        
        elif parsed_message["type"] == "help":
            help_msg = get_help_message()
            telegram_bot.send_message(chat_id, help_msg)
            return {"status": "success", "message": "Help message sent"}
        
        elif parsed_message["type"] == "empty":
            telegram_bot.send_message(chat_id, "Please provide some ingredients! Type /help for instructions.")
            return {"status": "success", "message": "Empty message handled"}
        
        elif parsed_message["type"] == "error":
            telegram_bot.send_message(chat_id, f"Error: {parsed_message['error']}. Type /help for instructions.")
            return {"status": "success", "message": "Error message handled"}
        
        elif parsed_message["type"] == "recipe_request":
            # Process recipe request in background
            recipe_request = {
                'ingredients': parsed_message['ingredients'],
                'cuisine': parsed_message['cuisine'],
                'dietary_restrictions': parsed_message['dietary_restrictions'],
                'cooking_time': parsed_message['cooking_time']
            }
            
            background_tasks.add_task(process_recipe_request, chat_id, recipe_request)
            return {"status": "processing", "message": "Recipe generation started"}
        
    except Exception as e:
        logger.error(f"Error in Telegram webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/webhook/telegram/setup")
async def setup_telegram_webhook(webhook_url: str):
    """Endpoint to set up Telegram webhook (call this once after deployment)"""
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=501, detail="Telegram integration not configured")
    
    success = telegram_bot.set_webhook(webhook_url)
    if success:
        return {"status": "success", "message": "Webhook set successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to set webhook")

@router.get("/webhook/telegram/info")
async def get_telegram_bot_info():
    """Get information about the Telegram bot"""
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=501, detail="Telegram integration not configured")
    
    try:
        url = f"{TELEGRAM_API_URL}/getMe"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        bot_info = response.json()
        return {"status": "success", "bot_info": bot_info}
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to get bot info: {e}")

@router.get("/webhook/telegram/remove")
async def remove_telegram_webhook():
    """Remove Telegram webhook"""
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=501, detail="Telegram integration not configured")
    
    try:
        url = f"{TELEGRAM_API_URL}/deleteWebhook"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return {"status": "success", "message": "Webhook removed successfully"}
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove webhook: {e}")

def get_no_ingredients_message():
    """Return formatted message for no ingredients found"""
    return """🔄 Message received, but no ingredients found.

Possible issues:
• Only emojis were used 🍅🥕 (please use text)
• Too vague: "some stuff from fridge"
• Formatting issues

Try: 'ingredient1, ingredient2, ingredient3'"""