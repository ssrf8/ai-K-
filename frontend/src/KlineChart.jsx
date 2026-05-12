import { useEffect, useMemo, useRef } from "react";
import { CandlestickSeries, ColorType, createChart, LineStyle } from "lightweight-charts";

function toChartCandles(candles = []) {
  return candles.map((candle) => ({
    time: Math.floor(new Date(candle.open_time).getTime() / 1000),
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
  }));
}

function toNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function priceLinesFromAnalysis(analysis) {
  if (!analysis) return [];

  const lines = [];
  for (const zone of analysis.resistance_zones || []) {
    const high = toNumber(zone.high);
    const low = toNumber(zone.low);
    if (high !== null) {
      lines.push({ price: high, title: zone.label || "阻力", color: "#f4c86a", style: LineStyle.Solid });
    }
    if (low !== null) {
      lines.push({ price: low, title: "阻力下沿", color: "#a98b4a", style: LineStyle.Dashed });
    }
  }

  for (const zone of analysis.support_zones || []) {
    const high = toNumber(zone.high);
    const low = toNumber(zone.low);
    if (high !== null) {
      lines.push({ price: high, title: "支撑上沿", color: "#6ab7ff", style: LineStyle.Dashed });
    }
    if (low !== null) {
      lines.push({ price: low, title: zone.label || "支撑", color: "#8bd5ff", style: LineStyle.Solid });
    }
  }

  const boxUpper = toNumber(analysis.box?.upper);
  const boxLower = toNumber(analysis.box?.lower);
  if (boxUpper !== null) {
    lines.push({ price: boxUpper, title: "箱体上沿", color: "#aab8ff", style: LineStyle.Dotted });
  }
  if (boxLower !== null) {
    lines.push({ price: boxLower, title: "箱体下沿", color: "#aab8ff", style: LineStyle.Dotted });
  }

  return lines;
}

function fmt(value) {
  const number = toNumber(value);
  if (number === null) return "无";
  return number.toLocaleString("zh-CN", { maximumFractionDigits: 8 });
}

export default function KlineChart({ chartData, analysis }) {
  const containerRef = useRef(null);
  const primary = chartData?.[0];
  const candles = primary?.candles || [];
  const symbol = primary?.symbol || analysis?.symbol || "未识别";
  const interval = primary?.interval || analysis?.interval || "15m";
  const marketType = primary?.market_type === "futures" ? "U本位合约" : primary?.market_type === "spot" ? "现货" : "自动";

  const chartCandles = useMemo(() => toChartCandles(candles), [candles]);
  const priceLines = useMemo(() => priceLinesFromAnalysis(analysis), [analysis]);
  const lastClose = toNumber(candles.at(-1)?.close);

  useEffect(() => {
    if (!containerRef.current || !chartCandles.length) return undefined;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#070b12" },
        textColor: "#aebbd1",
        panes: {
          separatorColor: "rgba(112, 145, 190, 0.18)",
        },
      },
      grid: {
        vertLines: { color: "rgba(112, 145, 190, 0.12)" },
        horzLines: { color: "rgba(112, 145, 190, 0.12)" },
      },
      rightPriceScale: {
        visible: true,
        borderVisible: true,
        borderColor: "rgba(139, 181, 255, 0.36)",
        ticksVisible: true,
        entireTextOnly: false,
        scaleMargins: {
          top: 0.08,
          bottom: 0.12,
        },
      },
      leftPriceScale: {
        visible: false,
      },
      localization: {
        priceFormatter: (price) => Number(price).toLocaleString("zh-CN", { maximumFractionDigits: 8 }),
      },
      timeScale: {
        borderVisible: true,
        borderColor: "rgba(139, 181, 255, 0.28)",
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        mode: 1,
        vertLine: {
          color: "rgba(139, 181, 255, 0.45)",
          labelBackgroundColor: "#1b2538",
        },
        horzLine: {
          color: "rgba(139, 181, 255, 0.45)",
          labelBackgroundColor: "#1b2538",
        },
      },
      autoSize: true,
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ff6f91",
      wickUpColor: "#86efac",
      wickDownColor: "#ff9aae",
      priceLineVisible: true,
      priceLineColor: "#d8e7ff",
      priceLineWidth: 1,
      lastValueVisible: true,
    });

    candleSeries.setData(chartCandles);
    for (const line of priceLines) {
      candleSeries.createPriceLine({
        price: line.price,
        color: line.color,
        lineWidth: 1,
        lineStyle: line.style,
        axisLabelVisible: true,
        title: line.title,
      });
    }

    if (lastClose !== null) {
      candleSeries.createPriceLine({
        price: lastClose,
        color: "#e8f0ff",
        lineWidth: 1,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: true,
        title: "现价",
      });
    }

    chart.timeScale().fitContent();

    return () => chart.remove();
  }, [chartCandles, priceLines, lastClose]);

  if (!chartCandles.length) {
    return (
      <section className="chart-card empty-chart">
        <div className="chart-title">K 线图</div>
        <p>本轮没有可展示的 K 线数据。</p>
      </section>
    );
  }

  return (
    <section className="chart-card">
      <div className="chart-header">
        <div>
          <div className="chart-title">{symbol} · {interval}</div>
          <div className="chart-subtitle">币安{marketType} K 线 · 最近 {candles.length} 根 · 现价 {fmt(lastClose)}</div>
        </div>
        <div className="chart-badge">{analysis?.structure || "结构待判定"}</div>
      </div>

      <div className="chart-summary">
        <span>方向：<strong>{analysis?.bias || "无"}</strong></span>
        <span>阻力：<strong>{fmt(analysis?.resistance_zones?.[0]?.low)} - {fmt(analysis?.resistance_zones?.[0]?.high)}</strong></span>
        <span>支撑：<strong>{fmt(analysis?.support_zones?.[0]?.low)} - {fmt(analysis?.support_zones?.[0]?.high)}</strong></span>
        <span>箱体：<strong>{fmt(analysis?.box?.lower)} - {fmt(analysis?.box?.upper)}</strong></span>
      </div>

      <div ref={containerRef} className="kline-canvas" />

      <div className="analysis-notes">
        <div>
          <span>确认</span>
          <p>{analysis?.confirmation || "暂无"}</p>
        </div>
        <div>
          <span>失效</span>
          <p>{analysis?.invalidation || "暂无"}</p>
        </div>
        <div>
          <span>风险</span>
          <p>{analysis?.risk_note || "暂无"}</p>
        </div>
      </div>
    </section>
  );
}
