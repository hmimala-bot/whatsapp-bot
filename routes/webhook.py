import json
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from config import settings
from utils.logger import logger
from utils.security import verify_webhook_signature
from utils.rate_limiter import is_rate_limited
from database.redis_client import (
    get_conversation, save_conversation,
    get_user_profile, save_user_profile,
)
from services.whatsapp import send_text_message, send_admin_notification
from services.openai_service import get_ai_response
from services.lead_service import (
    process_message_for_lead,
    update_profile_from_lead,
)
from services.sheets_service import append_to_sheets

router = APIRouter(tags=["webhook"])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Static responses for non-text messages
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_AUDIO_REPLY = (
    "للأسف ما أقدر أسمع الرسائل الصوتية 😅 "
    "تقدر تكتب لي وش تبي وأساعدك؟"
)
_IMAGE_NO_CAPTION_REPLY = (
    "شايف إنك أرسلت صورة 😊 "
    "تقدر توضح لي وش تبي بالضبط؟"
)
_RATE_LIMIT_REPLY = (
    "أرسلت رسائل كثيرة في وقت قصير 😅 "
    "انتظر لحظة وحاول مرة ثانية."
)

# Max messages to keep in Redis per user
_MAX_HISTORY = 30


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Message type parser
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _parse_message(message: dict) -> tuple[Optional[str], str]:
    """
    Returns (text_for_gpt, special_action).
    special_action: 'skip' | 'send_audio_reply' | 'send_image_reply' | 'continue'
    """
    msg_type = message.get("type", "")

    if msg_type == "text":
        body = message.get("text", {}).get("body", "").strip()
        if not body:
            return None, "skip"
        return body, "continue"

    elif msg_type == "audio":
        return None, "send_audio_reply"

    elif msg_type == "image":
        caption = message.get("image", {}).get("caption", "").strip()
        if caption:
            return f"[صورة مع تعليق: {caption}]", "continue"
        return None, "send_image_reply"

    elif msg_type == "video":
        caption = message.get("video", {}).get("caption", "").strip()
        if caption:
            return f"[فيديو مع تعليق: {caption}]", "continue"
        return None, "skip"

    elif msg_type == "document":
        name = message.get("document", {}).get("filename", "ملف")
        return f"[ملف: {name}]", "continue"

    elif msg_type == "sticker":
        # Stickers: acknowledge briefly then ignore (don't consume GPT tokens)
        return None, "skip"

    elif msg_type == "reaction":
        # Reactions to bot messages — no response needed
        return None, "skip"

    elif msg_type == "location":
        return None, "skip"

    elif msg_type == "contacts":
        return "[شارك جهة اتصال]", "continue"

    else:
        return None, "skip"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Webhook endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/webhook")
async def verify_webhook(request: Request):
    """Meta webhook verification challenge."""
    params = dict(request.query_params)
    if params.get("hub.verify_token") == settings.VERIFY_TOKEN:
        logger.info("Webhook verified ✅")
        return PlainTextResponse(content=params.get("hub.challenge", ""))
    logger.warning("Webhook verification failed — wrong token")
    return JSONResponse(status_code=403, content={"error": "Invalid verify token"})


@router.post("/webhook")
async def handle_webhook(request: Request):
    """Main webhook handler — processes all incoming WhatsApp events."""

    # ── 1. Read body once (FastAPI caches it) ──────────────────────────────
    body_bytes = await request.body()

    # ── 2. Verify Meta signature ────────────────────────────────────────────
    signature = request.headers.get("X-Hub-Signature-256", "")
    await verify_webhook_signature(body_bytes, signature)

    # ── 3. Parse payload ────────────────────────────────────────────────────
    try:
        data = json.loads(body_bytes)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook payload")
        return JSONResponse(content={"status": "ok"})

    try:
        entry = data.get("entry", [{}])[0]
        change = entry.get("changes", [{}])[0]
        value = change.get("value", {})

        # Ignore status updates (read receipts, delivery reports)
        if "statuses" in value and "messages" not in value:
            return JSONResponse(content={"status": "ok"})

        messages = value.get("messages", [])
        if not messages:
            return JSONResponse(content={"status": "ok"})

        message = messages[0]
        from_number = message.get("from", "")
        if not from_number:
            return JSONResponse(content={"status": "ok"})

        # ── 4. Rate limiting ─────────────────────────────────────────────────
        if await is_rate_limited(from_number):
            await send_text_message(from_number, _RATE_LIMIT_REPLY)
            return JSONResponse(content={"status": "ok"})

        # ── 5. Parse message type ────────────────────────────────────────────
        text, action = _parse_message(message)

        if action == "skip":
            return JSONResponse(content={"status": "ok"})

        if action == "send_audio_reply":
            await send_text_message(from_number, _AUDIO_REPLY)
            return JSONResponse(content={"status": "ok"})

        if action == "send_image_reply":
            await send_text_message(from_number, _IMAGE_NO_CAPTION_REPLY)
            return JSONResponse(content={"status": "ok"})

        # action == "continue" — process with GPT
        if not text:
            return JSONResponse(content={"status": "ok"})

        # ── 6. Load user context ─────────────────────────────────────────────
        history = await get_conversation(from_number)
        user_profile = await get_user_profile(from_number)

        # ── 7. Generate AI response ──────────────────────────────────────────
        reply = await get_ai_response(from_number, text, history, user_profile)

        # ── 8. Update conversation history ───────────────────────────────────
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": reply})

        # Keep only the most recent N messages (rolling window)
        if len(history) > _MAX_HISTORY:
            history = history[-_MAX_HISTORY:]

        await save_conversation(from_number, history)

        # ── 9. Update user profile from this message ─────────────────────────
        updated_profile = await update_profile_from_lead(from_number, text, user_profile)
        if updated_profile != user_profile:
            await save_user_profile(from_number, updated_profile)

        # ── 10. Process lead classification ──────────────────────────────────
        lead, became_hot = await process_message_for_lead(
            from_number, text, history, updated_profile
        )

        # ── 11. HOT lead: push to Sheets + notify admin ──────────────────────
        if became_hot:
            logger.info(f"🔥 NEW HOT LEAD: {from_number}")
            await append_to_sheets(lead)
            notification = (
                f"🔥 New HOT Lead!\n"
                f"WA: {from_number}\n"
                f"Name: {lead.get('name', '—')}\n"
                f"Interest: {lead.get('interest', '—')}\n"
                f"Budget: {lead.get('budget', '—')}\n"
                f"Last msg: {lead.get('last_message', '')[:80]}"
            )
            await send_admin_notification(notification)

        # ── 12. Send reply ───────────────────────────────────────────────────
        await send_text_message(from_number, reply)

    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)

    # Always return 200 — Meta retries on non-200
    return JSONResponse(content={"status": "ok"})
