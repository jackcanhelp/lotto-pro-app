"""
News number extraction API routes.

Enhanced extraction with support for:
- Arabic numerals (阿拉伯數字)
- Chinese numerals (中文數字)
- Date extraction (日期)
- Amount/currency extraction (金額)
- Multiple transformation strategies
- Smart number set generation
- Auto news fetching from RSS feeds
"""
import re
import random
import asyncio
import xml.etree.ElementTree as ET
from collections import Counter
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException

from app.models import (
    NewsExtractRequest,
    NewsExtractResponse,
    ExtractedNumber,
    TransformedNumber,
    NumberSet,
    BatchExtractRequest,
    BatchExtractResponse,
    SmartPickRequest,
    NewsItem,
    NewsFetchResponse,
    NewsAutoExtractRequest,
)

router = APIRouter(prefix="/news")

# ============ Chinese Number Mapping ============

CHINESE_DIGITS = {
    '零': 0, '〇': 0, 'O': 0,
    '一': 1, '壹': 1,
    '二': 2, '貳': 2, '两': 2, '兩': 2,
    '三': 3, '參': 3, '叁': 3,
    '四': 4, '肆': 4,
    '五': 5, '伍': 5,
    '六': 6, '陸': 6,
    '七': 7, '柒': 7,
    '八': 8, '捌': 8,
    '九': 9, '玖': 9,
    '十': 10, '拾': 10,
    '百': 100, '佰': 100,
    '千': 1000, '仟': 1000,
    '萬': 10000, '万': 10000,
    '億': 100000000, '亿': 100000000,
}

# Game configuration
GAME_CONFIG = {
    "lotto": {
        "main_max": 49,
        "main_count": 6,
        "special_max": 49,
        "name": "大樂透",
    },
    "power": {
        "main_max": 38,
        "main_count": 6,
        "special_max": 8,
        "name": "威力彩",
    },
    "daily539": {
        "main_max": 39,
        "main_count": 5,
        "special_max": 0,  # 今彩539沒有特別號
        "name": "今彩539",
    }
}


# ============ Number Extraction Functions ============

def parse_chinese_number(text: str) -> Optional[int]:
    """Parse Chinese numeral string to integer."""
    if not text:
        return None

    # Simple single character
    if len(text) == 1 and text in CHINESE_DIGITS:
        return CHINESE_DIGITS[text]

    # Complex Chinese number parsing
    result = 0
    temp = 0
    billion = 0

    for char in text:
        if char not in CHINESE_DIGITS:
            continue

        val = CHINESE_DIGITS[char]

        if val == 100000000:  # 億
            if temp == 0:
                temp = 1
            billion = (result + temp) * val
            result = 0
            temp = 0
        elif val == 10000:  # 萬
            if temp == 0:
                temp = 1
            result = (result + temp) * val
            temp = 0
        elif val >= 10:  # 十百千
            if temp == 0:
                temp = 1
            result += temp * val
            temp = 0
        else:  # 0-9
            temp = temp * 10 + val

    result += temp + billion

    return result if result > 0 else None


