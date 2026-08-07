import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware

from database import init_db
from routers.auth_router import router as auth_router
from routers.players_router import router as players_router
from routers.packages_router import router as packages_router
from routers.rate_cards_router import router as rate_cards_router
from routers.sessions_router import router as sessions_router
from routers.payments_router import router as payments_router
from routers.reports_router import router as reports_router

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# Never hardcode a domain here — nginx (or Vercel/Railway if this ever moves
# there) owns the public hostname; the app only knows its own sub-path.
ROOT_PATH = os.environ.get("PADEL_ROOT_PATH", "/padel")
SECRET_KEY = os.environ.get("PADEL_SECRET_KEY", os.urandom(32).hex())


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Padel Court Payment & Wallet Tracker", root_path=ROOT_PATH, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax")

app.include_router(auth_router)
app.include_router(players_router)
app.include_router(packages_router)
app.include_router(rate_cards_router)
app.include_router(sessions_router)
app.include_router(payments_router)
app.include_router(reports_router)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/{full_path:path}")
async def spa(full_path: str):
    """Single-page app: every non-API path serves index.html and the
    client-side router in app.js decides what to render.
    """
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
