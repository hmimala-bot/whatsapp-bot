import re
from datetime import datetime
from typing import Optional, Tuple

from database.redis_client import upsert_lead, get_lead
from utils.logger import logger

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Regex patterns
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_PHONE_RE = re.compile(
    r'\b(?:05\d{8}|\+9715\d{8}|009715\d{8}|05\d{1}\s?\d{3}\s?\d{4})\b'
)

_NAME_RE = re.compile(
    r'(?:اسمي|أنا|انا|اسمك|يسموني|يناديني|ناد(?:ني|وني)|call me|my name is|i\'m|i am)\s+([^\s،,\.؟!]{2,20})',
    re.IGNORECASE,
)

_BUDGET_RE = re.compile(
    r'(\d[\d,.]*)\s*(?:درهم|دولار|ريال|AED|USD|SAR|جنيه)',
    re.IGNORECASE,
)

_SERVICE_KEYWORDS = {
    "موقع": "website", "site": "website", "website": "website",
    "بوت واتساب": "whatsapp_bot", "واتساب بوت": "whatsapp_bot",
    "whatsapp bot": "whatsapp_bot", "chatbot": "whatsapp_bot",
    "أتمتة": "automation", "automation": "automation", "n8n": "automation",
    "عقار": "real_estate_system", "real estate": "real_estate_system",
    "مساعد ai": "ai_assistant", "ai assistant": "ai_assistant",
    "ربط": "integration", "integration": "integration", "api": "integration",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Intent signals
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_NEGATIVE = [
    "ما أبي", "مو محتاج", "لا شكراً", "لا شكرا", "مش محتاج",
    "مو الحين", "مب راضي", "مش مهتم", "ما أريد", "مو مهتم",
    "لا يهمني", "ما يهمني", "بعدين ربما", "مو مهتم الحين",
    "not interested", "no thanks", "maybe later", "not now",
    "no need", "i'm good",
]

_HOT = [
    "ابغى الحين", "أبي الحين", "مستعد الحين", "متى تقدر تبدأ",
    "كيف أدفع", "أبي أتعاقد", "أبي أبدأ الحين", "وش الخطوة الجاية",
    "كم التكلفة الكاملة", "متى يخلص", "مستعجل", "urgent",
    "ready to start", "let's go", "how do i pay", "i want to start",
    "when can we begin", "send me the invoice", "ابغى اشتري",
]

_WARM = [
    "ممكن", "أفكر", "بفكر", "شايف", "محتاج وقت", "أدرس الموضوع",
    "ارسل تفاصيل", "وين أشوف أعمالك", "كم يأخذ وقت",
    "عندي مشروع", "أبي أعرف أكثر", "وش الخدمات",
    "considering", "thinking about it", "send me more info",
    "what are your services", "portfolio", "examples",
]

# Priority map for upgrade-only logic
_PRIORITY = {"NOT_INTERESTED": -1, "COLD": 0, "WARM": 1, "HOT": 2}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Classification
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def classify_intent(text: str, history_length: int = 0) -> str:
    """
    Classify lead intent from text + conversation depth.
    Rule: a lead can only be UPGRADED, never downgraded in one call.
    (The upgrade-only enforcement happens in process_message_for_lead.)
    """
    t = text.lower()

    # Negative intent overrides everything
    if any(phrase in t for phrase in _NEGATIVE):
        return "NOT_INTERESTED"

    if any(phrase in t for phrase in _HOT):
        return "HOT"

    if any(phrase in t for phrase in _WARM):
        return "WARM"

    # Deep engagement without explicit signal → WARM
    if history_length >= 8:
        return "WARM"

    return "COLD"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Extraction helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def extract_phone(text: str) -> Optional[str]:
    m = _PHONE_RE.search(text)
    return m.group().replace(" ", "") if m else None


def extract_name(text: str) -> Optional[str]:
    m = _NAME_RE.search(text)
    return m.group(1).strip() if m else None


def extract_budget(text: str) -> Optional[str]:
    m = _BUDGET_RE.search(text)
    if m:
        amount = m.group(1).replace(",", "")
        currency = m.group(0).split(amount)[-1].strip()
        return f"{amount} {currency}"
    return None


def extract_interest(text: str) -> Optional[str]:
    t = text.lower()
    for keyword, service in _SERVICE_KEYWORDS.items():
        if keyword in t:
            return service
    return None


def detect_language(text: str) -> str:
    """Simple heuristic: if more than 30% ASCII → English."""
    ascii_chars = sum(1 for c in text if ord(c) < 128 and c.isalpha())
    return "en" if text and ascii_chars / len(text) > 0.3 else "ar"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main lead processor
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_message_for_lead(
    from_number: str,
    text: str,
    history: list,
    user_profile: dict,
) -> Tuple[dict, bool]:
    """
    Update or create a lead entry.
    Returns (lead_dict, became_hot) — became_hot triggers admin notification.
    """
    now = datetime.now()
    existing = await get_lead(from_number) or {}

    # Intent classification
    new_type = classify_intent(text, len(history))
    old_type = existing.get("type", "COLD")

    # Upgrade-only: never downgrade an existing classification
    if _PRIORITY.get(new_type, 0) < _PRIORITY.get(old_type, 0):
        new_type = old_type

    # Extract signals from this message
    extracted_phone = extract_phone(text)
    extracted_name = extract_name(text)
    extracted_budget = extract_budget(text)
    extracted_interest = extract_interest(text)
    language = detect_language(text)

    lead = {
        "whatsapp": from_number,
        "contact_phone": extracted_phone or existing.get("contact_phone", ""),
        "name": extracted_name or existing.get("name", user_profile.get("name", "")),
        "type": new_type,
        "language": language,
        "first_seen": existing.get("first_seen", now.isoformat()),
        "last_seen": now.isoformat(),
        "updated_ts": now.timestamp(),
        "messages_count": len(history),
        "last_message": text[:150],
        "interest": extracted_interest or existing.get("interest", user_profile.get("interest", "")),
        "budget": extracted_budget or existing.get("budget", user_profile.get("budget", "")),
    }

    await upsert_lead(from_number, lead)

    became_hot = (new_type == "HOT" and old_type != "HOT")
    logger.info(
        f"Lead | {from_number} | {old_type}→{new_type} "
        f"| msgs:{len(history)} | 🔥HOT:{became_hot}"
    )

    return lead, became_hot


async def update_profile_from_lead(
    phone: str,
    text: str,
    current_profile: dict,
) -> dict:
    """
    Extract profile fields from the latest message and merge into profile.
    Returns the updated profile dict (caller must save it).
    """
    profile = dict(current_profile)

    name = extract_name(text)
    if name:
        profile["name"] = name

    budget = extract_budget(text)
    if budget:
        profile["budget"] = budget

    interest = extract_interest(text)
    if interest:
        profile["interest"] = interest

    lang = detect_language(text)
    profile["language"] = lang

    return profile
