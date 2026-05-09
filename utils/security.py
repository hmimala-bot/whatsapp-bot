import hmac
import hashlib
from fastapi import Request, HTTPException, Security
from fastapi.security import APIKeyHeader

from config import settings
from utils.logger import logger

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_webhook_signature(body: bytes, signature_header: str) -> None:
    """
    Verify Meta webhook X-Hub-Signature-256 header.
    Raises HTTP 403 if signature is missing or invalid.
    Skipped entirely when APP_SECRET is not configured (dev mode).
    """
    if not settings.APP_SECRET:
        logger.warning("APP_SECRET not set — skipping signature verification (dev mode)")
        return

    if not signature_header.startswith("sha256="):
        logger.error("Webhook received without signature")
        raise HTTPException(status_code=403, detail="Missing webhook signature")

    expected = hmac.new(
        settings.APP_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature_header[7:], expected):
        logger.error("Webhook signature mismatch — possible spoofed request")
        raise HTTPException(status_code=403, detail="Invalid webhook signature")


def require_api_key(api_key: str = Security(_api_key_header)) -> str:
    """FastAPI dependency — enforces X-API-Key header on protected endpoints."""
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")
    if not hmac.compare_digest(api_key, settings.DASHBOARD_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key
