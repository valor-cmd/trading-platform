import { useEffect, useRef, useCallback } from "react";
import {
  createChart,
  ColorType,
  LineStyle,
  CrosshairMode,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  type IChartApi,
} from "lightweight-charts";

interface OHLCVBar {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface SymbolChartProps {
  data: OHLCVBar[];
  symbol: string;
  entryPrice?: number;
  stopLoss?: number;
  takeProfit?: number;
  height?: number;
  showVolume?: boolean;
  showBB?: boolean;
  showRSI?: boolean;
  showMACD?: boolean;
}

function toTime(ts: number) {
  return Math.floor(ts / 1000) as unknown as import("lightweight-charts").UTCTimestamp;
}

function calcSMA(closes: number[], period: number): (number | null)[] {
  const result: (number | null)[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) {
      result.push(null);
    } else {
      let sum = 0;
      for (let j = i - period + 1; j <= i; j++) sum += closes[j];
      result.push(sum / period);
    }
  }
  return result;
}

function calcBB(closes: number[], period = 20, mult = 2) {
  const sma = calcSMA(closes, period);
  const upper: (number | null)[] = [];
  const lower: (number | null)[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (sma[i] == null) {
      upper.push(null);
      lower.push(null);
    } else {
      let variance = 0;
      for (let j = i - period + 1; j <= i; j++) {
        variance += (closes[j] - sma[i]!) ** 2;
      }
      const std = Math.sqrt(variance / period);
      upper.push(sma[i]! + mult * std);
      lower.push(sma[i]! - mult * std);
    }
  }
  return { sma, upper, lower };
}

function calcRSI(closes: number[], period = 14): (number | null)[] {
  const result: (number | null)[] = [null];
  let avgGain = 0;
  let avgLoss = 0;
  for (let i = 1; i < closes.length; i++) {
    const change = closes[i] - closes[i - 1];
    const gain = change > 0 ? change : 0;
    const loss = change < 0 ? -change : 0;
    if (i <= period) {
      avgGain += gain / period;
      avgLoss += loss / period;
      if (i < period) {
        result.push(null);
      } else {
        const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
        result.push(100 - 100 / (1 + rs));
      }
    } else {
      avgGain = (avgGain * (period - 1) + gain) / period;
      avgLoss = (avgLoss * (period - 1) + loss) / period;
      const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
      result.push(100 - 100 / (1 + rs));
    }
  }
  return result;
}

function calcEMA(values: number[], period: number): number[] {
  const k = 2 / (period + 1);
  const result: number[] = [values[0]];
  for (let i = 1; i < values.length; i++) {
    result.push(values[i] * k + result[i - 1] * (1 - k));
  }
  return result;
}

function calcMACD(closes: number[], fast = 12, slow = 26, signal = 9) {
  const emaFast = calcEMA(closes, fast);
  const emaSlow = calcEMA(closes, slow);
  const macdLine: number[] = [];
  for (let i = 0; i < closes.length; i++) {
    macdLine.push(emaFast[i] - emaSlow[i]);
  }
  const signalLine = calcEMA(macdLine, signal);
  const histogram: number[] = macdLine.map((v, i) => v - signalLine[i]);
  return { macdLine, signalLine, histogram };
}

