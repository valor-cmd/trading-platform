import { useEffect, useRef, useCallback } from "react";
import {
  createChart,
  createSeriesMarkers,
  ColorType,
  LineStyle,
  CrosshairMode,
  AreaSeries,
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

interface PortfolioChartProps {
  data: ChartPoint[];
  trades?: TradeMarker[];
  height?: number;
  pnlPositive?: boolean;
}

function toUTCTimestamp(iso: string) {
  return Math.floor(new Date(iso).getTime() / 1000) as unknown as import("lightweight-charts").UTCTimestamp;
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

  const buildChart = useCallback(() => {
    if (!containerRef.current) return;

    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
      seriesRef.current = null;
    }

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
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      timeScale: {
        borderColor: "rgba(255,255,255,0.1)",
        timeVisible: true,
        secondsVisible: false,
      },
      handleScroll: { vertTouchDrag: false },
    });

    const lineColor = pnlPositive ? "#00ff88" : "#ff4d6a";

    const areaSeries = chart.addSeries(AreaSeries, {
      lineColor,
      lineWidth: 2,
      topColor: pnlPositive ? "rgba(0,255,136,0.15)" : "rgba(255,77,106,0.15)",
      bottomColor: "transparent",
      crosshairMarkerRadius: 4,
      crosshairMarkerBorderColor: lineColor,
      crosshairMarkerBackgroundColor: "#000",
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    });

    const lineData = data
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

    areaSeries.setData(deduped);

    if (trades.length > 0) {
      const markers = trades
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
              ? `${t.symbol} ${t.pnl_usd != null ? (t.pnl_usd >= 0 ? "+" : "") + "$" + t.pnl_usd.toFixed(2) : ""}`
              : `${t.side.toUpperCase()} ${t.symbol}`,
            size: 1,
          };
        })
        .sort((a, b) => (a.time as number) - (b.time as number));

      createSeriesMarkers(areaSeries, markers);
    }

    chart.timeScale().fitContent();
    chartRef.current = chart;
    seriesRef.current = areaSeries as unknown as ISeriesApi<SeriesType>;
  }, [data, trades, height, pnlPositive]);

  useEffect(() => {
    buildChart();
    return () => {
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [buildChart]);

  useEffect(() => {
    if (!containerRef.current || !chartRef.current) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        chartRef.current?.applyOptions({ width: entry.contentRect.width });
      }
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  return <div ref={containerRef} style={{ width: "100%", height }} />;
}
