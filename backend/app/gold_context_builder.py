import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.binance_client import fetch_futures_klines


GOLD_SYMBOL = "XAUUSDT"
GOLD_INTERVALS = ["15m", "1h", "4h", "1d"]
GOLD_CANDLES_PER_INTERVAL = 30
GOLD_ANALYSIS_CANDLES = 120
GOLD_CHART_CANDLES = 120
GOLD_FETCH_LIMIT = 220
GOLD_CHART_INTERVAL = "15m"
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_RELEASE_DATES_URL = "https://api.stlouisfed.org/fred/releases/dates"
BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
FED_RSS_URLS = [
    "https://www.federalreserve.gov/feeds/press_all.xml",
    "https://www.federalreserve.gov/feeds/speeches.xml",
]

FRED_SERIES = {
    "DGS10": "10年期美债收益率",
    "DGS2": "2年期美债收益率",
    "DFII10": "10年期实际收益率",
    "T10YIE": "10年通胀预期",
    "T10Y2Y": "10年-2年利差",
    "DTWEXBGS": "广义美元指数",
    "DFF": "有效联邦基金利率",
    "DFEDTARU": "联邦基金目标上限",
    "DFEDTARL": "联邦基金目标下限",
    "PAYEMS": "非农就业人数",
    "UNRATE": "失业率",
    "CPIAUCSL": "CPI",
    "CPILFESL": "核心CPI",
    "PCEPI": "PCE物价指数",
    "PCEPILFE": "核心PCE",
}

BLS_SERIES = {
    "CES0000000001": "nfp",
    "LNS14000000": "unemployment_rate",
    "CES0500000003": "average_hourly_earnings",
    "CES0500000002": "average_weekly_hours",
    "CUSR0000SA0": "cpi",
    "CUSR0000SA0L1E": "core_cpi",
}

EVENT_KEYWORDS = [
    "Non Farm",
    "Unemployment Rate",
    "Average Hourly Earnings",
    "CPI",
    "Core CPI",
    "Consumer Price Index",
    "PCE",
    "Personal Income",
    "Personal Consumption",
    "Core PCE",
    "Fed Interest Rate",
    "FOMC",
    "Fed Chair",
    "Initial Jobless Claims",
    "ISM Manufacturing",
    "ISM Services",
    "Retail Sales",
    "PPI",
    "Producer Price Index",
    "GDP",
    "Gross Domestic Product",
    "JOLTS",
    "Employment Situation",
    "Job Openings",
    "FOMC Press Release",
    "10-Year Note",
    "30-Year Bond",
]

FED_KEYWORDS = [
    "monetary policy",
    "fomc",
    "powell",
    "minutes",
    "statement",
    "interest rate",
]
FED_RECENT_ALERT_DAYS = 7

