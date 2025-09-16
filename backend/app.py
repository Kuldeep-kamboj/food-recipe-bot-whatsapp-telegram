from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import routers
from .routes.recipe_routes import router as recipe_router
from .integrations.whatsapp_api import router as whatsapp_router
from .integrations.telegram_bot import router as telegram_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    debug=True,
    title="Food Recipe Bot API",
    description="API for generating recipes using AI and integrating with WhatsApp",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
#app.include_router(whatsapp_router, prefix="/api/v1", tags=["health"])
app.include_router(recipe_router, prefix="/api/v1", tags=["recipes"])
app.include_router(whatsapp_router, prefix="/api/v1", tags=["whatsapp"])
app.include_router(telegram_router, prefix="/api/v1", tags=["telegram"])

@app.get("/api/v1")
async def root():
    """Health check endpoint"""
    return {
        "message": "Food Recipe Bot API is running",
        "version": "1.0.0",
        "endpoints": {
            "generate_recipe": "POST /api/v1/recipes/generate",
            "get_recipe": "GET /api/v1/recipes/{recipe_id}",
            "recent_recipes": "GET /api/v1/recipes",
            "whatsapp_webhook": "POST /api/v1/webhook/whatsapp",
            "telegram_webhook": "POST /api/v1/webhook/telegram"
        }
    }

@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "food-recipe-bot"}

# Error handlers
@app.exception_handler(500)
async def internal_server_error_handler(request, exc):
    logger.error(f"Internal server error: {exc}")
    return {"error": "Internal server error", "detail": str(exc)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True if os.getenv("ENVIRONMENT") == "development" else False
    )