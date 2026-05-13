from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.analysis_parser import build_mock_analysis, parse_analysis_response
from app.binance_client import fetch_klines_with_fallback
from app.llm_client import LLMClientError, chat_completion, fetch_models, has_api_config, mock_reply
from app.logger import write_jsonl
from app.market_context_builder import build_market_context
from app.prompt_builder import build_final_prompt, select_recent_context
from app.prompt_loader import load_methodology, load_persona
from app.schemas import ChatRequest, ChatResponse, ModelInfo, ModelsRequest, ModelsResponse
from app.symbol_extractor import extract_market_request


app = FastAPI(title="Prompt Template Auto-Loader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/models", response_model=ModelsResponse)
async def models(request: ModelsRequest) -> ModelsResponse:
    try:
        fetched = await fetch_models(request.base_url, request.api_key)
    except LLMClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ModelsResponse(models=[ModelInfo(id=item["id"]) for item in fetched])


@app.post("/api/models", response_model=ModelsResponse)
async def api_models(request: ModelsRequest) -> ModelsResponse:
    return await models(request)


def _resolve_api_config(request: ChatRequest) -> tuple[str | None, str | None, str | None]:
    base_url = request.api_base_url if request.api_base_url is not None else request.config.base_url
    api_key = request.api_key if request.api_key is not None else request.config.api_key
    model = request.model if request.model is not None else request.config.model
    return base_url, api_key, model


def _market_status(market_results: list[dict]) -> str:
    if not market_results:
        return "no_symbol"
    if all(result.get("status") == "ok" for result in market_results):
        return "ok"
    if any(result.get("status") == "ok" for result in market_results):
        return "partial_error"
    return "error"


def _build_chart_data(market_results: list[dict]) -> list[dict]:
    chart_data = []
    for result in market_results:
        if result.get("status") != "ok":
            continue
        chart_data.append(
            {
                "symbol": result.get("symbol"),
                "interval": result.get("interval"),
                "market_type": result.get("market_type"),
                "summary": result.get("summary", {}),
                "candles": result.get("candles", []),
            }
        )
    return chart_data


def _resolve_interval(request: ChatRequest, extracted_interval: str) -> tuple[str, str]:
    requested_interval = request.kline_interval or "auto"
    if requested_interval == "auto":
        return requested_interval, extracted_interval
    return requested_interval, requested_interval


async def _handle_chat(request: ChatRequest) -> ChatResponse:
    loaded_file, methodology = load_methodology()
    persona_file, persona = load_persona()
    loaded_files = [loaded_file, persona_file]
    recent_context = select_recent_context(request.history)
    market_request = extract_market_request(request.message)
    requested_interval, resolved_interval = _resolve_interval(request, market_request["interval"])
    requested_market_type = request.market_type or "auto"
    market_results = []
    for symbol in market_request["symbols"]:
        market_results.append(await fetch_klines_with_fallback(symbol, resolved_interval, requested_market_type))

    market_context = build_market_context(market_results)
    market_data_status = _market_status(market_results)
    chart_data = _build_chart_data(market_results)
    resolved_market_type = next((result.get("market_type") for result in market_results if result.get("status") == "ok"), None)
    final_prompt = build_final_prompt(methodology, persona, recent_context, market_context, request.message)

    api_base_url, api_key, model = _resolve_api_config(request)
    mocked = not has_api_config(api_base_url, api_key, model)
    if mocked:
        reply = mock_reply(request.message, ", ".join(loaded_files))
        analysis_data = build_mock_analysis(market_results, resolved_interval, market_request["symbols"])
    else:
        try:
            raw_reply = await chat_completion(
                api_base_url or "",
                api_key or "",
                model or "",
                final_prompt,
            )
            reply, analysis_data = parse_analysis_response(raw_reply)
        except LLMClientError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    write_jsonl(
        {
            "user_input": request.message,
            "detected_symbols": market_request["symbols"],
            "detected_interval": resolved_interval,
            "requested_interval": requested_interval,
            "requested_market_type": requested_market_type,
            "resolved_market_type": resolved_market_type,
            "market_data_status": market_data_status,
            "loaded_prompt_file": loaded_file,
            "loaded_prompt_files": loaded_files,
            "final_prompt": final_prompt,
            "ai_response": reply,
            "analysis_data": analysis_data,
            "model": model,
            "api_base_url": api_base_url,
            "mocked": mocked,
            "recent_context": [message.model_dump() for message in recent_context],
        }
    )

    return ChatResponse(
        reply=reply,
        final_prompt=final_prompt,
        loaded_prompt_file=loaded_file,
        loaded_prompt_files=loaded_files,
        loaded_file=loaded_file,
        detected_symbols=market_request["symbols"],
        detected_interval=resolved_interval,
        requested_interval=requested_interval,
        requested_market_type=requested_market_type,
        resolved_market_type=resolved_market_type,
        market_data_status=market_data_status,
        market_context=market_context,
        chart_data=chart_data,
        analysis_data=analysis_data,
        model=model,
        mocked=mocked,
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    return await _handle_chat(request)


@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(request: ChatRequest) -> ChatResponse:
    return await _handle_chat(request)
