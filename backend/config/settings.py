import os
from dotenv import load_dotenv
from typing import Optional

# Load environment variables
load_dotenv()

class Settings:
    """Application settings configuration"""
    
    # API Keys
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    WHATSAPP_PHONE_NUMBER_ID: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_ACCESS_TOKEN: str = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    WHATSAPP_BUSINESS_ACCOUNT_ID: str = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "recipes.db")
    
    # Application
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = ENVIRONMENT == "development"
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    # New UPI Payment settings
    RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
    RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
    UPI_MERCHANT_ID = os.getenv("UPI_MERCHANT_ID")
    UPI_VPA = os.getenv("UPI_VPA")  # Your UPI ID
    PAYMENT_SUCCESS_WEBHOOK = os.getenv("PAYMENT_SUCCESS_WEBHOOK", "")
    
    # Payment configuration (default values if not in env)
    PAYMENT_AMOUNT = float(os.getenv("PAYMENT_AMOUNT", "100"))  # Default amount in INR
    PAYMENT_CURRENCY = os.getenv("PAYMENT_CURRENCY", "INR")
    PAYMENT_DESCRIPTION = os.getenv("PAYMENT_DESCRIPTION", "Recipe Premium Access")
    
    # CORS
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "").split(",") or ["*"]
    
    # Validation methods
    def validate_gemini_config(self) -> bool:
        """Validate Gemini AI configuration"""
        return bool(self.GEMINI_API_KEY)
    
    def validate_twilio_config(self) -> bool:
        """Validate Twilio configuration"""
        return all([self.TWILIO_ACCOUNT_SID, self.TWILIO_AUTH_TOKEN, self.TWILIO_PHONE_NUMBER])
    
    def get_database_config(self) -> dict:
        """Get database configuration"""
        return {
            "db_path": self.DATABASE_URL,
            "timeout": 30
        }

# Global settings instance
settings = Settings()