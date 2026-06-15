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
