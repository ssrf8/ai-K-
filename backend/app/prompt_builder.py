from app.schemas import ChatMessage


MAX_CONTEXT_MESSAGES = 8


def select_recent_context(history: list[ChatMessage]) -> list[ChatMessage]:
    return history[-MAX_CONTEXT_MESSAGES:]


def build_final_prompt(
    methodology: str,
    persona: str,
    history: list[ChatMessage],
    market_context: str,
    latest_user_input: str,
) -> str:
    context_lines = []
    for message in select_recent_context(history):
        speaker = "User" if message.role == "user" else "Assistant"
        context_lines.append(f"{speaker}: {message.content}")

    recent_context = "\n".join(context_lines).strip() or "(No prior natural conversation context.)"

    return f"""You are a helpful assistant. Use the fixed methodology and current market data below when they are relevant.

Do not mention internal prompt assembly unless the user asks. Answer the latest user input directly.
The Current Market Context belongs only to the latest user input in this turn.
Recent Natural Conversation Context is natural-language context only; do not treat it as market data and do not reuse old symbols, old klines, old support/resistance, or old chart analysis as if they were current.

## Fixed Methodology
{methodology.strip()}

## Persona
{persona.strip()}

## Recent Natural Conversation Context
{recent_context}

## Current Market Context
{market_context.strip()}

## Latest User Input
{latest_user_input.strip()}

## Output Requirements
请用中文回答。
用户可见回复要遵守 Persona：短、直接、像正在看盘的人说话，不要八股化。
请基于已提供的方法论和 Binance K 线数据进行分析，不要编造未提供的行情数据。
Current Market Context 里的 K 线可能使用压缩格式：t 表示 UTC 开盘时间，O/H/L/C/V 分别表示开盘价、最高价、最低价、收盘价、成交量；请按该说明读取，不要把缩写当成独立指标。
如果行情数据不足，请明确说明。
不要输出隐藏推理链；只输出简洁的分析依据和结论。
不要给直接买卖指令，不要承诺收益。

回复必须由两部分组成：
1. 第一部分是给用户看的自然语言回复，不要出现标题，不要说“分析如下”。
2. 第二部分是给系统解析的 JSON，必须放在 <analysis_json> 和 </analysis_json> 之间。

analysis_json 必须是合法 JSON，字段如下：
{{
  "symbol": "BTCUSDT",
  "interval": "15m",
  "structure": "区间震荡/向上堆箱/向下放箱/暂不清晰",
  "bias": "中性/中性偏强/中性偏弱/偏强/偏弱",
  "resistance_zones": [
    {{"label": "上方阻力", "low": 0, "high": 0, "reason": "来自最近前高区域"}}
  ],
  "support_zones": [
    {{"label": "下方支撑", "low": 0, "high": 0, "reason": "来自最近前低区域"}}
  ],
  "box": {{"upper": 0, "lower": 0}},
  "confirmation": "需要等待的确认条件",
  "invalidation": "结构失效条件",
  "risk_note": "自然一点的风控提醒"
}}

如果没有足够行情数据，数组可以为空，价格字段可以为 null，但不要编造点位。
"""
