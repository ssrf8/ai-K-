from functools import lru_cache
from pathlib import Path


PROMPT_FILENAME = "blogger_trading_methodology.md"
PERSONA_FILENAME = "blogger_persona.md"
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
PROMPT_PATH = PROMPTS_DIR / PROMPT_FILENAME
PERSONA_PATH = PROMPTS_DIR / PERSONA_FILENAME


@lru_cache(maxsize=1)
def load_methodology() -> tuple[str, str]:
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"Prompt methodology file not found: {PROMPT_PATH}")

    return PROMPT_FILENAME, PROMPT_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def load_persona() -> tuple[str, str]:
    if not PERSONA_PATH.exists():
        raise FileNotFoundError(f"Prompt persona file not found: {PERSONA_PATH}")

    return PERSONA_FILENAME, PERSONA_PATH.read_text(encoding="utf-8")
