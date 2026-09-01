"""
JobHunter AI — FastAPI backend entry point
Run: uvicorn main:app --reload --port 8000
"""
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
from routes.stats import router as stats_router
from scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    create_tables()
    logger.info("✅ Database tables ready")
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()
    logger.info("👋 Scheduler stopped")


app = FastAPI(
    title="JobHunter AI",
    description="Personal job/internship finder and application assistant for Hedi Bou Maiza",
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

# Routers
app.include_router(jobs_router)
app.include_router(apps_router)
app.include_router(profile_router)
app.include_router(settings_router)
app.include_router(stats_router)


@app.get("/")
def root():
    return {"message": "JobHunter AI API is running 🚀", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}
