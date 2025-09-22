from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
from dotenv import load_dotenv
import time
from fastapi import Request

# Load environment variables
load_dotenv()

# Import routers
from .routes.recipe_routes import router as recipe_router
from .integrations.whatsapp_api import router as whatsapp_router
from .integrations.telegram_bot import router as telegram_router
from .routes.payment_routes import router as payment_router

# Create logs directory if it doesn't exist
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# Configure logging with file handler
logger = logging.getLogger(__name__)
#logger.setLevel(logging.INFO)
logger.setLevel(logging.DEBUG)

# Create formatters
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# File handler for app.log
file_handler = RotatingFileHandler(
    'logs/app.log', 
    maxBytes=10485760,  # 10MB
    backupCount=5
)
file_handler.setLevel(logging.DEBUG)
#file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
#console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Initialize FastAPI app
app = FastAPI(
    debug=True if os.getenv("ENVIRONMENT") == "development" else False,
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

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # Log the incoming request
    logger.info(f"Incoming request: {request.method} {request.url}")
    logger.debug(f"Headers: {dict(request.headers)}")
    
    try:
        response = await call_next(request)
    except Exception as e:
        logger.error(f"Request error: {str(e)}")
        raise
    
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    
    # Log the response
    logger.info(f"Completed request: {request.method} {request.url} - Status: {response.status_code} - Time: {process_time:.4f}s")
    
    return response

# Include routers
try:
    app.include_router(recipe_router, prefix="/api/v1", tags=["recipes"])
    app.include_router(whatsapp_router, prefix="/api/v1", tags=["whatsapp"])
    app.include_router(telegram_router, prefix="/api/v1", tags=["telegram"])
    app.include_router(payment_router, prefix="/api/v1", tags=["payments"])
    logger.info("All routers included successfully")
except Exception as e:
    logger.error(f"Failed to include routers: {str(e)}")
    raise

@app.get("/api/v1")
async def root():
    """Health check endpoint"""
    logger.info("Root endpoint called")
    return {
        "message": "Food Recipe Bot API is running",
        "version": "1.0.0",
        "endpoints": {
            "generate_recipe": "POST /api/v1/recipes/generate",
            "get_recipe": "GET /api/v1/recipes/{recipe_id}",
            "recent_recipes": "GET /api/v1/recipes",
            "whatsapp_webhook": "POST /api/v1/webhook/whatsapp",
            "telegram_webhook": "POST /api/v1/webhook/telegram",
            "payment_endpoints": "Various /api/v1/payments/* endpoints"
        }
    }

# Add health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    logger.info("Health check endpoint called")
    return {"status": "healthy", "service": "food-recipe-bot"}

@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint"""
    logger.info("Health check endpoint called")
    return {"status": "healthy", "service": "food-recipe-bot"}

# Error handlers
@app.exception_handler(500)
async def internal_server_error_handler(request, exc):
    logger.error(f"Internal server error: {exc}", exc_info=True)
    return {"error": "Internal server error", "detail": str(exc)}

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    logger.warning(f"HTTP exception: {exc.status_code} - {exc.detail}")
    return {"error": exc.detail, "status_code": exc.status_code}

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return {"error": "Internal server error", "detail": str(exc)}

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Food Recipe Bot API server")
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True if os.getenv("ENVIRONMENT") == "development" else False
    )