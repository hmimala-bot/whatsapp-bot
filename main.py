from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import httpx
import os
import re
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

VERIFY_TOKEN = "insightdrive123"
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

phone_regex = re.compile(r"\b05\d{8}\b")
leads = []

def classify_lead(msg):
    msg = msg.lower()
    if any(w in msg for w in ["ابغى", "مستعد", "الحين", "كم السعر", "أبي"]):
        return "🔥 HOT"
    elif any(w in msg for w in ["ممكن", "أفكر", "بفكر"]):
        return "🟡 WARM"
    return "❄️ COLD"

SYSTEM_PROMPT = """
أنت Hammam AI، سكرتير شخصي ذكي واحترافي لصالح همام، مطور مواقع وأنظمة AI.

خدماتك:
- تصميم مواقع AI احترافية: من 500 إلى 1500 درهم
- بوت واتساب AI: من 300 إلى 1000 درهم
- مساعد شخصي AI مخصص: حسب المتطلبات
- أنظمة عقارية ذكية وأتمتة: حسب المشروع
- ربط ChatGPT مع واتساب والمواقع والأنظمة

شخصيتك:
- احترافي، ودود، ذكي، مختصر وواضح
- لست روبوت تقليدي، أنت سكرتير رقمي حقيقي
- رد باللغة التي يكتب بها العميل (عربي أو إنجليزي)

تعليماتك:
- اجمع معلومات العميل: الاسم، الخدمة المطلوبة، الميزانية
- إذا سأل عن الأسعار أعطه سعر واضح ومباشر
- حوّل كل محادثة لفرصة عمل
- في نهاية كل محادثة اطلب رقمه أو بياناته للتواصل
- إذا أعطاك رقمه قل له إن همام سيتواصل معه قريباً
"""

@app.get("/")
def home():
    return {"message": "Hammam AI يشتغل 🔥"}

@app.get("/webhook")
async def verify(request: Request):
    params = dict(request.query_params)
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params["hub.challenge"])
    return JSONResponse(status_code=403, content={"error": "Invalid token"})

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    try:
        entry = data["entry"][0]["changes"][0]["value"]
        message = entry["messages"][0]
        from_number = message["from"]
        text = message["text"]["body"]

        # كشف رقم هاتف وحفظه كـ Lead
        match = phone_regex.search(text)
        if match:
            phone = match.group()
            lead_type = classify_lead(text)
            leads.append({
                "phone": phone,
                "whatsapp": from_number,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "note": text,
                "type": lead_type
            })
            print(f"🔥 Lead جديد: {phone} | {lead_type}")

        # رد GPT
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ]
        )
        reply = response.choices[0].message.content

        # إرسال الرد على واتساب
        async with httpx.AsyncClient() as c:
            await c.post(
                f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages",
                headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": from_number,
                    "text": {"body": reply}
                }
            )
    except Exception as e:
        print(f"Error: {e}")
    return JSONResponse(content={"status": "ok"})

@app.get("/leads")
def get_leads():
    return {"leads": leads, "total": len(leads)}
