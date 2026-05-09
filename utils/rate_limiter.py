from database.redis_client import get_redis_client
from config import settings
from utils.logger import logger


async def is_rate_limited(phone: str) -> bool:
    """
    Returns True if the phone number has exceeded rate limits.
    Uses two sliding windows: per-minute and per-hour.
    Fails open (returns False) if Redis is unavailable.
    """
    r = get_redis_client()
    if r is None:
        return False

    try:
        per_min_key = f"rl:min:{phone}"
        per_hr_key = f"rl:hr:{phone}"

        # Per-minute check
        min_count = await r.incr(per_min_key)
        if min_count == 1:
            await r.expire(per_min_key, 60)

        # Per-hour check
        hr_count = await r.incr(per_hr_key)
        if hr_count == 1:
            await r.expire(per_hr_key, 3600)

        if min_count > settings.RATE_LIMIT_PER_MINUTE:
            logger.warning(f"Rate limit (per-minute) exceeded: {phone} ({min_count} msgs)")
            return True

        if hr_count > settings.RATE_LIMIT_PER_HOUR:
            logger.warning(f"Rate limit (per-hour) exceeded: {phone} ({hr_count} msgs)")
            return True

        return False

    except Exception as e:
        logger.error(f"Rate limiter error for {phone}: {e}")
        return False  # Fail open — don't block legitimate users if Redis hiccups
