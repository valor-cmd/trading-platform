import { useEffect, useState } from "react";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";
import { runBacktest, getExchangesStatus, getExchangePairs } from "../services/api";

interface BacktestResult {
  symbol: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  final_capital: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  total_pnl_usd: number;
  total_fees_usd: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  trades: {
    entry_time: string;
    pnl_usd: number;
    side: string;
    symbol: string;
    entry_price: number;
    exit_price: number;
    exit_reason: string;
    pnl_pct: number;
    fees_usd: number;
  }[];
}

interface ExchangeInfo {
  type: string;
  chain: string | null;
  connected: boolean;
  pairs: number;
}

interface StrategyPreset {
  id: string;
  name: string;
  botType: string;
  color: string;
  icon: string;
  description: string;
  indicators: string[];
  params: {
    exchange_id: string;
    symbol: string;
    timeframe: string;
    initial_capital: number;
    risk_per_trade_pct: number;
    limit: number;
  };
}

const STRATEGY_PRESETS: StrategyPreset[] = [
  {
    id: "scalper_momentum",
    name: "Momentum Scalp",
    botType: "Scalper Strat",
    color: "#00ff88",
    icon: "⚡",
    description: "High-frequency scalping using RSI oversold/overbought zones with MACD crossover confirmation and Bollinger Band squeeze breakouts. Targets quick 1-2% moves with tight ATR-based stops.",
    indicators: ["RSI(14)", "MACD(12,26,9)", "Bollinger(20,2)", "Volume Spike", "ATR(14)"],
    params: { exchange_id: "binance", symbol: "BTC/USDT", timeframe: "5m", initial_capital: 1000, risk_per_trade_pct: 2, limit: 500 },
  },
  {
    id: "scalper_mean_reversion",
    name: "Mean Reversion Snipe",
    botType: "Snipe Strat",
    color: "#00e5ff",
    icon: "🎯",
    description: "Snipes extreme RSI deviations (<25 or >75) combined with Bollinger Band touches. Enters when price is 2+ standard deviations from mean with volume confirmation. Quick in-and-out trades.",
    indicators: ["RSI(14) extremes", "Bollinger Band touch", "Volume confirm", "EMA(9) direction"],
    params: { exchange_id: "binance", symbol: "ETH/USDT", timeframe: "5m", initial_capital: 1000, risk_per_trade_pct: 2, limit: 500 },
  },
  {
    id: "swing_trend",
    name: "EMA Trend Rider",
    botType: "Swing Strat",
    color: "#3b82f6",
    icon: "〰",
    description: "Swing strategy riding medium-term trends using EMA(9/21/50) alignment with sentiment-weighted entries. Uses Fear & Greed Index as a contrarian filter — buys fear, sells greed. Holds 4h-2d.",
    indicators: ["EMA(9,21,50)", "MACD trend", "Fear & Greed Index", "RSI(14)", "ATR trailing stop"],
    params: { exchange_id: "coinbase", symbol: "BTC/USDT", timeframe: "1h", initial_capital: 2000, risk_per_trade_pct: 2, limit: 500 },
  },
  {
    id: "swing_breakout",
    name: "Support/Resistance Breakout",
    botType: "Swing Strat",
    color: "#8b5cf6",
    icon: "📊",
    description: "Identifies key support/resistance levels and enters on confirmed breakouts with volume expansion. Uses EMA alignment for trend direction and MACD for momentum confirmation. Wider stops for swing holds.",
    indicators: ["S/R levels", "Volume breakout", "EMA(21,50) alignment", "MACD momentum", "Bollinger expansion"],
    params: { exchange_id: "binance", symbol: "SOL/USDT", timeframe: "4h", initial_capital: 2000, risk_per_trade_pct: 2, limit: 300 },
  },
  {
    id: "long_term_macro",
    name: "Macro Sentiment Accumulator",
    botType: "Long-Term Strat",
    color: "#a855f7",
    icon: "📈",
    description: "Long-term accumulation strategy heavily weighted by market sentiment. Buys aggressively during Extreme Fear (FGI < 20), scales in during Fear zones, and takes profit during Extreme Greed. Uses weekly EMA(50/200) golden/death cross.",
    indicators: ["Fear & Greed Index (heavy)", "EMA(50,200) cross", "Weekly RSI", "MACD weekly", "Volume trend"],
    params: { exchange_id: "coinbase", symbol: "BTC/USDT", timeframe: "1d", initial_capital: 5000, risk_per_trade_pct: 1.5, limit: 365 },
  },
  {
    id: "grid_range",
    name: "Grid Bot Range Trader",
    botType: "Grid Bot Strat",
    color: "#ff9f1c",
    icon: "⊞",
    description: "Places a grid of buy/sell orders across a defined price range. Profits from sideways price oscillation by buying dips and selling rips within the range. Uses Bollinger Bands to define dynamic grid boundaries and ATR for grid spacing.",
    indicators: ["Bollinger(20,2) range", "ATR(14) grid spacing", "RSI mean reversion", "Volume profile"],
    params: { exchange_id: "binance", symbol: "ETH/USDT", timeframe: "15m", initial_capital: 2000, risk_per_trade_pct: 1, limit: 500 },
  },
  {
    id: "multi_factor",
    name: "Multi-Factor Convergence",
    botType: "Multi-Factor Strat",
    color: "#f43f5e",
    icon: "◈",
    description: "Requires convergence of 3+ independent signals before entry: RSI zone + MACD crossover + EMA alignment + volume confirmation + sentiment bias. Highest confidence trades only. Scores each factor and requires minimum score of 4/6.",
    indicators: ["RSI(14) zone", "MACD crossover", "EMA(9,21,50) align", "Volume spike", "Bollinger position", "Sentiment bias"],
    params: { exchange_id: "binance", symbol: "BTC/USDT", timeframe: "1h", initial_capital: 3000, risk_per_trade_pct: 2, limit: 500 },
  },
  {
    id: "arb_cross_exchange",
    name: "Cross-Exchange Arbitrage",
    botType: "Arbitrage Strat",
    color: "#06b6d4",
    icon: "⇄",
    description: "Scans price differentials across 9+ CEXs and DEXs simultaneously. Executes when spread exceeds 0.3% after fees. Simultaneous buy on cheaper exchange and sell on expensive one. Max 5% capital per trade, 3 concurrent positions.",
    indicators: ["Price spread > 0.3%", "Fee calculation", "Liquidity check", "Slippage estimate"],
    params: { exchange_id: "binance", symbol: "BTC/USDT", timeframe: "1m", initial_capital: 5000, risk_per_trade_pct: 5, limit: 200 },
  },
];

