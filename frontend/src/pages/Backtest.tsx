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

      <div className="card mb-md">
        <div className="card-header">
          <h3>Strategy Tester</h3>
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
