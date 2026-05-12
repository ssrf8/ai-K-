from datetime import datetime, timezone
from typing import Any

import httpx


BINANCE_SPOT_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_FUTURES_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"


def _iso_from_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()


def _to_float(value: Any) -> float:
    return float(value)


async def _fetch_klines(url: str, symbol: str, interval: str, limit: int, market_type: str) -> dict:
    params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(url, params=params)

        if response.status_code >= 400:
            return {
                "symbol": symbol.upper(),
                "interval": interval,
                "limit": limit,
                "market_type": market_type,
                "status": "error",
                "error": f"HTTP {response.status_code}: {response.text[:300]}",
                "candles": [],
            }

        raw_klines = response.json()
        candles = []
        for item in raw_klines:
            candles.append(
                {
                    "open_time": _iso_from_ms(int(item[0])),
                    "open": _to_float(item[1]),
                    "high": _to_float(item[2]),
                    "low": _to_float(item[3]),
                    "close": _to_float(item[4]),
                    "volume": _to_float(item[5]),
                    "close_time": _iso_from_ms(int(item[6])),
                }
            )

        if not candles:
            return {
                "symbol": symbol.upper(),
                "interval": interval,
                "limit": limit,
                "market_type": market_type,
                "status": "error",
                "error": "Binance returned no kline data.",
                "candles": [],
            }

        first_close = candles[0]["close"]
        last_close = candles[-1]["close"]
        change_pct = ((last_close - first_close) / first_close * 100) if first_close else 0.0

        return {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": limit,
            "market_type": market_type,
            "status": "ok",
            "summary": {
                "symbol": symbol.upper(),
                "interval": interval,
                "limit": limit,
                "market_type": market_type,
                "last_close": last_close,
                "change_pct_from_first_to_last": change_pct,
                "highest_high": max(candle["high"] for candle in candles),
                "lowest_low": min(candle["low"] for candle in candles),
                "latest_volume": candles[-1]["volume"],
                "status": "ok",
            },
            "candles": candles,
        }
    except Exception as exc:
        return {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": limit,
            "market_type": market_type,
            "status": "error",
            "error": str(exc),
            "candles": [],
        }


async def fetch_spot_klines(symbol: str, interval: str, limit: int = 80) -> dict:
    return await _fetch_klines(BINANCE_SPOT_KLINES_URL, symbol, interval, limit, "spot")


async def fetch_futures_klines(symbol: str, interval: str, limit: int = 80) -> dict:
    return await _fetch_klines(BINANCE_FUTURES_KLINES_URL, symbol, interval, limit, "futures")


async def fetch_klines_with_fallback(symbol: str, interval: str, market_type: str = "auto", limit: int = 80) -> dict:
    normalized_market = (market_type or "auto").lower()

    if normalized_market == "spot":
        return await fetch_spot_klines(symbol, interval, limit)

    if normalized_market == "futures":
        return await fetch_futures_klines(symbol, interval, limit)

    spot_result = await fetch_spot_klines(symbol, interval, limit)
    futures_result = await fetch_futures_klines(symbol, interval, limit)

    # 自动模式：两个都有时优先使用合约；只有一个可用就使用可用的那个。
    if futures_result.get("status") == "ok":
        futures_result["fallback_checked"] = ["spot", "futures"]
        futures_result["fallback_note"] = "auto_selected_futures"
        return futures_result

    if spot_result.get("status") == "ok":
        spot_result["fallback_checked"] = ["spot", "futures"]
        spot_result["fallback_note"] = "auto_selected_spot"
        return spot_result

    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": limit,
        "market_type": "auto",
        "status": "error",
        "error": f"Spot failed: {spot_result.get('error', 'unknown error')} | Futures failed: {futures_result.get('error', 'unknown error')}",
        "candles": [],
        "fallback_checked": ["spot", "futures"],
    }
