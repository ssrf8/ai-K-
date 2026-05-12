import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "conversations.jsonl"


def write_jsonl(record: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    enriched = {
        "id": str(uuid4()),
        "timestamp": timestamp,
        "created_at": timestamp,
        **record,
    }
    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(enriched, ensure_ascii=False) + "\n")
