import json
import time
from typing import Optional

import httpx

from config import settings
from utils.logger import logger

_SHEET_RANGE = "Sheet1"
_HEADERS = [
    "WhatsApp", "Name", "Contact Phone", "Type", "Language",
    "Interest", "Budget", "Messages", "First Seen", "Last Seen", "Last Message",
]

# Cache the access token to avoid re-fetching on every lead
_token_cache: dict = {"token": None, "expires_at": 0}


async def _get_access_token(creds: dict) -> Optional[str]:
    """Mint a Google OAuth2 access token from service account credentials."""
    global _token_cache

    now = int(time.time())
    if _token_cache["token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    try:
        import jwt  # PyJWT

        payload = {
            "iss": creds["client_email"],
            "scope": "https://www.googleapis.com/auth/spreadsheets",
            "aud": "https://oauth2.googleapis.com/token",
            "iat": now,
            "exp": now + 3600,
        }
        signed_jwt = jwt.encode(payload, creds["private_key"], algorithm="RS256")

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": signed_jwt,
                },
            )
            r.raise_for_status()
            data = r.json()
            _token_cache["token"] = data["access_token"]
            _token_cache["expires_at"] = now + data.get("expires_in", 3600)
            return _token_cache["token"]

    except Exception as e:
        logger.error(f"Google Sheets token error: {e}")
        return None


async def _ensure_header_row(token: str) -> None:
    """Write header row if sheet is empty."""
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/"
        f"{settings.GOOGLE_SHEET_ID}/values/{_SHEET_RANGE}!A1?majorDimension=ROWS"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        data = r.json()
        if not data.get("values"):
            await _append_row(token, _HEADERS)


async def _append_row(token: str, row: list) -> None:
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/"
        f"{settings.GOOGLE_SHEET_ID}/values/{_SHEET_RANGE}:append"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
            json={"values": [row]},
        )
        r.raise_for_status()


async def append_to_sheets(lead: dict) -> bool:
    """
    Append a lead row to the configured Google Sheet.
    Silently skips if Sheets is not configured.
    Returns True on success.
    """
    if not settings.GOOGLE_SHEET_ID or not settings.GOOGLE_CREDENTIALS_JSON:
        return False

    try:
        creds = json.loads(settings.GOOGLE_CREDENTIALS_JSON)
        token = await _get_access_token(creds)
        if not token:
            return False

        await _ensure_header_row(token)

        row = [
            lead.get("whatsapp", ""),
            lead.get("name", ""),
            lead.get("contact_phone", ""),
            lead.get("type", ""),
            lead.get("language", ""),
            lead.get("interest", ""),
            lead.get("budget", ""),
            str(lead.get("messages_count", 0)),
            lead.get("first_seen", "")[:16],
            lead.get("last_seen", "")[:16],
            lead.get("last_message", ""),
        ]

        await _append_row(token, row)
        logger.info(f"✅ Lead appended to Sheets: {lead.get('whatsapp')}")
        return True

    except Exception as e:
        logger.error(f"Sheets append error: {e}")
        return False