def extract_numbers_from_text(text: str) -> List[Dict[str, Any]]:
    """
    Extract all types of numbers from text with context and metadata.
    Returns list of dicts with: number, original, context, source_type, weight
    """
    results = []
    seen_positions = set()

    # 1. Extract Arabic numerals (with optional commas)
    for match in re.finditer(r'(\d{1,3}(?:,\d{3})*|\d+)', text):
        pos = match.start()
        if pos in seen_positions:
            continue

        original = match.group(1)
        number_str = original.replace(',', '')

        try:
            number = int(number_str)
            context = get_context(text, match.start(), match.end())

            # Determine weight based on context
            weight = calculate_weight(text, match.start(), match.end(), number)

            results.append({
                "number": number,
                "original": original,
                "context": context,
                "source_type": "digit",
                "weight": weight,
                "position": pos,
            })
            seen_positions.add(pos)
        except ValueError:
            continue

    # 2. Extract Chinese numerals
    chinese_pattern = r'[零一二三四五六七八九十百千萬億壹貳參肆伍陸柒捌玖拾佰仟兩两〇]+'
    for match in re.finditer(chinese_pattern, text):
        pos = match.start()
        if any(abs(pos - p) < 3 for p in seen_positions):
            continue

        original = match.group()
        number = parse_chinese_number(original)

        if number is not None and number > 0:
            context = get_context(text, match.start(), match.end())
            weight = calculate_weight(text, match.start(), match.end(), number)

            results.append({
                "number": number,
                "original": original,
                "context": context,
                "source_type": "chinese",
                "weight": weight * 1.1,  # Slight boost for Chinese numbers (more intentional)
                "position": pos,
            })
            seen_positions.add(pos)

    # 3. Extract dates (various formats)
    date_patterns = [
        (r'(\d{4})[/\-年](\d{1,2})[/\-月](\d{1,2})', 'date_ymd'),
        (r'(\d{1,2})[/\-月](\d{1,2})[日號]?', 'date_md'),
        (r'(\d{2,3})[/\-\.](\d{1,2})[/\-\.](\d{1,2})', 'date_tw'),  # Taiwan format
    ]

    for pattern, date_type in date_patterns:
        for match in re.finditer(pattern, text):
            pos = match.start()
            groups = match.groups()
            context = get_context(text, match.start(), match.end())

            for i, g in enumerate(groups):
                try:
                    num = int(g)
                    if num > 0:
                        results.append({
                            "number": num,
                            "original": g,
                            "context": context,
                            "source_type": date_type,
                            "weight": 0.8,  # Dates slightly lower weight
                            "position": pos + i,
                        })
                except ValueError:
                    continue

    # 4. Extract amounts/currency
    amount_patterns = [
        r'(\d+(?:,\d{3})*)\s*(?:元|塊|圓|萬|億|千|百)',
        r'(?:NT\$|＄|\$)\s*(\d+(?:,\d{3})*)',
    ]

    for pattern in amount_patterns:
        for match in re.finditer(pattern, text):
            pos = match.start()
            original = match.group(1) if match.lastindex else match.group()
            number_str = original.replace(',', '')

            try:
                number = int(number_str)
                context = get_context(text, match.start(), match.end())

                results.append({
                    "number": number,
                    "original": original,
                    "context": context,
                    "source_type": "amount",
                    "weight": 0.9,
                    "position": pos,
                })
            except ValueError:
                continue

    # 5. Extract percentages
    for match in re.finditer(r'(\d+(?:\.\d+)?)\s*[%％]', text):
        try:
            number = int(float(match.group(1)))
            if number > 0:
                context = get_context(text, match.start(), match.end())
                results.append({
                    "number": number,
                    "original": match.group(1),
                    "context": context,
                    "source_type": "percentage",
                    "weight": 0.7,
                    "position": match.start(),
                })
        except ValueError:
            continue

    # Sort by position and remove duplicates
    results.sort(key=lambda x: x["position"])

    # Remove exact duplicates (same number at same position)
    unique_results = []
    seen = set()
    for r in results:
        key = (r["number"], r["position"])
        if key not in seen:
            seen.add(key)
            unique_results.append(r)

    return unique_results


def get_context(text: str, start: int, end: int, context_size: int = 25) -> str:
    """Get surrounding context for a match."""
    ctx_start = max(0, start - context_size)
    ctx_end = min(len(text), end + context_size)
    context = text[ctx_start:ctx_end]

    if ctx_start > 0:
        context = "..." + context
    if ctx_end < len(text):
        context = context + "..."

    return context


def calculate_weight(text: str, start: int, end: int, number: int) -> float:
    """Calculate importance weight for a number based on context."""
    weight = 1.0
    context = text[max(0, start - 50):min(len(text), end + 50)].lower()

    # Boost for lottery-related keywords
    lottery_keywords = ['樂透', '彩券', '號碼', '開獎', '中獎', '頭獎', '威力彩', '大樂透', '選號']
    for kw in lottery_keywords:
        if kw in context:
            weight *= 1.3
            break

    # Boost for lucky/fortune keywords
    lucky_keywords = ['幸運', '吉祥', '好運', '財運', '發財', '旺']
    for kw in lucky_keywords:
        if kw in context:
            weight *= 1.2
            break

    # Reduce weight for very large numbers (likely not lottery numbers)
    if number > 1000:
        weight *= 0.5
    elif number > 100:
        weight *= 0.8

    # Boost for numbers in valid lottery range
    if 1 <= number <= 49:
        weight *= 1.1

    return round(weight, 2)


def validate_number_for_game(number: int, game_type: str) -> bool:
    """Check if a number is valid for the specified game type."""
    config = GAME_CONFIG.get(game_type)
    if not config:
        return False
    return 1 <= number <= config["main_max"]


