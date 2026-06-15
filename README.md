# AI K Line Prompt Loader

一个极简的行情分析聊天工具：用户输入币种和周期后，后端自动拉取 Binance K 线，把方法论、人设、最近自然对话、本轮行情上下文组合成 prompt，再调用 OpenAI-compatible API。需要配置完整模型接口后才会调用 LLM。

## 功能

- React + Vite 前端，生产容器用 Nginx 托管
- Python + FastAPI 后端
- 支持 OpenAI-compatible API
- API Base URL、API Key、模型选择通过前端“设置”按钮配置
- 配置保存在浏览器 localStorage，不写入后端日志
- 加密货币模板固定加载：
  - `backend/prompts/blogger_trading_methodology.md`
  - `backend/prompts/blogger_persona.md`
- 黄金模板固定加载：
  - `backend/prompts/gold_trading_methodology.md`
- 支持 Binance K 线：
  - Spot 现货
  - USD-M Futures U 本位合约
  - 自动模式：同时检查现货和合约，两个都有时优先合约
- 黄金分析模式固定使用 Binance USD-M Futures `XAUUSDT`
- 黄金分析模式会额外注入宏观摘要、FRED Release Calendar 经济日历、BLS 官方实际值、Fed RSS 官方快讯
- 前端展示 K 线图、右侧价格轴、当前价、支撑/阻力/箱体标注
- 黄金图表支持 Fibonacci 价格线显示/隐藏
- LLM 返回 `<analysis_json>` 后由后端解析，前端用结构化数据画图
- 自动过滤 `<think>...</think>`
- JSONL 日志写入 `backend/logs/conversations.jsonl`
- 未配置完整模型接口时 `/api/chat` 会返回错误，不再自动生成 mock 回复
- 不支持交易下单，不读取 Binance API Key，不接私有接口

## Docker Compose 启动

```bash
docker compose up --build
```

打开：

- 前端：http://localhost:5173
- 后端健康检查：http://localhost:5173/health

Compose 中前端容器使用 Nginx：

- 页面静态文件由 Nginx 提供
- `/api/*` 自动反向代理到后端 `backend:18073`
- 浏览器不需要直接知道后端容器地址

## 本地开发启动

