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

REAL_ESTATE_LINK = "https://ajman-ai-closers.lovable.app/ai-chat"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Real Estate State Machine — Logic in Code
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Keywords that trigger real estate flow
REAL_ESTATE_KEYWORDS_AR = [
    "شقة", "شقه", "فيلا", "فيللا", "إيجار", "ايجار", "استئجار",
    "عقار", "غرفة", "غرفه", "سكن", "أرض", "ارض", "محل", "مكتب",
    "تاون هاوس", "استوديو", "دوبلكس", "بنتهاوس", "مشروع سكني",
    "شراء شقة", "بيع شقة", "شقق", "عقارات", "سكنية", "villa",
]
REAL_ESTATE_KEYWORDS_EN = [
    "apartment", "flat", "studio", "villa", "rent", "buy", "property",
    "real estate", "room", "bedroom", "townhouse", "duplex", "penthouse",
    "1bhk", "2bhk", "3bhk", "for rent", "for sale",
]

RENT_SIGNALS_AR = ["إيجار", "ايجار", "استئجار", "للإيجار", "للايجار", "أستأجر", "استاجر"]
RENT_SIGNALS_EN = ["rent", "for rent", "renting", "lease"]
BUY_SIGNALS_AR = ["شراء", "أشتري", "اشتري", "تملك", "شراء", "للبيع", "أبي أشتري"]
BUY_SIGNALS_EN = ["buy", "purchase", "buying", "for sale", "own"]

BUDGET_KEYWORDS = ["ألف", "الف", "k", "درهم", "دولار", "ريال", "AED", "aed", "000"]


def _is_real_estate(text: str) -> bool:
    t = text.lower()
    return (
        any(kw in t for kw in REAL_ESTATE_KEYWORDS_AR) or
        any(kw in t for kw in REAL_ESTATE_KEYWORDS_EN)
    )


def _extract_rent_or_buy(text: str) -> Optional[str]:
    t = text.lower()
    if any(s in t for s in RENT_SIGNALS_AR + RENT_SIGNALS_EN):
        return "rent"
    if any(s in t for s in BUY_SIGNALS_AR + BUY_SIGNALS_EN):
        return "buy"
    return None


def _has_budget(text: str) -> bool:
    return any(kw in text.lower() for kw in BUDGET_KEYWORDS)


def _handle_real_estate_flow(text: str, profile: dict) -> Optional[str]:
    """
    State machine for real estate qualification.
    Returns a fixed reply if we're in the RE flow, or None to fall through to GPT.
    """
    # Check if this message OR history indicates real estate intent
    re_intent = profile.get("re_intent", False) or _is_real_estate(text)

    if not re_intent:
        return None  # Not real estate — let GPT handle it

    # Mark real estate intent in profile
    profile["re_intent"] = True

    # Check what we know so far
    rent_or_buy = profile.get("re_type") or _extract_rent_or_buy(text)
    has_budget = profile.get("re_budget") or _has_budget(text)

    # Update profile with new info
    if rent_or_buy:
        profile["re_type"] = rent_or_buy
    if _has_budget(text):
        profile["re_budget"] = True

    # State machine:
    if not rent_or_buy:
        return "إيجار أو شراء؟ 😊"

    if not has_budget and not profile.get("re_budget"):
        rent_label = "الإيجار" if rent_or_buy == "rent" else "الشراء"
        return f"وكم ميزانيتك التقريبية لـ{rent_label}؟"

    # Both known → send link
    return (
        f"تمام، عندي نظام ذكي يلاقيلك الخيار المناسب بالضبط 👌\n"
        f"تفضل هنا وأكمل معه: {REAL_ESTATE_LINK}"
    )


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

_MAX_HISTORY = 30


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Message type parser
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _parse_message(message: dict) -> tuple:
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

    elif msg_type in ("sticker", "reaction", "location"):
        return None, "skip"

    elif msg_type == "contacts":
        return "[شارك جهة اتصال]", "continue"

    return None, "skip"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Webhook endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/webhook")
async def verify_webhook(request: Request):
    params = dict(request.query_params)
    if params.get("hub.verify_token") == settings.VERIFY_TOKEN:
        logger.info("Webhook verified ✅")
        return PlainTextResponse(content=params.get("hub.challenge", ""))
    return JSONResponse(status_code=403, content={"error": "Invalid verify token"})


@router.post("/webhook")
async def handle_webhook(request: Request):
    body_bytes = await request.body()

    signature = request.headers.get("X-Hub-Signature-256", "")
    await verify_webhook_signature(body_bytes, signature)

    try:
        data = json.loads(body_bytes)
    except json.JSONDecodeError:
        return JSONResponse(content={"status": "ok"})

    try:
        entry = data.get("entry", [{}])[0]
        change = entry.get("changes", [{}])[0]
        value = change.get("value", {})

        if "statuses" in value and "messages" not in value:
            return JSONResponse(content={"status": "ok"})

        messages = value.get("messages", [])
        if not messages:
            return JSONResponse(content={"status": "ok"})

        message = messages[0]
        from_number = message.get("from", "")
        if not from_number:
            return JSONResponse(content={"status": "ok"})

        # Rate limiting
        if await is_rate_limited(from_number):
            await send_text_message(from_number, _RATE_LIMIT_REPLY)
            return JSONResponse(content={"status": "ok"})

        # Parse message type
        text, action = _parse_message(message)

        if action == "skip":
            return JSONResponse(content={"status": "ok"})

        if action == "send_audio_reply":
            await send_text_message(from_number, _AUDIO_REPLY)
            return JSONResponse(content={"status": "ok"})

        if action == "send_image_reply":
            await send_text_message(from_number, _IMAGE_NO_CAPTION_REPLY)
            return JSONResponse(content={"status": "ok"})

        if not text:
            return JSONResponse(content={"status": "ok"})

        # Load context
        history = await get_conversation(from_number)
        user_profile = await get_user_profile(from_number)

        # ━━━ Real Estate State Machine (Code Logic) ━━━
        re_reply = _handle_real_estate_flow(text, user_profile)

        if re_reply:
            reply = re_reply
            logger.info(f"RE flow reply to {from_number}: step handled by code")
        else:
            # Fall through to GPT for non-RE messages
            reply = await get_ai_response(from_number, text, history, user_profile)

        # Update conversation history
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": reply})

        if len(history) > _MAX_HISTORY:
            history = history[-_MAX_HISTORY:]

        await save_conversation(from_number, history)

        # Update user profile
        updated_profile = await update_profile_from_lead(from_number, text, user_profile)
        # Preserve RE state flags
        for key in ("re_intent", "re_type", "re_budget"):
            if key in user_profile:
                updated_profile[key] = user_profile[key]

        if updated_profile != user_profile:
            await save_user_profile(from_number, updated_profile)

        # Process lead classification
        lead, became_hot = await process_message_for_lead(
            from_number, text, history, updated_profile
        )

        # HOT lead: notify admin + push to Sheets
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

        # Send reply
        await send_text_message(from_number, reply)

    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)

    return JSONResponse(content={"status": "ok"})