"""FastAPI main application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import API_PREFIX, CORS_ORIGINS
from app.database import init_db
from app.routes import lottery, news, scraper


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await init_db()
    yield


app = FastAPI(
    title="智能彩券選號系統 Pro API",
    description="台灣樂透歷史資料與智能選號後端服務",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(lottery.router, prefix=API_PREFIX, tags=["Lottery"])
app.include_router(news.router, prefix=API_PREFIX, tags=["News"])
app.include_router(scraper.router, prefix=API_PREFIX, tags=["Scraper"])


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "message": "智能彩券選號系統 Pro API",
        "version": "1.0.0",
    }


@app.get("/health")
async def health_check():
    """API health status."""
    return {"status": "healthy"}
