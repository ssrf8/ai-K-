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
