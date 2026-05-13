const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:18073/api").replace(/\/$/, "");

async function parseResponse(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `Request failed with HTTP ${response.status}`);
  }
  return data;
}

export async function fetchModels({ baseUrl, apiKey }) {
  const response = await fetch(`${API_BASE_URL}/models`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ base_url: baseUrl, api_key: apiKey }),
  });
  return parseResponse(response);
}

export async function sendChat({ message, history, config }) {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      history,
      api_base_url: config.baseUrl,
      api_key: config.apiKey,
      model: config.model,
      market_type: config.marketType || "auto",
      kline_interval: config.klineInterval || "auto",
      symbol_override: config.symbolOverride || "",
    }),
  });
  return parseResponse(response);
}
