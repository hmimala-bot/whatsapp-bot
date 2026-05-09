from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # ━━━ WhatsApp Business API ━━━
    WHATSAPP_TOKEN: str = ""
    PHONE_NUMBER_ID: str = ""
    VERIFY_TOKEN: str = "hammam_secure_verify_2024"
    APP_SECRET: str = ""          # Meta App Secret — for webhook signature verification

    # ━━━ OpenAI ━━━
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    MAX_TOKENS: int = 200
    TEMPERATURE: float = 0.75

    # ━━━ Redis ━━━
    REDIS_URL: str = "redis://localhost:6379"
    CONVERSATION_TTL: int = 86400       # 24 hours
    PROFILE_TTL: int = 604800           # 7 days
    LEAD_TTL: int = 2592000             # 30 days

    # ━━━ Security ━━━
    DASHBOARD_API_KEY: str = "change_this_to_something_strong"

    # ━━━ Contacts ━━━
    HAMMAM_WHATSAPP: str = "971501234567"   # Hammam's real WhatsApp number
    ADMIN_WHATSAPP: Optional[str] = None     # Receives admin notifications

    # ━━━ Google Sheets (optional) ━━━
    GOOGLE_SHEET_ID: Optional[str] = None
    GOOGLE_CREDENTIALS_JSON: Optional[str] = None   # Full JSON of service account

    # ━━━ Rate Limiting ━━━
    RATE_LIMIT_PER_MINUTE: int = 20
    RATE_LIMIT_PER_HOUR: int = 120

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()