def validate_special_number(number: int, game_type: str) -> bool:
    """Check if a number is valid as special number for the game."""
    config = GAME_CONFIG.get(game_type)
    if not config:
        return False
    return 1 <= number <= config["special_max"]


# ============ Number Transformation Functions ============

def transform_number(number: int, game_type: str) -> List[Dict[str, Any]]:
    """
    Apply various transformation strategies to convert a number to valid lottery range.
    Returns list of transformed numbers with methods.
    """
    config = GAME_CONFIG.get(game_type)
    if not config:
        return []

    max_num = config["main_max"]
    results = []

    # Already valid
    if 1 <= number <= max_num:
        return []

    # 1. Modulo transformation
    mod_result = (number % max_num)
    if mod_result == 0:
        mod_result = max_num
    results.append({
        "original": number,
        "transformed": mod_result,
        "method": "modulo",
        "is_valid": True,
    })

    # 2. Digital root (repeated digit sum until single digit or valid)
    dr = digital_root(number, max_num)
    if dr != mod_result:
        results.append({
            "original": number,
            "transformed": dr,
            "method": "digital_root",
            "is_valid": 1 <= dr <= max_num,
        })

    # 3. Last N digits
    if number >= 10:
        last_two = number % 100
        if 1 <= last_two <= max_num and last_two != mod_result:
            results.append({
                "original": number,
                "transformed": last_two,
                "method": "last_digits",
                "is_valid": True,
            })

    # 4. Digit sum
    digit_sum = sum(int(d) for d in str(number))
    if digit_sum <= max_num and digit_sum not in [r["transformed"] for r in results]:
        results.append({
            "original": number,
            "transformed": digit_sum,
            "method": "digit_sum",
            "is_valid": 1 <= digit_sum <= max_num,
        })

    # 5. First valid digits
    num_str = str(number)
    for i in range(1, len(num_str) + 1):
        prefix = int(num_str[:i])
        if 1 <= prefix <= max_num and prefix not in [r["transformed"] for r in results]:
            results.append({
                "original": number,
                "transformed": prefix,
                "method": "prefix_digits",
                "is_valid": True,
            })
            break

    return results


def digital_root(n: int, max_val: int) -> int:
    """Calculate digital root, adjusted for lottery range."""
    while n > max_val:
        n = sum(int(d) for d in str(n))
    return n if n > 0 else 1


# ============ Number Set Generation Functions ============

def generate_number_sets(
    valid_numbers: List[int],
    transformed: List[TransformedNumber],
    weights: Dict[int, float],
    game_type: str,
    num_sets: int = 3,
    include_special: bool = True
) -> List[NumberSet]:
    """Generate suggested number sets using various strategies."""
    config = GAME_CONFIG.get(game_type)
    if not config:
        return []

    sets = []
    all_valid = list(set(valid_numbers))
    transformed_valid = [t.transformed for t in transformed if t.is_valid]
    combined = list(set(all_valid + transformed_valid))

    # Strategy 1: Frequency-based (most common numbers)
    if len(combined) >= 6:
        freq_set = generate_frequency_set(combined, weights, config, include_special)
        if freq_set:
            sets.append(freq_set)

    # Strategy 2: Weighted random selection
    if len(combined) >= 6:
        weighted_set = generate_weighted_set(combined, weights, config, include_special)
        if weighted_set:
            sets.append(weighted_set)

    # Strategy 3: Balanced selection (spread across range)
    if len(combined) >= 6:
        balanced_set = generate_balanced_set(combined, config, include_special)
        if balanced_set:
            sets.append(balanced_set)

    # Strategy 4: Mixed with random fill
    if len(combined) >= 3:
        mixed_set = generate_mixed_set(combined, weights, config, include_special)
        if mixed_set:
            sets.append(mixed_set)

    # If not enough sets, add random completion sets
    while len(sets) < num_sets and len(combined) >= 1:
        random_set = generate_random_fill_set(combined, config, include_special)
        if random_set and random_set.numbers not in [s.numbers for s in sets]:
            sets.append(random_set)
        else:
            break

    return sets[:num_sets]


