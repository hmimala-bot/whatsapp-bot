from datetime import datetime

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import HTMLResponse

from config import settings
from database.redis_client import get_all_leads, get_lead_stats

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_TYPE_COLORS = {
    "HOT": ("#ff4757", "🔥"),
    "WARM": ("#ffa502", "🟡"),
    "COLD": ("#1e90ff", "❄️"),
    "NOT_INTERESTED": ("#747d8c", "✖️"),
}

_INTEREST_LABELS = {
    "website": "موقع",
    "whatsapp_bot": "بوت واتساب",
    "automation": "أتمتة",
    "real_estate_system": "نظام عقاري",
    "ai_assistant": "مساعد AI",
    "integration": "ربط أنظمة",
}


def _badge(lead_type: str) -> str:
    color, icon = _TYPE_COLORS.get(lead_type, ("#747d8c", "?"))
    return (
        f'<span style="background:{color};color:#fff;padding:3px 10px;'
        f'border-radius:20px;font-size:11px;font-weight:600;">'
        f'{icon} {lead_type}</span>'
    )


def _build_rows(leads: list) -> str:
    if not leads:
        return (
            '<tr><td colspan="9" style="text-align:center;color:#666;'
            'padding:48px;font-size:14px;">لا يوجد عملاء بعد 👀</td></tr>'
        )

    rows = []
    for lead in leads:
        interest_raw = lead.get("interest", "")
        interest_label = _INTEREST_LABELS.get(interest_raw, interest_raw or "—")
        wa = lead.get("whatsapp", "")
        wa_link = f'<a href="https://wa.me/{wa}" target="_blank" style="color:#25d366">{wa}</a>' if wa else "—"

        rows.append(
            f"""<tr>
            <td>{lead.get("name") or "—"}</td>
            <td>{wa_link}</td>
            <td>{lead.get("contact_phone") or "—"}</td>
            <td>{_badge(lead.get("type", "COLD"))}</td>
            <td>{interest_label}</td>
            <td>{lead.get("budget") or "—"}</td>
            <td style="text-align:center">{lead.get("messages_count", 0)}</td>
            <td>{(lead.get("last_seen") or "")[:16]}</td>
            <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;
                       white-space:nowrap;color:#aaa"
                title="{lead.get('last_message', '').replace('"', '')}"
            >{lead.get("last_message") or "—"}</td>
            </tr>"""
        )
    return "\n".join(rows)


