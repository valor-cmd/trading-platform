import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ComposedChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Scatter, Cell,
} from "recharts";
import {
  getAccountingSummary, getRiskStatus, getBotStatus, getPortfolioChart,
  recordDeposit, recordWithdrawal, rebalanceBuckets, getBotsRunning, getArbStatus,
  getLiveBalance, resetAccount,
} from "../services/api";

interface Summary {
  summary: {
    total_deposits_usd: number;
    total_withdrawals_usd: number;
    net_deposits_usd: number;
    total_pnl_usd: number;
    total_fees_usd: number;
    net_pnl_usd: number;
    total_trades: number;
    open_trades: number;
    closed_trades: number;
    account_value_usd: number;
    total_fees_all_time: number;
    cash_balance_usd: number;
    open_position_value_usd: number;
  };
  win_rate: {
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    win_rate: number;
  };
}

interface LiveBalance {
  cash_balance_usd: number;
  open_position_value_usd: number;
  total_live_balance_usd: number;
  open_trade_count: number;
}

interface TradeEvent {
  timestamp: string;
  side: string;
  symbol: string;
  price: number;
  quantity: number;
  bot_type: string;
  type: "entry" | "exit";
  trade_id: number;
  stop_loss?: number;
  take_profit?: number;
  entry_fee?: number;
  strategy?: string;
  signal_score?: number;
  status?: string;
  pnl_usd?: number;
  pnl_pct?: number;
  exit_fee?: number;
  exit_reason?: string;
  entry_price?: number;
}

interface RiskStatus {
  daily_pnl_usd: number;
  circuit_breaker_active: boolean;
  max_daily_loss_usd: number;
  paper_trading: boolean;
  bucket_allocation: {
    scalper_pct: number;
    swing_pct: number;
    long_term_pct: number;
    arbitrage_pct: number;
  };
}

const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: { value: number; dataKey: string }[]; label?: string }) => {
  if (active && payload?.length) {
    const ts = label ? new Date(label).toLocaleString() : "";
    const balanceEntry = payload.find((p) => p.dataKey === "balance");
    const buyEntry = payload.find((p) => p.dataKey === "buy" && p.value != null);
    const sellEntry = payload.find((p) => p.dataKey === "sell" && p.value != null);
    return (
      <div style={{
        background: "#1e1e1e",
        border: "1px solid #222",
        borderRadius: 12,
        padding: "8px 12px",
        fontSize: "0.8rem",
      }}>
        <div style={{ color: "#8a8a8a", marginBottom: 2 }}>{ts}</div>
        <div style={{ color: "#00ff88", fontWeight: 600 }}>
          ${balanceEntry?.value?.toLocaleString("en", { minimumFractionDigits: 5, maximumFractionDigits: 5 }) ?? "—"}
        </div>
        {buyEntry && <div style={{ color: "#00ff88", fontSize: "0.7rem", marginTop: 2 }}>BUY</div>}
        {sellEntry && <div style={{ color: "#ff4d6a", fontSize: "0.7rem", marginTop: 2 }}>SELL</div>}
        {payload.find((p) => p.dataKey === "deposit" && p.value != null) && (
          <div style={{ color: "#ff9f1c", fontSize: "0.7rem", marginTop: 2 }}>DEPOSIT</div>
        )}
      </div>
    );
  }
  return null;
};

