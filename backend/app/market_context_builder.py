MAX_PROMPT_CANDLES = 20


def _fmt(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.8g}"


def _local_extremes(candles: list[dict], key: str, mode: str, limit: int = 5) -> list[dict]:
    if len(candles) < 3:
        return []

    points = []
    for index in range(1, len(candles) - 1):
        previous_value = candles[index - 1][key]
        current_value = candles[index][key]
        next_value = candles[index + 1][key]
        if mode == "high" and current_value >= previous_value and current_value >= next_value:
            points.append({"time": candles[index]["open_time"], "price": current_value})
        if mode == "low" and current_value <= previous_value and current_value <= next_value:
            points.append({"time": candles[index]["open_time"], "price": current_value})

    return points[-limit:]


def _build_structure_summary(candles: list[dict]) -> list[str]:
    if not candles:
        return []

    first_close = candles[0]["close"]
    last_close = candles[-1]["close"]
    highest = max(candles, key=lambda candle: candle["high"])
    lowest = min(candles, key=lambda candle: candle["low"])
    range_pct = ((highest["high"] - lowest["low"]) / first_close * 100) if first_close else 0
    close_position = (
        (last_close - lowest["low"]) / (highest["high"] - lowest["low"]) * 100
        if highest["high"] != lowest["low"]
        else 50
    )

    lines = [
        "Compressed structure summary from fetched candles:",
        f"- Window high: time={highest['open_time']}, price={_fmt(highest['high'])}",
        f"- Window low: time={lowest['open_time']}, price={_fmt(lowest['low'])}",
        f"- Window range: {_fmt(range_pct)}%",
        f"- Last close position in range: {_fmt(close_position)}% from low to high",
    ]

    swing_highs = _local_extremes(candles, "high", "high")
    swing_lows = _local_extremes(candles, "low", "low")
    if swing_highs:
        lines.append(
            "- Recent swing highs: "
            + "; ".join(f"{point['time']}@{_fmt(point['price'])}" for point in swing_highs)
        )
    if swing_lows:
        lines.append(
            "- Recent swing lows: "
            + "; ".join(f"{point['time']}@{_fmt(point['price'])}" for point in swing_lows)
        )

    return lines


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
        structure_summary = _build_structure_summary(candles)
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
                    f"Fetched Candles: {len(candles)}",
                    f"Detailed Candles Included Below: {len(recent_candles)}",
                    f"Last Close: {_fmt(summary.get('last_close'))}",
                    f"Change From First To Last: {_fmt(summary.get('change_pct_from_first_to_last'))}%",
                    f"Highest High: {_fmt(summary.get('highest_high'))}",
                    f"Lowest Low: {_fmt(summary.get('lowest_low'))}",
                    f"Latest Volume: {_fmt(summary.get('latest_volume'))}",
                    "",
                    *structure_summary,
                    "",
                    "Recent candles:",
                    *candle_lines,
                ]
            )
        )

    return "\n".join(sections)
