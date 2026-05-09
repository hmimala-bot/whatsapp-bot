import json
from typing import Optional, List

import redis.asyncio as aioredis

from config import settings
from utils.logger import logger

# Module-level client — initialised on startup, cleaned up on shutdown
_redis: Optional[aioredis.Redis] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Lifecycle
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def init_redis() -> None:
    global _redis
    try:
        _redis = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        await _redis.ping()
        logger.info("✅ Redis connected")
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e} — running in memory-less mode")
        _redis = None


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
        logger.info("Redis connection closed")


def get_redis_client() -> Optional[aioredis.Redis]:
    return _redis


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Conversations
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def get_conversation(phone: str) -> List[dict]:
    if not _redis:
        return []
    try:
        data = await _redis.get(f"conv:{phone}")
        return json.loads(data) if data else []
    except Exception as e:
        logger.error(f"get_conversation error ({phone}): {e}")
        return []


async def save_conversation(phone: str, messages: List[dict]) -> None:
    if not _redis:
        return
    try:
        await _redis.setex(
            f"conv:{phone}",
            settings.CONVERSATION_TTL,
            json.dumps(messages, ensure_ascii=False),
        )
    except Exception as e:
        logger.error(f"save_conversation error ({phone}): {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# User Profiles
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def get_user_profile(phone: str) -> dict:
    if not _redis:
        return {}
    try:
        data = await _redis.get(f"profile:{phone}")
        return json.loads(data) if data else {}
    except Exception as e:
        logger.error(f"get_user_profile error ({phone}): {e}")
        return {}


async def save_user_profile(phone: str, profile: dict) -> None:
    if not _redis:
        return
    try:
        await _redis.setex(
            f"profile:{phone}",
            settings.PROFILE_TTL,
            json.dumps(profile, ensure_ascii=False),
        )
    except Exception as e:
        logger.error(f"save_user_profile error ({phone}): {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Leads
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def upsert_lead(phone: str, lead_data: dict) -> None:
    if not _redis:
        return
    try:
        await _redis.setex(
            f"lead:{phone}",
            settings.LEAD_TTL,
            json.dumps(lead_data, ensure_ascii=False),
        )
        # Sorted set keeps all lead phones ordered by last activity
        await _redis.zadd("leads:index", {phone: lead_data.get("updated_ts", 0)})
    except Exception as e:
        logger.error(f"upsert_lead error ({phone}): {e}")


async def get_lead(phone: str) -> Optional[dict]:
    if not _redis:
        return None
    try:
        data = await _redis.get(f"lead:{phone}")
        return json.loads(data) if data else None
    except Exception as e:
        logger.error(f"get_lead error ({phone}): {e}")
        return None


async def get_all_leads() -> List[dict]:
    if not _redis:
        return []
    try:
        phones = await _redis.zrevrange("leads:index", 0, 500)
        leads = []
        for phone in phones:
            data = await _redis.get(f"lead:{phone}")
            if data:
                leads.append(json.loads(data))
        return leads
    except Exception as e:
        logger.error(f"get_all_leads error: {e}")
        return []


async def get_lead_stats() -> dict:
    leads = await get_all_leads()
    stats = {"total": len(leads), "HOT": 0, "WARM": 0, "COLD": 0, "NOT_INTERESTED": 0}
    for lead in leads:
        t = lead.get("type", "COLD")
        stats[t] = stats.get(t, 0) + 1
    return stats
