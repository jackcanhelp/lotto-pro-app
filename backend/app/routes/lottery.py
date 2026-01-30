"""Lottery history API routes."""
from datetime import date
from typing import Optional
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, LotteryDraw
from app.models import (
    LotteryDrawResponse,
    LotteryHistoryResponse,
    StatisticsResponse,
)

router = APIRouter(prefix="/lottery")


@router.get("/history", response_model=LotteryHistoryResponse)
async def get_lottery_history(
    game_type: str = Query(..., description="Game type: 'lotto' or 'power'"),
    limit: int = Query(50, ge=1, le=200, description="Number of records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db),
):
    """Get lottery draw history for a specific game type."""
    if game_type not in ["lotto", "power"]:
        raise HTTPException(status_code=400, detail="Invalid game_type. Use 'lotto' or 'power'")

    # Get total count
    count_query = select(func.count()).where(LotteryDraw.game_type == game_type)
    total_result = await db.execute(count_query)
    total_records = total_result.scalar()

    # Get draws
    query = (
        select(LotteryDraw)
        .where(LotteryDraw.game_type == game_type)
        .order_by(desc(LotteryDraw.draw_date))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    draws = result.scalars().all()

    return LotteryHistoryResponse(
        game_type=game_type,
        total_records=total_records,
        draws=[LotteryDrawResponse.model_validate(d) for d in draws],
    )


@router.get("/history/{draw_id}", response_model=LotteryDrawResponse)
async def get_lottery_draw(
    draw_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific lottery draw by ID."""
    query = select(LotteryDraw).where(LotteryDraw.id == draw_id)
    result = await db.execute(query)
    draw = result.scalar_one_or_none()

    if not draw:
        raise HTTPException(status_code=404, detail="Draw not found")

    return LotteryDrawResponse.model_validate(draw)


@router.get("/latest", response_model=LotteryDrawResponse)
async def get_latest_draw(
    game_type: str = Query(..., description="Game type: 'lotto' or 'power'"),
    db: AsyncSession = Depends(get_db),
):
    """Get the most recent lottery draw."""
    if game_type not in ["lotto", "power"]:
        raise HTTPException(status_code=400, detail="Invalid game_type")

    query = (
        select(LotteryDraw)
        .where(LotteryDraw.game_type == game_type)
        .order_by(desc(LotteryDraw.draw_date))
        .limit(1)
    )
    result = await db.execute(query)
    draw = result.scalar_one_or_none()

    if not draw:
        raise HTTPException(status_code=404, detail="No draws found for this game type")

    return LotteryDrawResponse.model_validate(draw)


@router.get("/statistics", response_model=StatisticsResponse)
async def get_lottery_statistics(
    game_type: str = Query(..., description="Game type: 'lotto' or 'power'"),
    limit: int = Query(100, ge=10, le=500, description="Number of draws to analyze"),
    db: AsyncSession = Depends(get_db),
):
    """Get statistical analysis of lottery numbers."""
    if game_type not in ["lotto", "power"]:
        raise HTTPException(status_code=400, detail="Invalid game_type")

    # Get draws for analysis
    query = (
        select(LotteryDraw)
        .where(LotteryDraw.game_type == game_type)
        .order_by(desc(LotteryDraw.draw_date))
        .limit(limit)
    )
    result = await db.execute(query)
    draws = result.scalars().all()

    if not draws:
        raise HTTPException(status_code=404, detail="No draws found for analysis")

    # Calculate number frequency
    all_numbers = []
    for draw in draws:
        all_numbers.extend(draw.numbers)

    frequency = Counter(all_numbers)

    # Determine max number based on game type
    max_num = 49 if game_type == "lotto" else 38

    # Ensure all numbers have a count (even if 0)
    for i in range(1, max_num + 1):
        if i not in frequency:
            frequency[i] = 0

    # Sort by frequency
    sorted_freq = sorted(frequency.items(), key=lambda x: x[1], reverse=True)

    # Hot numbers (top 10)
    hot_numbers = [
        {"number": num, "count": count, "percentage": round(count / len(draws) * 100, 1)}
        for num, count in sorted_freq[:10]
    ]

    # Cold numbers (bottom 10)
    cold_numbers = [
        {"number": num, "count": count, "percentage": round(count / len(draws) * 100, 1)}
        for num, count in sorted_freq[-10:]
    ]

    return StatisticsResponse(
        game_type=game_type,
        total_draws=len(draws),
        hot_numbers=hot_numbers,
        cold_numbers=cold_numbers,
        number_frequency=dict(frequency),
    )


@router.get("/search")
async def search_draws(
    game_type: str = Query(..., description="Game type: 'lotto' or 'power'"),
    number: Optional[int] = Query(None, description="Search for draws containing this number"),
    start_date: Optional[date] = Query(None, description="Start date for search"),
    end_date: Optional[date] = Query(None, description="End date for search"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Search lottery draws with filters."""
    query = select(LotteryDraw).where(LotteryDraw.game_type == game_type)

    if start_date:
        query = query.where(LotteryDraw.draw_date >= start_date)
    if end_date:
        query = query.where(LotteryDraw.draw_date <= end_date)

    query = query.order_by(desc(LotteryDraw.draw_date)).limit(limit)
    result = await db.execute(query)
    draws = result.scalars().all()

    # Filter by number if specified (done in Python since JSON column)
    if number is not None:
        draws = [d for d in draws if number in d.numbers]

    return {
        "game_type": game_type,
        "filters": {
            "number": number,
            "start_date": start_date,
            "end_date": end_date,
        },
        "count": len(draws),
        "draws": [LotteryDrawResponse.model_validate(d) for d in draws],
    }
