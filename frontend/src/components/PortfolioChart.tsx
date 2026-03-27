import { useEffect, useRef, useState } from "react";
import {
  createChart,
  createSeriesMarkers,
  ColorType,
  LineStyle,
  CrosshairMode,
  AreaSeries,
  CandlestickSeries,
  type IChartApi,
  type ISeriesApi,
  type SeriesType,
} from "lightweight-charts";

interface ChartPoint {
  timestamp: string;
  balance: number;
}

interface TradeMarker {
  timestamp: string;
  side: string;
  symbol: string;
  type: "entry" | "exit";
  pnl_usd?: number;
}

type ChartMode = "area" | "candle";
type TimeRange = "1m" | "5m" | "15m" | "1h" | "6h" | "24h" | "7d" | "30d" | "all";

interface PortfolioChartProps {
  data: ChartPoint[];
  trades?: TradeMarker[];
  height?: number;
  pnlPositive?: boolean;
}

function toUTCTimestamp(iso: string) {
  return Math.floor(new Date(iso).getTime() / 1000) as unknown as import("lightweight-charts").UTCTimestamp;
}

function shortSymbol(sym: string) {
  return sym.replace("/USDT", "").replace("/USDC", "").replace("/USD", "");
}

function filterByRange<T extends { timestamp: string }>(data: T[], range: TimeRange): T[] {
  if (range === "all") return data;
  const now = Date.now();
  const ms: Record<TimeRange, number> = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3600_000,
    "6h": 21600_000,
    "24h": 86400_000,
    "7d": 604800_000,
    "30d": 2592000_000,
    "all": 0,
  };
  const cutoff = now - ms[range];
  return data.filter((d) => new Date(d.timestamp).getTime() >= cutoff);
}

