import httpx
from config import settings
from utils.logger import logger

# Always use latest stable API version
_API_URL = f"https://graph.facebook.com/v19.0/{settings.PHONE_NUMBER_ID}/messages"


def _headers() -> dict:
    """Return fresh headers (token could change via env reload)."""
    return {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }


async def send_text_message(to: str, text: str, max_retries: int = 3) -> bool:
    """
    Send a WhatsApp text message with automatic retry on timeout.
    Returns True on success, False after all retries exhausted.
    """
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": text, "preview_url": False},
    }

    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                response = await client.post(_API_URL, headers=_headers(), json=payload)
                response.raise_for_status()
                logger.info(f"✅ Message sent → {to} (attempt {attempt})")
                return True

        except httpx.TimeoutException:
            logger.warning(f"⏱ Timeout sending to {to} (attempt {attempt}/{max_retries})")
            if attempt == max_retries:
                logger.error(f"❌ All retries exhausted for {to}")

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            body = e.response.text[:200]
            logger.error(f"❌ HTTP {status} sending to {to}: {body}")
            # 4xx errors are not retryable
            if 400 <= status < 500:
                break

        except Exception as e:
            logger.error(f"❌ Unexpected error sending to {to}: {e}")
            break

    return False


async def send_admin_notification(text: str) -> None:
    """Send an alert message to the admin WhatsApp number."""
    if settings.ADMIN_WHATSAPP:
        await send_text_message(settings.ADMIN_WHATSAPP, f"🔔 Admin:\n{text}")
