"""
JobHunter AI — FastAPI backend entry point
Run: uvicorn main:app --reload --port 8000
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from database import create_tables
from routes.jobs import router as jobs_router
from routes.applications import router as apps_router
from routes.profile_routes import router as profile_router
from routes.settings_routes import router as settings_router
from routes.setup import router as setup_router
from routes.stats import router as stats_router
from scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    create_tables()
    logger.info("✅ Database tables ready")
    start_scheduler(asyncio.get_running_loop())
    yield
    # Shutdown
    stop_scheduler()
    logger.info("👋 Scheduler stopped")


app = FastAPI(
    title="JobHunter AI",
    description="Personal job/internship finder and application assistant",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve generated PDFs as static files
app.mount("/files", StaticFiles(directory=str(settings.generated_dir)), name="files")

# Routers — under /api. Without this prefix, e.g. GET /settings/ (the API's
# "list current settings" endpoint) sits at the exact same URL as the frontend's
# /settings page, and since routers are matched before the static mount below,
# the API always won: clicking Settings/Jobs/Applications/Profile showed raw
# JSON instead of the page. /health and /files stay unprefixed (no page shares
# those names).
API_PREFIX = "/api"
app.include_router(jobs_router, prefix=API_PREFIX)
app.include_router(apps_router, prefix=API_PREFIX)
app.include_router(profile_router, prefix=API_PREFIX)
app.include_router(settings_router, prefix=API_PREFIX)
app.include_router(setup_router, prefix=API_PREFIX)
app.include_router(stats_router, prefix=API_PREFIX)


@app.get("/health")
def health():
    return {"status": "ok"}


# Serve the built frontend (frontend/out — `npm run build` with output:'export')
# at "/". Registered LAST: a root mount matches every path, so anything above
# (API routers, /files, /health, FastAPI's own /docs) must win first. In dev
# without a build — or before `npm run build` has run — this just no-ops and
# leaves "/" a 404; use `npm run dev` on :3000 as usual for frontend work.
_static_dir = settings.frontend_dist_dir
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
    logger.info(f"🖥️  Serving frontend from {_static_dir}")
