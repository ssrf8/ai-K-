const STORAGE_KEY = "prompt-template-auto-loader-config";

export function loadConfig() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return {
        baseUrl: "https://api.openai.com/v1",
        apiKey: "",
        model: "",
        marketType: "auto",
        klineInterval: "auto",
        symbolOverride: "",
      };
    }
    return { marketType: "auto", klineInterval: "auto", symbolOverride: "", ...JSON.parse(raw) };
  } catch {
    return {
      baseUrl: "https://api.openai.com/v1",
      apiKey: "",
      model: "",
      marketType: "auto",
      klineInterval: "auto",
      symbolOverride: "",
    };
  }
}

export function saveConfig(config) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
}
