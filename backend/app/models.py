"""Pydantic models for API request/response."""
from datetime import date
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class LotteryDrawBase(BaseModel):
    """Base lottery draw schema."""
    game_type: str = Field(..., description="Game type: 'lotto' or 'power'")
    draw_date: date
    numbers: List[int] = Field(..., description="Main lottery numbers")
    special_number: Optional[int] = Field(None, description="Special/bonus number")


class LotteryDrawCreate(LotteryDrawBase):
    """Schema for creating a lottery draw."""
    draw_number: Optional[str] = None
    second_special: Optional[int] = None


class LotteryDrawResponse(LotteryDrawBase):
    """Schema for lottery draw response."""
    id: int
    draw_number: Optional[str] = None
    second_special: Optional[int] = None

    class Config:
        from_attributes = True


class LotteryHistoryResponse(BaseModel):
    """Response for lottery history query."""
    game_type: str
    total_records: int
    draws: List[LotteryDrawResponse]


# ============ News Extraction Models ============

class NewsExtractRequest(BaseModel):
    """Request for news number extraction."""
    text: str = Field(..., min_length=1, description="News text to extract numbers from")
    game_type: str = Field(default="lotto", description="Target game type: 'lotto' or 'power'")


class ExtractedNumber(BaseModel):
    """Extracted number with context and metadata."""
    number: int = Field(..., description="The extracted number")
    original: str = Field(..., description="Original text that was parsed")
    context: str = Field(..., description="Surrounding text context")
    source_type: str = Field(..., description="Type: digit, chinese, date, amount, etc.")
    is_valid: bool = Field(..., description="Whether number is valid for the game type")
    weight: float = Field(default=1.0, description="Importance weight for selection")


class TransformedNumber(BaseModel):
    """A number after transformation."""
    original: int = Field(..., description="Original number before transformation")
    transformed: int = Field(..., description="Transformed number")
    method: str = Field(..., description="Transformation method used")
    is_valid: bool = Field(..., description="Whether transformed number is valid")


class NumberSet(BaseModel):
    """A suggested set of lottery numbers."""
    numbers: List[int] = Field(..., description="The 6 main numbers")
    special_number: Optional[int] = Field(None, description="Special/power number if applicable")
    strategy: str = Field(..., description="Strategy used to generate this set")
    confidence: float = Field(default=0.5, description="Confidence score 0-1")
    explanation: str = Field(..., description="Explanation of how numbers were chosen")


class NewsExtractResponse(BaseModel):
    """Response for news number extraction."""
    original_text: str
    game_type: str
    extracted_numbers: List[ExtractedNumber]
    valid_numbers: List[int] = Field(..., description="Numbers valid for lottery selection")
    transformed_numbers: List[TransformedNumber] = Field(default=[], description="Numbers after transformation")
    suggested_sets: List[NumberSet] = Field(default=[], description="Suggested number sets")
    statistics: Dict[str, Any] = Field(default={}, description="Extraction statistics")


class BatchExtractRequest(BaseModel):
    """Request for batch text extraction."""
    texts: List[str] = Field(..., min_items=1, max_items=20, description="List of texts to process")
    game_type: str = Field(default="lotto", description="Target game type")
    combine_results: bool = Field(default=True, description="Whether to combine all results for suggestions")


class BatchExtractResponse(BaseModel):
    """Response for batch extraction."""
    game_type: str
    total_texts: int
    results: List[Dict[str, Any]]
    combined_valid_numbers: List[int]
    suggested_sets: List[NumberSet]


class SmartPickRequest(BaseModel):
    """Request for smart number picking from text."""
    text: str = Field(..., min_length=1, description="Text to analyze")
    game_type: str = Field(default="lotto", description="Target game type")
    num_sets: int = Field(default=3, ge=1, le=10, description="Number of sets to generate")
    include_special: bool = Field(default=True, description="Include special/power number")
    strategies: Optional[List[str]] = Field(
        default=None,
        description="Specific strategies to use: frequency, weighted, transformed, random_mix"
    )


# ============ News Fetch Models ============

class NewsItem(BaseModel):
    """A single news item."""
    title: str = Field(..., description="News title")
    description: Optional[str] = Field(None, description="News description/summary")
    source: str = Field(..., description="News source name")
    url: Optional[str] = Field(None, description="Link to full article")
    published: Optional[str] = Field(None, description="Publication date")
    category: str = Field(default="general", description="News category: taiwan, international, finance, etc.")


class NewsFetchResponse(BaseModel):
    """Response for news fetch."""
    total_news: int
    news_items: List[NewsItem]
    combined_text: str = Field(..., description="Combined text from all news for extraction")


class NewsAutoExtractRequest(BaseModel):
    """Request for auto news fetch and extract."""
    game_type: str = Field(default="lotto", description="Target game type: 'lotto' or 'power'")
    news_count: int = Field(default=10, ge=5, le=20, description="Number of news to fetch")
    categories: Optional[List[str]] = Field(
        default=None,
        description="News categories: taiwan, international, finance, sports, entertainment"
    )


# ============ Scraper Models ============

class ScraperRunRequest(BaseModel):
    """Request to run scraper."""
    game_type: str = Field(..., description="Game type: 'lotto', 'power', or 'all'")
    pages: int = Field(default=1, ge=1, le=10, description="Number of pages to scrape")


class ScraperRunResponse(BaseModel):
    """Response from scraper run."""
    status: str
    game_type: str
    records_added: int
    message: str


# ============ Statistics Models ============

class StatisticsResponse(BaseModel):
    """Response for lottery statistics."""
    game_type: str
    total_draws: int
    hot_numbers: List[dict] = Field(..., description="Most frequent numbers")
    cold_numbers: List[dict] = Field(..., description="Least frequent numbers")
    number_frequency: dict = Field(..., description="Frequency count for each number")
