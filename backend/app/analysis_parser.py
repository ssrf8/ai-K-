import json
import re
from typing import Any


ANALYSIS_PATTERN = re.compile(r"<analysis_json>\s*(\{.*?\})\s*</analysis_json>", re.DOTALL)
THINK_PATTERN = re.compile(r"<think\b[^>]*>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_think_blocks(text: str) -> str:
    return THINK_PATTERN.sub("", text).strip()


def parse_analysis_response(text: str) -> tuple[str, dict[str, Any] | None]:
    text = strip_think_blocks(text)
    match = ANALYSIS_PATTERN.search(text)
    if not match:
        return text.strip(), None

    visible_reply = (text[: match.start()] + text[match.end() :]).strip()
    try:
        analysis_data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return visible_reply or text.strip(), None

    return visible_reply, analysis_data


def build_mock_analysis(market_results: list[dict], interval: str, symbols: list[str]) -> dict[str, Any] | None:
    ok_result = next((result for result in market_results if result.get("status") == "ok"), None)
    if not ok_result:
        return None

    candles = ok_result.get("candles", [])
    summary = ok_result.get("summary", {})
    if not candles:
        return None

    recent = candles[-20:]
    highs = [candle["high"] for candle in recent]
    lows = [candle["low"] for candle in recent]
    closes = [candle["close"] for candle in recent]
    last_close = closes[-1]
    highest_high = max(highs)
    lowest_low = min(lows)
    price_range = highest_high - lowest_low
    pad = price_range * 0.08 if price_range else last_close * 0.002

    resistance_low = max(last_close, highest_high - pad)
    resistance_high = highest_high
    support_low = lowest_low
    support_high = min(last_close, lowest_low + pad)

    change_pct = summary.get("change_pct_from_first_to_last", 0)
    if change_pct > 0.6:
        structure = "偏强震荡"
        bias = "中性偏强"
    elif change_pct < -0.6:
        structure = "偏弱震荡"
        bias = "中性偏弱"
    else:
        structure = "区间震荡"
        bias = "中性"

    symbol = ok_result.get("symbol") or (symbols[0] if symbols else "")
    return {
        "symbol": symbol,
        "interval": interval,
        "structure": structure,
        "bias": bias,
        "resistance_zones": [
            {
                "label": "上方阻力",
                "low": round(resistance_low, 8),
                "high": round(resistance_high, 8),
                "reason": "最近窗口内高点区域",
            }
        ],
        "support_zones": [
            {
                "label": "下方支撑",
                "low": round(support_low, 8),
                "high": round(support_high, 8),
                "reason": "最近窗口内低点区域",
            }
        ],
        "box": {
            "upper": round(highest_high, 8),
            "lower": round(lowest_low, 8),
        },
        "confirmation": "站稳上方阻力区后再看延续，没确认前别急。",
        "invalidation": "跌破下方支撑区，当前结构就要重新看。",
        "risk_note": "中间位置硬开容易被来回磨，先想好止损。",
    }