export default function PortfolioChart({
  data,
  trades = [],
  height = 400,
  pnlPositive = true,
}: PortfolioChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<SeriesType> | null>(null);
  const initRef = useRef(false);
  const [mode, setMode] = useState<ChartMode>("area");
  const [timeRange, setTimeRange] = useState<TimeRange>("all");
  const [showMarkers, setShowMarkers] = useState(true);

  useEffect(() => {
    if (!containerRef.current) return;

    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
      seriesRef.current = null;
    }
    initRef.current = false;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#888",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.04)" },
        horzLines: { color: "rgba(255,255,255,0.04)" },
      },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: { color: "rgba(255,255,255,0.15)", style: LineStyle.Dashed, width: 1, labelBackgroundColor: "#1a1a1a" },
        horzLine: { color: "rgba(255,255,255,0.15)", style: LineStyle.Dashed, width: 1, labelBackgroundColor: "#1a1a1a" },
      },
      rightPriceScale: {
        borderColor: "rgba(255,255,255,0.1)",
        scaleMargins: { top: 0.15, bottom: 0.15 },
      },
      timeScale: {
        borderColor: "rgba(255,255,255,0.1)",
        timeVisible: true,
        secondsVisible: false,
      },
      handleScroll: { vertTouchDrag: false },
    });

    const lineColor = pnlPositive ? "#00ff88" : "#ff4d6a";

    let series: ISeriesApi<SeriesType>;
    if (mode === "candle") {
      series = chart.addSeries(CandlestickSeries, {
        upColor: "#00ff88",
        downColor: "#ff4d6a",
        borderUpColor: "#00ff88",
        borderDownColor: "#ff4d6a",
        wickUpColor: "#00ff88",
        wickDownColor: "#ff4d6a",
        priceFormat: { type: "price", precision: 2, minMove: 0.01 },
      });
    } else {
      series = chart.addSeries(AreaSeries, {
        lineColor,
        lineWidth: 2,
        topColor: pnlPositive ? "rgba(0,255,136,0.15)" : "rgba(255,77,106,0.15)",
        bottomColor: "transparent",
        crosshairMarkerRadius: 4,
        crosshairMarkerBorderColor: lineColor,
        crosshairMarkerBackgroundColor: "#000",
        priceFormat: { type: "price", precision: 2, minMove: 0.01 },
      });
    }

    chartRef.current = chart;
    seriesRef.current = series;

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        chart.applyOptions({ width: entry.contentRect.width });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      initRef.current = false;
    };
  }, [height, pnlPositive, mode]);

  useEffect(() => {
    if (!seriesRef.current || !chartRef.current) return;

    const filtered = filterByRange(data, timeRange);

    if (mode === "candle") {
      const bucketMs = 300_000;
      const buckets = new Map<number, { o: number; h: number; l: number; c: number }>();
      for (const pt of filtered) {
        const ts = Math.floor(new Date(pt.timestamp).getTime() / bucketMs) * bucketMs;
        const existing = buckets.get(ts);
        if (!existing) {
          buckets.set(ts, { o: pt.balance, h: pt.balance, l: pt.balance, c: pt.balance });
        } else {
          existing.h = Math.max(existing.h, pt.balance);
          existing.l = Math.min(existing.l, pt.balance);
          existing.c = pt.balance;
        }
      }
      const candleData = Array.from(buckets.entries())
        .map(([ts, b]) => ({
          time: (ts / 1000) as unknown as import("lightweight-charts").UTCTimestamp,
          open: b.o,
          high: b.h,
          low: b.l,
          close: b.c,
        }))
        .sort((a, b) => (a.time as number) - (b.time as number));

      const dedupedCandles: typeof candleData = [];
      for (const c of candleData) {
        if (dedupedCandles.length === 0 || (c.time as number) > (dedupedCandles[dedupedCandles.length - 1].time as number)) {
          dedupedCandles.push(c);
        }
      }
      seriesRef.current.setData(dedupedCandles);
    } else {
      const lineData = filtered
        .map((pt) => ({
          time: toUTCTimestamp(pt.timestamp),
          value: pt.balance,
        }))
        .sort((a, b) => (a.time as number) - (b.time as number));

      const deduped: typeof lineData = [];
      for (const pt of lineData) {
        if (deduped.length === 0 || (pt.time as number) > (deduped[deduped.length - 1].time as number)) {
          deduped.push(pt);
        }
      }
      seriesRef.current.setData(deduped);
    }

    if (showMarkers && trades.length > 0 && mode === "area") {
      const filteredTrades = filterByRange(trades, timeRange);
      const markers = filteredTrades
        .map((t) => {
          const time = toUTCTimestamp(t.timestamp);
          const isBuy = t.side === "buy";
          const isExit = t.type === "exit";
          return {
            time,
            position: isBuy ? ("belowBar" as const) : ("aboveBar" as const),
            color: isExit
              ? (t.pnl_usd != null && t.pnl_usd >= 0 ? "#00ff88" : "#ff4d6a")
              : (isBuy ? "#00ff88" : "#ff4d6a"),
            shape: isExit ? ("square" as const) : (isBuy ? ("arrowUp" as const) : ("arrowDown" as const)),
            text: isExit
              ? `${shortSymbol(t.symbol)} ${t.pnl_usd != null ? (t.pnl_usd >= 0 ? "+" : "") + t.pnl_usd.toFixed(2) : ""}`
              : `${t.side === "buy" ? "B" : "S"} ${shortSymbol(t.symbol)}`,
            size: 0,
          };
        })
        .sort((a, b) => (a.time as number) - (b.time as number));

      createSeriesMarkers(seriesRef.current, markers);
    } else if (mode === "area") {
      createSeriesMarkers(seriesRef.current, []);
    }

    if (!initRef.current) {
      chartRef.current.timeScale().fitContent();
      initRef.current = true;
    }
  }, [data, trades, timeRange, showMarkers, mode]);

  const btnStyle = (active: boolean): React.CSSProperties => ({
    padding: "0.2rem 0.5rem",
    fontSize: "0.65rem",
    borderRadius: 6,
    border: active ? "1px solid rgba(0,255,136,0.4)" : "1px solid #333",
    background: active ? "rgba(0,255,136,0.1)" : "transparent",
    color: active ? "#00ff88" : "#888",
    cursor: "pointer",
    fontWeight: active ? 600 : 400,
  });

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem", flexWrap: "wrap", gap: "0.3rem" }}>
        <div style={{ display: "flex", gap: "0.25rem" }}>
          {(["1m", "5m", "15m", "1h", "6h", "24h", "7d", "30d", "all"] as TimeRange[]).map((r) => (
            <button key={r} onClick={() => { setTimeRange(r); initRef.current = false; }} style={btnStyle(timeRange === r)}>{r}</button>
          ))}
        </div>
        <div style={{ display: "flex", gap: "0.25rem" }}>
          <button onClick={() => setMode("area")} style={btnStyle(mode === "area")}>Line</button>
          <button onClick={() => setMode("candle")} style={btnStyle(mode === "candle")}>Candle</button>
          <button onClick={() => setShowMarkers(!showMarkers)} style={btnStyle(showMarkers)}>Trades</button>
        </div>
      </div>
      <div ref={containerRef} style={{ width: "100%", height }} />
    </div>
  );
}
