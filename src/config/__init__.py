from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )
    
    # Application
    APP_NAME: str = "Telegram Voice Bot"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Telegram Configuration
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_API_ID: int = 0
    TELEGRAM_API_HASH: str = ""
    TELEGRAM_WEBHOOK_URL: Optional[str] = None
    
    # Google AI Studio Configuration
    GOOGLE_AI_API_KEY: str = ""
    GOOGLE_AI_MODEL: str = "gemini-1.5-flash"
    
    # PayPal Configuration
    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_CLIENT_SECRET: str = ""
    PAYPAL_MODE: str = "sandbox"  # sandbox or live
    PAYPAL_WEBHOOK_ID: str = ""
    
    # Database (optional - for future use)
    DATABASE_URL: Optional[str] = None
    
    # Redis Cache (optional)
    REDIS_URL: Optional[str] = None
    
    @property
    def is_production(self) -> bool:
        return not self.DEBUG


settings = Settings()