_CACHE: dict[str, dict[str, Any]] = {}
CACHE_TTL_SECONDS = {
    "fred_summary": 30 * 60,
    "bls_summary": 6 * 60 * 60,
    "economic_calendar": 6 * 60 * 60,
    "fed_news": 10 * 60,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _cache_get(key: str) -> Any | None:
    item = _CACHE.get(key)
    if not item:
        return None
    ttl_seconds = CACHE_TTL_SECONDS[key]
    age_seconds = time.time() - item["stored_at"]
    if age_seconds > ttl_seconds:
        return None
    value = item["value"]
    if isinstance(value, dict):
        return {
            **value,
            "cache": {
                **item["cache"],
                "cache_status": "hit",
                "age_seconds": round(age_seconds, 2),
            },
        }
    return value


def _cache_set(key: str, value: Any) -> Any:
    ttl_seconds = CACHE_TTL_SECONDS[key]
    stored_at_ts = time.time()
    cached_at = datetime.fromtimestamp(stored_at_ts, tz=timezone.utc)
    expires_at = datetime.fromtimestamp(stored_at_ts + ttl_seconds, tz=timezone.utc)
    cache_meta = {
        "cache_key": key,
        "cache_status": "refreshed",
        "cached_at": cached_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "ttl_seconds": ttl_seconds,
        "age_seconds": 0,
    }
    stored_value = {**value, "cache": cache_meta} if isinstance(value, dict) else value
    _CACHE[key] = {"stored_at": stored_at_ts, "value": stored_value, "cache": cache_meta}
    return stored_value


def _iso_from_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()


def _compact_candle(candle: dict) -> dict[str, float | str]:
    return {
        "time": candle["open_time"],
        "open": candle["open"],
        "high": candle["high"],
        "low": candle["low"],
        "close": candle["close"],
        "volume": candle["volume"],
    }


def _round_price(value: float) -> float:
    return round(value, 2)


def _build_fibonacci(candles: list[dict]) -> dict[str, Any] | None:
    if not candles:
        return None

    high_candle = max(candles, key=lambda candle: candle["high"])
    low_candle = min(candles, key=lambda candle: candle["low"])
    swing_high = float(high_candle["high"])
    swing_low = float(low_candle["low"])
    price_range = swing_high - swing_low
    if price_range <= 0:
        return {
            "status": "flat_range",
            "swing_high": {"price": _round_price(swing_high), "time": high_candle["open_time"]},
            "swing_low": {"price": _round_price(swing_low), "time": low_candle["open_time"]},
            "levels": {},
        }

    direction = "up_swing" if candles[-1]["close"] >= candles[0]["close"] else "down_swing"
    retracement_ratios = [0.236, 0.382, 0.5, 0.618, 0.786, 0.886]
    extension_ratios = [1.272, 1.618]

    if direction == "up_swing":
        retracements = {
            str(ratio): _round_price(swing_high - price_range * ratio)
            for ratio in retracement_ratios
        }
        extensions = {
            str(ratio): _round_price(swing_low + price_range * ratio)
            for ratio in extension_ratios
        }
    else:
        retracements = {
            str(ratio): _round_price(swing_low + price_range * ratio)
            for ratio in retracement_ratios
        }
        extensions = {
            str(ratio): _round_price(swing_high - price_range * ratio)
            for ratio in extension_ratios
        }

    return {
        "status": "ok",
        "basis": f"latest {len(candles)} closed candles in this interval",
        "direction": direction,
        "swing_high": {"price": _round_price(swing_high), "time": high_candle["open_time"]},
        "swing_low": {"price": _round_price(swing_low), "time": low_candle["open_time"]},
        "range": _round_price(price_range),
        "levels": {
            "retracements": retracements,
            "extensions": extensions,
        },
    }


def _ema(values: list[float], period: int) -> list[float | None]:
    if len(values) < period:
        return [None for _ in values]

    multiplier = 2 / (period + 1)
    result: list[float | None] = [None for _ in values]
    current = sum(values[:period]) / period
    result[period - 1] = current
    for index in range(period, len(values)):
        current = (values[index] - current) * multiplier + current
        result[index] = current
    return result


def _last_number(values: list[float | None]) -> float | None:
    for value in reversed(values):
        if value is not None:
            return value
    return None


def _build_moving_averages(candles: list[dict]) -> dict[str, Any]:
    closes = [float(candle["close"]) for candle in candles]
    if not closes:
        return {"status": "no_data"}

    ema21_series = _ema(closes, 21)
    ema55_series = _ema(closes, 55)
    ema144_series = _ema(closes, 144)
    ema169_series = _ema(closes, 169)
    last_close = closes[-1]
    ema21 = _last_number(ema21_series)
    ema55 = _last_number(ema55_series)
    ema144 = _last_number(ema144_series)
    ema169 = _last_number(ema169_series)

    if ema21 is not None and ema55 is not None:
        if last_close > ema21 > ema55:
            trend = "bullish_alignment"
        elif last_close < ema21 < ema55:
            trend = "bearish_alignment"
        else:
            trend = "mixed"
    else:
        trend = "insufficient_data"

    vegas_position = "insufficient_data"
    tunnel_width = None
    if ema144 is not None and ema169 is not None:
        upper = max(ema144, ema169)
        lower = min(ema144, ema169)
        tunnel_width = upper - lower
        if last_close > upper:
            vegas_position = "above_tunnel"
        elif last_close < lower:
            vegas_position = "below_tunnel"
        else:
            vegas_position = "inside_tunnel"

    return {
        "status": "ok",
        "basis": f"computed from latest {len(candles)} closed candles",
        "ema21": _round_price(ema21) if ema21 is not None else None,
        "ema55": _round_price(ema55) if ema55 is not None else None,
        "trend": trend,
        "vegas": {
            "ema144": _round_price(ema144) if ema144 is not None else None,
            "ema169": _round_price(ema169) if ema169 is not None else None,
            "position": vegas_position,
            "tunnel_width": _round_price(tunnel_width) if tunnel_width is not None else None,
        },
    }


def _build_macd(candles: list[dict]) -> dict[str, Any]:
    closes = [float(candle["close"]) for candle in candles]
    if len(closes) < 35:
        return {"status": "insufficient_data", "required_closed_candles": 35, "available": len(closes)}

    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    dif_values: list[float | None] = []
    for fast, slow in zip(ema12, ema26):
        dif_values.append(fast - slow if fast is not None and slow is not None else None)

    valid_dif = [value for value in dif_values if value is not None]
    dea_valid = _ema(valid_dif, 9)
    dea_values: list[float | None] = []
    dea_index = 0
    for dif in dif_values:
        if dif is None:
            dea_values.append(None)
        else:
            dea_values.append(dea_valid[dea_index])
            dea_index += 1

    hist_values = [
        (dif - dea) if dif is not None and dea is not None else None
        for dif, dea in zip(dif_values, dea_values)
    ]
    dif = _last_number(dif_values)
    dea = _last_number(dea_values)
    hist = _last_number(hist_values)
    previous_hist = next((value for value in reversed(hist_values[:-1]) if value is not None), None)
    previous_dif = next((value for value in reversed(dif_values[:-1]) if value is not None), None)
    previous_dea = next((value for value in reversed(dea_values[:-1]) if value is not None), None)

    if hist is None or previous_hist is None:
        histogram_direction = "unknown"
    elif hist > previous_hist:
        histogram_direction = "expanding_up"
    elif hist < previous_hist:
        histogram_direction = "expanding_down"
    else:
        histogram_direction = "flat"

    cross = "none"
    if previous_dif is not None and previous_dea is not None and dif is not None and dea is not None:
        if previous_dif <= previous_dea and dif > dea:
            cross = "bullish_cross"
        elif previous_dif >= previous_dea and dif < dea:
            cross = "bearish_cross"

    return {
        "status": "ok",
        "basis": "MACD(12,26,9) from closed candles",
        "dif": round(dif, 4) if dif is not None else None,
        "dea": round(dea, 4) if dea is not None else None,
        "histogram": round(hist, 4) if hist is not None else None,
        "previous_histogram": round(previous_hist, 4) if previous_hist is not None else None,
        "histogram_direction": histogram_direction,
        "cross": cross,
        "zero_position": "above_zero" if dif is not None and dif > 0 else "below_zero" if dif is not None and dif < 0 else "at_zero",
    }


def _build_box_structure(candles: list[dict]) -> dict[str, Any] | None:
    if not candles:
        return None

    highs = [float(candle["high"]) for candle in candles]
    lows = [float(candle["low"]) for candle in candles]
    closes = [float(candle["close"]) for candle in candles]
    upper = max(highs)
    lower = min(lows)
    price_range = upper - lower
    last_close = closes[-1]
    first_close = closes[0]
    position_pct = ((last_close - lower) / price_range * 100) if price_range else 50
    range_pct = (price_range / first_close * 100) if first_close else 0

    recent_high = max(highs[-10:]) if len(highs) >= 10 else upper
    previous_high = max(highs[:10]) if len(highs) >= 20 else upper
    recent_low = min(lows[-10:]) if len(lows) >= 10 else lower
    previous_low = min(lows[:10]) if len(lows) >= 20 else lower

    if recent_high > previous_high and recent_low > previous_low:
        structure = "向上堆箱"
    elif recent_high < previous_high and recent_low < previous_low:
        structure = "向下放箱"
    elif range_pct <= 1.2:
        structure = "窄幅横盘"
    else:
        structure = "区间震荡"

    if position_pct >= 75:
        position = "near_box_high"
    elif position_pct <= 25:
        position = "near_box_low"
    else:
        position = "box_middle"

    return {
        "status": "ok",
        "basis": f"latest {len(candles)} closed candles",
        "structure": structure,
        "upper": _round_price(upper),
        "lower": _round_price(lower),
        "middle": _round_price((upper + lower) / 2),
        "range": _round_price(price_range),
        "range_pct": round(range_pct, 2),
        "last_close_position_pct": round(position_pct, 2),
        "last_close_position": position,
        "recent_high_vs_previous": "higher" if recent_high > previous_high else "lower" if recent_high < previous_high else "flat",
        "recent_low_vs_previous": "higher" if recent_low > previous_low else "lower" if recent_low < previous_low else "flat",
    }


def _body_size(candle: dict) -> float:
    return abs(float(candle["close"]) - float(candle["open"]))


def _candle_range(candle: dict) -> float:
    return max(0.0, float(candle["high"]) - float(candle["low"]))


def _build_candle_patterns(candles: list[dict]) -> dict[str, Any]:
    if not candles:
        return {"status": "no_data", "labels": []}

    labels = []
    last = candles[-1]
    last_open = float(last["open"])
    last_close = float(last["close"])
    last_high = float(last["high"])
    last_low = float(last["low"])
    last_range = _candle_range(last)
    body = _body_size(last)
    upper_shadow = last_high - max(last_open, last_close)
    lower_shadow = min(last_open, last_close) - last_low
    body_ratio = body / last_range if last_range else 0

    if last_range and upper_shadow / last_range >= 0.45 and upper_shadow >= body * 1.5:
        labels.append("长上影")
    if last_range and lower_shadow / last_range >= 0.45 and lower_shadow >= body * 1.5:
        labels.append("长下影")
    if body_ratio >= 0.65 and last_close > last_open:
        labels.append("大阳线")
    if body_ratio >= 0.65 and last_close < last_open:
        labels.append("大阴线")

    if len(candles) >= 2:
        prev = candles[-2]
        prev_open = float(prev["open"])
        prev_close = float(prev["close"])
        prev_body_high = max(prev_open, prev_close)
        prev_body_low = min(prev_open, prev_close)
        last_body_high = max(last_open, last_close)
        last_body_low = min(last_open, last_close)
        if prev_close < prev_open and last_close > last_open and last_body_high >= prev_body_high and last_body_low <= prev_body_low:
            labels.append("多头吞没")
        if prev_close > prev_open and last_close < last_open and last_body_high >= prev_body_high and last_body_low <= prev_body_low:
            labels.append("空头吞没")
        if last_high <= float(prev["high"]) and last_low >= float(prev["low"]):
            labels.append("孕线")

    if len(candles) >= 3:
        mother = candles[-3]
        if (
            float(candles[-2]["high"]) <= float(mother["high"])
            and float(candles[-2]["low"]) >= float(mother["low"])
            and last_high <= float(mother["high"])
            and last_low >= float(mother["low"])
        ):
            labels.append("双孕线")

        previous_range = candles[-11:-1] if len(candles) >= 11 else candles[:-1]
        if previous_range:
            previous_high = max(float(candle["high"]) for candle in previous_range)
            previous_low = min(float(candle["low"]) for candle in previous_range)
            if last_high > previous_high and last_close < previous_high:
                labels.append("向上假突破")
            if last_low < previous_low and last_close > previous_low:
                labels.append("向下假跌破")

    return {
        "status": "ok",
        "basis": "latest closed candle plus recent context",
        "labels": labels or ["无明显形态"],
        "last_candle": {
            "time": last["open_time"],
            "body_ratio": round(body_ratio, 3),
            "upper_shadow_ratio": round(upper_shadow / last_range, 3) if last_range else None,
            "lower_shadow_ratio": round(lower_shadow / last_range, 3) if last_range else None,
        },
    }


def _seconds_elapsed(open_time: str) -> int | None:
    try:
        opened = datetime.fromisoformat(open_time.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, int((datetime.now(timezone.utc) - opened).total_seconds()))


def _closed_and_forming(candles: list[dict]) -> tuple[list[dict], dict[str, Any] | None]:
    if not candles:
        return [], None

    latest = candles[-1]
    now = datetime.now(timezone.utc)
    try:
        close_time = datetime.fromisoformat(latest["close_time"].replace("Z", "+00:00"))
    except ValueError:
        close_time = now

    if close_time > now:
        closed = candles[:-1]
        forming = latest
    else:
        closed = candles
        forming = latest

    current = {
        "current_price": forming["close"],
        "open_time": forming["open_time"],
        "elapsed_seconds": _seconds_elapsed(forming["open_time"]),
    }
    return closed, current


async def fetch_gold_klines() -> tuple[dict[str, Any], list[dict], list[dict]]:
    kline_by_interval = {}
    chart_data = []
    market_results = []

    for interval in GOLD_INTERVALS:
        result = await fetch_futures_klines(GOLD_SYMBOL, interval, GOLD_FETCH_LIMIT)
        market_results.append(result)
        if result.get("status") != "ok":
            kline_by_interval[interval] = {
                "status": "error",
                "error": result.get("error", "unknown error"),
                "candles": [],
                "current_forming_period": None,
            }
            continue

        all_closed, current = _closed_and_forming(result.get("candles", []))
        closed = all_closed[-GOLD_CANDLES_PER_INTERVAL:]
        analysis_closed = all_closed[-GOLD_ANALYSIS_CANDLES:]
        kline_by_interval[interval] = {
            "status": "ok",
            "candles": [_compact_candle(candle) for candle in closed],
            "analysis_window": {
                "closed_candles_used_for_indicators": len(all_closed),
                "closed_candles_used_for_structure": len(analysis_closed),
                "raw_candles_sent_to_llm": len(closed),
                "note": "指标和结构用更长历史计算；发送给 LLM 的原始 K 线仍只保留最近 30 根。",
            },
            "fibonacci": _build_fibonacci(analysis_closed),
            "moving_averages": _build_moving_averages(all_closed),
            "macd": _build_macd(all_closed),
            "box_structure": _build_box_structure(analysis_closed),
            "candle_patterns": _build_candle_patterns(analysis_closed),
            "current_forming_period": {
                "included": True,
                "format": "current price / elapsed only",
                "interval": interval,
                **(current or {}),
            },
        }

        if interval == GOLD_CHART_INTERVAL:
            chart_closed = all_closed[-GOLD_CHART_CANDLES:]
            chart_result = {
                **result,
                "candles": chart_closed,
                "summary": {
                    **result.get("summary", {}),
                    "display_limit": len(chart_closed),
                    "llm_injected_limit": len(closed),
                    "last_close": chart_closed[-1]["close"] if chart_closed else result.get("summary", {}).get("last_close"),
                },
            }
            chart_data.append(
                {
                    "symbol": GOLD_SYMBOL,
                    "interval": interval,
                    "market_type": "futures",
                    "summary": chart_result.get("summary", {}),
                    "candles": chart_result.get("candles", []),
                }
            )

    ok_candles = sum(len(item.get("candles", [])) for item in kline_by_interval.values())
    current_price = next(
        (
            item.get("current_forming_period", {}).get("current_price")
            for item in kline_by_interval.values()
            if item.get("current_forming_period", {}).get("current_price") is not None
        ),
        None,
    )
    payload = {
        "symbol": GOLD_SYMBOL,
        "source": "Binance USD-M Futures",
        "intervals": GOLD_INTERVALS,
        "candles_per_interval": GOLD_CANDLES_PER_INTERVAL,
        "fields": ["time", "open", "high", "low", "close", "volume"],
        "symbols_per_request": 1,
        "total_candles_per_symbol": ok_candles,
        "expected_total_candles_per_symbol": len(GOLD_INTERVALS) * GOLD_CANDLES_PER_INTERVAL,
        "current_price": current_price,
        "current_forming_period": {
            "included": True,
            "format": "current price / elapsed only",
            "by_interval": {
                interval: item.get("current_forming_period")
                for interval, item in kline_by_interval.items()
                if item.get("current_forming_period")
            },
        },
        "by_interval": kline_by_interval,
    }
    return payload, market_results, chart_data


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == ".":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _valid_observations(observations: list[dict]) -> list[dict]:
    valid = []
    for observation in observations:
        number = _to_float(observation.get("value"))
        if number is None:
            continue
        valid.append({"date": observation.get("date"), "value": number, "raw_value": observation.get("value")})
    return valid


def _fred_series_from_observations(series_id: str, label: str, observations: list[dict]) -> tuple[dict[str, Any], str | None]:
    latest_raw = observations[0] if observations else None
    valid = _valid_observations(observations)
    if not valid:
        note = f"{series_id} 没有可用的 FRED 有效数据。"
        return (
            {
                "label": label,
                "status": "no_valid_data",
                "latest_raw": latest_raw,
                "freshness": "unavailable",
                "missing_current_data": True,
                "note": note,
            },
            note,
        )

    latest_valid = valid[0]
    previous_valid = valid[1] if len(valid) > 1 else None
    latest_raw_value = _to_float(latest_raw.get("value") if latest_raw else None)
    is_stale = latest_raw_value is None or latest_raw.get("date") != latest_valid.get("date")
    note = None
    if is_stale:
        note = f"{series_id} FRED 当前日期没有有效数据，已使用上一条有效数据。"

    return (
        {
            "label": label,
            "status": "ok",
            "date": latest_valid.get("date"),
            "value": latest_valid.get("value"),
            "previous_date": previous_valid.get("date") if previous_valid else None,
            "previous_value": previous_valid.get("value") if previous_valid else None,
            "direction": _direction(
                latest_valid.get("value"),
                previous_valid.get("value") if previous_valid else None,
            ),
            "freshness": "stale" if is_stale else "current",
            "missing_current_data": is_stale,
            "latest_raw": latest_raw,
            "note": note,
        },
        note,
    )


def _direction(current: float | None, previous: float | None) -> str:
    if current is None or previous is None:
        return "unknown"
    if current > previous:
        return "up"
    if current < previous:
        return "down"
    return "flat"


async def fetch_fred_summary() -> dict[str, Any]:
    cached = _cache_get("fred_summary")
    if cached is not None:
        return cached

    api_key = os.getenv("FRED_API_KEY", "").strip()
    if not api_key:
        return _cache_set(
            "fred_summary",
            {
                "status": "missing_config",
                "series": {},
                "notes": ["FRED_API_KEY 未配置，宏观评分不包含 FRED 数据。"],
            },
        )

    series_payload = {}
    notes = []
    async with httpx.AsyncClient(timeout=20) as client:
        for series_id, label in FRED_SERIES.items():
            try:
                response = await client.get(
                    FRED_BASE_URL,
                    params={
                        "series_id": series_id,
                        "api_key": api_key,
                        "file_type": "json",
                        "sort_order": "desc",
                        "limit": 10,
                    },
                )
                if response.status_code >= 400:
                    series_payload[series_id] = {
                        "label": label,
                        "status": "error",
                        "error": f"HTTP {response.status_code}: {response.text[:240]}",
                    }
                    continue

                series_payload[series_id], note = _fred_series_from_observations(
                    series_id,
                    label,
                    response.json().get("observations", []),
                )
                if note:
                    notes.append(note)
            except Exception as exc:
                series_payload[series_id] = {"label": label, "status": "error", "error": str(exc)}

    status = "ok_with_stale_values" if notes else "ok"
    return _cache_set("fred_summary", {"status": status, "series": series_payload, "notes": notes})


def _score_fred(series: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    scoring_rules = {
        "DFII10": {"up": (-2, "实际收益率上升压制黄金"), "down": (2, "实际收益率下降利多黄金")},
        "DGS10": {"up": (-1, "10年美债收益率上升压制黄金"), "down": (1, "10年美债收益率下降利多黄金")},
        "DTWEXBGS": {"up": (-1, "美元指数上升压制黄金"), "down": (1, "美元指数下降利多黄金")},
        "T10YIE": {"up": (1, "通胀预期上升支撑黄金"), "down": (-1, "通胀预期下降削弱黄金支撑")},
    }
    for series_id, rules in scoring_rules.items():
        direction = series.get(series_id, {}).get("direction")
        if direction in rules:
            delta, reason = rules[direction]
            score += delta
            reasons.append(reason)
    return score, reasons


def _source_status(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": payload.get("status"),
        "cache": payload.get("cache"),
    }


async def fetch_bls_summary() -> dict[str, Any]:
    cached = _cache_get("bls_summary")
    if cached is not None:
        return cached

    current_year = str(datetime.now(timezone.utc).year)
    start_year = str(int(current_year) - 1)
    payload = {"seriesid": list(BLS_SERIES.keys()), "startyear": start_year, "endyear": current_year}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(BLS_URL, json=payload)
        if response.status_code >= 400:
            return _cache_set("bls_summary", {"status": "error", "error": f"HTTP {response.status_code}: {response.text[:240]}"})
        data = response.json()
        series = {}
        for item in data.get("Results", {}).get("series", []):
            series_id = item.get("seriesID")
            name = BLS_SERIES.get(series_id, series_id)
            latest = (item.get("data") or [{}])[0]
            series[name] = {
                "series_id": series_id,
                "period": latest.get("periodName"),
                "year": latest.get("year"),
                "value": _to_float(latest.get("value")),
                "raw_value": latest.get("value"),
            }
        return _cache_set("bls_summary", {"status": "ok", "series": series})
    except Exception as exc:
        return _cache_set(
            "bls_summary",
            {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc!r}",
                "note": "BLS API 当前网络不可达或被出口代理/Akamai 拒绝；黄金分析会继续使用 FRED 官方序列作为宏观补充。",
            },
        )


def _event_matches(event_name: str) -> bool:
    return any(keyword.lower() in event_name.lower() for keyword in EVENT_KEYWORDS)


def _event_importance(event_name: str) -> str:
    lowered = event_name.lower()
    high_keywords = [
        "employment situation",
        "non farm",
        "consumer price index",
        "cpi",
        "personal income",
        "personal consumption",
        "pce",
        "producer price index",
        "ppi",
        "gross domestic product",
        "gdp",
        "fomc",
        "interest rate",
        "fed chair",
    ]
    return "high" if any(keyword in lowered for keyword in high_keywords) else "medium"


def _event_timing_reliability(event_name: str) -> dict[str, Any]:
    lowered = event_name.lower()
    if "fomc" in lowered:
        return {
            "date_confidence": "low",
            "affects_today": False,
            "timing_note": (
                "FRED Release Calendar 对 FOMC 只适合作为低可信风险提示，"
                "可能返回发布序列或窗口日期，不等同于真实会议/发布会时间。"
            ),
        }
    return {
        "date_confidence": "medium",
        "affects_today": None,
        "timing_note": "FRED Release Calendar 只提供日期，不提供具体发布时间。",
    }


def _release_date_value(item: dict) -> str | None:
    value = item.get("date") or item.get("release_date")
    if isinstance(value, str):
        return value[:10]
    return None


async def fetch_economic_calendar() -> dict[str, Any]:
    cached = _cache_get("economic_calendar")
    if cached is not None:
        return cached

    api_key = os.getenv("FRED_API_KEY", "").strip()
    if not api_key:
        return _cache_set(
            "economic_calendar",
            {
                "status": "missing_config",
                "source": "FRED Release Calendar",
                "has_high_impact_event_today": False,
                "next_event": None,
                "events": [],
                "trade_filter": "FRED_API_KEY 未配置，无法获取 FRED 发布日历。",
                "notes": ["FRED Release Calendar 需要 FRED_API_KEY。"],
            },
        )

    today = datetime.now(timezone.utc).date()
    end_date = today + timedelta(days=7)

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                FRED_RELEASE_DATES_URL,
                params={
                    "api_key": api_key,
                    "file_type": "json",
                    "realtime_start": today.isoformat(),
                    "realtime_end": end_date.isoformat(),
                    "sort_order": "asc",
                    "limit": 1000,
                    "include_release_dates_with_no_data": "true",
                },
            )
        if response.status_code >= 400:
            return _cache_set(
                "economic_calendar",
                {
                    "status": "error",
                    "source": "FRED Release Calendar",
                    "error": f"HTTP {response.status_code}: {response.text[:240]}",
                    "events": [],
                    "trade_filter": "FRED 发布日历获取失败，本轮不使用经济日历过滤。",
                },
            )
        payload = response.json()
        items = payload.get("release_dates", [])
        if not isinstance(items, list):
            return _cache_set(
                "economic_calendar",
                {
                    "status": "error",
                    "source": "FRED Release Calendar",
                    "error": "Unexpected FRED release calendar response.",
                    "events": [],
                    "trade_filter": "FRED 发布日历格式异常，本轮不使用经济日历过滤。",
                },
            )

        events = []
        for item in items:
            event_name = str(item.get("release_name") or item.get("name") or "")
            if not _event_matches(event_name):
                continue
            release_date = _release_date_value(item)
            timing = _event_timing_reliability(event_name)
            affects_today = (
                bool(timing["affects_today"])
                if timing["affects_today"] is not None
                else release_date == today.isoformat()
            )
            events.append(
                {
                    "event": event_name,
                    "date": release_date,
                    "actual": None,
                    "forecast": None,
                    "previous": None,
                    "importance": _event_importance(event_name),
                    "date_confidence": timing["date_confidence"],
                    "affects_today": affects_today,
                    "release_id": item.get("release_id"),
                    "source": "FRED Release Calendar",
                    "note": timing["timing_note"],
                }
            )

        actionable_events = [
            event for event in events
            if event.get("affects_today") is True or event.get("date_confidence") != "low"
        ]
        unconfirmed_events = [
            event for event in events
            if event.get("date_confidence") == "low"
        ]
        next_event = actionable_events[0] if actionable_events else None
        has_high_today = any(
            event.get("importance") == "high" and event.get("affects_today") is True
            for event in events
        )
        return _cache_set(
            "economic_calendar",
            {
                "status": "ok",
                "source": "FRED Release Calendar",
                "has_high_impact_event_today": has_high_today,
                "next_event": next_event,
                "events": actionable_events[:10],
                "unconfirmed_events": unconfirmed_events[:10],
                "trade_filter": (
                    "今日有高影响事件风险；FRED 只提供日期不提供具体发布时间。该日历只作为风险因子，不单独否决结构方案；请提高确认要求，并同时给出主方案与备选方案概率。"
                    if has_high_today
                    else "未来7天有高影响事件日历或低可信日期风险；FRED 日期不等同于精确发布时间。该日历只作为风险因子，不单独否决结构方案。"
                    if next_event or unconfirmed_events
                    else "暂无筛选到的美国高影响事件。"
                ),
                "notes": [
                    "FRED Release Calendar 不提供 forecast/actual，预期值和公布值仍需其他来源补充。",
                    "FOMC 类事件的 FRED 日期可能是发布序列或窗口日期，未用来直接触发今日高影响事件。",
                ],
            },
        )
    except Exception as exc:
        return _cache_set(
            "economic_calendar",
            {
                "status": "error",
                "source": "FRED Release Calendar",
                "error": str(exc),
                "events": [],
                "trade_filter": "FRED 发布日历获取失败，本轮不使用经济日历过滤。",
            },
        )


