from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database.redis_client import init_redis, close_redis
from routes.webhook import router as webhook_router
from routes.leads import router as leads_router
from routes.dashboard import router as dashboard_router
from utils.logger import logger


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Lifespan — startup & shutdown
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Hammam AI v2 starting up...")
    await init_redis()
    logger.info("✅ All services ready")
    yield
    logger.info("👋 Hammam AI shutting down...")
    await close_redis()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# App instance
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

app = FastAPI(
    title="Hammam AI WhatsApp Bot",
    description="Production-grade WhatsApp AI assistant",
    version="2.0.0",
    lifespan=lifespan,
    # Disable public docs in production
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Middleware
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# CORS: Only Meta's servers need to reach the webhook
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://graph.facebook.com"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Hub-Signature-256", "X-API-Key"],
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Routers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

app.include_router(webhook_router)
app.include_router(leads_router)
app.include_router(dashboard_router)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Global exception handler
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.exception_handler(Exception)
async def _global_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Health check
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/", tags=["health"])
def health_check():
    return {"status": "ok", "service": "Hammam AI", "version": "2.0.0"}