def generate_frequency_set(
    numbers: List[int],
    weights: Dict[int, float],
    config: dict,
    include_special: bool
) -> Optional[NumberSet]:
    """Generate set based on frequency/weight."""
    # Sort by weight descending
    sorted_nums = sorted(numbers, key=lambda x: weights.get(x, 1.0), reverse=True)
    selected = sorted_nums[:6]

    if len(selected) < 6:
        return None

    selected = sorted(selected)
    special = None

    if include_special:
        remaining = [n for n in sorted_nums[6:] if n <= config["special_max"]]
        if remaining:
            special = remaining[0]
        elif selected:
            special = random.randint(1, config["special_max"])

    return NumberSet(
        numbers=selected,
        special_number=special,
        strategy="frequency",
        confidence=0.7,
        explanation=f"根據文字中數字出現頻率和重要性選取前6個號碼"
    )


def generate_weighted_set(
    numbers: List[int],
    weights: Dict[int, float],
    config: dict,
    include_special: bool
) -> Optional[NumberSet]:
    """Generate set using weighted random selection."""
    if len(numbers) < 6:
        return None

    # Weighted random selection
    weighted_list = []
    for n in numbers:
        w = weights.get(n, 1.0)
        weighted_list.extend([n] * int(w * 10))

    selected = set()
    attempts = 0
    while len(selected) < 6 and attempts < 100:
        pick = random.choice(weighted_list)
        if pick <= config["main_max"]:
            selected.add(pick)
        attempts += 1

    if len(selected) < 6:
        return None

    selected = sorted(list(selected))
    special = None

    if include_special:
        special = random.randint(1, config["special_max"])

    return NumberSet(
        numbers=selected,
        special_number=special,
        strategy="weighted_random",
        confidence=0.6,
        explanation=f"根據數字權重進行加權隨機選取"
    )


