"""Database configuration and models."""
from datetime import date
from typing import Optional

from sqlalchemy import Column, Integer, String, Date, JSON, create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import DATABASE_URL

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


class LotteryDraw(Base):
    """Lottery draw result model."""
    __tablename__ = "lottery_draws"

    id = Column(Integer, primary_key=True, index=True)
    game_type = Column(String(20), nullable=False, index=True)  # 'lotto' or 'power'
    draw_date = Column(Date, nullable=False, index=True)
    draw_number = Column(String(20))  # Draw period number
    numbers = Column(JSON, nullable=False)  # List of main numbers
    special_number = Column(Integer)  # Special/power number
    second_special = Column(Integer, nullable=True)  # For power lottery second special


class ScraperLog(Base):
    """Log for scraper runs."""
    __tablename__ = "scraper_logs"

    id = Column(Integer, primary_key=True, index=True)
    game_type = Column(String(20), nullable=False)
    run_date = Column(Date, nullable=False)
    records_added = Column(Integer, default=0)
    status = Column(String(20))  # 'success', 'failed', 'partial'
    error_message = Column(String(500), nullable=True)


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """Dependency for getting database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
