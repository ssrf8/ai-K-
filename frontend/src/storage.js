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
      };
    }
    return { marketType: "auto", klineInterval: "auto", ...JSON.parse(raw) };
  } catch {
    return {
      baseUrl: "https://api.openai.com/v1",
      apiKey: "",
      model: "",
      marketType: "auto",
      klineInterval: "auto",
    };
  }
}

export function saveConfig(config) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
}
