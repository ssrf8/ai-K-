import { useEffect, useMemo, useState } from "react";

import { fetchModels, sendChat } from "./api";
import KlineChart from "./KlineChart";
import { loadConfig, saveConfig } from "./storage";

const MAX_CONTEXT_MESSAGES = 8;

const MARKET_STATUS_LABELS = {
  ok: "获取成功",
  error: "获取失败",
  partial_error: "部分失败",
  no_symbol: "未识别币种",
};

const MARKET_TYPE_LABELS = {
  auto: "自动",
  spot: "现货",
  futures: "U本位合约",
};

const THINK_PATTERN = /<think\b[^>]*>[\s\S]*?<\/think>/gi;

function stripThinkBlocks(text) {
  return (text || "").replace(THINK_PATTERN, "").trim();
}

function formatList(values, fallback = "无") {
  return values?.length ? values.join("，") : fallback;
}

function marketStatusLabel(status) {
  return MARKET_STATUS_LABELS[status] || status || "待机";
}

function marketTypeLabel(type) {
  return MARKET_TYPE_LABELS[type] || type || "自动";
}

function keepNaturalContext(messages) {
  return messages
    .filter((message) => message.role === "user" || message.role === "assistant")
    .slice(-MAX_CONTEXT_MESSAGES)
    .map((message) => ({
      role: message.role,
      content:
        message.role === "assistant" && message.run
          ? "上一轮已完成一次行情结构分析；上一轮的K线、支撑阻力和图表标注不作为本轮行情数据使用。"
          : stripThinkBlocks(message.content),
    }));
}

