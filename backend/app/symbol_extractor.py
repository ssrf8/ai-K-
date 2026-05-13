import re


DEFAULT_INTERVAL = "15m"
MAX_SYMBOLS = 3
DEFAULT_QUOTE = "USDT"

BASE_TO_SYMBOL = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "BNB": "BNBUSDT",
    "XRP": "XRPUSDT",
    "DOGE": "DOGEUSDT",
    "ADA": "ADAUSDT",
    "AVAX": "AVAXUSDT",
    "LINK": "LINKUSDT",
    "TON": "TONUSDT",
}

CHINESE_SYMBOLS = {
    "比特币": "BTCUSDT",
    "以太坊": "ETHUSDT",
    "狗狗币": "DOGEUSDT",
}

SUPPORTED_INTERVALS = {
    "1m",
    "3m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "3d",
    "1w",
    "1M",
}

CHINESE_INTERVALS = {
    "1分钟": "1m",
    "一分钟": "1m",
    "5分钟": "5m",
    "五分钟": "5m",
    "15分钟": "15m",
    "十五分钟": "15m",
    "30分钟": "30m",
    "1小时": "1h",
    "1时": "1h",
    "一小时": "1h",
    "一时": "1h",
    "4小时": "4h",
    "4时": "4h",
    "四小时": "4h",
    "四时": "4h",
    "日线": "1d",
    "周线": "1w",
    "月线": "1M",
}

STOP_TOKENS = {
    "API",
    "KEY",
    "URL",
    "LLM",
    "JSON",
    "K",
    "USDT",
    "USD",
    "AI",
}


def _append_symbol(symbols: list[str], raw_mentions: list[str], symbol: str, raw: str) -> None:
    normalized = symbol.upper()
    if normalized not in symbols and len(symbols) < MAX_SYMBOLS:
        symbols.append(normalized)
        raw_mentions.append(raw)


def _extract_interval(text: str) -> str:
    for phrase, interval in sorted(CHINESE_INTERVALS.items(), key=lambda item: len(item[0]), reverse=True):
        if phrase in text:
            return interval

    minute_match = re.search(r"(?<![A-Za-z0-9])(\d{1,2})\s*(?:分钟|分|m)(?![A-Za-z0-9])", text, re.IGNORECASE)
    if minute_match:
        interval = f"{minute_match.group(1)}m"
        if interval in SUPPORTED_INTERVALS:
            return interval

    hour_match = re.search(r"(?<![A-Za-z0-9])(\d{1,2})\s*(?:小时|时|h)(?![A-Za-z0-9])", text, re.IGNORECASE)
    if hour_match:
        interval = f"{hour_match.group(1)}h"
        if interval in SUPPORTED_INTERVALS:
            return interval

    lowered = text.lower()
    for interval in sorted(SUPPORTED_INTERVALS - {"1M"}, key=len, reverse=True):
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(interval.lower())}(?![A-Za-z0-9])", lowered):
            return interval

    return DEFAULT_INTERVAL


def _symbol_from_base(base: str) -> str:
    normalized = base.upper()
    return BASE_TO_SYMBOL.get(normalized, f"{normalized}{DEFAULT_QUOTE}")


def _is_symbol_candidate(token: str) -> bool:
    normalized = token.upper()
    if normalized in STOP_TOKENS:
        return False
    if normalized in {interval.upper() for interval in SUPPORTED_INTERVALS}:
        return False
    return bool(re.fullmatch(r"[A-Z][A-Z0-9]{1,9}", normalized))


def extract_market_request(text: str) -> dict:
    symbols: list[str] = []
    raw_mentions: list[str] = []
    upper_text = text.upper()

    for raw, symbol in CHINESE_SYMBOLS.items():
        if raw in text:
            _append_symbol(symbols, raw_mentions, symbol, raw)

    pair_pattern = re.compile(r"\b([A-Z][A-Z0-9]{1,9})\s*(?:/|-|\s)\s*USDT\b", re.IGNORECASE)
    for match in pair_pattern.finditer(text):
        base = match.group(1).upper()
        if _is_symbol_candidate(base):
            _append_symbol(symbols, raw_mentions, _symbol_from_base(base), match.group(0))

    compact_pair_pattern = re.compile(r"\b([A-Z][A-Z0-9]{1,9})USDT\b", re.IGNORECASE)
    for match in compact_pair_pattern.finditer(text):
        base = match.group(1).upper()
        if _is_symbol_candidate(base):
            _append_symbol(symbols, raw_mentions, _symbol_from_base(base), match.group(0))

    for base, symbol in BASE_TO_SYMBOL.items():
        if re.search(rf"(?<![A-Z0-9]){re.escape(base)}(?![A-Z0-9])", upper_text):
            _append_symbol(symbols, raw_mentions, symbol, base)

    # Fallback: let users type newer symbols that are not in the MVP whitelist.
    # Example: "分析一下 BAS" -> BASUSDT. Binance validation happens during kline fetch.
    uppercase_token_pattern = re.compile(r"(?<![A-Za-z0-9])([A-Z][A-Z0-9]{1,9})(?![A-Za-z0-9])")
    for match in uppercase_token_pattern.finditer(text):
        token = match.group(1).upper()
        if _is_symbol_candidate(token):
            _append_symbol(symbols, raw_mentions, _symbol_from_base(token), match.group(0))

    return {
        "symbols": symbols[:MAX_SYMBOLS],
        "interval": _extract_interval(text),
        "raw_mentions": raw_mentions[:MAX_SYMBOLS],
    }
