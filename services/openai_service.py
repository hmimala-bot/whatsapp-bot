from openai import AsyncOpenAI
from typing import List

from config import settings
from prompts.system_prompt import get_system_prompt
from utils.logger import logger

_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

# Phrases that should immediately trigger human handoff
_HANDOFF_TRIGGERS = [
    "أبي شخص حقيقي", "أبي أكلم إنسان", "أكلم واحد حقيقي",
    "أبي أكلم همام", "كلم همام", "تكلم همام", "وين همام",
    "مو بوت", "مو روبوت", "مش بوت", "أبي المدير", "صاحب الشركة",
    "human", "real person", "talk to someone", "speak to agent",
    "agent please", "not a bot",
]

_FALLBACK_REPLY = (
    f"عذراً، في مشكلة تقنية بسيطة 😅 "
    f"حاول مرة ثانية أو راسل همام مباشرة: wa.me/{settings.HAMMAM_WHATSAPP}"
)


def _detect_handoff(text: str) -> bool:
    t = text.lower()
    return any(phrase in t for phrase in _HANDOFF_TRIGGERS)


def _build_system(user_profile: dict) -> str:
    """Inject remembered profile info into the system prompt."""
    base = get_system_prompt()
    extras = []

    if user_profile.get("name"):
        extras.append(f"اسم العميل: {user_profile['name']}")
    if user_profile.get("interest"):
        extras.append(f"اهتمام العميل: {user_profile['interest']}")
    if user_profile.get("budget"):
        extras.append(f"الميزانية التقريبية: {user_profile['budget']}")
    if user_profile.get("language") == "en":
        extras.append("العميل يتكلم الإنجليزي — رد بالإنجليزي")

    if extras:
        base += "\n\n## 📋 معلومات محفوظة عن هذا العميل:\n" + "\n".join(f"• {e}" for e in extras)

    return base


async def get_ai_response(
    phone: str,
    user_message: str,
    conversation_history: List[dict],
    user_profile: dict,
) -> str:
    """
    Generate an AI response.
    - Detects human handoff requests before calling GPT (saves tokens).
    - Injects user profile into system prompt.
    - Keeps last 14 messages (7 exchanges) for context window.
    """
    # Fast-path: human handoff — no GPT call needed
    if _detect_handoff(user_message):
        logger.info(f"Human handoff triggered by {phone}")
        return f"أكيد! همام مباشرة: wa.me/{settings.HAMMAM_WHATSAPP} 📱"

    system = _build_system(user_profile)
    history_slice = conversation_history[-14:] if len(conversation_history) > 14 else conversation_history

    try:
        response = await _client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                *history_slice,
            ],
            max_tokens=settings.MAX_TOKENS,
            temperature=settings.TEMPERATURE,
        )
        reply = response.choices[0].message.content.strip()
        logger.info(f"AI replied to {phone} ({len(reply)} chars)")
        return reply

    except Exception as e:
        logger.error(f"OpenAI error for {phone}: {e}")
        return _FALLBACK_REPLY
