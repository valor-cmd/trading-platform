import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  getAccountingSummary, getRiskStatus, getBotStatus, getPortfolioChart,
  recordDeposit, recordWithdrawal, rebalanceBuckets, getBotsRunning, getArbStatus,
  getLiveBalance, resetAccount, getOHLCV, getConfig, updateConfig,
  createAccount, startAccountBots, stopAccountBots,
  closeTrade,
} from "../services/api";
import PortfolioChart from "../components/PortfolioChart";
import SymbolChart from "../components/SymbolChart";

interface BotTradeDetail {
  order_id: string;
  symbol: string;
  side: string;
  entry_price: number;
  amount: number;
  position_usd: number;
  stop_loss: number;
  take_profit: number | null;
  opened_at: string;
  reasoning: string;
  signal_confidence: number;
  bot_type: string;
  regime?: string;
  strategy?: string;
  signal_score?: number;
  confirmations?: string[];
}

interface OHLCVBar {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

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
    closed_trades: number;
    open_trades: number;
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
    grid_pct: number;
    mean_reversion_pct: number;
    momentum_pct: number;
    dca_pct: number;
  };
}


interface AccountInfo {
  name: string;
  label: string;
  daily_target_pct: number | null;
  max_daily_loss_usd: number;
  auto_stop_on_target: boolean;
  balance_usd: number;
  active: boolean;
  target_hit: boolean;
}

interface DashboardProps {
  activeAccount: string;
  setActiveAccount: (name: string) => void;
  accounts: AccountInfo[];
  reloadAccounts: () => void;
}

