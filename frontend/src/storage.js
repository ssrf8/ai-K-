const STORAGE_KEY = "prompt-template-auto-loader-config";

export function loadConfig() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return {
        baseUrl: "https://api.openai.com/v1",
        apiKey: "",
        model: "",
        templateMode: "crypto",
        marketType: "auto",
        klineInterval: "auto",
        symbolOverride: "",
        showFibonacci: true,
      };
    }
    return {
      templateMode: "crypto",
      marketType: "auto",
      klineInterval: "auto",
      symbolOverride: "",
      showFibonacci: true,
      ...JSON.parse(raw),
    };
  } catch {
    return {
      baseUrl: "https://api.openai.com/v1",
      apiKey: "",
      model: "",
      templateMode: "crypto",
      marketType: "auto",
      klineInterval: "auto",
      symbolOverride: "",
      showFibonacci: true,
    };
  }
}

export function saveConfig(config) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
}
