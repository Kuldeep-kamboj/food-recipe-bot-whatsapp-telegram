import os
from dotenv import load_dotenv
from typing import Optional

# Load environment variables
load_dotenv()

class Settings:
    """Application settings configuration"""
    
    # API Keys
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_PHONE_NUMBER: str = os.getenv("TWILIO_PHONE_NUMBER", "")
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "recipes.db")
    
    # Application
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = ENVIRONMENT == "development"
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    
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