function Dashboard({ activeAccount, setActiveAccount, accounts, reloadAccounts }: DashboardProps) {
  const navigate = useNavigate();
  const [showCreateAccount, setShowCreateAccount] = useState(false);
  const [newAcctName, setNewAcctName] = useState("");
  const [newAcctLabel, setNewAcctLabel] = useState("");
  const [newAcctTarget, setNewAcctTarget] = useState("1");
  const [newAcctLoss, setNewAcctLoss] = useState("50");
  const [newAcctDeposit, setNewAcctDeposit] = useState("100");
  const [newAcctAutoStop, setNewAcctAutoStop] = useState(true);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [risk, setRisk] = useState<RiskStatus | null>(null);
  const [bots, setBots] = useState<Record<string, { active_trades: number; running?: boolean }>>({});
  const [arbStatus, setArbStatus] = useState<{ running: boolean; trades_executed: number; actionable: number } | null>(null);
  const [liveBalance, setLiveBalance] = useState<LiveBalance | null>(null);
  const [chartData, setChartData] = useState<{ timestamp: string; balance: number }[]>([]);
  const [tradeMarkers, setTradeMarkers] = useState<{ timestamp: string; side: string; symbol: string; type: "entry" | "exit"; pnl_usd?: number }[]>([]);
  const [showDeposit, setShowDeposit] = useState(false);
  const [showWithdraw, setShowWithdraw] = useState(false);
  const [depositAmount, setDepositAmount] = useState("");
  const [withdrawAmount, setWithdrawAmount] = useState("");
  const [rebalanceMsg, setRebalanceMsg] = useState("");
  const [selectedTrade, setSelectedTrade] = useState<TradeEvent | null>(null);
  const [activeBotTrades, setActiveBotTrades] = useState<BotTradeDetail[]>([]);
  const [selectedBotTrade, setSelectedBotTrade] = useState<BotTradeDetail | null>(null);
  const [tradeOHLCV, setTradeOHLCV] = useState<OHLCVBar[]>([]);
  const [tradeChartLoading, setTradeChartLoading] = useState(false);
  const [closingTrade, setClosingTrade] = useState(false);
  const [riskCfg, setRiskCfg] = useState({ max_daily_loss_usd: 50, max_position_size_usd: 500, default_stop_loss_pct: 2, max_leverage: 3 });
  const [riskCfgDraft, setRiskCfgDraft] = useState(riskCfg);
  const [riskCfgSaving, setRiskCfgSaving] = useState(false);
  const [riskCfgMsg, setRiskCfgMsg] = useState("");

  const load = async () => {
    try {
      const results = await Promise.allSettled([
        getAccountingSummary(activeAccount),
        getRiskStatus(),
        getBotStatus(activeAccount),
        getPortfolioChart(0, activeAccount),
        getBotsRunning(activeAccount),
        getArbStatus(),
        getLiveBalance(activeAccount),
      ]);
      const val = (i: number) => results[i].status === "fulfilled" ? (results[i] as PromiseFulfilledResult<any>).value : null;
      const s = val(0);
      const r = val(1);
      const p = val(3);
      const br = val(4);
      const ar = val(5);
      const lb = val(6);
      if (s) setSummary(s.data);
      if (r) setRisk(r.data);
      if (br) setBots(br.data);
      if (ar) setArbStatus(ar.data);
      if (lb) setLiveBalance(lb.data);

      const chartPoints: { timestamp: string; balance: number }[] = p?.data?.chart ?? p?.data ?? [];
      const tradeEvents: TradeEvent[] = p?.data?.trades ?? [];

      setChartData(chartPoints);
      setTradeMarkers(
        tradeEvents.map((te) => ({
          timestamp: te.timestamp,
          side: te.side,
          symbol: te.symbol,
          type: te.type,
          pnl_usd: te.pnl_usd,
        }))
      );
    } catch {
      /* API not connected */
    }
  };

  useEffect(() => {
    getConfig().then((r) => {
      const c = { max_daily_loss_usd: r.data.max_daily_loss_usd, max_position_size_usd: r.data.max_position_size_usd, default_stop_loss_pct: r.data.default_stop_loss_pct, max_leverage: r.data.max_leverage };
      setRiskCfg(c);
      setRiskCfgDraft(c);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, [activeAccount]);

  const handleDeposit = async () => {
    const amt = parseFloat(depositAmount);
    if (!amt || amt <= 0) return;
    await recordDeposit({ exchange: "paper", amount_usd: amt, asset: "USDT", asset_amount: amt }, activeAccount);
    setDepositAmount("");
    setShowDeposit(false);
    await load();
  };

  const handleWithdraw = async () => {
    const amt = parseFloat(withdrawAmount);
    if (!amt || amt <= 0) return;
    await recordWithdrawal({ exchange: "paper", amount_usd: amt, asset: "USDT", asset_amount: amt }, activeAccount);
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

  const s = summary?.summary;
  const netPnl = s?.net_pnl_usd ?? 0;
  const pnlPositive = netPnl >= 0;
  const hasClosedTrades = (s?.closed_trades ?? 0) > 0;
  const realizedPnl = s?.total_pnl_usd ?? 0;
  const unrealizedPnl = netPnl - realizedPnl;
  const totalFeesPaid = s?.total_fees_all_time ?? 0;

  return (
    <div>
      <div className="page-header" style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>Portfolio</h2>
        <span className={`badge ${risk?.paper_trading ? "badge-paper" : "badge-active"}`}>
          <span className="badge-dot" />
          {risk?.paper_trading ? "Paper" : "Live"}
        </span>
      </div>
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center", marginBottom: "1rem" }}>
        <select
          value={activeAccount}
          onChange={(e) => setActiveAccount(e.target.value)}
          style={{
            background: "var(--bg-secondary)", color: "var(--text-primary)", border: "1px solid var(--border)",
            borderRadius: 8, padding: "0.5rem 0.75rem", fontSize: "0.85rem", cursor: "pointer",
            flex: "1 1 auto", minWidth: 0, maxWidth: "100%",
          }}
        >
          {accounts.map((a) => (
            <option key={a.name} value={a.name}>
              {a.label}{a.daily_target_pct ? ` (${a.daily_target_pct}%)` : ""}{a.target_hit ? " HIT" : ""}
            </option>
          ))}
        </select>
        <button
          onClick={() => setShowCreateAccount(true)}
          style={{
            background: "var(--accent)", color: "#000", border: "none", borderRadius: 8,
            padding: "0.5rem 0.75rem", fontSize: "0.75rem", fontWeight: 600, cursor: "pointer",
            whiteSpace: "nowrap", flexShrink: 0,
          }}
        >+ New</button>
        {activeAccount !== "default" && (
          <>
            <button
              onClick={async () => { try { await startAccountBots(activeAccount); await load(); } catch {} }}
              style={{ background: "var(--green)", color: "#000", border: "none", borderRadius: 6, padding: "0.5rem 0.6rem", fontSize: "0.7rem", fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap", flexShrink: 0 }}
            >Start</button>
            <button
              onClick={async () => { try { await stopAccountBots(activeAccount); await load(); } catch {} }}
              style={{ background: "var(--red)", color: "#fff", border: "none", borderRadius: 6, padding: "0.5rem 0.6rem", fontSize: "0.7rem", fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap", flexShrink: 0 }}
            >Stop</button>
          </>
        )}
      </div>

      {showCreateAccount && (
        <div className="card mb-md" style={{ padding: "1.5rem" }}>
          <h3 style={{ marginTop: 0, marginBottom: "1rem" }}>Create New Account</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
            <div>
              <label style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Account ID (alphanumeric)</label>
              <input value={newAcctName} onChange={(e) => setNewAcctName(e.target.value.replace(/[^a-zA-Z0-9]/g, ""))}
                placeholder="e.g. daily1pct" style={{ width: "100%", background: "var(--bg-tertiary)", color: "var(--text-primary)", border: "1px solid var(--border)", borderRadius: 8, padding: "0.5rem" }} />
            </div>
            <div>
              <label style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Display Name</label>
              <input value={newAcctLabel} onChange={(e) => setNewAcctLabel(e.target.value)}
                placeholder="e.g. 1% Daily Target" style={{ width: "100%", background: "var(--bg-tertiary)", color: "var(--text-primary)", border: "1px solid var(--border)", borderRadius: 8, padding: "0.5rem" }} />
            </div>
            <div>
              <label style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Daily Target %</label>
              <input value={newAcctTarget} onChange={(e) => setNewAcctTarget(e.target.value)} type="number" step="0.1"
                style={{ width: "100%", background: "var(--bg-tertiary)", color: "var(--text-primary)", border: "1px solid var(--border)", borderRadius: 8, padding: "0.5rem" }} />
            </div>
            <div>
              <label style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Max Daily Loss (USD)</label>
              <input value={newAcctLoss} onChange={(e) => setNewAcctLoss(e.target.value)} type="number"
                style={{ width: "100%", background: "var(--bg-tertiary)", color: "var(--text-primary)", border: "1px solid var(--border)", borderRadius: 8, padding: "0.5rem" }} />
            </div>
            <div>
              <label style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Initial Deposit (USD)</label>
              <input value={newAcctDeposit} onChange={(e) => setNewAcctDeposit(e.target.value)} type="number"
                style={{ width: "100%", background: "var(--bg-tertiary)", color: "var(--text-primary)", border: "1px solid var(--border)", borderRadius: 8, padding: "0.5rem" }} />
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", paddingTop: "1.2rem" }}>
              <input type="checkbox" checked={newAcctAutoStop} onChange={(e) => setNewAcctAutoStop(e.target.checked)} id="autoStop" />
              <label htmlFor="autoStop" style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>Auto-stop bots when target hit</label>
            </div>
          </div>
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem" }}>
            <button
              onClick={async () => {
                try {
                  await createAccount({
                    name: newAcctName,
                    label: newAcctLabel || newAcctName,
                    daily_target_pct: parseFloat(newAcctTarget) || undefined,
                    max_daily_loss_usd: parseFloat(newAcctLoss) || 50,
                    auto_stop_on_target: newAcctAutoStop,
                    initial_deposit_usd: parseFloat(newAcctDeposit) || 0,
                  });
                  setShowCreateAccount(false);
                  setNewAcctName(""); setNewAcctLabel("");
                  await reloadAccounts();
                  setActiveAccount(newAcctName);
                } catch (e: any) {
                  alert(e?.response?.data?.detail || "Failed to create account");
                }
              }}
              style={{ background: "var(--accent)", color: "#000", border: "none", borderRadius: 8, padding: "0.5rem 1.25rem", fontWeight: 600, cursor: "pointer" }}
            >Create</button>
            <button
              onClick={() => setShowCreateAccount(false)}
              style={{ background: "var(--bg-tertiary)", color: "var(--text-secondary)", border: "1px solid var(--border)", borderRadius: 8, padding: "0.5rem 1.25rem", cursor: "pointer" }}
            >Cancel</button>
          </div>
        </div>
      )}

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

        <div style={{ marginTop: "1rem" }}>
          <PortfolioChart
            data={chartData}
            trades={tradeMarkers}
            height={400}
            pnlPositive={pnlPositive}
          />
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
            await resetAccount(activeAccount);
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
            <span style={{ color: "var(--text-tertiary)", marginLeft: 4 }}>
              ({summary?.win_rate?.closed_trades ?? 0} closed{(summary?.win_rate?.open_trades ?? 0) > 0 ? `, ${summary?.win_rate?.open_trades} open` : ""})
            </span>
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
          {[
            { key: "scalper", icon: "S", tf: "5m-15m" },
            { key: "swing", icon: "W", tf: "1h-4h" },
            { key: "long_term", icon: "L", tf: "1d-1w" },
            { key: "grid", icon: "G", tf: "1h-4h" },
            { key: "mean_reversion", icon: "M", tf: "1h-4h" },
            { key: "momentum", icon: "P", tf: "4h-1d" },
            { key: "dca", icon: "D", tf: "1h-4h" },
          ].map((bot) => (
            <div className="asset-row" key={bot.key}>
              <div className="asset-info">
                <div className="asset-icon">{bot.icon}</div>
                <div>
                  <div className="asset-name" style={{ textTransform: "capitalize" }}>
                    {bot.key.replace("_", " ")}
                  </div>
                  <div className="asset-price">{bot.tf}</div>
                </div>
              </div>
              <div className="asset-value" style={{ cursor: (bots[bot.key]?.active_trades ?? 0) > 0 ? "pointer" : "default" }} onClick={async () => {
                const count = bots[bot.key]?.active_trades ?? 0;
                if (count === 0) return;
                try {
                  const res = await getBotStatus();
                  const botData = res.data?.[bot.key];
                  if (botData?.trades?.length > 0) {
                    setActiveBotTrades(botData.trades);
                    const trade = botData.trades[0];
                    setSelectedBotTrade(trade);
                    setTradeChartLoading(true);
                    const sym = trade.symbol.replace("/", "-");
                    const ohlcvRes = await getOHLCV("paper", sym, "5m", 100);
                    setTradeOHLCV(ohlcvRes.data || []);
                    setTradeChartLoading(false);
                  }
                } catch { /* */ }
              }}>
                <div className="asset-amount" style={{ color: (bots[bot.key]?.active_trades ?? 0) > 0 ? "var(--accent)" : undefined, textDecoration: (bots[bot.key]?.active_trades ?? 0) > 0 ? "underline" : undefined }}>{bots[bot.key]?.active_trades ?? 0}</div>
                <div className="asset-usd">open trades</div>
              </div>
            </div>
          ))}
          <div className="asset-row">
            <div className="asset-info">
              <div className="asset-icon">A</div>
              <div>
                <div className="asset-name">Arbitrage</div>
                <div className="asset-price">
                  {arbStatus?.running ? "Active" : "Inactive"} - Cross-exchange
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
            { label: "Scalper", pct: risk?.bucket_allocation?.scalper_pct ?? 10, color: "#00ff88" },
            { label: "Swing", pct: risk?.bucket_allocation?.swing_pct ?? 12, color: "#3b82f6" },
            { label: "Long-Term", pct: risk?.bucket_allocation?.long_term_pct ?? 12, color: "#a855f7" },
            { label: "Arbitrage", pct: risk?.bucket_allocation?.arbitrage_pct ?? 10, color: "#ff9f1c" },
            { label: "Grid", pct: risk?.bucket_allocation?.grid_pct ?? 18, color: "#06b6d4" },
            { label: "Mean Rev", pct: risk?.bucket_allocation?.mean_reversion_pct ?? 14, color: "#f472b6" },
            { label: "Momentum", pct: risk?.bucket_allocation?.momentum_pct ?? 12, color: "#facc15" },
            { label: "DCA", pct: risk?.bucket_allocation?.dca_pct ?? 12, color: "#fb923c" },
          ].map((bucket) => (
            <div key={bucket.label} style={{ marginBottom: "0.6rem" }}>
              <div className="flex-between" style={{ marginBottom: "0.15rem" }}>
                <span style={{ fontSize: "0.75rem", fontWeight: 500 }}>{bucket.label}</span>
                <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
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
        </div>

        <div className="card">
          <div className="card-header">
            <h3>Risk Configuration</h3>
          </div>
          {[
            { key: "max_daily_loss_usd" as const, label: "Max Daily Loss (USD)", prefix: "$", step: 5 },
            { key: "max_position_size_usd" as const, label: "Max Position Size (USD)", prefix: "$", step: 50 },
            { key: "default_stop_loss_pct" as const, label: "Default Stop Loss (%)", prefix: "", step: 0.5 },
            { key: "max_leverage" as const, label: "Max Leverage", prefix: "", step: 1 },
          ].map((field) => (
            <div key={field.key} style={{ marginBottom: "0.75rem" }}>
              <div style={{ fontSize: "0.72rem", color: "#999", marginBottom: "0.25rem" }}>{field.label}</div>
              <div style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
                <input
                  type="number"
                  step={field.step}
                  min={0}
                  value={riskCfgDraft[field.key]}
                  onChange={(e) => setRiskCfgDraft({ ...riskCfgDraft, [field.key]: parseFloat(e.target.value) || 0 })}
                  style={{
                    flex: 1, padding: "0.4rem 0.6rem", background: "#111", border: "1px solid #333",
                    borderRadius: 8, color: "#fff", fontSize: "0.85rem",
                  }}
                />
                {riskCfgDraft[field.key] !== riskCfg[field.key] && (
                  <span style={{ fontSize: "0.65rem", color: "#facc15" }}>changed</span>
                )}
              </div>
            </div>
          ))}
          <button
            disabled={riskCfgSaving || JSON.stringify(riskCfgDraft) === JSON.stringify(riskCfg)}
            onClick={async () => {
              setRiskCfgSaving(true);
              setRiskCfgMsg("");
              try {
                const res = await updateConfig(riskCfgDraft);
                const c = { max_daily_loss_usd: res.data.max_daily_loss_usd, max_position_size_usd: res.data.max_position_size_usd, default_stop_loss_pct: res.data.default_stop_loss_pct, max_leverage: res.data.max_leverage };
                setRiskCfg(c);
                setRiskCfgDraft(c);
                setRiskCfgMsg("Saved");
                setTimeout(() => setRiskCfgMsg(""), 2000);
              } catch {
                setRiskCfgMsg("Error saving");
              }
              setRiskCfgSaving(false);
            }}
            style={{
              width: "100%", padding: "0.5rem", background: JSON.stringify(riskCfgDraft) === JSON.stringify(riskCfg) ? "#333" : "var(--accent)",
              border: "none", borderRadius: 8, color: "#000", fontWeight: 600, fontSize: "0.8rem",
              cursor: JSON.stringify(riskCfgDraft) === JSON.stringify(riskCfg) ? "default" : "pointer",
              opacity: JSON.stringify(riskCfgDraft) === JSON.stringify(riskCfg) ? 0.5 : 1,
            }}
          >
            {riskCfgSaving ? "Saving..." : "Save Risk Settings"}
          </button>
          {riskCfgMsg && <div style={{ fontSize: "0.7rem", color: riskCfgMsg === "Saved" ? "var(--accent)" : "#ff4d6a", marginTop: "0.3rem", textAlign: "center" }}>{riskCfgMsg}</div>}
          <div className="divider" style={{ margin: "0.6rem 0" }} />
          <div className="flex-between">
            <span className="text-sm text-secondary">Daily P&L</span>
            <span className={`text-sm font-semibold ${(risk?.daily_pnl_usd ?? 0) >= 0 ? "positive" : "negative"}`}>${(risk?.daily_pnl_usd ?? 0).toFixed(2)}</span>
          </div>
          <div className="flex-between" style={{ marginTop: "0.3rem" }}>
            <span className="text-sm text-secondary">Circuit Breaker</span>
            <span className={`text-sm font-semibold ${risk?.circuit_breaker_active ? "negative" : "positive"}`}>{risk?.circuit_breaker_active ? "ACTIVE" : "Off"}</span>
          </div>
        </div>
      </div>
      {selectedBotTrade && (
        <div
          onClick={() => { setSelectedBotTrade(null); setActiveBotTrades([]); setTradeOHLCV([]); }}
          style={{
            position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
            background: "rgba(0,0,0,0.8)", zIndex: 1000,
            display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem",
            overflow: "auto",
          }}
        >
          <div onClick={(e) => e.stopPropagation()} style={{
            background: "#1a1a1a", border: "1px solid #333", borderRadius: 16,
            padding: "1.5rem", maxWidth: 700, width: "100%", position: "relative",
          }}>
            <button onClick={() => { setSelectedBotTrade(null); setActiveBotTrades([]); setTradeOHLCV([]); }} style={{
              position: "absolute", top: 12, right: 16, background: "transparent",
              border: "none", color: "#888", fontSize: "1.2rem", cursor: "pointer",
            }}>x</button>

            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
              <div style={{
                width: 40, height: 40, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: "1.2rem", fontWeight: 700,
                background: selectedBotTrade.side === "buy" ? "rgba(0,255,136,0.15)" : "rgba(255,77,106,0.15)",
                color: selectedBotTrade.side === "buy" ? "#00ff88" : "#ff4d6a",
              }}>{selectedBotTrade.side === "buy" ? "B" : "S"}</div>
              <div>
                <div style={{ fontWeight: 700, fontSize: "1.1rem" }}>{selectedBotTrade.symbol}</div>
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                  <span style={{
                    fontSize: "0.65rem", padding: "0.1rem 0.4rem", borderRadius: 20,
                    background: selectedBotTrade.side === "buy" ? "rgba(0,255,136,0.15)" : "rgba(255,77,106,0.15)",
                    color: selectedBotTrade.side === "buy" ? "#00ff88" : "#ff4d6a", fontWeight: 600,
                  }}>{selectedBotTrade.side.toUpperCase()}</span>
                  <span style={{
                    fontSize: "0.65rem", padding: "0.1rem 0.4rem", borderRadius: 20,
                    background: "rgba(255,255,255,0.08)", color: "#aaa", fontWeight: 500, textTransform: "capitalize",
                  }}>{selectedBotTrade.bot_type.replace("_", " ")} bot</span>
                  {selectedBotTrade.regime && <span style={{
                    fontSize: "0.65rem", padding: "0.1rem 0.4rem", borderRadius: 20,
                    background: "rgba(59,130,246,0.15)", color: "#3b82f6", fontWeight: 500,
                  }}>{selectedBotTrade.regime.replace(/_/g, " ")}</span>}
                </div>
              </div>
            </div>

            {activeBotTrades.length > 1 && (
              <div style={{ display: "flex", gap: "0.4rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
                {activeBotTrades.map((t, i) => (
                  <button key={t.order_id} onClick={async () => {
                    setSelectedBotTrade(t);
                    setTradeChartLoading(true);
                    try {
                      const sym = t.symbol.replace("/", "-");
                      const r = await getOHLCV("paper", sym, "5m", 100);
                      setTradeOHLCV(r.data || []);
                    } catch { setTradeOHLCV([]); }
                    setTradeChartLoading(false);
                  }} style={{
                    padding: "0.3rem 0.6rem", fontSize: "0.7rem", borderRadius: 20, cursor: "pointer",
                    background: selectedBotTrade.order_id === t.order_id ? "rgba(0,255,136,0.2)" : "rgba(255,255,255,0.06)",
                    border: selectedBotTrade.order_id === t.order_id ? "1px solid #00ff88" : "1px solid #333",
                    color: selectedBotTrade.order_id === t.order_id ? "#00ff88" : "#aaa",
                  }}>{t.symbol} #{i + 1}</button>
                ))}
              </div>
            )}

            <div style={{ marginBottom: "1rem" }}>
              {tradeChartLoading ? (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 280, color: "#666" }}>Loading chart...</div>
              ) : tradeOHLCV.length > 0 ? (
                <SymbolChart
                  data={tradeOHLCV}
                  symbol={selectedBotTrade.symbol}
                  entryPrice={selectedBotTrade.entry_price}
                  stopLoss={selectedBotTrade.stop_loss}
                  takeProfit={selectedBotTrade.take_profit ?? undefined}
                  height={320}
                  showBB={true}
                  showRSI={true}
                />
              ) : (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 280, color: "#666", fontSize: "0.85rem" }}>
                  No chart data available for this symbol
                </div>
              )}
            </div>

            <div style={{ borderTop: "1px solid #333", paddingTop: "0.75rem" }}>
              {[
                { label: "Entry Price", value: `$${selectedBotTrade.entry_price < 0.01 ? selectedBotTrade.entry_price.toExponential(4) : selectedBotTrade.entry_price.toFixed(8)}` },
                { label: "Position Size", value: `$${selectedBotTrade.position_usd.toFixed(2)}` },
                { label: "Quantity", value: selectedBotTrade.amount.toFixed(4) },
                { label: "Stop Loss", value: `$${selectedBotTrade.stop_loss < 0.01 ? selectedBotTrade.stop_loss.toExponential(4) : selectedBotTrade.stop_loss.toFixed(8)}`, cls: "negative" },
                { label: "Take Profit", value: selectedBotTrade.take_profit ? `$${selectedBotTrade.take_profit < 0.01 ? selectedBotTrade.take_profit.toExponential(4) : selectedBotTrade.take_profit.toFixed(8)}` : "None", cls: "positive" },
                { label: "Confidence", value: `${(selectedBotTrade.signal_confidence * 100).toFixed(1)}%` },
                { label: "Signal Score", value: String(selectedBotTrade.signal_score ?? "--") },
                { label: "Opened", value: new Date(selectedBotTrade.opened_at).toLocaleString() },
              ].map((row: { label: string; value: string; cls?: string }) => (
                <div key={row.label} style={{ display: "flex", justifyContent: "space-between", padding: "0.35rem 0", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                  <span style={{ fontSize: "0.8rem", color: "#888" }}>{row.label}</span>
                  <span style={{ fontSize: "0.8rem", fontWeight: 600 }} className={row.cls ?? ""}>{row.value}</span>
                </div>
              ))}
            </div>

            {selectedBotTrade.stop_loss > 0 && selectedBotTrade.take_profit && selectedBotTrade.take_profit > 0 && (
              <div style={{ marginTop: "0.75rem", padding: "0.75rem", background: "rgba(255,255,255,0.03)", borderRadius: 8 }}>
                <div style={{ fontSize: "0.7rem", color: "#888", marginBottom: "0.4rem", fontWeight: 600 }}>Risk/Reward</div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <div style={{ flex: 1, height: 6, borderRadius: 3, background: "#333", position: "relative", overflow: "hidden" }}>
                    {(() => {
                      const riskD = Math.abs(selectedBotTrade.entry_price - selectedBotTrade.stop_loss);
                      const rewD = Math.abs(selectedBotTrade.take_profit! - selectedBotTrade.entry_price);
                      const total = riskD + rewD;
                      const riskPct = total > 0 ? (riskD / total) * 100 : 50;
                      return (<>
                        <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${riskPct}%`, background: "#ff4d6a", borderRadius: 3 }} />
                        <div style={{ position: "absolute", right: 0, top: 0, bottom: 0, width: `${100 - riskPct}%`, background: "#00ff88", borderRadius: 3 }} />
                      </>);
                    })()}
                  </div>
                  <span style={{ fontSize: "0.7rem", color: "#aaa", whiteSpace: "nowrap" }}>
                    1:{(Math.abs(selectedBotTrade.take_profit! - selectedBotTrade.entry_price) / (Math.abs(selectedBotTrade.entry_price - selectedBotTrade.stop_loss) || 1)).toFixed(1)}
                  </span>
                </div>
              </div>
            )}

            {selectedBotTrade.strategy && (
              <div style={{ marginTop: "0.75rem", padding: "0.6rem", background: "rgba(59,130,246,0.06)", borderRadius: 8 }}>
                <div style={{ fontSize: "0.7rem", color: "#3b82f6", fontWeight: 600, marginBottom: "0.3rem" }}>Strategy</div>
                <div style={{ fontSize: "0.75rem", color: "#aaa", lineHeight: 1.4 }}>{selectedBotTrade.strategy}</div>
              </div>
            )}

            {selectedBotTrade.confirmations && selectedBotTrade.confirmations.length > 0 && (
              <div style={{ marginTop: "0.5rem", padding: "0.6rem", background: "rgba(255,255,255,0.03)", borderRadius: 8 }}>
                <div style={{ fontSize: "0.7rem", color: "#888", fontWeight: 600, marginBottom: "0.3rem" }}>Confirmations ({selectedBotTrade.confirmations.length})</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem" }}>
                  {selectedBotTrade.confirmations.map((c, i) => (
                    <span key={i} style={{ fontSize: "0.65rem", padding: "0.15rem 0.5rem", borderRadius: 20, background: "rgba(0,255,136,0.08)", color: "#00ff88" }}>{c}</span>
                  ))}
                </div>
              </div>
            )}

            {selectedBotTrade.reasoning && (
              <div style={{ marginTop: "0.5rem", fontSize: "0.7rem", color: "#666", fontStyle: "italic" }}>{selectedBotTrade.reasoning}</div>
            )}

            <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem" }}>
              <button
                disabled={closingTrade}
                onClick={async () => {
                  if (!window.confirm(`Close ${selectedBotTrade.symbol} position at market price?`)) return;
                  setClosingTrade(true);
                  try {
                    const res = await closeTrade(selectedBotTrade.order_id, activeAccount);
                    const pnl = res.data?.pnl_usd ?? 0;
                    alert(`Closed ${selectedBotTrade.symbol}: ${pnl >= 0 ? "+" : ""}$${pnl.toFixed(5)}`);
                    setSelectedBotTrade(null);
                    setActiveBotTrades([]);
                    setTradeOHLCV([]);
                    await load();
                  } catch (e: any) {
                    alert(e?.response?.data?.detail || "Failed to close trade");
                  }
                  setClosingTrade(false);
                }}
                style={{
                  flex: 1, padding: "0.6rem", border: "none", borderRadius: 8,
                  background: "var(--red)", color: "#fff", fontWeight: 600,
                  fontSize: "0.85rem", cursor: closingTrade ? "wait" : "pointer",
                  opacity: closingTrade ? 0.6 : 1,
                }}
              >{closingTrade ? "Closing..." : "Close at Market"}</button>
            </div>
          </div>
        </div>
      )}

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
                { label: "Price", value: `$${selectedTrade.price?.toLocaleString("en", { maximumFractionDigits: 8 }) ?? "--"}` },
                { label: "Quantity", value: selectedTrade.quantity?.toFixed(6) ?? "--" },
                ...(selectedTrade.type === "entry" ? [
                  { label: "Stop Loss", value: selectedTrade.stop_loss ? `$${selectedTrade.stop_loss.toLocaleString("en", { maximumFractionDigits: 8 })}` : "None", cls: "negative" },
                  { label: "Take Profit", value: selectedTrade.take_profit ? `$${selectedTrade.take_profit.toLocaleString("en", { maximumFractionDigits: 8 })}` : "None", cls: "positive" },
                  { label: "Entry Fee", value: selectedTrade.entry_fee != null ? `$${selectedTrade.entry_fee.toFixed(5)}` : "--" },
                  { label: "Signal Score", value: selectedTrade.signal_score != null ? String(selectedTrade.signal_score) : "--" },
                ] : [
                  { label: "Entry Price", value: selectedTrade.entry_price ? `$${selectedTrade.entry_price.toLocaleString("en", { maximumFractionDigits: 8 })}` : "--" },
                  { label: "P&L", value: selectedTrade.pnl_usd != null ? `${selectedTrade.pnl_usd >= 0 ? "+" : ""}$${selectedTrade.pnl_usd.toFixed(5)}` : "--", cls: (selectedTrade.pnl_usd ?? 0) >= 0 ? "positive" : "negative" },
                  { label: "P&L %", value: selectedTrade.pnl_pct != null ? `${selectedTrade.pnl_pct >= 0 ? "+" : ""}${selectedTrade.pnl_pct}%` : "--", cls: (selectedTrade.pnl_pct ?? 0) >= 0 ? "positive" : "negative" },
                  { label: "Exit Fee", value: selectedTrade.exit_fee != null ? `$${selectedTrade.exit_fee.toFixed(5)}` : "--" },
                  { label: "Exit Reason", value: selectedTrade.exit_reason ? selectedTrade.exit_reason.replace("_", " ") : "--",
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