后端：

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 18073
```

前端：

```bash
cd frontend
npm install
npm run dev
```

开发模式默认请求：

```text
http://localhost:18073/api
```

## 使用方式

1. 打开前端页面
2. 顶部选择模板：
   - 加密货币
   - 黄金分析
3. 加密货币模板下选择行情市场：
   - 自动：优先合约
   - 只看 U 本位合约
   - 只看现货
4. 加密货币模板下选择 K 线周期：
   - 自动识别
   - 1M
   - 5M
   - 15M
   - 1H
   - 4H
   - 1D
5. 黄金模板下：
   - 行情市场、K 线周期、指定币种会锁定
   - 固定分析 `XAUUSDT`
   - 默认图表周期为 `15m`
   - 可用“显示Fib”开关控制图表 Fibonacci 线
6. 输入示例：
   - `BTC 15m`
   - `ETH 4小时怎么看`
   - `分析一下BAS`
   - `SOL 最近走势怎么样`
   - `黄金现在怎么看`
7. 页面会展示 K 线图和结构标注
8. 点击“设置”配置模型接口
9. 必须填写 API Base URL、API Key 和 Model 后才能发送真实 LLM 请求

## Binance 行情规则

- 默认 quote asset 为 USDT
- `BTC` 会转换为 `BTCUSDT`
- `btc/usdt`、`BTC-USDT`、`BTC USDT` 都会转换为 `BTCUSDT`
- 白名单外的大写币种也会尝试转换，例如 `BAS` -> `BASUSDT`
- 常见中文币名会先转换成 Binance symbol，例如 `比特币` -> `BTCUSDT`、`索拉纳` -> `SOLUSDT`、`佩佩币` -> `PEPEUSDT`
- 如果是小众中文名，建议显式写出 symbol：`【BAS】`、`[BAS]`、`$BAS`、`巴斯(BAS)` 都会识别为 `BASUSDT`
- 顶部“指定币种”可以手动填写实际 Binance symbol，填了会优先于聊天内容识别；支持 `BAS`、`BASUSDT`、`币安人生`、`币安人生USDT` 这类输入
- 如果中文 symbol 不在当前 Binance public K 线 API 中，页面会显示行情获取失败，但不会影响聊天流程
- 如果前端选择了固定 K 线周期，会优先使用该周期
- 如果前端选择“自动识别”，会从用户输入里识别 `15分钟`、`十五分钟`、`5M`、`1H`、`4H` 等周期
- 如果没有识别到周期，默认使用 `15m`
- 如果所选市场没有该交易对，行情状态会显示失败，但聊天不会中断
- 自动模式会检查现货和合约，两个都有时优先合约

## 黄金分析模式

黄金模板是独立链路，不复用加密货币 prompt。

固定规则：

- 交易对：`XAUUSDT`
- 市场：Binance USD-M Futures
- 图表默认周期：`15m`
- 注入 LLM 的周期：`15m / 1h / 4h / 1d`
- 每个周期只发送最近 30 根已收 K 线
- 总发送原始 K 线：120 根
- 当前形成中周期只给 `current_price / elapsed`，不发送未收完整 OHLCV

黄金模式会在后端先做本地清洗和计算，再把结构化 JSON 注入 prompt：

- Fibonacci：`0.236 / 0.382 / 0.5 / 0.618 / 0.786 / 0.886`，以及 `1.272 / 1.618` 扩展
- 均线：EMA21、EMA55、Vegas EMA144/EMA169
- MACD：DIF、DEA、Histogram、cross、zero position
- 箱体结构：上沿、下沿、中轴、区间位置、堆箱/放箱/震荡判断
- K 线形态标签：长上影、长下影、吞没、孕线、双孕线、假突破等
- 宏观评分：FRED 利率、实际收益率、通胀预期、美元指数等
- 经济日历：FRED Release Calendar
- 官方实际值：BLS 就业和 CPI 相关字段
- 官方快讯：Fed RSS

黄金模式的 K 线分三层处理：

- 前端展示：`15m` 图表显示最近 120 根已收 K 线，让图表更完整。
- 本地计算：结构、Fibonacci、箱体、形态用最近 120 根已收 K 线；EMA/MACD/Vegas 使用已拉取到的更长历史。
- 发送给 LLM：原始 K 线仍保持每周期 30 根，避免 prompt 过长。

FRED 数据兜底：

- 每个 series 按时间倒序查找有效 observation。
- 有效值必须非空、不是 `.`，且能转成数字。
- 如果最新 observation 无效，但历史有有效值，会使用上一条有效值并标记 `freshness = "stale"`。
- 如果完全没有有效值，该指标标记 `status = "no_valid_data"`，不参与宏观评分。

宏观源缓存：

- FRED observations：30 分钟
- BLS 官方实际值：6 小时
- FRED Release Calendar：6 小时
- Fed RSS：10 分钟

需要 FRED 宏观数据和 FRED Release Calendar 时，在后端环境变量里配置：

```text
FRED_API_KEY=你的 FRED key
```

不要把真实 key 提交进仓库。

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

## K 线写入 Prompt 的方式

后端会按所选周期拉取一段固定窗口的 K 线，用于图表、统计和 prompt 压缩分析。

当前窗口规则：

- `5M`：120 根，约 10 小时
- `15M`：96 根，约 1 天
- `1H`：72 根，约 3 天
- `4H`：42 根，约 7 天
- `1M`：120 根，作为保护性上限，避免 prompt 过长

当前 prompt 中包含：

- `Fetched Candles`：后端实际获取的 K 线数量
- `Compressed Candles Included Below`：压缩写入 prompt 的 K 线数量
- 完整窗口压缩摘要：
  - 窗口最高点
  - 窗口最低点
  - 窗口振幅
  - 最新收盘价在窗口区间中的位置
  - 最近局部高点
  - 最近局部低点
- 压缩 K 线序列，按从旧到新排列

压缩 K 线格式示例：

```text
1 t=05-13 10:15 O=103000 H=103500 L=102800 C=103200 V=123.45
```

其中 `t` 是 UTC 开盘时间，`O/H/L/C/V` 分别是开盘价、最高价、最低价、收盘价、成交量。这样既保留窗口内的高低点、结构摘要和连续 K 线，又避免把完整 JSON 明细塞进 prompt。

黄金模板不使用上述压缩文本格式，而是注入 `Current Gold Context JSON`。其中原始 K 线仍为精简后的 30 根/周期，指标、结构和宏观数据由后端提前计算。

## 日志

每次 `/api/chat` 会追加 JSONL 到：

```text
backend/logs/conversations.jsonl
```

黄金本地调试脚本也可能写入：

```text
backend/logs/gold_api_chat_simulation_response.jsonl
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
- gold_context_json（黄金模板）
- macro_data_status（黄金模板）
- model
- api_base_url

不会记录 API Key。

## 边界

- 不支持交易下单
- 不读取 Binance API Key
- 不接账户资产
- 不接 Binance 私有接口
- 不构成投资建议