export default function SymbolChart({
  data,
  symbol,
  entryPrice,
  stopLoss,
  takeProfit,
  height = 500,
  showVolume = true,
  showBB = true,
  showRSI = true,
  showMACD = false,
}: SymbolChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  const buildChart = useCallback(() => {
    if (!containerRef.current || data.length === 0) return;

    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
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
        mode: CrosshairMode.Normal,
        vertLine: { color: "rgba(255,255,255,0.15)", style: LineStyle.Dashed, width: 1, labelBackgroundColor: "#1a1a1a" },
        horzLine: { color: "rgba(255,255,255,0.15)", style: LineStyle.Dashed, width: 1, labelBackgroundColor: "#1a1a1a" },
      },
      rightPriceScale: {
        borderColor: "rgba(255,255,255,0.1)",
        scaleMargins: { top: 0.05, bottom: showRSI || showMACD ? 0.3 : 0.1 },
      },
      timeScale: {
        borderColor: "rgba(255,255,255,0.1)",
        timeVisible: true,
        secondsVisible: false,
      },
      handleScroll: { vertTouchDrag: false },
    });

    const sorted = [...data].sort((a, b) => a.timestamp - b.timestamp);
    const closes = sorted.map((d) => d.close);

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#00ff88",
      downColor: "#ff4d6a",
      borderUpColor: "#00ff88",
      borderDownColor: "#ff4d6a",
      wickUpColor: "#00ff88",
      wickDownColor: "#ff4d6a",
    });

    candleSeries.setData(
      sorted.map((d) => ({
        time: toTime(d.timestamp),
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
      }))
    );

    if (showVolume) {
      const volumeSeries = chart.addSeries(HistogramSeries, {
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
      });

      chart.priceScale("volume").applyOptions({
        scaleMargins: { top: 0.85, bottom: 0 },
      });

      volumeSeries.setData(
        sorted.map((d) => ({
          time: toTime(d.timestamp),
          value: d.volume,
          color: d.close >= d.open ? "rgba(0,255,136,0.15)" : "rgba(255,77,106,0.15)",
        }))
      );
    }

    if (showBB) {
      const bb = calcBB(closes);
      const times = sorted.map((d) => toTime(d.timestamp));

      const bbMiddle = chart.addSeries(LineSeries, {
        color: "rgba(168,85,247,0.5)",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      bbMiddle.setData(
        times
          .map((t, i) => (bb.sma[i] != null ? { time: t, value: bb.sma[i]! } : null))
          .filter(Boolean) as any
      );

      const bbUpper = chart.addSeries(LineSeries, {
        color: "rgba(168,85,247,0.3)",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      bbUpper.setData(
        times
          .map((t, i) => (bb.upper[i] != null ? { time: t, value: bb.upper[i]! } : null))
          .filter(Boolean) as any
      );

      const bbLower = chart.addSeries(LineSeries, {
        color: "rgba(168,85,247,0.3)",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      bbLower.setData(
        times
          .map((t, i) => (bb.lower[i] != null ? { time: t, value: bb.lower[i]! } : null))
          .filter(Boolean) as any
      );
    }

    if (entryPrice) {
      candleSeries.createPriceLine({
        price: entryPrice,
        color: "#3b82f6",
        lineWidth: 2,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "Entry",
      });
    }
    if (stopLoss) {
      candleSeries.createPriceLine({
        price: stopLoss,
        color: "#ff4d6a",
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: true,
        title: "SL",
      });
    }
    if (takeProfit) {
      candleSeries.createPriceLine({
        price: takeProfit,
        color: "#00ff88",
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: true,
        title: "TP",
      });
    }

    if (showRSI) {
      const rsi = calcRSI(closes);
      const times = sorted.map((d) => toTime(d.timestamp));

      const rsiSeries = chart.addSeries(LineSeries, {
        color: "#facc15",
        lineWidth: 1,
        priceScaleId: "rsi",
        priceLineVisible: false,
        lastValueVisible: false,
        priceFormat: { type: "price", precision: 1, minMove: 0.1 },
      });

      chart.priceScale("rsi").applyOptions({
        scaleMargins: { top: 0.8, bottom: 0.02 },
        autoScale: false,
      });

      rsiSeries.setData(
        times
          .map((t, i) => (rsi[i] != null ? { time: t, value: rsi[i]! } : null))
          .filter(Boolean) as any
      );

      const rsiOver = chart.addSeries(LineSeries, {
        color: "rgba(255,77,106,0.3)",
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        priceScaleId: "rsi",
        priceLineVisible: false,
        lastValueVisible: false,
      });
      rsiOver.setData(
        times.map((t) => ({ time: t, value: 70 }))
      );

      const rsiUnder = chart.addSeries(LineSeries, {
        color: "rgba(0,255,136,0.3)",
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        priceScaleId: "rsi",
        priceLineVisible: false,
        lastValueVisible: false,
      });
      rsiUnder.setData(
        times.map((t) => ({ time: t, value: 30 }))
      );
    }

    if (showMACD) {
      const macd = calcMACD(closes);
      const times = sorted.map((d) => toTime(d.timestamp));

      const macdLineSeries = chart.addSeries(LineSeries, {
        color: "#3b82f6",
        lineWidth: 1,
        priceScaleId: "macd",
        priceLineVisible: false,
        lastValueVisible: false,
      });

      chart.priceScale("macd").applyOptions({
        scaleMargins: { top: 0.9, bottom: 0.02 },
      });

      macdLineSeries.setData(
        times.slice(26).map((t, i) => ({ time: t, value: macd.macdLine[i + 26] }))
      );

      const signalSeries = chart.addSeries(LineSeries, {
        color: "#ff9f1c",
        lineWidth: 1,
        priceScaleId: "macd",
        priceLineVisible: false,
        lastValueVisible: false,
      });
      signalSeries.setData(
        times.slice(26).map((t, i) => ({ time: t, value: macd.signalLine[i + 26] }))
      );

      const histSeries = chart.addSeries(HistogramSeries, {
        priceScaleId: "macd",
        priceFormat: { type: "price", precision: 6, minMove: 0.000001 },
      });
      histSeries.setData(
        times.slice(26).map((t, i) => ({
          time: t,
          value: macd.histogram[i + 26],
          color: macd.histogram[i + 26] >= 0 ? "rgba(0,255,136,0.4)" : "rgba(255,77,106,0.4)",
        }))
      );
    }

    chart.timeScale().fitContent();
    chartRef.current = chart;
  }, [data, symbol, entryPrice, stopLoss, takeProfit, height, showVolume, showBB, showRSI, showMACD]);

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