def _parse_rss_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except Exception:
        return value


def _parse_rss_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc)
    except Exception:
        return None


def _days_old(published_at: str | None) -> float | None:
    parsed = _parse_rss_datetime(published_at)
    if parsed is None:
        return None
    return round((datetime.now(timezone.utc) - parsed).total_seconds() / 86400, 2)


def _fed_impact(title: str) -> str:
    lowered = title.lower()
    high_keywords = ["fomc", "minutes", "statement", "interest rate", "discount rate", "monetary policy"]
    if any(keyword in lowered for keyword in high_keywords):
        return "high"
    if "powell" in lowered:
        return "medium"
    return "low"


async def fetch_fed_news() -> dict[str, Any]:
    cached = _cache_get("fed_news")
    if cached is not None:
        return cached

    alerts = []
    feed_items = []
    errors = []
    async with httpx.AsyncClient(timeout=20) as client:
        for url in FED_RSS_URLS:
            try:
                response = await client.get(url)
                if response.status_code >= 400:
                    errors.append(f"{url}: HTTP {response.status_code}")
                    continue
                root = ET.fromstring(response.text)
                for item in root.findall(".//item"):
                    title = (item.findtext("title") or "").strip()
                    published_raw = item.findtext("pubDate")
                    published_at = _parse_rss_date(published_raw)
                    feed_items.append(
                        {
                            "source": "Federal Reserve",
                            "title": title,
                            "published_at": published_at,
                            "link": item.findtext("link"),
                        }
                    )
                    lowered = title.lower()
                    if not any(keyword in lowered for keyword in FED_KEYWORDS):
                        continue
                    impact = _fed_impact(title)
                    age_days = _days_old(published_raw)
                    alerts.append(
                        {
                            "source": "Federal Reserve",
                            "title": title,
                            "published_at": published_at,
                            "link": item.findtext("link"),
                            "impact": impact,
                            "days_old": age_days,
                            "is_recent": age_days is None or age_days <= FED_RECENT_ALERT_DAYS,
                            "need_wait_for_kline_confirmation": impact in {"high", "medium"},
                        }
                    )
            except Exception as exc:
                errors.append(f"{url}: {exc}")

    def sort_key(item: dict) -> str:
        return item.get("published_at") or ""

    feed_items.sort(key=sort_key, reverse=True)
    alerts.sort(key=sort_key, reverse=True)
    recent_alerts = [item for item in alerts if item.get("is_recent")]

    return _cache_set(
        "fed_news",
        {
            "status": "ok" if alerts or not errors else "error",
            "fed_alert": bool(recent_alerts),
            "latest_alert": recent_alerts[0] if recent_alerts else None,
            "latest_relevant_alert": alerts[0] if alerts else None,
            "latest_feed_item": feed_items[0] if feed_items else None,
            "recent_window_days": FED_RECENT_ALERT_DAYS,
            "alerts": alerts[:5],
            "recent_alerts": recent_alerts[:5],
            "errors": errors,
        },
    )


