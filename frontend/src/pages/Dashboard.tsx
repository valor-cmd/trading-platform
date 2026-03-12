import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";
import {
  getAccountingSummary, getRiskStatus, getBotStatus, getPortfolioChart,
  recordDeposit, recordWithdrawal, rebalanceBuckets, getBotsRunning, getArbStatus,
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
    account_value_usd: number;
  };
  win_rate: {
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    win_rate: number;
  };
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
  };
}

const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: { value: number }[]; label?: string }) => {
  if (active && payload?.length) {
    const ts = label ? new Date(label).toLocaleString() : "";
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
          ${payload[0].value.toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
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
  const [chartData, setChartData] = useState<{ timestamp: string; balance: number }[]>([]);
  const [timeRange, setTimeRange] = useState("1W");
  const [showDeposit, setShowDeposit] = useState(false);
  const [showWithdraw, setShowWithdraw] = useState(false);
  const [depositAmount, setDepositAmount] = useState("");
  const [withdrawAmount, setWithdrawAmount] = useState("");

  const load = async () => {
    try {
      const [s, r, b, p, br, ar] = await Promise.all([
        getAccountingSummary(),
        getRiskStatus(),
        getBotStatus(),
        getPortfolioChart(200),
        getBotsRunning(),
        getArbStatus(),
      ]);
      setSummary(s.data);
      setRisk(r.data);
      setBots(b.data);
      setChartData(p.data);
      setArbStatus(ar.data);
    } catch {
      /* API not connected */
    }
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 10000);
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
    await rebalanceBuckets();
    await load();
  };

  const filterChartByRange = (data: { timestamp: string; balance: number }[], range: string) => {
    if (range === "ALL" || data.length === 0) return data;
    const now = new Date();
    const rangeMs: Record<string, number> = {
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

  const filteredChart = filterChartByRange(chartData, timeRange);
  const s = summary?.summary;
  const pnlPositive = (s?.net_pnl_usd ?? 0) >= 0;

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
          ${s?.account_value_usd?.toLocaleString("en", { minimumFractionDigits: 2 }) ?? "0.00"}
        </div>
        <div style={{
          fontSize: "0.95rem",
          fontWeight: 600,
          color: pnlPositive ? "var(--green)" : "var(--red)",
          marginTop: "0.35rem",
        }}>
          {pnlPositive ? "+" : ""}${s?.net_pnl_usd?.toFixed(2) ?? "0.00"}
          {s?.net_deposits_usd ? ` (${((s?.net_pnl_usd ?? 0) / s.net_deposits_usd * 100).toFixed(1)}%)` : ""}
        </div>

        <div className="chart-container" style={{ marginTop: "1rem" }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={filteredChart}>
              <defs>
                <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={pnlPositive ? "#00ff88" : "#ff4d6a"} stopOpacity={0.2} />
                  <stop offset="100%" stopColor={pnlPositive ? "#00ff88" : "#ff4d6a"} stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="timestamp" hide />
              <YAxis hide domain={["auto", "auto"]} padding={{ top: 10, bottom: 10 }} />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="balance"
                stroke={pnlPositive ? "#00ff88" : "#ff4d6a"}
                strokeWidth={2}
                fill="url(#pnlGrad)"
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div style={{ display: "flex", justifyContent: "center", gap: "0.25rem", marginTop: "0.75rem" }}>
          {["5M", "15M", "1H", "4H", "1D", "1W", "ALL"].map((range) => (
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
          <span className="action-btn-label">Rebalance</span>
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
          </div>
        </div>
        <div className="card stat-card">
          <h3>Total Trades</h3>
          <div className="value">{s?.total_trades ?? 0}</div>
          <div className="value-sm">All time</div>
        </div>
        <div className="card stat-card">
          <h3>Total Fees</h3>
          <div className="value">${s?.total_fees_usd?.toFixed(2) ?? "0.00"}</div>
          <div className="value-sm">Paid to exchanges</div>
        </div>
        <div className="card stat-card">
          <h3>Daily P&L</h3>
          <div className={`value ${(risk?.daily_pnl_usd ?? 0) >= 0 ? "positive" : "negative"}`}>
            ${risk?.daily_pnl_usd?.toFixed(2) ?? "0.00"}
          </div>
          <div className="value-sm">
            {risk?.circuit_breaker_active
              ? <span className="negative">Circuit breaker active</span>
              : "Within limits"
            }
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
            { label: "Scalper", pct: risk?.bucket_allocation?.scalper_pct ?? 20, color: "#00ff88" },
            { label: "Swing", pct: risk?.bucket_allocation?.swing_pct ?? 40, color: "#3b82f6" },
            { label: "Long-Term", pct: risk?.bucket_allocation?.long_term_pct ?? 40, color: "#a855f7" },
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
    </div>
  );
}

export default Dashboard;
