# 🤖 Hammam AI — WhatsApp Business Bot v2

Production-ready WhatsApp AI assistant for freelance services (websites, bots, AI systems).

---

## 📁 Project Structure

```
hammam-ai/
├── main.py                  # FastAPI entry point
├── config.py                # All settings via environment variables
├── requirements.txt
├── Procfile
├── .env.example             # Copy to .env and fill in values
├── routes/
│   ├── webhook.py           # Core message handler
│   ├── leads.py             # REST API for leads (protected)
│   └── dashboard.py        # Web dashboard (protected)
├── services/
│   ├── whatsapp.py          # WhatsApp API — send messages with retry
│   ├── openai_service.py    # GPT responses with context
│   ├── lead_service.py      # Lead classification + profile extraction
│   └── sheets_service.py   # Google Sheets integration (optional)
├── database/
│   └── redis_client.py     # Conversations, profiles, leads in Redis
├── prompts/
│   └── system_prompt.py    # AI personality + instructions
└── utils/
    ├── security.py          # Webhook signature verification + API key auth
    ├── rate_limiter.py      # Per-user rate limiting
    └── logger.py            # Structured logging
```

---

## 🚀 Quick Deployment (Render.com)

### 1. Create Redis Service
- Render Dashboard → New → Redis
- Copy the **Internal Redis URL**

### 2. Deploy Web Service
- New → Web Service → Connect GitHub repo
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`

### 3. Set Environment Variables
Copy from `.env.example` and fill in Render's Environment section.

### 4. Configure Meta Webhook
- Meta Developer Console → WhatsApp → Configuration
- **Webhook URL:** `https://your-app.onrender.com/webhook`
- **Verify Token:** same as `VERIFY_TOKEN` in your env

---

## 🔒 Security

| Feature | Status |
|---|---|
| Webhook signature verification | ✅ X-Hub-Signature-256 |
| API key for /leads | ✅ X-API-Key header |
| Dashboard auth | ✅ ?key= query param |
| Rate limiting | ✅ Per-minute + per-hour per user |
| No hardcoded secrets | ✅ All via env vars |
| CORS restricted | ✅ Meta only |

---

## 📊 Endpoints

| Endpoint | Auth | Description |
|---|---|---|
| `GET /` | None | Health check |
| `GET /webhook` | Meta token | Webhook verification |
| `POST /webhook` | Signature | Incoming messages |
| `GET /leads` | X-API-Key | All leads (JSON) |
| `GET /leads?lead_type=HOT` | X-API-Key | Filter by type |
| `GET /leads/export/csv` | X-API-Key | Download as CSV |
| `GET /dashboard?key=...` | key param | Web dashboard |

---

## 🧠 Lead Classification

| Type | Signals |
|---|---|
| 🔥 HOT | "أبي الحين", "كيف أدفع", "متى تبدأ", "مستعد" |
| 🟡 WARM | "أفكر", "ممكن", "ارسل تفاصيل", deep conversation |
| ❄️ COLD | First contact, no strong signals |
| ✖️ NOT_INTERESTED | "ما أبي", "لا شكراً", "not interested" |

**Key rule:** Leads only upgrade, never downgrade. HOT stays HOT.

---

## 📋 Google Sheets Setup (Optional)

1. Create a Google Cloud project
2. Enable Google Sheets API
3. Create a Service Account → Download JSON key
4. Share your Google Sheet with the service account email
5. Set `GOOGLE_SHEET_ID` and `GOOGLE_CREDENTIALS_JSON` (full JSON as one line)

HOT leads are automatically pushed to Sheets when they're first classified.

---

## 💬 Accessing the Dashboard

```
https://your-app.onrender.com/dashboard?key=YOUR_DASHBOARD_API_KEY
```

Features:
- Real-time lead counts by type
- Filterable table by lead type
- Clickable WhatsApp links
- CSV export button

---

## 🔧 Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set up Redis (Docker)
docker run -d -p 6379:6379 redis:alpine

# Copy and fill environment
cp .env.example .env

# Run
uvicorn main:app --reload --port 8000
```

---

## ⚠️ Important Notes

- **Do not use `--workers` > 1** without switching to a shared Redis pub/sub for rate limiting
- APP_SECRET should always be set in production (META_APP_SECRET from Meta console)
- DASHBOARD_API_KEY should be a long random string (32+ chars)
- Conversation history is stored for 24 hours, profiles for 7 days, leads for 30 days