def generate_balanced_set(
    numbers: List[int],
    config: dict,
    include_special: bool
) -> Optional[NumberSet]:
    """Generate a balanced set spread across the number range."""
    max_num = config["main_max"]
    valid_nums = [n for n in numbers if 1 <= n <= max_num]

    if len(valid_nums) < 6:
        return None

    # Divide range into zones
    zones = [
        (1, max_num // 3),
        (max_num // 3 + 1, 2 * max_num // 3),
        (2 * max_num // 3 + 1, max_num)
    ]

    selected = []
    for low, high in zones:
        zone_nums = [n for n in valid_nums if low <= n <= high]
        if zone_nums:
            selected.extend(random.sample(zone_nums, min(2, len(zone_nums))))

    # Fill remaining
    remaining = [n for n in valid_nums if n not in selected]
    while len(selected) < 6 and remaining:
        pick = random.choice(remaining)
        selected.append(pick)
        remaining.remove(pick)

    if len(selected) < 6:
        return None

    selected = sorted(selected[:6])
    special = random.randint(1, config["special_max"]) if include_special else None

    return NumberSet(
        numbers=selected,
        special_number=special,
        strategy="balanced",
        confidence=0.65,
        explanation=f"平衡選取，確保號碼分布在整個數字範圍"
    )


def generate_mixed_set(
    numbers: List[int],
    weights: Dict[int, float],
    config: dict,
    include_special: bool
) -> Optional[NumberSet]:
    """Generate set mixing extracted numbers with random fill."""
    max_num = config["main_max"]
    valid_nums = [n for n in numbers if 1 <= n <= max_num]

    # Take top weighted numbers
    sorted_nums = sorted(valid_nums, key=lambda x: weights.get(x, 1.0), reverse=True)
    selected = set(sorted_nums[:min(4, len(sorted_nums))])

    # Random fill
    all_nums = set(range(1, max_num + 1))
    available = list(all_nums - selected)

    while len(selected) < 6 and available:
        pick = random.choice(available)
        selected.add(pick)
        available.remove(pick)

    selected = sorted(list(selected))[:6]
    special = random.randint(1, config["special_max"]) if include_special else None

    extracted_count = len([n for n in selected if n in valid_nums])

    return NumberSet(
        numbers=selected,
        special_number=special,
        strategy="mixed",
        confidence=0.5,
        explanation=f"混合策略：{extracted_count}個來自文字提取，其餘隨機補充"
    )


def generate_random_fill_set(
    numbers: List[int],
    config: dict,
    include_special: bool
) -> Optional[NumberSet]:
    """Generate set with at least one extracted number and random fill."""
    max_num = config["main_max"]
    valid_nums = [n for n in numbers if 1 <= n <= max_num]

    if not valid_nums:
        return None

    # Pick 1-2 from extracted
    selected = set(random.sample(valid_nums, min(2, len(valid_nums))))

    # Random fill
    all_nums = set(range(1, max_num + 1))
    available = list(all_nums - selected)

    while len(selected) < 6:
        pick = random.choice(available)
        selected.add(pick)
        available.remove(pick)

    selected = sorted(list(selected))
    special = random.randint(1, config["special_max"]) if include_special else None

    return NumberSet(
        numbers=selected,
        special_number=special,
        strategy="random_fill",
        confidence=0.4,
        explanation=f"以提取的數字為基礎，隨機補充其餘號碼"
    )


# ============ API Endpoints ============

@router.post("/extract", response_model=NewsExtractResponse)
async def extract_numbers_from_news(request: NewsExtractRequest):
    """
    Extract numbers from news text and generate lottery number suggestions.

    Supports:
    - Arabic numerals (123, 1,000)
    - Chinese numerals (一二三, 壹貳參)
    - Dates (2024/01/15, 113年1月)
    - Amounts (100元, NT$500)
    - Percentages (50%)

    Returns extracted numbers with context and suggested lottery sets.
    """
    text = request.text.strip()
    game_type = request.game_type

    if game_type not in GAME_CONFIG:
        raise HTTPException(status_code=400, detail="Invalid game_type. Use 'lotto' or 'power'")

    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    # Extract all numbers
    raw_extractions = extract_numbers_from_text(text)

    # Build extracted numbers list and collect valid numbers
    extracted_numbers = []
    valid_numbers = []
    weights = {}

    for ext in raw_extractions:
        number = ext["number"]
        is_valid = validate_number_for_game(number, game_type)

        extracted_numbers.append(ExtractedNumber(
            number=number,
            original=ext["original"],
            context=ext["context"],
            source_type=ext["source_type"],
            is_valid=is_valid,
            weight=ext["weight"],
        ))

        if is_valid:
            valid_numbers.append(number)
            weights[number] = max(weights.get(number, 0), ext["weight"])

    # Apply transformations to invalid numbers
    transformed_numbers = []
    for ext in raw_extractions:
        if not validate_number_for_game(ext["number"], game_type):
            transforms = transform_number(ext["number"], game_type)
            for t in transforms:
                transformed_numbers.append(TransformedNumber(**t))
                if t["is_valid"]:
                    weights[t["transformed"]] = max(
                        weights.get(t["transformed"], 0),
                        ext["weight"] * 0.8
                    )

    # Generate suggested sets
    suggested_sets = generate_number_sets(
        valid_numbers=valid_numbers,
        transformed=transformed_numbers,
        weights=weights,
        game_type=game_type,
        num_sets=3,
        include_special=True
    )

    # Build statistics
    statistics = {
        "total_extracted": len(extracted_numbers),
        "valid_count": len(valid_numbers),
        "unique_valid": len(set(valid_numbers)),
        "transformed_count": len(transformed_numbers),
        "source_types": dict(Counter(e.source_type for e in extracted_numbers)),
    }

    return NewsExtractResponse(
        original_text=text[:500] + "..." if len(text) > 500 else text,
        game_type=game_type,
        extracted_numbers=extracted_numbers,
        valid_numbers=sorted(set(valid_numbers)),
        transformed_numbers=transformed_numbers,
        suggested_sets=suggested_sets,
        statistics=statistics,
    )


@router.post("/batch-extract", response_model=BatchExtractResponse)
async def batch_extract_numbers(request: BatchExtractRequest):
    """
    Extract numbers from multiple text sources.
    Useful for processing multiple news headlines at once.
    """
    game_type = request.game_type
    texts = request.texts

    if game_type not in GAME_CONFIG:
        raise HTTPException(status_code=400, detail="Invalid game_type")

    all_valid_numbers = []
    all_weights = {}
    results = []

    for text in texts:
        raw_extractions = extract_numbers_from_text(text)

        text_valid = []
        for ext in raw_extractions:
            if validate_number_for_game(ext["number"], game_type):
                text_valid.append(ext["number"])
                all_valid_numbers.append(ext["number"])
                all_weights[ext["number"]] = max(
                    all_weights.get(ext["number"], 0),
                    ext["weight"]
                )

        results.append({
            "text": text[:100] + "..." if len(text) > 100 else text,
            "extracted_count": len(raw_extractions),
            "valid_numbers": sorted(set(text_valid)),
        })

    # Generate combined suggestions
    suggested_sets = generate_number_sets(
        valid_numbers=all_valid_numbers,
        transformed=[],
        weights=all_weights,
        game_type=game_type,
        num_sets=3,
        include_special=True
    )

    return BatchExtractResponse(
        game_type=game_type,
        total_texts=len(texts),
        results=results,
        combined_valid_numbers=sorted(set(all_valid_numbers)),
        suggested_sets=suggested_sets,
    )


@router.post("/smart-pick")
async def smart_pick_numbers(request: SmartPickRequest):
    """
    Smart number picking from text with customizable strategies.

    Strategies available:
    - frequency: Based on number occurrence frequency
    - weighted: Weighted random based on context importance
    - balanced: Spread numbers across the range
    - mixed: Combine extracted with random numbers
    - random_fill: Minimal extraction with random fill
    """
    text = request.text.strip()
    game_type = request.game_type
    num_sets = request.num_sets

    if game_type not in GAME_CONFIG:
        raise HTTPException(status_code=400, detail="Invalid game_type")

    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    # Extract numbers
    raw_extractions = extract_numbers_from_text(text)

    valid_numbers = []
    weights = {}
    transformed = []

    for ext in raw_extractions:
        if validate_number_for_game(ext["number"], game_type):
            valid_numbers.append(ext["number"])
            weights[ext["number"]] = max(weights.get(ext["number"], 0), ext["weight"])
        else:
            # Transform invalid numbers
            transforms = transform_number(ext["number"], game_type)
            for t in transforms:
                if t["is_valid"]:
                    transformed.append(TransformedNumber(**t))
                    weights[t["transformed"]] = max(
                        weights.get(t["transformed"], 0),
                        ext["weight"] * 0.8
                    )

    # Generate sets
    suggested_sets = generate_number_sets(
        valid_numbers=valid_numbers,
        transformed=transformed,
        weights=weights,
        game_type=game_type,
        num_sets=num_sets,
        include_special=request.include_special
    )

    return {
        "game_type": game_type,
        "text_preview": text[:200] + "..." if len(text) > 200 else text,
        "numbers_found": len(valid_numbers),
        "unique_numbers": len(set(valid_numbers)),
        "suggested_sets": [s.model_dump() for s in suggested_sets],
    }


@router.get("/strategies")
async def list_strategies():
    """List available number selection strategies."""
    return {
        "strategies": [
            {
                "name": "frequency",
                "description": "根據數字出現頻率和重要性權重選取",
                "confidence": "高",
            },
            {
                "name": "weighted_random",
                "description": "根據權重進行加權隨機選取",
                "confidence": "中",
            },
            {
                "name": "balanced",
                "description": "平衡選取，確保號碼分布均勻",
                "confidence": "中",
            },
            {
                "name": "mixed",
                "description": "混合提取數字與隨機號碼",
                "confidence": "中低",
            },
            {
                "name": "random_fill",
                "description": "以少量提取數字為基礎，隨機補充",
                "confidence": "低",
            },
        ],
        "supported_games": [
            {"type": "lotto", "name": "大樂透", "main_range": "1-49", "special_range": "1-49"},
            {"type": "power", "name": "威力彩", "main_range": "1-38", "special_range": "1-8"},
        ],
        "supported_sources": [
            "digit (阿拉伯數字)",
            "chinese (中文數字)",
            "date_ymd (年月日)",
            "date_md (月日)",
            "date_tw (民國年)",
            "amount (金額)",
            "percentage (百分比)",
        ],
    }


# ============ News Fetching Functions ============

# News RSS Feed URLs
NEWS_FEEDS = {
    "taiwan": [
        ("https://news.google.com/rss/search?q=台灣+新聞&hl=zh-TW&gl=TW&ceid=TW:zh-Hant", "Google 台灣新聞"),
        ("https://news.google.com/rss/topics/CAAqJQgKIh9DQkFTRVFvSUwyMHZNRFptTXpJU0JYcG9MVlJYS0FBUAE?hl=zh-TW&gl=TW&ceid=TW:zh-Hant", "Google 台灣焦點"),
    ],
    "international": [
        ("https://news.google.com/rss/topics/CAAqKggKIiRDQkFTRlFvSUwyMHZNRGx1YlY4U0JYcG9MVlJYR2dKVVZ5Z0FQAQ?hl=zh-TW&gl=TW&ceid=TW:zh-Hant", "Google 國際新聞"),
        ("https://news.google.com/rss/search?q=國際+大事&hl=zh-TW&gl=TW&ceid=TW:zh-Hant", "Google 國際大事"),
    ],
    "finance": [
        ("https://news.google.com/rss/topics/CAAqKggKIiRDQkFTRlFvSUwyMHZNRGx6TVdZU0JYcG9MVlJYR2dKVVZ5Z0FQAQ?hl=zh-TW&gl=TW&ceid=TW:zh-Hant", "Google 財經新聞"),
        ("https://news.google.com/rss/search?q=股市+財經&hl=zh-TW&gl=TW&ceid=TW:zh-Hant", "Google 股市財經"),
    ],
    "sports": [
        ("https://news.google.com/rss/topics/CAAqKggKIiRDQkFTRlFvSUwyMHZNRFp1ZEdvU0JYcG9MVlJYR2dKVVZ5Z0FQAQ?hl=zh-TW&gl=TW&ceid=TW:zh-Hant", "Google 體育新聞"),
    ],
    "entertainment": [
        ("https://news.google.com/rss/topics/CAAqKggKIiRDQkFTRlFvSUwyMHZNREpxYW5RU0JYcG9MVlJYR2dKVVZ5Z0FQAQ?hl=zh-TW&gl=TW&ceid=TW:zh-Hant", "Google 娛樂新聞"),
    ],
}


async def fetch_rss_feed(url: str, source_name: str, timeout: float = 15.0) -> List[NewsItem]:
    """Fetch and parse a single RSS feed."""
    news_items = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.content)

            # Handle RSS 2.0 format
            channel = root.find("channel")
            if channel is not None:
                for item in channel.findall("item"):
                    title_elem = item.find("title")
                    desc_elem = item.find("description")
                    link_elem = item.find("link")
                    pub_date_elem = item.find("pubDate")

                    if title_elem is not None and title_elem.text:
                        news_items.append(NewsItem(
                            title=title_elem.text.strip(),
                            description=desc_elem.text.strip() if desc_elem is not None and desc_elem.text else None,
                            source=source_name,
                            url=link_elem.text.strip() if link_elem is not None and link_elem.text else None,
                            published=pub_date_elem.text.strip() if pub_date_elem is not None and pub_date_elem.text else None,
                        ))

            # Handle Atom format
            else:
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                for entry in root.findall("atom:entry", ns):
                    title_elem = entry.find("atom:title", ns)
                    summary_elem = entry.find("atom:summary", ns)
                    link_elem = entry.find("atom:link", ns)
                    updated_elem = entry.find("atom:updated", ns)

                    if title_elem is not None and title_elem.text:
                        link_url = None
                        if link_elem is not None:
                            link_url = link_elem.get("href")

                        news_items.append(NewsItem(
                            title=title_elem.text.strip(),
                            description=summary_elem.text.strip() if summary_elem is not None and summary_elem.text else None,
                            source=source_name,
                            url=link_url,
                            published=updated_elem.text.strip() if updated_elem is not None and updated_elem.text else None,
                        ))

    except Exception as e:
        print(f"Error fetching {source_name}: {e}")

    return news_items


async def fetch_news_from_categories(
    categories: List[str],
    max_per_category: int = 5
) -> List[NewsItem]:
    """Fetch news from multiple categories."""
    all_news = []
    tasks = []

    for category in categories:
        if category in NEWS_FEEDS:
            for url, source_name in NEWS_FEEDS[category]:
                tasks.append(fetch_rss_feed(url, source_name))

    if not tasks:
        # Default: fetch from all categories
        for category, feeds in NEWS_FEEDS.items():
            for url, source_name in feeds:
                tasks.append(fetch_rss_feed(url, source_name))

    # Fetch all feeds concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Collect results
    category_counts = {}
    for result in results:
        if isinstance(result, list):
            for news_item in result:
                cat = news_item.source.split()[0] if news_item.source else "general"
                category_counts[cat] = category_counts.get(cat, 0) + 1

                # Limit per source to ensure variety
                if category_counts[cat] <= max_per_category:
                    all_news.append(news_item)

    return all_news


def clean_html_tags(text: str) -> str:
    """Remove HTML tags from text."""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text)


@router.get("/fetch", response_model=NewsFetchResponse)
async def fetch_latest_news(
    count: int = 10,
    categories: Optional[str] = None,
):
    """
    Fetch latest news from various sources.

    - count: Number of news items to fetch (5-20)
    - categories: Comma-separated list of categories (taiwan, international, finance, sports, entertainment)

    Returns news items with combined text for number extraction.
    """
    if count < 5:
        count = 5
    elif count > 20:
        count = 20

    # Parse categories
    cat_list = ["taiwan", "international"]  # Default categories
    if categories:
        cat_list = [c.strip().lower() for c in categories.split(",")]

    # Fetch news
    all_news = await fetch_news_from_categories(cat_list, max_per_category=count // 2 + 1)

    # Remove duplicates based on title similarity
    unique_news = []
    seen_titles = set()
    for news in all_news:
        # Simple dedup by first 20 chars of title
        title_key = news.title[:20].lower() if news.title else ""
        if title_key and title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_news.append(news)

    # Limit to requested count
    selected_news = unique_news[:count]

    # Combine text for extraction
    combined_parts = []
    for news in selected_news:
        if news.title:
            combined_parts.append(clean_html_tags(news.title))
        if news.description:
            combined_parts.append(clean_html_tags(news.description))

    combined_text = " ".join(combined_parts)

    return NewsFetchResponse(
        total_news=len(selected_news),
        news_items=selected_news,
        combined_text=combined_text,
    )


@router.post("/auto-extract")
async def auto_extract_from_news(request: NewsAutoExtractRequest):
    """
    Automatically fetch news and extract numbers for lottery selection.

    This combines news fetching and number extraction into a single call.
    Perfect for the "auto-generate from news" feature.
    """
    game_type = request.game_type
    news_count = request.news_count
    categories = request.categories

    if game_type not in GAME_CONFIG:
        raise HTTPException(status_code=400, detail="Invalid game_type. Use 'lotto' or 'power'")

    # Default categories if not specified
    if not categories:
        categories = ["taiwan", "international", "finance"]

    # Fetch news
    all_news = await fetch_news_from_categories(categories, max_per_category=news_count // 2 + 1)

    # Remove duplicates
    unique_news = []
    seen_titles = set()
    for news in all_news:
        title_key = news.title[:20].lower() if news.title else ""
        if title_key and title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_news.append(news)

    selected_news = unique_news[:news_count]

    if not selected_news:
        raise HTTPException(status_code=503, detail="無法取得新聞資料，請稍後再試")

    # Combine text
    combined_parts = []
    for news in selected_news:
        if news.title:
            combined_parts.append(clean_html_tags(news.title))
        if news.description:
            combined_parts.append(clean_html_tags(news.description))

    combined_text = " ".join(combined_parts)

    # Extract numbers
    raw_extractions = extract_numbers_from_text(combined_text)

    # Build extracted numbers list
    extracted_numbers = []
    valid_numbers = []
    weights = {}

    for ext in raw_extractions:
        number = ext["number"]
        is_valid = validate_number_for_game(number, game_type)

        extracted_numbers.append(ExtractedNumber(
            number=number,
            original=ext["original"],
            context=ext["context"],
            source_type=ext["source_type"],
            is_valid=is_valid,
            weight=ext["weight"],
        ))

        if is_valid:
            valid_numbers.append(number)
            weights[number] = max(weights.get(number, 0), ext["weight"])

    # Transform invalid numbers
    transformed_numbers = []
    for ext in raw_extractions:
        if not validate_number_for_game(ext["number"], game_type):
            transforms = transform_number(ext["number"], game_type)
            for t in transforms:
                transformed_numbers.append(TransformedNumber(**t))
                if t["is_valid"]:
                    weights[t["transformed"]] = max(
                        weights.get(t["transformed"], 0),
                        ext["weight"] * 0.8
                    )

    # Generate suggested sets
    suggested_sets = generate_number_sets(
        valid_numbers=valid_numbers,
        transformed=transformed_numbers,
        weights=weights,
        game_type=game_type,
        num_sets=3,
        include_special=True
    )

    # Statistics
    statistics = {
        "total_extracted": len(extracted_numbers),
        "valid_count": len(valid_numbers),
        "unique_valid": len(set(valid_numbers)),
        "transformed_count": len(transformed_numbers),
        "source_types": dict(Counter(e.source_type for e in extracted_numbers)),
        "news_sources": dict(Counter(n.source for n in selected_news)),
    }

    return {
        "game_type": game_type,
        "news_count": len(selected_news),
        "news_items": [
            {
                "title": n.title,
                "source": n.source,
                "category": n.category,
            }
            for n in selected_news
        ],
        "extracted_numbers": extracted_numbers,
        "valid_numbers": sorted(set(valid_numbers)),
        "transformed_numbers": transformed_numbers,
        "suggested_sets": suggested_sets,
        "statistics": statistics,
        "combined_text_preview": combined_text[:500] + "..." if len(combined_text) > 500 else combined_text,
    }
