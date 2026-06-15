from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os

from database import init_db
from scheduler import start_scheduler, stop_scheduler, run_market_state_job
from routers.market   import router as market_router
from routers.trades   import router as trades_router
from routers.spot     import router as spot_router
from routers.journal  import router as journal_router
from routers.plans    import router as plans_router
from routers.stats    import router as stats_router, settings_router
from routers.playbook import router as playbook_router

STATIC_DIR  = os.path.join(os.path.dirname(__file__), "static")
UPLOAD_DIR  = os.environ.get("WBTRADE_UPLOADS", "/home/ubuntu/wbtrade/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

PAGE_MAP = {
    "":          "index.html",
    "journal":   "journal.html",
    "plan":      "plan.html",
    "spot":      "spot.html",
    "stats":     "stats.html",
    "playbook":  "playbook.html",
    "settings":  "settings.html",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="WB Trade", root_path="/trade", lifespan=lifespan)

app.include_router(market_router)
app.include_router(trades_router)
app.include_router(spot_router)
app.include_router(journal_router)
app.include_router(plans_router)
app.include_router(stats_router)
app.include_router(settings_router)
app.include_router(playbook_router)


@app.post("/api/market/refresh")
def manual_refresh():
    from database import SessionLocal, MarketState, Setting
    from market_engine import compute_market_state
    from datetime import datetime
    db = SessionLocal()
    try:
        grok_key = db.get(Setting, "grok_api_key")
        result   = compute_market_state(grok_key=grok_key.value if grok_key else "")
        row = MarketState(
            timestamp=datetime.utcnow(), state=result["state"], score=result["score"],
            ema_score=result["ema_score"], volume_score=result["volume_score"],
            funding_score=result["funding_score"], fng_score=result["fng_score"],
            funding_rate=result["funding_rate"], fng_value=result["fng_value"],
            btc_price=result["btc_price"], reason=result["reason"], risk_note=result["risk_note"],
        )
        db.add(row); db.commit()
        return result
    finally:
        db.close()


app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static",  StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/{page}")
async def serve_page(page: str):
    filename = PAGE_MAP.get(page)
    if filename:
        return FileResponse(os.path.join(STATIC_DIR, filename))
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/")
async def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