function Dashboard() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [risk, setRisk] = useState<RiskStatus | null>(null);
  const [bots, setBots] = useState<Record<string, { active_trades: number; running?: boolean }>>({});
  const [arbStatus, setArbStatus] = useState<{ running: boolean; trades_executed: number; actionable: number } | null>(null);
  const [liveBalance, setLiveBalance] = useState<LiveBalance | null>(null);
  const [chartData, setChartData] = useState<{ timestamp: string; balance: number; buy?: number; sell?: number; deposit?: number }[]>([]);
  const [timeRange, setTimeRange] = useState("1W");
  const [showDeposit, setShowDeposit] = useState(false);
  const [showWithdraw, setShowWithdraw] = useState(false);
  const [depositAmount, setDepositAmount] = useState("");
  const [withdrawAmount, setWithdrawAmount] = useState("");
  const [rebalanceMsg, setRebalanceMsg] = useState("");
  const [showTradeDots, setShowTradeDots] = useState(true);
  const [selectedTrade, setSelectedTrade] = useState<TradeEvent | null>(null);
  const [tradeEventsMap, setTradeEventsMap] = useState<Record<string, TradeEvent>>({});

  const load = async () => {
    try {
      const results = await Promise.allSettled([
        getAccountingSummary(),
        getRiskStatus(),
        getBotStatus(),
        getPortfolioChart(500),
        getBotsRunning(),
        getArbStatus(),
        getLiveBalance(),
      ]);
      const val = (i: number) => results[i].status === "fulfilled" ? (results[i] as PromiseFulfilledResult<any>).value : null;
      const s = val(0);
      const r = val(1);
      const b = val(2);
      const p = val(3);
      const ar = val(5);
      const lb = val(6);
      if (s) setSummary(s.data);
      if (r) setRisk(r.data);
      if (b) setBots(b.data);
      if (ar) setArbStatus(ar.data);
      if (lb) setLiveBalance(lb.data);

      const chartPoints: { timestamp: string; balance: number }[] = p?.data?.chart ?? p?.data ?? [];
      const tradeEvents: TradeEvent[] = p?.data?.trades ?? [];
      const depositEvents: { timestamp: string; type: string }[] = p?.data?.events ?? [];

      const allMarkers: { timestamp: string; kind: "buy" | "sell" | "deposit"; used: boolean; tradeEvent?: TradeEvent }[] = [];
      const teMap: Record<string, TradeEvent> = {};
      for (const te of tradeEvents) {
        allMarkers.push({ timestamp: te.timestamp, kind: te.side === "buy" ? "buy" : "sell", used: false, tradeEvent: te });
      }
      for (const de of depositEvents) {
        if (de.type === "deposit") {
          allMarkers.push({ timestamp: de.timestamp, kind: "deposit", used: false });
        }
      }

      const merged: typeof chartData = chartPoints.map((pt) => {
        const ptTime = new Date(pt.timestamp).getTime();
        let bestIdx = -1;
        let bestDiff = Infinity;
        for (let i = 0; i < allMarkers.length; i++) {
          if (allMarkers[i].used) continue;
          const diff = Math.abs(new Date(allMarkers[i].timestamp).getTime() - ptTime);
          if (diff < 30000 && diff < bestDiff) {
            bestDiff = diff;
            bestIdx = i;
          }
        }
        if (bestIdx >= 0) {
          allMarkers[bestIdx].used = true;
          const mk = allMarkers[bestIdx];
          if (mk.tradeEvent) teMap[pt.timestamp] = mk.tradeEvent;
          return {
            ...pt,
            buy: mk.kind === "buy" ? pt.balance : undefined,
            sell: mk.kind === "sell" ? pt.balance : undefined,
            deposit: mk.kind === "deposit" ? pt.balance : undefined,
          };
        }
        return { ...pt, buy: undefined, sell: undefined, deposit: undefined };
      });

      for (const mk of allMarkers) {
        if (mk.used) continue;
        if (chartPoints.length > 0) {
          const closest = chartPoints.reduce((prev, curr) =>
            Math.abs(new Date(curr.timestamp).getTime() - new Date(mk.timestamp).getTime()) <
            Math.abs(new Date(prev.timestamp).getTime() - new Date(mk.timestamp).getTime()) ? curr : prev
          );
          merged.push({
            timestamp: mk.timestamp,
            balance: closest.balance,
            buy: mk.kind === "buy" ? closest.balance : undefined,
            sell: mk.kind === "sell" ? closest.balance : undefined,
            deposit: mk.kind === "deposit" ? closest.balance : undefined,
          });
        }
      }

      for (const mk of allMarkers) {
        if (!mk.used && mk.tradeEvent) {
          teMap[mk.timestamp] = mk.tradeEvent;
        }
      }

      merged.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
      setChartData(merged);
      setTradeEventsMap(teMap);
    } catch {
      /* API not connected */
    }
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleDeposit = async () => {
    const amt = parseFloat(depositAmount);
    if (!amt || amt <= 0) return;
    await recordDeposit({ exchange: "paper", amount_usd: amt, asset: "USDT", asset_amount: amt });
    setDepositAmount("");
    setShowDeposit(false);
    await load();
  };

  const handleWithdraw = async () => {
    const amt = parseFloat(withdrawAmount);
    if (!amt || amt <= 0) return;
    await recordWithdrawal({ exchange: "paper", amount_usd: amt, asset: "USDT", asset_amount: amt });
    setWithdrawAmount("");
    setShowWithdraw(false);
    await load();
  };

  const handleRebalance = async () => {
    try {
      setRebalanceMsg("Rebalancing...");
      const res = await rebalanceBuckets();
      const total = res.data?.total_capital_usd ?? 0;
      setRebalanceMsg(`Rebalanced: $${total.toFixed(2)}`);
      await load();
      setTimeout(() => setRebalanceMsg(""), 3000);
    } catch {
      setRebalanceMsg("Rebalance failed");
      setTimeout(() => setRebalanceMsg(""), 3000);
    }
  };

  const filterChartByRange = (data: typeof chartData, range: string) => {
    if (range === "ALL" || data.length === 0) return data;
    const now = new Date();
    const rangeMs: Record<string, number> = {
      "1M": 1 * 60 * 1000,
      "5M": 5 * 60 * 1000,
      "15M": 15 * 60 * 1000,
      "1H": 60 * 60 * 1000,
      "4H": 4 * 60 * 60 * 1000,
      "1D": 24 * 60 * 60 * 1000,
      "1W": 7 * 24 * 60 * 60 * 1000,
    };
    const ms = rangeMs[range];
    if (!ms) return data;
    const cutoff = new Date(now.getTime() - ms);
    const filtered = data.filter((d) => new Date(d.timestamp) >= cutoff);
    return filtered.length > 0 ? filtered : data.slice(-1);
  };

  const formatXAxisTick = (ts: string) => {
    const d = new Date(ts);
    const rangeMs: Record<string, number> = {
      "1M": 60000, "5M": 300000, "15M": 900000, "1H": 3600000,
      "4H": 14400000, "1D": 86400000, "1W": 604800000,
    };
    const ms = rangeMs[timeRange] ?? 604800000;
    if (ms <= 3600000) {
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } else if (ms <= 86400000) {
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  };

  const filteredChart = filterChartByRange(chartData, timeRange);
  const s = summary?.summary;
  const netPnl = s?.net_pnl_usd ?? 0;
  const pnlPositive = netPnl >= 0;
  const hasClosedTrades = (s?.closed_trades ?? 0) > 0;
  const realizedPnl = s?.total_pnl_usd ?? 0;
  const unrealizedPnl = netPnl - realizedPnl;
  const totalFeesPaid = s?.total_fees_all_time ?? 0;

  return (
    <div>
      <div className="page-header">
        <h2>Portfolio</h2>
        <span className={`badge ${risk?.paper_trading ? "badge-paper" : "badge-active"}`}>
          <span className="badge-dot" />
          {risk?.paper_trading ? "Paper" : "Live"}
        </span>
      </div>

      <div className="card mb-md" style={{ textAlign: "center", padding: "2rem 1.25rem" }}>
        <div style={{ fontSize: "0.8rem", color: "var(--text-tertiary)", marginBottom: "0.5rem" }}>
          Total Balance
        </div>
        <div style={{ fontSize: "2.5rem", fontWeight: 800, letterSpacing: "-0.03em" }}>
          ${s?.account_value_usd?.toLocaleString("en", { minimumFractionDigits: 5, maximumFractionDigits: 5 }) ?? "0.00000"}
        </div>
        <div style={{
          fontSize: "0.95rem",
          fontWeight: 600,
          color: pnlPositive ? "var(--green)" : "var(--red)",
          marginTop: "0.35rem",
        }}>
          {pnlPositive ? "+" : ""}${netPnl.toFixed(5)}
          {s?.net_deposits_usd ? ` (${(netPnl / s.net_deposits_usd * 100).toFixed(2)}%)` : ""}
          <span style={{ fontSize: "0.7rem", color: "var(--text-secondary)", marginLeft: "0.5rem" }}>
            {!hasClosedTrades ? "unrealized" : unrealizedPnl !== 0 ? `${realizedPnl >= 0 ? "+" : ""}$${realizedPnl.toFixed(2)} realized` : ""}
          </span>
        </div>
        <div style={{
          display: "flex", justifyContent: "center", gap: "1.5rem",
          marginTop: "0.5rem", fontSize: "0.75rem", color: "var(--text-secondary)",
        }}>
          <span>Cash: ${(s?.cash_balance_usd ?? liveBalance?.cash_balance_usd ?? 0).toFixed(5)}</span>
          <span>Positions: ${(s?.open_position_value_usd ?? liveBalance?.open_position_value_usd ?? 0).toFixed(5)}</span>
          <span style={{ color: "var(--red)" }}>Fees: -${totalFeesPaid.toFixed(5)}</span>
        </div>

        <div className="chart-container" style={{ marginTop: "1rem" }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={filteredChart} margin={{ top: 5, right: 50, left: 0, bottom: 5 }}>
              <defs>
                <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={pnlPositive ? "#00ff88" : "#ff4d6a"} stopOpacity={0.2} />
                  <stop offset="100%" stopColor={pnlPositive ? "#00ff88" : "#ff4d6a"} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis
                dataKey="timestamp"
                tickFormatter={formatXAxisTick}
                stroke="#555"
                fontSize={10}
                tickLine={false}
                axisLine={{ stroke: "#333" }}
                minTickGap={40}
              />
              <YAxis
                orientation="right"
                stroke="#555"
                fontSize={10}
                tickLine={false}
                axisLine={{ stroke: "#333" }}
                domain={["auto", "auto"]}
                padding={{ top: 10, bottom: 10 }}
                tickFormatter={(v: number) => `$${v.toFixed(2)}`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="balance"
                stroke={pnlPositive ? "#00ff88" : "#ff4d6a"}
                strokeWidth={2}
                fill="url(#pnlGrad)"
                dot={false}
              />
              {showTradeDots && (
                <Scatter dataKey="buy" shape="circle" fill="#00ff88" isAnimationActive={false}
                  onClick={(_: unknown, idx: number) => {
                    const pt = filteredChart[idx];
                    if (pt?.buy != null) {
                      const te = tradeEventsMap[pt.timestamp];
                      if (te) setSelectedTrade(te);
                    }
                  }}
                  cursor="pointer"
                >
                  {filteredChart.map((entry, i) => (
                    entry.buy != null
                      ? <Cell key={i} fill="#00ff88" stroke="#000" strokeWidth={1} r={5} />
                      : <Cell key={i} fill="transparent" stroke="transparent" r={0} />
                  ))}
                </Scatter>
              )}
              {showTradeDots && (
                <Scatter dataKey="sell" shape="circle" fill="#ff4d6a" isAnimationActive={false}
                  onClick={(_: unknown, idx: number) => {
                    const pt = filteredChart[idx];
                    if (pt?.sell != null) {
                      const te = tradeEventsMap[pt.timestamp];
                      if (te) setSelectedTrade(te);
                    }
                  }}
                  cursor="pointer"
                >
                  {filteredChart.map((entry, i) => (
                    entry.sell != null
                      ? <Cell key={i} fill="#ff4d6a" stroke="#000" strokeWidth={1} r={5} />
                      : <Cell key={i} fill="transparent" stroke="transparent" r={0} />
                  ))}
                </Scatter>
              )}
              {showTradeDots && (
                <Scatter dataKey="deposit" shape="diamond" fill="#ff9f1c" isAnimationActive={false}>
                  {filteredChart.map((entry, i) => (
                    entry.deposit != null
                      ? <Cell key={i} fill="#ff9f1c" stroke="#000" strokeWidth={1} r={6} />
                      : <Cell key={i} fill="transparent" stroke="transparent" r={0} />
                  ))}
                </Scatter>
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: "0.5rem", marginTop: "0.75rem", flexWrap: "wrap" }}>
          <div style={{ display: "flex", gap: "0.25rem" }}>
            {["1M", "5M", "15M", "1H", "4H", "1D", "1W", "ALL"].map((range) => (
              <button
                key={range}
                className={`tab ${timeRange === range ? "active" : ""}`}
                onClick={() => setTimeRange(range)}
                style={{ padding: "0.4rem 0.75rem", fontSize: "0.75rem", borderBottom: "none" }}
              >
                {range}
              </button>
            ))}
          </div>
          <button
            onClick={() => setShowTradeDots(!showTradeDots)}
            style={{
              padding: "0.35rem 0.75rem",
              fontSize: "0.7rem",
              background: showTradeDots ? "rgba(255,255,255,0.1)" : "transparent",
              border: "1px solid #444",
              borderRadius: 20,
              color: showTradeDots ? "#fff" : "#666",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
            }}
          >
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#00ff88", display: "inline-block" }} />
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#ff4d6a", display: "inline-block" }} />
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#ff9f1c", display: "inline-block" }} />
            {showTradeDots ? "Dots On" : "Dots Off"}
          </button>
        </div>
      </div>

      <div className="action-buttons mb-md">
        <div className="action-btn" onClick={() => setShowDeposit(!showDeposit)} style={{ cursor: "pointer" }}>
          <div className="action-btn-circle">↑</div>
          <span className="action-btn-label">Deposit</span>
        </div>
        <div className="action-btn" onClick={() => setShowWithdraw(!showWithdraw)} style={{ cursor: "pointer" }}>
          <div className="action-btn-circle">↓</div>
          <span className="action-btn-label">Withdraw</span>
        </div>
        <div className="action-btn" onClick={handleRebalance} style={{ cursor: "pointer" }}>
          <div className="action-btn-circle">⟳</div>
          <span className="action-btn-label">{rebalanceMsg || "Rebalance"}</span>
        </div>
        <div className="action-btn" onClick={async () => {
          if (window.confirm("Reset account to zero? This clears all trades, deposits, and balance.")) {
            await resetAccount();
            await load();
          }
        }} style={{ cursor: "pointer" }}>
          <div className="action-btn-circle" style={{ color: "#ff4d6a" }}>✕</div>
          <span className="action-btn-label">Reset</span>
        </div>
        <div className="action-btn" onClick={() => navigate("/accounting")} style={{ cursor: "pointer" }}>
          <div className="action-btn-circle">⋯</div>
          <span className="action-btn-label">More</span>
        </div>
      </div>

      {showDeposit && (
        <div className="card mb-md" style={{ padding: "1rem 1.25rem" }}>
          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
            <div className="input-group" style={{ flex: 1, minWidth: 150 }}>
              <label className="input-label">Deposit Amount (USD)</label>
              <input
                type="number"
                value={depositAmount}
                onChange={(e) => setDepositAmount(e.target.value)}
                placeholder="e.g. 1000"
              />
            </div>
            <button className="btn btn-success" onClick={handleDeposit} style={{ marginTop: "auto" }}>
              Deposit
            </button>
            <button className="btn" onClick={() => setShowDeposit(false)} style={{ marginTop: "auto" }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {showWithdraw && (
        <div className="card mb-md" style={{ padding: "1rem 1.25rem" }}>
          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
            <div className="input-group" style={{ flex: 1, minWidth: 150 }}>
              <label className="input-label">Withdraw Amount (USD)</label>
              <input
                type="number"
                value={withdrawAmount}
                onChange={(e) => setWithdrawAmount(e.target.value)}
                placeholder="e.g. 500"
              />
            </div>
            <button className="btn btn-danger" onClick={handleWithdraw} style={{ marginTop: "auto" }}>
              Withdraw
            </button>
            <button className="btn" onClick={() => setShowWithdraw(false)} style={{ marginTop: "auto" }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-4 mb-md">
        <div className="card stat-card green">
          <h3>Win Rate</h3>
          <div className="value">{summary?.win_rate?.win_rate?.toFixed(1) ?? "0.0"}%</div>
          <div className="value-sm">
            {summary?.win_rate?.winning_trades ?? 0}W / {summary?.win_rate?.losing_trades ?? 0}L
            {!hasClosedTrades && (s?.open_trades ?? 0) > 0 && (
              <span style={{ color: "var(--text-tertiary)", marginLeft: 4 }}>(no closes yet)</span>
            )}
          </div>
        </div>
        <div className="card stat-card">
          <h3>Total Trades</h3>
          <div className="value">{s?.total_trades ?? 0}</div>
          <div className="value-sm">
            {s?.open_trades ?? 0} open / {s?.closed_trades ?? 0} closed
          </div>
        </div>
        <div className="card stat-card">
          <h3>Total Fees</h3>
          <div className="value negative">${totalFeesPaid.toFixed(5)}</div>
          <div className="value-sm">Deducted from cash</div>
        </div>
        <div className="card stat-card">
          <h3>Unrealized P&L</h3>
          <div className={`value ${unrealizedPnl >= 0 ? "positive" : "negative"}`}>
            {unrealizedPnl >= 0 ? "+" : ""}${unrealizedPnl.toFixed(5)}
          </div>
          <div className="value-sm">
            {(s?.open_trades ?? 0)} open position{(s?.open_trades ?? 0) !== 1 ? "s" : ""}
            {risk?.circuit_breaker_active && <span className="negative"> | Circuit breaker</span>}
          </div>
        </div>
      </div>

      <div className="grid grid-2 mb-md">
        <div className="card">
          <div className="card-header">
            <h3>Active Bots</h3>
          </div>
          {["scalper", "swing", "long_term"].map((bot) => (
            <div className="asset-row" key={bot}>
              <div className="asset-info">
                <div className="asset-icon">
                  {bot === "scalper" ? "⚡" : bot === "swing" ? "〰" : "📈"}
                </div>
                <div>
                  <div className="asset-name" style={{ textTransform: "capitalize" }}>
                    {bot.replace("_", " ")}
                  </div>
                  <div className="asset-price">
                    {bot === "scalper" ? "5m–15m" : bot === "swing" ? "1h–4h" : "1d–1w"}
                  </div>
                </div>
              </div>
              <div className="asset-value">
                <div className="asset-amount">{bots[bot]?.active_trades ?? 0}</div>
                <div className="asset-usd">open trades</div>
              </div>
            </div>
          ))}
          <div className="asset-row">
            <div className="asset-info">
              <div className="asset-icon">⇄</div>
              <div>
                <div className="asset-name">Arbitrage</div>
                <div className="asset-price">
                  {arbStatus?.running ? "Active" : "Inactive"} · Cross-exchange
                </div>
              </div>
            </div>
            <div className="asset-value">
              <div className="asset-amount">{arbStatus?.trades_executed ?? 0}</div>
              <div className="asset-usd">
                {arbStatus?.actionable ?? 0} opportunities
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <h3>Bucket Allocation</h3>
          </div>
          {[
            { label: "Scalper", pct: risk?.bucket_allocation?.scalper_pct ?? 25, color: "#00ff88" },
            { label: "Swing", pct: risk?.bucket_allocation?.swing_pct ?? 25, color: "#3b82f6" },
            { label: "Long-Term", pct: risk?.bucket_allocation?.long_term_pct ?? 25, color: "#a855f7" },
            { label: "Arbitrage", pct: risk?.bucket_allocation?.arbitrage_pct ?? 25, color: "#ff9f1c" },
          ].map((bucket) => (
            <div key={bucket.label} style={{ marginBottom: "1rem" }}>
              <div className="flex-between mb-sm">
                <span style={{ fontSize: "0.85rem", fontWeight: 500 }}>{bucket.label}</span>
                <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                  {bucket.pct}%
                </span>
              </div>
              <div className="progress-bar">
                <div
                  className="progress-fill"
                  style={{ width: `${bucket.pct}%`, background: bucket.color }}
                />
              </div>
            </div>
          ))}
          <div className="divider" />
          <div className="flex-between">
            <span className="text-sm text-secondary">Max daily loss</span>
            <span className="text-sm font-semibold">${risk?.max_daily_loss_usd ?? 50}</span>
          </div>
        </div>
      </div>
      {selectedTrade && (
        <div
          onClick={() => setSelectedTrade(null)}
          style={{
            position: "fixed",
            top: 0, left: 0, right: 0, bottom: 0,
            background: "rgba(0,0,0,0.7)",
            zIndex: 1000,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "1rem",
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: "#1a1a1a",
              border: "1px solid #333",
              borderRadius: 16,
              padding: "1.5rem",
              maxWidth: 480,
              width: "100%",
              position: "relative",
            }}
          >
            <button
              onClick={() => setSelectedTrade(null)}
              style={{
                position: "absolute", top: 12, right: 16,
                background: "transparent", border: "none", color: "#888",
                fontSize: "1.2rem", cursor: "pointer",
              }}
            >
              x
            </button>

            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
              <div style={{
                width: 40, height: 40, borderRadius: "50%",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: "1.2rem", fontWeight: 700,
                background: selectedTrade.type === "entry"
                  ? (selectedTrade.side === "buy" ? "rgba(0,255,136,0.15)" : "rgba(255,77,106,0.15)")
                  : (selectedTrade.pnl_usd != null && selectedTrade.pnl_usd >= 0 ? "rgba(0,255,136,0.15)" : "rgba(255,77,106,0.15)"),
                color: selectedTrade.type === "entry"
                  ? (selectedTrade.side === "buy" ? "#00ff88" : "#ff4d6a")
                  : (selectedTrade.pnl_usd != null && selectedTrade.pnl_usd >= 0 ? "#00ff88" : "#ff4d6a"),
              }}>
                {selectedTrade.type === "entry" ? (selectedTrade.side === "buy" ? "B" : "S") : (selectedTrade.pnl_usd != null && selectedTrade.pnl_usd >= 0 ? "+" : "-")}
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: "1.1rem" }}>
                  {selectedTrade.type === "entry" ? "Entry" : "Exit"} - {selectedTrade.symbol}
                </div>
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                  <span style={{
                    fontSize: "0.65rem",
                    padding: "0.1rem 0.4rem",
                    borderRadius: 20,
                    background: selectedTrade.side === "buy" ? "rgba(0,255,136,0.15)" : "rgba(255,77,106,0.15)",
                    color: selectedTrade.side === "buy" ? "#00ff88" : "#ff4d6a",
                    fontWeight: 600,
                  }}>
                    {selectedTrade.side.toUpperCase()}
                  </span>
                  {selectedTrade.bot_type && (
                    <span style={{
                      fontSize: "0.65rem",
                      padding: "0.1rem 0.4rem",
                      borderRadius: 20,
                      background: "rgba(255,255,255,0.08)",
                      color: "#aaa",
                      fontWeight: 500,
                      textTransform: "capitalize",
                    }}>
                      {selectedTrade.bot_type.replace("_", " ")} bot
                    </span>
                  )}
                  {selectedTrade.status && (
                    <span style={{
                      fontSize: "0.65rem",
                      padding: "0.1rem 0.4rem",
                      borderRadius: 20,
                      background: selectedTrade.status === "open" ? "rgba(0,255,136,0.1)" : selectedTrade.status === "stopped_out" ? "rgba(255,77,106,0.1)" : "rgba(255,255,255,0.06)",
                      color: selectedTrade.status === "open" ? "#00ff88" : selectedTrade.status === "stopped_out" ? "#ff4d6a" : "#888",
                      fontWeight: 500,
                    }}>
                      {selectedTrade.status.replace("_", " ")}
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div style={{ borderTop: "1px solid #333", paddingTop: "0.75rem" }}>
              {[
                { label: "Time", value: new Date(selectedTrade.timestamp).toLocaleString() },
                { label: "Price", value: `$${selectedTrade.price?.toLocaleString("en", { maximumFractionDigits: 8 }) ?? "—"}` },
                { label: "Quantity", value: selectedTrade.quantity?.toFixed(6) ?? "—" },
                ...(selectedTrade.type === "entry" ? [
                  { label: "Stop Loss", value: selectedTrade.stop_loss ? `$${selectedTrade.stop_loss.toLocaleString("en", { maximumFractionDigits: 8 })}` : "None", cls: "negative" },
                  { label: "Take Profit", value: selectedTrade.take_profit ? `$${selectedTrade.take_profit.toLocaleString("en", { maximumFractionDigits: 8 })}` : "None", cls: "positive" },
                  { label: "Entry Fee", value: selectedTrade.entry_fee != null ? `$${selectedTrade.entry_fee.toFixed(5)}` : "—" },
                  { label: "Signal Score", value: selectedTrade.signal_score != null ? String(selectedTrade.signal_score) : "—" },
                ] : [
                  { label: "Entry Price", value: selectedTrade.entry_price ? `$${selectedTrade.entry_price.toLocaleString("en", { maximumFractionDigits: 8 })}` : "—" },
                  { label: "P&L", value: selectedTrade.pnl_usd != null ? `${selectedTrade.pnl_usd >= 0 ? "+" : ""}$${selectedTrade.pnl_usd.toFixed(5)}` : "—", cls: (selectedTrade.pnl_usd ?? 0) >= 0 ? "positive" : "negative" },
                  { label: "P&L %", value: selectedTrade.pnl_pct != null ? `${selectedTrade.pnl_pct >= 0 ? "+" : ""}${selectedTrade.pnl_pct}%` : "—", cls: (selectedTrade.pnl_pct ?? 0) >= 0 ? "positive" : "negative" },
                  { label: "Exit Fee", value: selectedTrade.exit_fee != null ? `$${selectedTrade.exit_fee.toFixed(5)}` : "—" },
                  { label: "Exit Reason", value: selectedTrade.exit_reason ? selectedTrade.exit_reason.replace("_", " ") : "—",
                    cls: selectedTrade.exit_reason === "take_profit" ? "positive" : selectedTrade.exit_reason === "stop_loss" || selectedTrade.exit_reason === "stopped_out" ? "negative" : undefined },
                ]),
                ...(selectedTrade.strategy ? [{ label: "Strategy", value: selectedTrade.strategy }] : []),
              ].map((row: { label: string; value: string; cls?: string }) => (
                <div key={row.label} style={{
                  display: "flex",
                  justifyContent: "space-between",
                  padding: "0.45rem 0",
                  borderBottom: "1px solid rgba(255,255,255,0.05)",
                }}>
                  <span style={{ fontSize: "0.8rem", color: "#888" }}>{row.label}</span>
                  <span style={{ fontSize: "0.8rem", fontWeight: 600 }} className={row.cls ?? ""}>{row.value}</span>
                </div>
              ))}
            </div>

            {selectedTrade.type === "entry" && selectedTrade.stop_loss != null && selectedTrade.take_profit != null && selectedTrade.price > 0 && (
              <div style={{ marginTop: "0.75rem", padding: "0.75rem", background: "rgba(255,255,255,0.03)", borderRadius: 8 }}>
                <div style={{ fontSize: "0.7rem", color: "#888", marginBottom: "0.4rem", fontWeight: 600 }}>Risk/Reward</div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <div style={{ flex: 1, height: 6, borderRadius: 3, background: "#333", position: "relative", overflow: "hidden" }}>
                    {(() => {
                      const riskDist = Math.abs(selectedTrade.price - (selectedTrade.stop_loss ?? 0));
                      const rewardDist = Math.abs((selectedTrade.take_profit ?? 0) - selectedTrade.price);
                      const total = riskDist + rewardDist;
                      const riskPct = total > 0 ? (riskDist / total) * 100 : 50;
                      return (
                        <>
                          <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${riskPct}%`, background: "#ff4d6a", borderRadius: 3 }} />
                          <div style={{ position: "absolute", right: 0, top: 0, bottom: 0, width: `${100 - riskPct}%`, background: "#00ff88", borderRadius: 3 }} />
                        </>
                      );
                    })()}
                  </div>
                  <span style={{ fontSize: "0.7rem", color: "#aaa", whiteSpace: "nowrap" }}>
                    1:{((Math.abs((selectedTrade.take_profit ?? 0) - selectedTrade.price)) / (Math.abs(selectedTrade.price - (selectedTrade.stop_loss ?? selectedTrade.price)) || 1)).toFixed(1)}
                  </span>
                </div>
              </div>
            )}

            {selectedTrade.type === "exit" && (
              <div style={{
                marginTop: "0.75rem",
                padding: "0.75rem",
                borderRadius: 8,
                background: (selectedTrade.pnl_usd ?? 0) >= 0 ? "rgba(0,255,136,0.06)" : "rgba(255,77,106,0.06)",
                textAlign: "center",
              }}>
                <div style={{ fontSize: "0.7rem", color: "#888", marginBottom: "0.25rem" }}>Trade Result</div>
                <div style={{
                  fontSize: "1.3rem",
                  fontWeight: 700,
                  color: (selectedTrade.pnl_usd ?? 0) >= 0 ? "#00ff88" : "#ff4d6a",
                }}>
                  {(selectedTrade.pnl_usd ?? 0) >= 0 ? "PROFIT" : "LOSS"} {(selectedTrade.pnl_usd ?? 0) >= 0 ? "+" : ""}${(selectedTrade.pnl_usd ?? 0).toFixed(5)}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default Dashboard;
