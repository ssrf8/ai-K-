# AI K Line Prompt Loader

一个极简的行情分析聊天工具：用户输入币种和周期后，后端自动拉取 Binance K 线，把方法论、人设、最近自然对话、本轮行情上下文组合成 prompt，再调用 OpenAI-compatible API。没有配置模型接口时会返回 mock，但仍会拉取 K 线并在前端展示。

## 功能

- React + Vite 前端，生产容器用 Nginx 托管
- Python + FastAPI 后端
- 支持 OpenAI-compatible API
- API Base URL、API Key、模型选择通过前端“设置”按钮配置
- 配置保存在浏览器 localStorage，不写入后端日志
- 固定加载：
  - `backend/prompts/blogger_trading_methodology.md`
  - `backend/prompts/blogger_persona.md`
- 支持 Binance K 线：
  - Spot 现货
  - USD-M Futures U 本位合约
  - 自动模式：同时检查现货和合约，两个都有时优先合约
- 前端展示 K 线图、右侧价格轴、当前价、支撑/阻力/箱体标注
- LLM 返回 `<analysis_json>` 后由后端解析，前端用结构化数据画图
- 自动过滤 `<think>...</think>`
- JSONL 日志写入 `backend/logs/conversations.jsonl`
- 不支持交易下单，不读取 Binance API Key，不接私有接口

## Docker Compose 启动

```bash
docker compose up --build
```

打开：

- 前端：http://localhost:5173
- 后端健康检查：http://localhost:8000/health

Compose 中前端容器使用 Nginx：

- 页面静态文件由 Nginx 提供
- `/api/*` 自动反向代理到后端 `backend:8000`
- 浏览器不需要直接知道后端容器地址

## 本地开发启动

后端：

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

开发模式默认请求：

```text
http://localhost:8000
```

## 使用方式

1. 打开前端页面
2. 顶部选择行情市场：
   - 自动：优先合约
   - 只看 U 本位合约
   - 只看现货
3. 输入示例：
   - `BTC 15m`
   - `ETH 4小时怎么看`
   - `分析一下BAS`
   - `SOL 最近走势怎么样`
4. 页面会展示 K 线图和结构标注
5. 点击“设置”可配置模型接口
6. 不配置模型接口时走 mock

## Binance 行情规则

- 默认 quote asset 为 USDT
- `BTC` 会转换为 `BTCUSDT`
- `btc/usdt`、`BTC-USDT`、`BTC USDT` 都会转换为 `BTCUSDT`
- 白名单外的大写币种也会尝试转换，例如 `BAS` -> `BASUSDT`
- 如果所选市场没有该交易对，行情状态会显示失败，但聊天不会中断
- 自动模式会检查现货和合约，两个都有时优先合约

## LLM 输出解析

Prompt 要求模型返回两部分：

1. 用户可见的自然语言回复
2. 放在 `<analysis_json>...</analysis_json>` 中的结构化 JSON

后端会解析 JSON，并返回 `analysis_data` 给前端，用于展示：

- 结构判断
- 方向倾向
- 支撑区域
- 阻力区域
- 箱体上下沿
- 确认条件
- 失效条件
- 风险提醒

`<think>...</think>` 会被后端和前端双重过滤。

## 日志

每次 `/api/chat` 会追加 JSONL 到：

```text
backend/logs/conversations.jsonl
```

日志包含：

- timestamp
- user_input
- detected_symbols
- detected_interval
- requested_market_type
- resolved_market_type
- market_data_status
- loaded_prompt_files
- final_prompt
- ai_response
- analysis_data
- model
- api_base_url

不会记录 API Key。

## 边界

- 不支持交易下单
- 不读取 Binance API Key
- 不接账户资产
- 不接 Binance 私有接口
- 不构成投资建议

