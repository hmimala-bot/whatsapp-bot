from fastapi import APIRouter, Depends, Query
from typing import Optional

from database.redis_client import get_all_leads, get_lead_stats
from utils.security import require_api_key

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("")
async def list_leads(
    lead_type: Optional[str] = Query(None, description="Filter by type: HOT | WARM | COLD | NOT_INTERESTED"),
    _: str = Depends(require_api_key),
):
    """
    Returns all leads ordered by last activity (newest first).
    Protected by X-API-Key header.

    Example:
        GET /leads
        GET /leads?lead_type=HOT
        Headers: X-API-Key: your_key
    """
    leads = await get_all_leads()

    if lead_type:
        leads = [l for l in leads if l.get("type") == lead_type.upper()]

    stats = await get_lead_stats()

    return {
        "stats": stats,
        "count": len(leads),
        "leads": leads,
    }


@router.get("/export/csv")
async def export_csv(_: str = Depends(require_api_key)):
    """Export all leads as CSV — useful for Excel/Sheets import."""
    from fastapi.responses import StreamingResponse
    import csv
    import io

    leads = await get_all_leads()

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "whatsapp", "name", "contact_phone", "type", "language",
            "interest", "budget", "messages_count",
            "first_seen", "last_seen", "last_message",
        ],
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(leads)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )
