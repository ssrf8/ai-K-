MAX_PROMPT_CANDLES = 20


def _fmt(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.8g}"


def build_market_context(market_results: list[dict]) -> str:
    if not market_results:
        return (
            "[MARKET DATA CONTEXT]\n"
            "No clear crypto symbol detected in the latest user input. No Binance kline data was loaded."
        )

    sections = ["[MARKET DATA CONTEXT - Binance Klines]"]
    for result in market_results:
        symbol = result.get("symbol", "UNKNOWN")
        interval = result.get("interval", "unknown")
        market_type = result.get("market_type", "unknown")

        if result.get("status") != "ok":
            sections.append(
                "\n".join(
                    [
                        "",
                        f"Detected symbol: {symbol}",
                        f"Requested market: {market_type}",
                        f"Binance kline fetch failed: {result.get('error', 'unknown error')}",
                    ]
                )
            )
            continue

        summary = result.get("summary", {})
        candles = result.get("candles", [])
        recent_candles = candles[-MAX_PROMPT_CANDLES:]
        candle_lines = []
        for index, candle in enumerate(recent_candles, start=1):
            candle_lines.append(
                f"{index}. time={candle['open_time']}, open={_fmt(candle['open'])}, "
                f"high={_fmt(candle['high'])}, low={_fmt(candle['low'])}, "
                f"close={_fmt(candle['close'])}, volume={_fmt(candle['volume'])}"
            )

        sections.append(
            "\n".join(
                [
                    "",
                    f"Symbol: {summary.get('symbol', symbol)}",
                    f"Market: {summary.get('market_type', market_type)}",
                    f"Interval: {summary.get('interval', interval)}",
                    f"Candles: {len(candles)}",
                    f"Last Close: {_fmt(summary.get('last_close'))}",
                    f"Change From First To Last: {_fmt(summary.get('change_pct_from_first_to_last'))}%",
                    f"Highest High: {_fmt(summary.get('highest_high'))}",
                    f"Lowest Low: {_fmt(summary.get('lowest_low'))}",
                    f"Latest Volume: {_fmt(summary.get('latest_volume'))}",
                    "",
                    "Recent candles:",
                    *candle_lines,
                ]
            )
        )

    return "\n".join(sections)