const CustomTooltip = ({ active, payload }: { active?: boolean; payload?: { value: number }[] }) => {
  if (active && payload?.length) {
    return (
      <div style={{
        background: "#1e1e1e",
        border: "1px solid #222",
        borderRadius: 12,
        padding: "8px 12px",
        fontSize: "0.8rem",
      }}>
        <div style={{ color: "#00ff88", fontWeight: 600 }}>${payload[0].value.toFixed(2)}</div>
      </div>
    );
  }
  return null;
};

function Backtest() {
  const [form, setForm] = useState({
    exchange_id: "coinbase",
    symbol: "BTC/USDT",
    timeframe: "1h",
    initial_capital: 1000,
    risk_per_trade_pct: 2,
    limit: 500,
  });
  const [activePreset, setActivePreset] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [exchanges, setExchanges] = useState<Record<string, ExchangeInfo>>({});
  const [symbols, setSymbols] = useState<string[]>([]);
  const [symbolSearch, setSymbolSearch] = useState("");
  const [symbolDropdownOpen, setSymbolDropdownOpen] = useState(false);
  const [loadingSymbols, setLoadingSymbols] = useState(false);

  useEffect(() => {
    getExchangesStatus().then((res) => {
      const exs = res.data?.exchanges ?? {};
      setExchanges(exs);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!form.exchange_id) return;
    setLoadingSymbols(true);
    getExchangePairs(form.exchange_id, "", 5000).then((res) => {
      const pairs: string[] = res.data?.pairs ?? [];
      setSymbols(pairs);
      if (pairs.length > 0 && !pairs.includes(form.symbol)) {
        const usdt = pairs.find((p) => p.includes("/USDT") || p.includes("/USD"));
        if (usdt) setForm((f) => ({ ...f, symbol: usdt }));
      }
    }).catch(() => setSymbols([]))
      .finally(() => setLoadingSymbols(false));
  }, [form.exchange_id]);

  const handlePresetSelect = (preset: StrategyPreset) => {
    setActivePreset(preset.id);
    setForm(preset.params);
    setResult(null);
  };

  const handleRun = async () => {
    setLoading(true);
    try {
      const res = await runBacktest(form);
      setResult(res.data);
    } catch {
      alert("Backtest failed. Make sure exchange is connected.");
    }
    setLoading(false);
  };

  const equityCurve = result?.trades.reduce<{ idx: number; equity: number }[]>((acc, trade, i) => {
    const prev = acc.length > 0 ? acc[acc.length - 1].equity : (result?.initial_capital ?? 1000);
    acc.push({ idx: i + 1, equity: +(prev + trade.pnl_usd).toFixed(2) });
    return acc;
  }, []) ?? [];

  const profitable = result ? result.final_capital >= result.initial_capital : true;

  const exchangeEntries = Object.entries(exchanges)
    .filter(([, v]) => v.connected)
    .sort((a, b) => {
      if (a[1].type === "cex" && b[1].type !== "cex") return -1;
      if (a[1].type !== "cex" && b[1].type === "cex") return 1;
      return a[0].localeCompare(b[0]);
    });

  const filteredSymbols = symbolSearch
    ? symbols.filter((s) => s.toLowerCase().includes(symbolSearch.toLowerCase())).slice(0, 50)
    : symbols.slice(0, 50);

  const formatExchangeName = (id: string, info: ExchangeInfo) => {
    const label = id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    return info.type === "dex" ? `${label} (DEX)` : label;
  };

  return (
    <div>
      <div className="page-header">
        <h2>Backtesting</h2>
      </div>

      <div className="mb-md">
        <h3 style={{ marginBottom: "0.75rem" }}>Strategy Presets</h3>
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          gap: "0.75rem",
        }}>
          {STRATEGY_PRESETS.map((preset) => (
            <div
              key={preset.id}
              onClick={() => handlePresetSelect(preset)}
              style={{
                background: activePreset === preset.id ? "rgba(255,255,255,0.06)" : "var(--card-bg, #141414)",
                border: activePreset === preset.id ? `1px solid ${preset.color}` : "1px solid var(--border, #222)",
                borderRadius: 12,
                padding: "1rem",
                cursor: "pointer",
                transition: "all 0.2s",
                position: "relative",
                overflow: "hidden",
              }}
              onMouseEnter={(e) => {
                if (activePreset !== preset.id) e.currentTarget.style.border = `1px solid ${preset.color}55`;
              }}
              onMouseLeave={(e) => {
                if (activePreset !== preset.id) e.currentTarget.style.border = "1px solid var(--border, #222)";
              }}
            >
              <div style={{
                position: "absolute",
                top: 0,
                left: 0,
                right: 0,
                height: 3,
                background: preset.color,
                opacity: activePreset === preset.id ? 1 : 0.3,
              }} />
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                <span style={{ fontSize: "1.2rem" }}>{preset.icon}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>{preset.name}</div>
                  <span style={{
                    fontSize: "0.6rem",
                    padding: "0.1rem 0.4rem",
                    borderRadius: 20,
                    background: `${preset.color}20`,
                    color: preset.color,
                    fontWeight: 600,
                    letterSpacing: "0.02em",
                  }}>
                    {preset.botType}
                  </span>
                </div>
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-secondary, #888)", lineHeight: 1.5, marginBottom: "0.5rem" }}>
                {preset.description}
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem" }}>
                {preset.indicators.map((ind) => (
                  <span key={ind} style={{
                    fontSize: "0.6rem",
                    padding: "0.15rem 0.4rem",
                    borderRadius: 6,
                    background: "rgba(255,255,255,0.06)",
                    color: "var(--text-secondary, #888)",
                    border: "1px solid rgba(255,255,255,0.08)",
                  }}>
                    {ind}
                  </span>
                ))}
              </div>
              <div style={{
                display: "flex",
                gap: "0.75rem",
                marginTop: "0.5rem",
                fontSize: "0.65rem",
                color: "var(--text-tertiary, #666)",
              }}>
                <span>{preset.params.timeframe} candles</span>
                <span>${preset.params.initial_capital}</span>
                <span>{preset.params.risk_per_trade_pct}% risk</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card mb-md">
        <div className="card-header">
          <h3>Strategy Tester</h3>
          {activePreset && (
            <span style={{
              fontSize: "0.7rem",
              padding: "0.15rem 0.5rem",
              borderRadius: 20,
              background: `${STRATEGY_PRESETS.find((p) => p.id === activePreset)?.color ?? "#fff"}20`,
              color: STRATEGY_PRESETS.find((p) => p.id === activePreset)?.color ?? "#fff",
              fontWeight: 600,
            }}>
              {STRATEGY_PRESETS.find((p) => p.id === activePreset)?.name}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
          <div className="input-group" style={{ flex: 1, minWidth: 160 }}>
            <label className="input-label">Exchange / DEX</label>
            <select
              value={form.exchange_id}
              onChange={(e) => setForm({ ...form, exchange_id: e.target.value, symbol: "" })}
            >
              {exchangeEntries.length === 0 && (
                <option value={form.exchange_id}>{form.exchange_id}</option>
              )}
              {exchangeEntries.map(([id, info]) => (
                <option key={id} value={id}>
                  {formatExchangeName(id, info)} ({info.pairs} pairs)
                </option>
              ))}
            </select>
          </div>
          <div className="input-group" style={{ flex: 1, minWidth: 160, position: "relative" }}>
            <label className="input-label">Symbol</label>
            <input
              value={symbolDropdownOpen ? symbolSearch : form.symbol}
              onChange={(e) => {
                setSymbolSearch(e.target.value);
                setSymbolDropdownOpen(true);
              }}
              onFocus={() => {
                setSymbolDropdownOpen(true);
                setSymbolSearch(form.symbol);
              }}
              onBlur={() => setTimeout(() => setSymbolDropdownOpen(false), 200)}
              placeholder={loadingSymbols ? "Loading..." : "Search symbol..."}
            />
            {symbolDropdownOpen && filteredSymbols.length > 0 && (
              <div style={{
                position: "absolute",
                top: "100%",
                left: 0,
                right: 0,
                background: "#1a1a1a",
                border: "1px solid #333",
                borderRadius: 8,
                maxHeight: 200,
                overflowY: "auto",
                zIndex: 100,
              }}>
                {filteredSymbols.map((sym) => (
                  <div
                    key={sym}
                    onMouseDown={() => {
                      setForm({ ...form, symbol: sym });
                      setSymbolSearch(sym);
                      setSymbolDropdownOpen(false);
                    }}
                    style={{
                      padding: "0.5rem 0.75rem",
                      cursor: "pointer",
                      fontSize: "0.85rem",
                      borderBottom: "1px solid #222",
                      background: sym === form.symbol ? "rgba(255,255,255,0.05)" : "transparent",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.08)")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = sym === form.symbol ? "rgba(255,255,255,0.05)" : "transparent")}
                  >
                    {sym}
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="input-group" style={{ flex: 1, minWidth: 100 }}>
            <label className="input-label">Timeframe</label>
            <select value={form.timeframe} onChange={(e) => setForm({ ...form, timeframe: e.target.value })}>
              <option value="1m">1m</option>
              <option value="5m">5m</option>
              <option value="15m">15m</option>
              <option value="1h">1h</option>
              <option value="4h">4h</option>
              <option value="1d">1d</option>
            </select>
          </div>
          <div className="input-group" style={{ flex: 1, minWidth: 100 }}>
            <label className="input-label">Capital ($)</label>
            <input type="number" value={form.initial_capital} onChange={(e) => setForm({ ...form, initial_capital: +e.target.value })} />
          </div>
          <div className="input-group" style={{ flex: 1, minWidth: 80 }}>
            <label className="input-label">Risk %</label>
            <input type="number" value={form.risk_per_trade_pct} onChange={(e) => setForm({ ...form, risk_per_trade_pct: +e.target.value })} />
          </div>
          <div className="input-group" style={{ flex: 1, minWidth: 80 }}>
            <label className="input-label">Candles</label>
            <input type="number" value={form.limit} onChange={(e) => setForm({ ...form, limit: +e.target.value })} />
          </div>
          <button
            className="btn btn-primary"
            onClick={handleRun}
            disabled={loading || !form.symbol}
            style={{ marginTop: "auto" }}
          >
            {loading ? "Running..." : "Run Backtest"}
          </button>
        </div>
      </div>

      {result && (
        <>
          <div className="grid grid-4 mb-md">
            <div className={`card stat-card ${profitable ? "green" : "red"}`}>
              <h3>Final Capital</h3>
              <div className={`value ${profitable ? "positive" : "negative"}`}>
                ${result.final_capital.toLocaleString()}
              </div>
              <div className="value-sm">
                {profitable ? "+" : ""}{((result.final_capital - result.initial_capital) / result.initial_capital * 100).toFixed(1)}%
              </div>
            </div>
            <div className="card stat-card">
              <h3>Win Rate</h3>
              <div className="value">{result.win_rate}%</div>
              <div className="value-sm">{result.winning_trades}W / {result.losing_trades}L</div>
            </div>
            <div className="card stat-card">
              <h3>Sharpe Ratio</h3>
              <div className="value">{result.sharpe_ratio}</div>
              <div className="value-sm">{result.sharpe_ratio >= 1 ? "Good" : result.sharpe_ratio >= 0.5 ? "Moderate" : "Low"}</div>
            </div>
            <div className="card stat-card red">
              <h3>Max Drawdown</h3>
              <div className="value negative">{result.max_drawdown_pct}%</div>
              <div className="value-sm">Peak to trough</div>
            </div>
          </div>

          <div className="grid grid-2 mb-md">
            <div className="card">
              <h3>Equity Curve</h3>
              <div className="chart-container">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={equityCurve}>
                    <defs>
                      <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={profitable ? "#00ff88" : "#ff4d6a"} stopOpacity={0.15} />
                        <stop offset="100%" stopColor={profitable ? "#00ff88" : "#ff4d6a"} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="idx" stroke="#555" fontSize={11} tickLine={false} axisLine={false} />
                    <YAxis stroke="#555" fontSize={11} tickLine={false} axisLine={false} />
                    <Tooltip content={<CustomTooltip />} />
                    <Area
                      type="monotone"
                      dataKey="equity"
                      stroke={profitable ? "#00ff88" : "#ff4d6a"}
                      strokeWidth={2}
                      fill="url(#eqGrad)"
                      dot={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="card">
              <h3>Summary</h3>
              <div style={{ marginTop: "0.5rem" }}>
                {[
                  { label: "Symbol", value: result.symbol },
                  { label: "Timeframe", value: result.timeframe },
                  { label: "Period", value: `${result.start_date?.slice(0, 10)} → ${result.end_date?.slice(0, 10)}` },
                  { label: "Total Trades", value: String(result.total_trades) },
                  { label: "Total P&L", value: `$${result.total_pnl_usd.toFixed(2)}`, cls: result.total_pnl_usd >= 0 ? "positive" : "negative" },
                  { label: "Total Fees", value: `$${result.total_fees_usd.toFixed(2)}`, cls: "negative" },
                  { label: "Initial → Final", value: `$${result.initial_capital} → $${result.final_capital}` },
                ].map((row) => (
                  <div className="flex-between" key={row.label} style={{ padding: "0.55rem 0", borderBottom: "1px solid var(--border)" }}>
                    <span className="text-sm text-secondary">{row.label}</span>
                    <span className={`text-sm font-semibold ${row.cls ?? ""}`}>{row.value}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="card">
            <h3>Trade Log ({result.trades.length} trades)</h3>
            <div style={{ maxHeight: 400, overflow: "auto", marginTop: "0.5rem" }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Side</th>
                    <th>Entry</th>
                    <th>Exit</th>
                    <th>P&L</th>
                    <th>%</th>
                    <th>Fees</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((t, i) => (
                    <tr key={i}>
                      <td className="text-secondary">{i + 1}</td>
                      <td>
                        <span className={`badge ${t.side === "buy" ? "badge-active" : "badge-stopped"}`} style={{ fontSize: "0.65rem" }}>
                          {t.side.toUpperCase()}
                        </span>
                      </td>
                      <td>${t.entry_price.toLocaleString()}</td>
                      <td>${t.exit_price.toLocaleString()}</td>
                      <td className={t.pnl_usd >= 0 ? "positive" : "negative"}>
                        {t.pnl_usd >= 0 ? "+" : ""}${t.pnl_usd.toFixed(2)}
                      </td>
                      <td className={t.pnl_pct >= 0 ? "positive" : "negative"}>
                        {t.pnl_pct >= 0 ? "+" : ""}{t.pnl_pct}%
                      </td>
                      <td className="text-secondary">${t.fees_usd.toFixed(4)}</td>
                      <td>
                        <span style={{
                          fontSize: "0.7rem",
                          padding: "0.15rem 0.5rem",
                          borderRadius: "var(--radius-full)",
                          background: t.exit_reason === "take_profit" ? "var(--green-dim)" :
                            t.exit_reason === "stop_loss" ? "var(--red-dim)" : "var(--yellow-dim)",
                          color: t.exit_reason === "take_profit" ? "var(--green)" :
                            t.exit_reason === "stop_loss" ? "var(--red)" : "var(--yellow)",
                        }}>
                          {t.exit_reason.replace("_", " ")}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {!result && !loading && (
        <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
          <div style={{ fontSize: "2.5rem", marginBottom: "0.75rem" }}>▦</div>
          <div style={{ fontSize: "1.1rem", fontWeight: 600, marginBottom: "0.5rem" }}>
            Test your strategies
          </div>
          <div className="text-sm text-secondary" style={{ maxWidth: 400, margin: "0 auto" }}>
            Run backtests against historical data to validate trading strategies before deploying them live.
          </div>
        </div>
      )}
    </div>
  );
}

export default Backtest;
