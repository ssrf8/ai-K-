import httpx


class LLMClientError(RuntimeError):
    pass


def has_api_config(base_url: str | None, api_key: str | None, model: str | None = None) -> bool:
    return bool(base_url and base_url.strip() and api_key and api_key.strip() and (model is None or model.strip()))


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


async def fetch_models(base_url: str, api_key: str) -> list[dict[str, str]]:
    url = f"{normalize_base_url(base_url)}/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, headers=headers)

    if response.status_code >= 400:
        raise LLMClientError(f"Model request failed: HTTP {response.status_code} {response.text[:500]}")

    payload = response.json()
    models = payload.get("data", [])
    return [{"id": item["id"]} for item in models if isinstance(item, dict) and item.get("id")]


async def chat_completion(base_url: str, api_key: str, model: str, final_prompt: str) -> str:
    url = f"{normalize_base_url(base_url)}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": final_prompt}],
        "temperature": 0.7,
    }

    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(url, headers=headers, json=payload)

    if response.status_code >= 400:
        raise LLMClientError(f"Chat request failed: HTTP {response.status_code} {response.text[:800]}")

    data = response.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMClientError("Chat response did not contain choices[0].message.content") from exc


def mock_reply(user_message: str, loaded_file: str) -> str:
    return (
        "[Mock reply]\n"
        "结论：当前未配置完整 LLM API，因此返回 mock 结果。\n\n"
        f"已加载提示词文件：{loaded_file}\n"
        f"收到的问题：{user_message}\n\n"
        "关键依据：后端已完成固定提示词、当前 market context 和用户输入的 prompt 组装。"
        "如需真实模型回复，请配置 API Base URL、API Key 和 Model。\n\n"
        "这不是投资建议。"
    )
