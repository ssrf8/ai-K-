from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ApiConfig(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)
    api_base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    market_type: Literal["auto", "spot", "futures"] | None = "auto"
    kline_interval: Literal["auto", "1m", "5m", "15m", "1h", "4h"] | None = "auto"
    config: ApiConfig = Field(default_factory=ApiConfig)


class ChatResponse(BaseModel):
    reply: str
    final_prompt: str
    loaded_prompt_file: str
    loaded_prompt_files: list[str] = Field(default_factory=list)
    detected_symbols: list[str]
    detected_interval: str
    requested_interval: str = "auto"
    requested_market_type: str = "auto"
    resolved_market_type: str | None = None
    market_data_status: str
    market_context: str
    chart_data: list[dict[str, Any]] = Field(default_factory=list)
    analysis_data: dict[str, Any] | None = None
    loaded_file: str | None = None
    model: str | None = None
    mocked: bool


class ModelsRequest(BaseModel):
    base_url: str = Field(min_length=1)
    api_key: str = Field(min_length=1)


class ModelInfo(BaseModel):
    id: str


class ModelsResponse(BaseModel):
    models: list[ModelInfo]