async def build_gold_context() -> tuple[dict[str, Any], list[dict], list[dict]]:
    kline_data, market_results, chart_data = await fetch_gold_klines()
    fred = await fetch_fred_summary()
    bls = await fetch_bls_summary()
    calendar = await fetch_economic_calendar()
    fed_news = await fetch_fed_news()

    fred_series = fred.get("series", {})
    score, reasons = _score_fred(fred_series)
    if score >= 2:
        macro_bias = "bullish"
    elif score <= -2:
        macro_bias = "bearish"
    else:
        macro_bias = "neutral" if fred.get("status") != "missing_config" else "unavailable"

    macro_summary = {
        "us10y": fred_series.get("DGS10", {}).get("value"),
        "us10y_change": fred_series.get("DGS10", {}).get("direction", "unknown"),
        "us2y": fred_series.get("DGS2", {}).get("value"),
        "us2y_change": fred_series.get("DGS2", {}).get("direction", "unknown"),
        "real_yield_10y": fred_series.get("DFII10", {}).get("value"),
        "real_yield_change": fred_series.get("DFII10", {}).get("direction", "unknown"),
        "inflation_expectation_10y": fred_series.get("T10YIE", {}).get("value"),
        "dollar_index": fred_series.get("DTWEXBGS", {}).get("value"),
        "dollar_change": fred_series.get("DTWEXBGS", {}).get("direction", "unknown"),
        "macro_score": score,
        "macro_bias_for_gold": macro_bias,
        "reason": "；".join(reasons) if reasons else "FRED 核心指标不足，宏观偏向暂不明确。",
        "data_quality": {
            "fred": {
                "status": fred.get("status"),
                "notes": fred.get("notes", []),
            }
        },
    }

    gold_context = {
        "symbol": GOLD_SYMBOL,
        "market": "Binance USD-M Futures",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kline_summary": kline_data,
        "macro_summary": macro_summary,
        "macro_data_status": {
            "fred": _source_status(fred),
            "bls": _source_status(bls),
            "fred_release_calendar": _source_status(calendar),
            "fed_rss": _source_status(fed_news),
        },
        "fred_series": fred_series,
        "official_actual": bls,
        "economic_calendar": calendar,
        "official_news": {
            "fed_alert": fed_news.get("fed_alert", False),
            "bls_alert": False,
            "bea_alert": False,
            "latest_alert": fed_news.get("latest_alert"),
            "fed_rss": fed_news,
        },
        "preference": {"style": "short_term", "target_move_usd": 15},
    }
    return gold_context, market_results, chart_data


def gold_context_to_prompt_json(context: dict[str, Any]) -> str:
    return json.dumps(context, ensure_ascii=False, separators=(",", ":"))
