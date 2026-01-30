"""Application configuration settings."""
import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_DIR = BASE_DIR / "database"
DATABASE_DIR.mkdir(exist_ok=True)

# Database
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_DIR}/lottery.db"

# Scraper settings
SCRAPER_CONFIG = {
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "request_delay": 2.0,  # seconds between requests
    "timeout": 30.0,
}

# Taiwan Lottery URLs
LOTTERY_URLS = {
    "lotto": "https://www.taiwanlottery.com.tw/Lotto/Lotto649/history.aspx",
    "power": "https://www.taiwanlottery.com.tw/Lotto/SuperLotto638/history.aspx",
    "daily539": "https://www.taiwanlottery.com.tw/Lotto/Daily539/history.aspx",
}

# API Settings
API_PREFIX = "/api"
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8080",
    "http://127.0.0.1:5500",
    "null",  # For local file access
]