export default function App() {
  const [config, setConfig] = useState(loadConfig);
  const [models, setModels] = useState([]);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [error, setError] = useState("");
  const [lastRun, setLastRun] = useState(null);
  const [expandedPromptIndex, setExpandedPromptIndex] = useState(null);
  const [expandedInjectIndex, setExpandedInjectIndex] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [debugPromptOpen, setDebugPromptOpen] = useState(false);

  useEffect(() => {
    saveConfig(config);
  }, [config]);

  const canLoadModels = config.baseUrl.trim() && config.apiKey.trim();
  const isMockMode = !(config.baseUrl.trim() && config.apiKey.trim() && config.model.trim());

  const finalPrompt = lastRun?.final_prompt || "";
  const loadedFile =
    lastRun?.loaded_prompt_files?.join("，") ||
    lastRun?.loaded_prompt_file ||
    lastRun?.loaded_file ||
    "尚未加载";

  const statusText = useMemo(() => {
    if (loading) return "推理中";
    if (isMockMode) return "模拟模式";
    return `接口已连接：${config.model}`;
  }, [config.model, isMockMode, loading]);

  function updateConfig(patch) {
    setConfig((current) => ({ ...current, ...patch }));
  }

  async function handleLoadModels() {
    setError("");
    setModelsLoading(true);
    try {
      const data = await fetchModels(config);
      setModels(data.models || []);
      if (!config.model && data.models?.[0]?.id) {
        updateConfig({ model: data.models[0].id });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setModelsLoading(false);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const content = input.trim();
    if (!content || loading) return;

    const history = keepNaturalContext(messages);
    const userMessage = { role: "user", content };

    setInput("");
    setError("");
    setLoading(true);
    setMessages((current) => [...current, userMessage]);

    try {
      const data = await sendChat({
        message: content,
        history,
        config,
      });
      const assistantMessage = {
        role: "assistant",
        content: stripThinkBlocks(data.reply),
        run: data,
      };
      setMessages((current) => [...current, assistantMessage]);
      setLastRun(data);
    } catch (err) {
      setError(err.message);
      setMessages((current) => [
        ...current,
        { role: "assistant", content: `请求失败：${err.message}` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function clearChat() {
    setMessages([]);
    setLastRun(null);
    setExpandedPromptIndex(null);
    setExpandedInjectIndex(null);
    setDebugPromptOpen(false);
    setError("");
  }

  function renderRunPanel(message, index) {
    if (message.role !== "assistant" || !message.run) return null;

    const run = message.run;
    const promptOpen = expandedPromptIndex === index;
    const injectOpen = expandedInjectIndex === index;
    const loadedFiles = run.loaded_prompt_files?.length
      ? run.loaded_prompt_files.join("，")
      : run.loaded_prompt_file || run.loaded_file;

    return (
      <div className="run-stack">
        <KlineChart chartData={run.chart_data} analysis={run.analysis_data} />

        <div className="market-panel collapsed-panel">
          <div className="market-panel-head">
            <div>
              <div className="market-title">本轮注入</div>
              <p className="muted">
                {formatList(run.detected_symbols)} · {run.detected_interval} ·{" "}
                {marketTypeLabel(run.resolved_market_type || run.requested_market_type)}
              </p>
            </div>
            <button
              className="secondary compact"
              type="button"
              onClick={() => setExpandedInjectIndex(injectOpen ? null : index)}
            >
              {injectOpen ? "收起" : "查看"}
            </button>
          </div>

          {injectOpen ? (
            <>
              <dl>
                <div>
                  <dt>提示词文件</dt>
                  <dd>{loadedFiles}</dd>
                </div>
                <div>
                  <dt>识别交易对</dt>
                  <dd>{formatList(run.detected_symbols)}</dd>
                </div>
                <div>
                  <dt>周期</dt>
                  <dd>{run.detected_interval}</dd>
                </div>
                <div>
                  <dt>行情市场</dt>
                  <dd>{marketTypeLabel(run.resolved_market_type || run.requested_market_type)}</dd>
                </div>
                <div>
                  <dt>币安状态</dt>
                  <dd>{marketStatusLabel(run.market_data_status)}</dd>
                </div>
              </dl>
              <button
                className="secondary compact"
                type="button"
                onClick={() => setExpandedPromptIndex(promptOpen ? null : index)}
              >
                {promptOpen ? "收起最终提示词" : "查看最终提示词"}
              </button>
              {promptOpen ? <pre className="inline-prompt">{run.final_prompt}</pre> : null}
            </>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      {settingsOpen ? (
        <div className="settings-backdrop" onClick={() => setSettingsOpen(false)}>
          <aside className="settings-panel" onClick={(event) => event.stopPropagation()}>
            <div className="settings-header">
              <div>
                <h2>模型设置</h2>
                <p className="muted">接口地址和密钥只保存在本地浏览器。</p>
              </div>
              <button className="secondary compact" type="button" onClick={() => setSettingsOpen(false)}>
                关闭
              </button>
            </div>

            <label>
              模型接口地址
              <input
                value={config.baseUrl}
                placeholder="填写兼容模型接口地址"
                onChange={(event) => updateConfig({ baseUrl: event.target.value })}
              />
            </label>

            <label>
              访问密钥
              <input
                value={config.apiKey}
                type="password"
                placeholder="填写访问密钥"
                onChange={(event) => updateConfig({ apiKey: event.target.value })}
              />
            </label>

            <div className="model-row">
              <label>
                模型选择
                <select value={config.model} onChange={(event) => updateConfig({ model: event.target.value })}>
                  <option value="">请选择模型</option>
                  {models.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.id}
                    </option>
                  ))}
                </select>
              </label>
              <button type="button" onClick={handleLoadModels} disabled={!canLoadModels || modelsLoading}>
                {modelsLoading ? "读取中" : "获取模型"}
              </button>
            </div>

            <label>
              手动填写模型
              <input
                value={config.model}
                placeholder="填写模型名称"
                onChange={(event) => updateConfig({ model: event.target.value })}
              />
            </label>

            <div className={`status ${isMockMode ? "mock" : "live"}`}>{statusText}</div>
          </aside>
        </div>
      ) : null}

      <main className="chat-panel">
        <header className="terminal-topbar">
          <div className="brand-block">
            <div className="brand-mark">链</div>
            <div>
              <h1>行情结构分析台</h1>
              <p className="muted">币安 K 线 · 方法论 · 人设 · 结构标注</p>
            </div>
          </div>
          <div className="topbar-actions">
            <label className="market-select">
              行情市场
              <select
                value={config.marketType || "auto"}
                onChange={(event) => updateConfig({ marketType: event.target.value })}
              >
                <option value="auto">自动：优先合约</option>
                <option value="futures">只看U本位合约</option>
                <option value="spot">只看现货</option>
              </select>
            </label>
            <div className={`status ${isMockMode ? "mock" : "live"}`}>{statusText}</div>
            <button className="secondary" type="button" onClick={() => setSettingsOpen(true)}>
              设置
            </button>
            <button className="secondary" type="button" onClick={clearChat}>
              清空
            </button>
          </div>
        </header>

        <section className="messages" aria-live="polite">
          {messages.length === 0 ? (
            <div className="empty-state">
              <div className="empty-emblem">◆</div>
              <h2>等待行情指令</h2>
              <p>输入“帮我分析比特币十五分钟”，系统会自动拉取 K 线、生成结构判断并标到图上。</p>
            </div>
          ) : (
            messages.map((message, index) => (
              <article key={`${message.role}-${index}`} className={`message ${message.role}`}>
                <div className="role">{message.role === "user" ? "我" : "智能分析"}</div>
                <div className="bubble">{stripThinkBlocks(message.content)}</div>
                {renderRunPanel(message, index)}
              </article>
            ))
          )}
        </section>

        {error ? <div className="error">{error}</div> : null}

        <form className="composer" onSubmit={handleSubmit}>
          <textarea
            value={input}
            placeholder="输入币种、周期或你的分析问题..."
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                handleSubmit(event);
              }
            }}
          />
          <button type="submit" disabled={loading || !input.trim()}>
            发送
          </button>
        </form>
      </main>

      <aside className="debug-panel">
        <div className="debug-header">
          <h2>本轮链路</h2>
          <span>{lastRun?.mocked ? "模拟" : lastRun ? "实时" : "待机"}</span>
        </div>

        <label>
          加载文件
          <input value={loadedFile} readOnly />
        </label>

        <label>
          识别交易对
          <input value={formatList(lastRun?.detected_symbols)} readOnly />
        </label>

        <label>
          K 线周期
          <input value={lastRun?.detected_interval || "15m"} readOnly />
        </label>

        <label>
          行情市场
          <input value={marketTypeLabel(lastRun?.resolved_market_type || lastRun?.requested_market_type)} readOnly />
        </label>

        <label>
          币安状态
          <input value={marketStatusLabel(lastRun?.market_data_status)} readOnly />
        </label>

        <label>
          结构判断
          <input value={lastRun?.analysis_data?.structure || "暂无"} readOnly />
        </label>

        <div className="prompt-toggle">
          <button className="secondary" type="button" onClick={() => setDebugPromptOpen((open) => !open)}>
            {debugPromptOpen ? "收起最终提示词" : "查看最终提示词"}
          </button>
          {debugPromptOpen ? (
            <label className="prompt-viewer">
              最终提示词
              <textarea value={finalPrompt} readOnly placeholder="发送消息后可查看本轮完整提示词。" />
            </label>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

