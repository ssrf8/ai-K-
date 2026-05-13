from datetime import datetime


MAX_COMPRESSED_PROMPT_CANDLES = 160


def _fmt(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.8g}"


def _compact_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.strftime("%m-%d %H:%M")
    except ValueError:
        return value


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
        prompt_candles = candles[-MAX_COMPRESSED_PROMPT_CANDLES:]
        structure_summary = _build_structure_summary(candles)
        candle_lines = []
        for index, candle in enumerate(prompt_candles, start=1):
            candle_lines.append(
                f"{index} t={_compact_time(candle['open_time'])} "
                f"O={_fmt(candle['open'])} H={_fmt(candle['high'])} "
                f"L={_fmt(candle['low'])} C={_fmt(candle['close'])} V={_fmt(candle['volume'])}"
            )
        compression_note = (
            "All fetched candles are included in compressed form."
            if len(prompt_candles) == len(candles)
            else f"Only the latest {len(prompt_candles)} candles are included in compressed form."
        )

        sections.append(
            "\n".join(
                [
                    "",
                    f"Symbol: {summary.get('symbol', symbol)}",
                    f"Market: {summary.get('market_type', market_type)}",
                    f"Interval: {summary.get('interval', interval)}",
                    f"Fetched Candles: {len(candles)}",
                    f"Compressed Candles Included Below: {len(prompt_candles)}",
                    f"Last Close: {_fmt(summary.get('last_close'))}",
                    f"Change From First To Last: {_fmt(summary.get('change_pct_from_first_to_last'))}%",
                    f"Highest High: {_fmt(summary.get('highest_high'))}",
                    f"Lowest Low: {_fmt(summary.get('lowest_low'))}",
                    f"Latest Volume: {_fmt(summary.get('latest_volume'))}",
                    "",
                    *structure_summary,
                    "",
                    "Compressed candle format guide:",
                    "- The compressed candles below are ordered from oldest to newest.",
                    "- t = UTC open time in MM-DD HH:MM.",
                    "- O/H/L/C/V = open/high/low/close/volume.",
                    f"- {compression_note}",
                    "",
                    "Compressed candles:",
                    *candle_lines,
                ]
            )
        )

    return "\n".join(sections)
