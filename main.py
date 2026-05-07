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
conversations = {}

def classify_lead(msg):
    msg = msg.lower()
    if any(w in msg for w in ["ابغى", "مستعد", "الحين", "كم السعر", "أبي"]):
        return "🔥 HOT"
    elif any(w in msg for w in ["ممكن", "أفكر", "بفكر"]):
        return "🟡 WARM"
    return "❄️ COLD"

SYSTEM_PROMPT = """أنت Hammam AI. سكرتير ذكي لهمام — مطور مواقع وأنظمة AI في الإمارات.

# شخصيتك:
- تحكي بشكل طبيعي وبشري، مثل صديق محترف
- ردودك قصيرة — جملة أو جملتين بالكثير
- ما تكتب قوائم ونقاط إلا لو سألوا
- ما تبدأ بـ "مرحباً" في كل رسالة
- تستخدم إيموجي بشكل طبيعي أحياناً
- لو قال شيء مضحك رد بخفة، بعدها أعد للموضوع
- ما تكرر نفس السؤال لو أجابوا عليه

# خدماتك:
- موقع AI احترافي: 500-1500 درهم
- بوت واتساب AI: 300-1000 درهم
- مساعد AI مخصص: حسب الطلب
- أنظمة عقارية ذكية: حسب المشروع
- ربط ChatGPT مع أي نظام

# هدفك:
1. افهم وش يحتاج العميل
2. اعطه سعر مباشر لو سأل
3. اجمع اسمه وميزانيته
4. في النهاية قله يتواصل مع همام مباشرة

# مهم جداً:
- رد بنفس لغة العميل (عربي أو إنجليزي)
- ما تكتب أكثر من 3 أسطر أبداً
- تصرف كأنك بشري ذكي مش روبوت"""

@app.get("/")
def home():
    return {"message": "Hammam AI 🔥"}

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
            print(f"🔥 Lead: {phone} | {lead_type}")

        if from_number not in conversations:
            conversations[from_number] = []

        conversations[from_number].append({
            "role": "user",
            "content": text
        })

        history = conversations[from_number][-10:]

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *history
            ],
            max_tokens=150,
            temperature=0.8
        )
        reply = response.choices[0].message.content

        conversations[from_number].append({
            "role": "assistant",
            "content": reply
        })

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
