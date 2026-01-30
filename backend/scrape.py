#!/usr/bin/env python3
"""
台灣彩券歷史資料爬蟲命令列工具

使用方式:
    python scrape.py                    # 爬取所有彩券最近1個月資料
    python scrape.py --game lotto       # 只爬大樂透
    python scrape.py --game power       # 只爬威力彩
    python scrape.py --months 12        # 爬取12個月歷史資料
    python scrape.py --seed             # 填充測試資料
    python scrape.py --status           # 查看資料庫狀態
"""

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_URL, LOTTERY_URLS
from app.database import Base, LotteryDraw, ScraperLog


async def init_database():
    """Initialize database and return session."""
    engine = create_async_engine(DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, AsyncSessionLocal


async def get_database_status(session: AsyncSession):
    """Get current database statistics."""
    lotto_count = await session.execute(
        select(func.count()).where(LotteryDraw.game_type == "lotto")
    )
    power_count = await session.execute(
        select(func.count()).where(LotteryDraw.game_type == "power")
    )

    lotto_range = await session.execute(
        select(func.min(LotteryDraw.draw_date), func.max(LotteryDraw.draw_date))
        .where(LotteryDraw.game_type == "lotto")
    )
    power_range = await session.execute(
        select(func.min(LotteryDraw.draw_date), func.max(LotteryDraw.draw_date))
        .where(LotteryDraw.game_type == "power")
    )

    lotto_dates = lotto_range.one()
    power_dates = power_range.one()

    print("\n" + "=" * 50)
    print("台灣彩券資料庫狀態")
    print("=" * 50)

    print(f"\n大樂透 (Lotto 649):")
    print(f"  記錄數量: {lotto_count.scalar() or 0}")
    if lotto_dates[0]:
        print(f"  資料範圍: {lotto_dates[0]} ~ {lotto_dates[1]}")
    else:
        print("  資料範圍: (無資料)")

    print(f"\n威力彩 (Super Lotto 638):")
    print(f"  記錄數量: {power_count.scalar() or 0}")
    if power_dates[0]:
        print(f"  資料範圍: {power_dates[0]} ~ {power_dates[1]}")
    else:
        print("  資料範圍: (無資料)")

    # Recent logs
    logs = await session.execute(
        select(ScraperLog).order_by(ScraperLog.run_date.desc()).limit(5)
    )
    logs = logs.scalars().all()

    if logs:
        print("\n最近爬蟲記錄:")
        for log in logs:
            status_icon = "✓" if log.status == "success" else "✗"
            print(f"  {status_icon} {log.run_date} | {log.game_type:6} | +{log.records_added} 筆 | {log.status}")
            if log.error_message:
                print(f"      錯誤: {log.error_message[:50]}...")

    print("\n" + "=" * 50)


async def seed_test_data(session: AsyncSession):
    """Seed database with test data."""
    import random

    print("\n正在填充測試資料...")
    records_added = 0
    current = date.today()

    # Generate Lotto 649 data
    for i in range(100):
        days_back = i * 3 + (i % 2)
        draw_date = date.fromordinal(current.toordinal() - days_back)

        existing = await session.execute(
            select(LotteryDraw).where(
                LotteryDraw.game_type == "lotto",
                LotteryDraw.draw_date == draw_date,
            )
        )
        if existing.scalar_one_or_none():
            continue

        numbers = sorted(random.sample(range(1, 50), 6))
        special = random.randint(1, 49)

        draw = LotteryDraw(
            game_type="lotto",
            draw_date=draw_date,
            numbers=numbers,
            special_number=special,
        )
        session.add(draw)
        records_added += 1

    # Generate Power Lotto data
    for i in range(100):
        days_back = i * 3 + ((i + 1) % 2)
        draw_date = date.fromordinal(current.toordinal() - days_back)

        existing = await session.execute(
            select(LotteryDraw).where(
                LotteryDraw.game_type == "power",
                LotteryDraw.draw_date == draw_date,
            )
        )
        if existing.scalar_one_or_none():
            continue

        numbers = sorted(random.sample(range(1, 39), 6))
        special = random.randint(1, 8)

        draw = LotteryDraw(
            game_type="power",
            draw_date=draw_date,
            numbers=numbers,
            special_number=special,
        )
        session.add(draw)
        records_added += 1

    await session.commit()
    print(f"已填充 {records_added} 筆測試資料")


async def run_scraper(session: AsyncSession, game_type: str, months: int):
    """Run the lottery scraper."""
    from app.routes.scraper import scraper, save_results_to_db

    games = ["lotto", "power"] if game_type == "all" else [game_type]
    total_added = 0

    for game in games:
        game_name = "大樂透" if game == "lotto" else "威力彩"
        print(f"\n正在爬取 {game_name} ({months} 個月歷史資料)...")

        try:
            results = await scraper.scrape_with_history(game, months)
            records_added = await save_results_to_db(results, session)

            # Log success
            log = ScraperLog(
                game_type=game,
                run_date=date.today(),
                records_added=records_added,
                status="success",
            )
            session.add(log)
            await session.commit()

            print(f"  爬取到 {len(results)} 筆資料")
            print(f"  新增 {records_added} 筆記錄到資料庫")
            total_added += records_added

        except Exception as e:
            print(f"  錯誤: {str(e)}")

            # Log failure
            log = ScraperLog(
                game_type=game,
                run_date=date.today(),
                records_added=0,
                status="failed",
                error_message=str(e)[:500],
            )
            session.add(log)
            await session.commit()

    return total_added


async def clear_data(session: AsyncSession, game_type: str):
    """Clear data from database."""
    print(f"\n正在清除 {game_type} 資料...")

    if game_type == "all":
        await session.execute(delete(LotteryDraw))
        await session.execute(delete(ScraperLog))
    else:
        await session.execute(delete(LotteryDraw).where(LotteryDraw.game_type == game_type))
        await session.execute(delete(ScraperLog).where(ScraperLog.game_type == game_type))

    await session.commit()
    print("已清除完成")


async def main():
    parser = argparse.ArgumentParser(
        description="台灣彩券歷史資料爬蟲",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python scrape.py                    爬取所有彩券最近1個月資料
  python scrape.py --game lotto       只爬大樂透
  python scrape.py --game power       只爬威力彩
  python scrape.py --months 12        爬取12個月歷史資料
  python scrape.py --seed             填充測試資料
  python scrape.py --status           查看資料庫狀態
  python scrape.py --clear            清除所有資料
        """
    )

    parser.add_argument(
        "--game", "-g",
        choices=["lotto", "power", "all"],
        default="all",
        help="彩券類型: lotto (大樂透), power (威力彩), all (全部)"
    )
    parser.add_argument(
        "--months", "-m",
        type=int,
        default=1,
        help="爬取幾個月的歷史資料 (預設: 1, 最大: 60)"
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="填充測試資料 (不爬取真實網站)"
    )
    parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="顯示資料庫狀態"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="清除資料庫資料"
    )

    args = parser.parse_args()

    # Validate months
    if args.months < 1 or args.months > 60:
        print("錯誤: --months 必須在 1-60 之間")
        sys.exit(1)

    # Initialize database
    engine, AsyncSessionLocal = await init_database()

    async with AsyncSessionLocal() as session:
        if args.status:
            await get_database_status(session)
        elif args.seed:
            await seed_test_data(session)
            await get_database_status(session)
        elif args.clear:
            await clear_data(session, args.game)
            await get_database_status(session)
        else:
            print("\n" + "=" * 50)
            print("台灣彩券歷史資料爬蟲")
            print("=" * 50)

            total = await run_scraper(session, args.game, args.months)

            print(f"\n總計新增 {total} 筆記錄")
            await get_database_status(session)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