@router.get("", response_class=HTMLResponse)
async def dashboard(request: Request, key: str = Query("")):
    """
    Dark web dashboard for viewing and filtering leads.
    Access: GET /dashboard?key=YOUR_DASHBOARD_API_KEY
    """
    import hmac
    if not key or not hmac.compare_digest(key, settings.DASHBOARD_API_KEY):
        raise HTTPException(status_code=401, detail="Unauthorized — add ?key=YOUR_KEY to the URL")

    leads = await get_all_leads()
    stats = await get_lead_stats()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows_html = _build_rows(leads)

    html = f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hammam AI — Dashboard</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', Tahoma, sans-serif; background: #0d0d1a; color: #e0e0e0; min-height: 100vh; }}

    /* Header */
    .header {{
      background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
      padding: 20px 32px;
      border-bottom: 1px solid #2a2a40;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
    }}
    .header-left h1 {{ font-size: 20px; font-weight: 700; color: #fff; }}
    .header-left p {{ font-size: 12px; color: #666; margin-top: 4px; }}
    .header-right {{ display: flex; gap: 8px; }}
    .btn {{
      background: #2563eb; color: #fff; border: none;
      padding: 8px 16px; border-radius: 8px; cursor: pointer;
      font-size: 13px; text-decoration: none; display: inline-block;
    }}
    .btn:hover {{ background: #1d4ed8; }}
    .btn-outline {{
      background: transparent; color: #aaa; border: 1px solid #333;
    }}
    .btn-outline:hover {{ border-color: #555; color: #fff; }}

    /* Stats */
    .stats {{ display: flex; gap: 16px; padding: 24px 32px; flex-wrap: wrap; }}
    .stat {{
      background: #1a1a2e; border: 1px solid #2a2a40;
      border-radius: 12px; padding: 18px 24px; min-width: 130px;
      transition: border-color 0.2s;
    }}
    .stat:hover {{ border-color: #3a3a5c; }}
    .stat .val {{ font-size: 28px; font-weight: 700; }}
    .stat .lbl {{ font-size: 12px; color: #666; margin-top: 4px; }}
    .stat.hot {{ border-color: #ff4757; }}
    .stat.hot .val {{ color: #ff4757; }}
    .stat.warm {{ border-color: #ffa502; }}
    .stat.warm .val {{ color: #ffa502; }}
    .stat.cold {{ border-color: #1e90ff; }}
    .stat.cold .val {{ color: #1e90ff; }}

    /* Filters */
    .filters {{ padding: 0 32px 16px; display: flex; gap: 8px; flex-wrap: wrap; }}
    .filter-btn {{
      background: #1a1a2e; border: 1px solid #2a2a40; color: #aaa;
      padding: 6px 14px; border-radius: 20px; cursor: pointer;
      font-size: 12px; transition: all 0.2s;
    }}
    .filter-btn:hover, .filter-btn.active {{ background: #2563eb; border-color: #2563eb; color: #fff; }}

    /* Table */
    .table-wrap {{ padding: 0 32px 40px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; background: #1a1a2e; border-radius: 12px; overflow: hidden; min-width: 800px; }}
    th {{
      background: #16213e; padding: 12px 14px; text-align: right;
      font-size: 12px; color: #666; font-weight: 600;
      border-bottom: 1px solid #2a2a40; white-space: nowrap;
    }}
    td {{ padding: 12px 14px; border-top: 1px solid #1e1e30; font-size: 13px; vertical-align: middle; }}
    tr:hover td {{ background: #1e1e2e; }}

    /* Responsive */
    @media (max-width: 600px) {{
      .header, .stats, .filters, .table-wrap {{ padding-left: 16px; padding-right: 16px; }}
      .stat {{ min-width: 100px; }}
    }}
  </style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <h1>🤖 Hammam AI — لوحة العملاء</h1>
    <p>آخر تحديث: {now_str}</p>
  </div>
  <div class="header-right">
    <a class="btn btn-outline" href="javascript:location.reload()">🔄 تحديث</a>
    <a class="btn" href="/leads/export/csv?key={key}" download>⬇️ تصدير CSV</a>
  </div>
</div>

<div class="stats">
  <div class="stat">
    <div class="val">{stats.get("total", 0)}</div>
    <div class="lbl">إجمالي العملاء</div>
  </div>
  <div class="stat hot">
    <div class="val">{stats.get("HOT", 0)}</div>
    <div class="lbl">🔥 HOT</div>
  </div>
  <div class="stat warm">
    <div class="val">{stats.get("WARM", 0)}</div>
    <div class="lbl">🟡 WARM</div>
  </div>
  <div class="stat cold">
    <div class="val">{stats.get("COLD", 0)}</div>
    <div class="lbl">❄️ COLD</div>
  </div>
  <div class="stat">
    <div class="val" style="color:#747d8c">{stats.get("NOT_INTERESTED", 0)}</div>
    <div class="lbl">✖️ غير مهتم</div>
  </div>
</div>

<div class="filters">
  <span class="filter-btn active" onclick="filterTable('ALL', this)">الكل</span>
  <span class="filter-btn" onclick="filterTable('HOT', this)">🔥 HOT</span>
  <span class="filter-btn" onclick="filterTable('WARM', this)">🟡 WARM</span>
  <span class="filter-btn" onclick="filterTable('COLD', this)">❄️ COLD</span>
  <span class="filter-btn" onclick="filterTable('NOT_INTERESTED', this)">✖️ غير مهتم</span>
</div>

<div class="table-wrap">
  <table id="leadsTable">
    <thead>
      <tr>
        <th>الاسم</th>
        <th>واتساب</th>
        <th>رقم التواصل</th>
        <th>التصنيف</th>
        <th>الاهتمام</th>
        <th>الميزانية</th>
        <th>رسائل</th>
        <th>آخر ظهور</th>
        <th>آخر رسالة</th>
      </tr>
    </thead>
    <tbody id="tableBody">
      {rows_html}
    </tbody>
  </table>
</div>

<script>
  function filterTable(type, btn) {{
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    const rows = document.querySelectorAll('#tableBody tr');
    rows.forEach(row => {{
      if (type === 'ALL') {{
        row.style.display = '';
      }} else {{
        const badge = row.querySelector('span');
        if (badge && badge.textContent.includes(type)) {{
          row.style.display = '';
        }} else {{
          row.style.display = 'none';
        }}
      }}
    }});
  }}
</script>

</body>
</html>"""

    return HTMLResponse(content=html)
