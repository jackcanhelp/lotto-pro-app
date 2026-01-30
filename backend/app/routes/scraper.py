"""Taiwan Lottery scraper API routes - Enhanced version with history support."""
import asyncio
import re
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import LOTTERY_URLS, SCRAPER_CONFIG
from app.database import get_db, LotteryDraw, ScraperLog
from app.models import ScraperRunRequest, ScraperRunResponse

router = APIRouter(prefix="/scraper")

# Base URL for Taiwan Lottery
BASE_URL = "https://www.taiwanlottery.com.tw"


class LotteryScraper:
    """Enhanced lottery scraper with session management and history support."""

    def __init__(self):
        self.headers = {
            "User-Agent": SCRAPER_CONFIG["user_agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        self.timeout = httpx.Timeout(SCRAPER_CONFIG["timeout"])

    async def fetch_page(self, url: str, params: Optional[dict] = None,
                         form_data: Optional[dict] = None) -> str:
        """Fetch a page with proper headers and error handling."""
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            if form_data:
                response = await client.post(url, headers=self.headers, data=form_data)
            else:
                response = await client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.text

    def extract_asp_form_data(self, html: str) -> Dict[str, str]:
        """Extract ASP.NET form hidden fields (ViewState, EventValidation, etc.)."""
        soup = BeautifulSoup(html, "lxml")
        form_data = {}

        hidden_fields = [
            "__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION",
            "__EVENTTARGET", "__EVENTARGUMENT"
        ]

        for field in hidden_fields:
            element = soup.find("input", {"name": field})
            if element:
                form_data[field] = element.get("value", "")

        return form_data

    def parse_taiwan_date(self, date_str: str) -> Optional[date]:
        """Parse Taiwan ROC date format (民國年/月/日) to Western date."""
        # Handle formats like: 113/12/27, 113年12月27日
        patterns = [
            r'(\d{2,3})[/\-年](\d{1,2})[/\-月](\d{1,2})',
            r'(\d{2,3})\.(\d{1,2})\.(\d{1,2})',
        ]

        for pattern in patterns:
            match = re.search(pattern, date_str)
            if match:
                try:
                    tw_year = int(match.group(1))
                    month = int(match.group(2))
                    day = int(match.group(3))

                    # Convert Taiwan year to Western year
                    western_year = tw_year + 1911
                    return date(western_year, month, day)
                except (ValueError, IndexError):
                    continue
        return None

    def parse_draw_number(self, text: str) -> Optional[str]:
        """Extract draw number from text."""
        # Match patterns like: 第113000101期, 113000101
        patterns = [
            r'第?(\d{9,12})期?',
            r'期號[：:\s]*(\d+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    def parse_lotto_649(self, html: str) -> List[dict]:
        """Parse 大樂透 (Lotto 649) results from HTML."""
        soup = BeautifulSoup(html, "lxml")
        results = []

        # Try multiple table class patterns
        table = soup.find("table", class_="table_gre")
        if not table:
            table = soup.find("table", {"class": re.compile(r"table.*")})
        if not table:
            # Try finding by structure
            tables = soup.find_all("table")
            for t in tables:
                if t.find("span", class_=re.compile(r"ball")):
                    table = t
                    break

        if not table:
            return results

        rows = table.find_all("tr")

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            try:
                # Extract date and draw number from first cell
                first_cell_text = cells[0].get_text(strip=True)
                draw_date = self.parse_taiwan_date(first_cell_text)
                if not draw_date:
                    continue

                draw_number = self.parse_draw_number(first_cell_text)

                # Extract main numbers - look for ball spans
                numbers = []

                # Method 1: Look for ball_tx class spans
                number_spans = row.find_all("span", class_=re.compile(r"ball_tx|ball_blue|球"))
                if number_spans:
                    for span in number_spans[:6]:
                        num_text = span.get_text(strip=True)
                        if num_text.isdigit():
                            numbers.append(int(num_text))

                # Method 2: Look in specific cells if spans not found
                if len(numbers) < 6 and len(cells) > 1:
                    numbers_cell = cells[1]
                    # Try to find all number elements
                    for span in numbers_cell.find_all(["span", "div", "b"]):
                        text = span.get_text(strip=True)
                        if text.isdigit() and 1 <= int(text) <= 49:
                            numbers.append(int(text))
                        if len(numbers) >= 6:
                            break

                # Extract special number
                special_number = None
                special_span = row.find("span", class_=re.compile(r"ball_red|red|特別"))
                if special_span:
                    special_text = special_span.get_text(strip=True)
                    if special_text.isdigit():
                        special_number = int(special_text)

                # Alternative: Look in the third cell for special number
                if special_number is None and len(cells) > 2:
                    special_cell = cells[2]
                    special_elem = special_cell.find(["span", "b", "div"])
                    if special_elem:
                        text = special_elem.get_text(strip=True)
                        if text.isdigit() and 1 <= int(text) <= 49:
                            special_number = int(text)

                if len(numbers) >= 6:
                    results.append({
                        "game_type": "lotto",
                        "draw_date": draw_date,
                        "draw_number": draw_number,
                        "numbers": sorted(numbers[:6]),
                        "special_number": special_number,
                    })

            except (ValueError, AttributeError, IndexError) as e:
                continue

        return results

    def parse_super_lotto(self, html: str) -> List[dict]:
        """Parse 威力彩 (Super Lotto 638) results from HTML."""
        soup = BeautifulSoup(html, "lxml")
        results = []

        table = soup.find("table", class_="table_gre")
        if not table:
            table = soup.find("table", {"class": re.compile(r"table.*")})
        if not table:
            tables = soup.find_all("table")
            for t in tables:
                if t.find("span", class_=re.compile(r"ball")):
                    table = t
                    break

        if not table:
            return results

        rows = table.find_all("tr")

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            try:
                first_cell_text = cells[0].get_text(strip=True)
                draw_date = self.parse_taiwan_date(first_cell_text)
                if not draw_date:
                    continue

                draw_number = self.parse_draw_number(first_cell_text)

                # Extract first zone numbers (1-38)
                numbers = []
                number_spans = row.find_all("span", class_=re.compile(r"ball_tx|ball_blue|球"))
                if number_spans:
                    for span in number_spans[:6]:
                        num_text = span.get_text(strip=True)
                        if num_text.isdigit():
                            numbers.append(int(num_text))

                if len(numbers) < 6 and len(cells) > 1:
                    numbers_cell = cells[1]
                    for span in numbers_cell.find_all(["span", "div", "b"]):
                        text = span.get_text(strip=True)
                        if text.isdigit() and 1 <= int(text) <= 38:
                            numbers.append(int(text))
                        if len(numbers) >= 6:
                            break

                # Extract second zone power number (1-8)
                power_number = None
                power_span = row.find("span", class_=re.compile(r"ball_red|red|power"))
                if power_span:
                    power_text = power_span.get_text(strip=True)
                    if power_text.isdigit() and 1 <= int(power_text) <= 8:
                        power_number = int(power_text)

                if power_number is None and len(cells) > 2:
                    power_cell = cells[2]
                    power_elem = power_cell.find(["span", "b", "div"])
                    if power_elem:
                        text = power_elem.get_text(strip=True)
                        if text.isdigit() and 1 <= int(text) <= 8:
                            power_number = int(text)

                if len(numbers) >= 6:
                    results.append({
                        "game_type": "power",
                        "draw_date": draw_date,
                        "draw_number": draw_number,
                        "numbers": sorted(numbers[:6]),
                        "special_number": power_number,
                    })

            except (ValueError, AttributeError, IndexError):
                continue

        return results

    async def get_available_periods(self, game_type: str, html: str) -> List[Dict[str, Any]]:
        """Extract available year/month periods from dropdown selectors."""
        soup = BeautifulSoup(html, "lxml")
        periods = []

        # Look for year dropdown
        year_select = soup.find("select", {"id": re.compile(r"year|Year")})
        month_select = soup.find("select", {"id": re.compile(r"month|Month")})

        if year_select:
            for option in year_select.find_all("option"):
                year = option.get("value")
                if year and year.isdigit():
                    periods.append({"year": int(year), "month": None})

        # Also try to find combined period selectors
        period_select = soup.find("select", {"name": re.compile(r"period|Period|DropDown")})
        if period_select:
            for option in period_select.find_all("option"):
                value = option.get("value")
                if value:
                    periods.append({"period": value})

        return periods

    async def scrape_with_history(self, game_type: str, months_back: int = 12) -> List[dict]:
        """Scrape lottery results including historical data."""
        if game_type not in LOTTERY_URLS:
            raise ValueError(f"Unknown game type: {game_type}")

        url = LOTTERY_URLS[game_type]
        all_results = []

        try:
            # First, get the initial page
            html = await self.fetch_page(url)

            # Parse current page results
            if game_type == "lotto":
                results = self.parse_lotto_649(html)
            else:
                results = self.parse_super_lotto(html)

            all_results.extend(results)

            # Try to get historical data by submitting forms
            form_data = self.extract_asp_form_data(html)

            if form_data:
                # Calculate date ranges for historical data
                current_date = datetime.now()

                for months_ago in range(1, months_back + 1):
                    # Calculate target month
                    target_month = current_date.month - months_ago
                    target_year = current_date.year

                    while target_month <= 0:
                        target_month += 12
                        target_year -= 1

                    # Taiwan year
                    tw_year = target_year - 1911

                    # Update form data for the target period
                    history_form_data = form_data.copy()
                    history_form_data["__EVENTTARGET"] = ""

                    # Different form field names for different games
                    if game_type == "lotto":
                        history_form_data["Lotto649Control_history$DropDownList1"] = str(tw_year)
                        history_form_data["Lotto649Control_history$DropDownList2"] = str(target_month)
                    else:
                        history_form_data["SuperLotto638Control_history$DropDownList1"] = str(tw_year)
                        history_form_data["SuperLotto638Control_history$DropDownList2"] = str(target_month)

                    try:
                        await asyncio.sleep(SCRAPER_CONFIG["request_delay"])
                        history_html = await self.fetch_page(url, form_data=history_form_data)

                        if game_type == "lotto":
                            history_results = self.parse_lotto_649(history_html)
                        else:
                            history_results = self.parse_super_lotto(history_html)

                        all_results.extend(history_results)

                    except Exception as e:
                        # Continue with other months if one fails
                        continue

            # Remove duplicates based on draw_date
            seen_dates = set()
            unique_results = []
            for result in all_results:
                date_key = (result["game_type"], result["draw_date"])
                if date_key not in seen_dates:
                    seen_dates.add(date_key)
                    unique_results.append(result)

            return unique_results

        except httpx.HTTPError as e:
            raise HTTPException(status_code=503, detail=f"Failed to fetch lottery data: {str(e)}")


# Global scraper instance
scraper = LotteryScraper()


async def save_results_to_db(results: List[dict], db: AsyncSession) -> int:
    """Save scraped results to database, returns number of new records added."""
    records_added = 0

    for result in results:
        # Check if already exists
        existing = await db.execute(
            select(LotteryDraw).where(
                LotteryDraw.game_type == result["game_type"],
                LotteryDraw.draw_date == result["draw_date"],
            )
        )
        if existing.scalar_one_or_none():
            continue

        draw = LotteryDraw(
            game_type=result["game_type"],
            draw_date=result["draw_date"],
            draw_number=result.get("draw_number"),
            numbers=result["numbers"],
            special_number=result["special_number"],
        )
        db.add(draw)
        records_added += 1

    await db.commit()
    return records_added


@router.post("/run", response_model=ScraperRunResponse)
async def run_scraper(
    request: ScraperRunRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Run the lottery scraper to fetch latest results.

    - game_type: 'lotto' for 大樂透, 'power' for 威力彩, 'all' for both
    - pages: Number of months of history to fetch (1-10)
    """
    game_type = request.game_type
    months_back = request.pages  # Reuse pages parameter for months

    if game_type == "all":
        results = []
        total_added = 0

        for gt in ["lotto", "power"]:
            try:
                gt_results = await scraper.scrape_with_history(gt, months_back)
                records_added = await save_results_to_db(gt_results, db)
                total_added += records_added
                results.append({
                    "game_type": gt,
                    "records_scraped": len(gt_results),
                    "records_added": records_added,
                })

                # Log success
                log = ScraperLog(
                    game_type=gt,
                    run_date=date.today(),
                    records_added=records_added,
                    status="success",
                )
                db.add(log)
                await db.commit()

            except Exception as e:
                # Log failure
                log = ScraperLog(
                    game_type=gt,
                    run_date=date.today(),
                    records_added=0,
                    status="failed",
                    error_message=str(e)[:500],
                )
                db.add(log)
                await db.commit()

            await asyncio.sleep(SCRAPER_CONFIG["request_delay"])

        return ScraperRunResponse(
            status="success",
            game_type="all",
            records_added=total_added,
            message=f"Scraped both game types, added {total_added} total records",
        )

    if game_type not in ["lotto", "power"]:
        raise HTTPException(status_code=400, detail="Invalid game_type. Use 'lotto', 'power', or 'all'")

    try:
        results = await scraper.scrape_with_history(game_type, months_back)
        records_added = await save_results_to_db(results, db)

        # Log success
        log = ScraperLog(
            game_type=game_type,
            run_date=date.today(),
            records_added=records_added,
            status="success",
        )
        db.add(log)
        await db.commit()

        return ScraperRunResponse(
            status="success",
            game_type=game_type,
            records_added=records_added,
            message=f"Successfully scraped {len(results)} records, added {records_added} new records",
        )

    except httpx.HTTPError as e:
        # Log failure
        log = ScraperLog(
            game_type=game_type,
            run_date=date.today(),
            records_added=0,
            status="failed",
            error_message=str(e)[:500],
        )
        db.add(log)
        await db.commit()

        raise HTTPException(status_code=503, detail=f"Failed to fetch lottery data: {str(e)}")


@router.post("/fetch-history")
async def fetch_history(
    game_type: str = Query(..., description="Game type: 'lotto' or 'power'"),
    months: int = Query(default=12, ge=1, le=60, description="Months of history to fetch"),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch historical lottery data for a specific time range.

    This endpoint fetches more historical data than the regular /run endpoint.
    Useful for initial data population.
    """
    if game_type not in ["lotto", "power"]:
        raise HTTPException(status_code=400, detail="Invalid game_type. Use 'lotto' or 'power'")

    try:
        results = await scraper.scrape_with_history(game_type, months)
        records_added = await save_results_to_db(results, db)

        # Log success
        log = ScraperLog(
            game_type=game_type,
            run_date=date.today(),
            records_added=records_added,
            status="success",
        )
        db.add(log)
        await db.commit()

        return {
            "status": "success",
            "game_type": game_type,
            "months_requested": months,
            "records_scraped": len(results),
            "records_added": records_added,
            "message": f"Fetched {months} months of history, added {records_added} new records",
        }

    except Exception as e:
        log = ScraperLog(
            game_type=game_type,
            run_date=date.today(),
            records_added=0,
            status="failed",
            error_message=str(e)[:500],
        )
        db.add(log)
        await db.commit()

        raise HTTPException(status_code=503, detail=f"Failed to fetch history: {str(e)}")


@router.get("/status")
async def get_scraper_status(db: AsyncSession = Depends(get_db)):
    """Get the status of recent scraper runs and database statistics."""
    query = (
        select(ScraperLog)
        .order_by(ScraperLog.run_date.desc())
        .limit(10)
    )
    result = await db.execute(query)
    logs = result.scalars().all()

    # Get count of records per game type
    lotto_count = await db.execute(
        select(func.count()).where(LotteryDraw.game_type == "lotto")
    )
    power_count = await db.execute(
        select(func.count()).where(LotteryDraw.game_type == "power")
    )

    # Get date range of data
    lotto_range = await db.execute(
        select(func.min(LotteryDraw.draw_date), func.max(LotteryDraw.draw_date))
        .where(LotteryDraw.game_type == "lotto")
    )
    power_range = await db.execute(
        select(func.min(LotteryDraw.draw_date), func.max(LotteryDraw.draw_date))
        .where(LotteryDraw.game_type == "power")
    )

    lotto_dates = lotto_range.one()
    power_dates = power_range.one()

    return {
        "database_stats": {
            "lotto": {
                "records": lotto_count.scalar(),
                "date_range": {
                    "earliest": lotto_dates[0].isoformat() if lotto_dates[0] else None,
                    "latest": lotto_dates[1].isoformat() if lotto_dates[1] else None,
                }
            },
            "power": {
                "records": power_count.scalar(),
                "date_range": {
                    "earliest": power_dates[0].isoformat() if power_dates[0] else None,
                    "latest": power_dates[1].isoformat() if power_dates[1] else None,
                }
            },
        },
        "recent_runs": [
            {
                "game_type": log.game_type,
                "run_date": log.run_date.isoformat(),
                "records_added": log.records_added,
                "status": log.status,
                "error": log.error_message,
            }
            for log in logs
        ],
    }


@router.post("/seed")
async def seed_sample_data(db: AsyncSession = Depends(get_db)):
    """
    Seed the database with sample lottery data for testing.
    Includes realistic historical data from recent months.
    """
    import random

    records_added = 0

    # Generate sample Lotto 649 data (draws on Tue, Fri)
    lotto_dates = []
    current = date.today()
    for i in range(100):  # Generate 100 sample draws
        days_back = i * 3 + (i % 2)  # Approximate Tue/Fri pattern
        draw_date = date.fromordinal(current.toordinal() - days_back)
        lotto_dates.append(draw_date)

    for draw_date in lotto_dates:
        existing = await db.execute(
            select(LotteryDraw).where(
                LotteryDraw.game_type == "lotto",
                LotteryDraw.draw_date == draw_date,
            )
        )
        if existing.scalar_one_or_none():
            continue

        # Generate random numbers
        numbers = sorted(random.sample(range(1, 50), 6))
        special = random.randint(1, 49)

        draw = LotteryDraw(
            game_type="lotto",
            draw_date=draw_date,
            numbers=numbers,
            special_number=special,
        )
        db.add(draw)
        records_added += 1

    # Generate sample Power Lotto data (draws on Mon, Thu)
    power_dates = []
    for i in range(100):
        days_back = i * 3 + ((i + 1) % 2)
        draw_date = date.fromordinal(current.toordinal() - days_back)
        power_dates.append(draw_date)

    for draw_date in power_dates:
        existing = await db.execute(
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
        db.add(draw)
        records_added += 1

    await db.commit()

    return {
        "status": "success",
        "message": f"Seeded {records_added} sample records (historical data for testing)",
        "records_added": records_added,
    }


@router.delete("/clear")
async def clear_data(
    game_type: str = Query(default="all", description="Game type to clear: 'lotto', 'power', or 'all'"),
    db: AsyncSession = Depends(get_db),
):
    """Clear lottery data from database. Use with caution."""
    from sqlalchemy import delete

    if game_type == "all":
        await db.execute(delete(LotteryDraw))
        await db.execute(delete(ScraperLog))
    else:
        await db.execute(delete(LotteryDraw).where(LotteryDraw.game_type == game_type))
        await db.execute(delete(ScraperLog).where(ScraperLog.game_type == game_type))

    await db.commit()

    return {
        "status": "success",
        "message": f"Cleared {game_type} data from database",
    }
