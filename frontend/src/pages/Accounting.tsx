import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import {
  getAccountingSummary, getPnlByBot, recordDeposit, recordWithdrawal,
  getTradesWithBalance, getActiveTradesLive, getFees, getLiveBalance,
} from "../services/api";

interface PnlDay { date: string; pnl_usd: number }

interface TradeRecord {
  id: number;
  bot_type: string;
  symbol: string;
  side: string;
  entry_price: number;
  exit_price?: number;
  quantity: number;
  pnl_usd?: number;
  pnl_pct?: number;
  status: string;
  opened_at: string;
  closed_at?: string;
  entry_fee_usd?: number;
  exit_fee_usd?: number;
  balance_at_entry?: number;
  balance_at_exit?: number;
}

interface ActiveTrade extends TradeRecord {
  current_price: number;
  current_value_usd: number;
  unrealized_pnl_usd: number;
  unrealized_pnl_pct: number;
  stop_loss_price: number;
  take_profit_price: number;
}

interface FeeData {
  total_fees_usd: number;
  fee_breakdown: { entry_fees: number; exit_fees: number };
}

interface LiveBalance {
  cash_balance_usd: number;
  open_position_value_usd: number;
  total_live_balance_usd: number;
  open_trade_count: number;
}

const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: { value: number }[]; label?: string }) => {
  if (active && payload?.length) {
    return (
      <div style={{
        background: "#1e1e1e",
        border: "1px solid #222",
        borderRadius: 12,
        padding: "8px 12px",
        fontSize: "0.8rem",
      }}>
        <div style={{ color: "#8a8a8a", marginBottom: 2 }}>{label}</div>
        <div style={{ color: payload[0].value >= 0 ? "#00ff88" : "#ff4d6a", fontWeight: 600 }}>
          ${payload[0].value.toFixed(2)}
        </div>
      </div>
    );
  }
  return null;
};

function Accounting() {
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [byBot, setByBot] = useState<Record<string, { pnl_usd: number; trades: number }>>({});
  const [tradeHistory, setTradeHistory] = useState<TradeRecord[]>([]);
  const [activeTrades, setActiveTrades] = useState<ActiveTrade[]>([]);
  const [fees, setFees] = useState<FeeData | null>(null);
  const [liveBalance, setLiveBalance] = useState<LiveBalance | null>(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [showForm, setShowForm] = useState(false);
  const [pnlMode, setPnlMode] = useState<"usd" | "pct">("usd");
  const [form, setForm] = useState({
    exchange: "paper", amount_usd: 0, asset: "USDT", asset_amount: 0, type: "deposit",
  });

  const load = async () => {
    try {
      const [s, b, t, at, f, lb] = await Promise.all([
        getAccountingSummary(),
        getPnlByBot(),
        getTradesWithBalance(),
        getActiveTradesLive(),
        getFees(),
        getLiveBalance(),
      ]);
      setSummary(s.data);
      setByBot(b.data);
      setTradeHistory(Array.isArray(t.data) ? t.data : []);
      setActiveTrades(Array.isArray(at.data) ? at.data : []);
      setFees(f.data);
      setLiveBalance(lb.data);
    } catch {
      /* not connected */
    }
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, []);

  const s = (summary as { summary?: Record<string, number> })?.summary;
  const wr = (summary as { win_rate?: Record<string, number> })?.win_rate;
  const pnlByDate = ((summary as { pnl_by_date?: PnlDay[] })?.pnl_by_date ?? []) as PnlDay[];

  const handleSubmit = async () => {
    const data = {
      exchange: form.exchange, amount_usd: form.amount_usd,
      asset: form.asset, asset_amount: form.asset_amount || form.amount_usd,
    };
    if (form.type === "deposit") {
      await recordDeposit(data);
    } else {
      await recordWithdrawal(data);
    }
    setShowForm(false);
    setForm({ ...form, amount_usd: 0, asset_amount: 0 });
    await load();
  };

  const closedTrades = tradeHistory.filter(
    (t) => t.status === "closed" || t.status === "stopped_out"
  );

  return (
    <div>
      <div className="page-header">
        <h2>Accounting</h2>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? "Cancel" : "+ Record Entry"}
        </button>
      </div>

      {showForm && (
        <div className="card mb-md">
          <div className="card-header">
            <h3>New Entry</h3>
          </div>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            <div className="input-group" style={{ flex: 1, minWidth: 120 }}>
              <label className="input-label">Type</label>
              <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
                <option value="deposit">Deposit</option>
                <option value="withdrawal">Withdrawal</option>
              </select>
            </div>
            <div className="input-group" style={{ flex: 1, minWidth: 120 }}>
              <label className="input-label">Exchange</label>
              <input value={form.exchange} onChange={(e) => setForm({ ...form, exchange: e.target.value })} />
            </div>
            <div className="input-group" style={{ flex: 1, minWidth: 120 }}>
              <label className="input-label">USD Amount</label>
              <input type="number" value={form.amount_usd || ""} onChange={(e) => setForm({ ...form, amount_usd: +e.target.value })} placeholder="0.00" />
            </div>
            <div className="input-group" style={{ flex: 1, minWidth: 100 }}>
              <label className="input-label">Asset</label>
              <input value={form.asset} onChange={(e) => setForm({ ...form, asset: e.target.value })} />
            </div>
            <div className="input-group" style={{ flex: 1, minWidth: 120 }}>
              <label className="input-label">Asset Amount</label>
              <input type="number" value={form.asset_amount || ""} onChange={(e) => setForm({ ...form, asset_amount: +e.target.value })} placeholder="0.00" />
            </div>
            <button className="btn btn-success" onClick={handleSubmit} style={{ marginTop: "auto" }}>
              Submit
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-3 mb-md">
        <div className="card stat-card green">
          <h3>Live Total Balance</h3>
          <div className="value">
            ${liveBalance?.total_live_balance_usd?.toLocaleString("en", { minimumFractionDigits: 2 }) ?? "0.00"}
          </div>
          <div className="value-sm" style={{ display: "flex", justifyContent: "space-between", marginTop: "0.25rem" }}>
            <span>Cash: ${liveBalance?.cash_balance_usd?.toLocaleString("en", { minimumFractionDigits: 2 }) ?? "0.00"}</span>
            <span>Positions: ${liveBalance?.open_position_value_usd?.toLocaleString("en", { minimumFractionDigits: 2 }) ?? "0.00"}</span>
          </div>
        </div>

        <div className="card stat-card">
          <h3>Net Account Value</h3>
          <div className="value">
            ${s?.account_value_usd?.toLocaleString("en", { minimumFractionDigits: 2 }) ?? "0.00"}
          </div>
          <div className="value-sm" style={{ display: "flex", justifyContent: "space-between", marginTop: "0.25rem" }}>
            <span>Deposited: ${s?.total_deposits_usd?.toFixed(2) ?? "0.00"}</span>
            <span className={`${(s?.net_pnl_usd ?? 0) >= 0 ? "positive" : "negative"}`}>
              P&L: {(s?.net_pnl_usd ?? 0) >= 0 ? "+" : ""}${s?.net_pnl_usd?.toFixed(2) ?? "0.00"}
            </span>
          </div>
        </div>

        <div className="card stat-card" style={{ borderLeft: "3px solid var(--red)" }}>
          <h3>Fees Paid</h3>
          <div className="value negative">
            ${fees?.total_fees_usd?.toFixed(2) ?? "0.00"}
          </div>
          <div className="value-sm" style={{ display: "flex", justifyContent: "space-between", marginTop: "0.25rem" }}>
            <span>Entry: ${fees?.fee_breakdown?.entry_fees?.toFixed(2) ?? "0.00"}</span>
            <span>Exit: ${fees?.fee_breakdown?.exit_fees?.toFixed(2) ?? "0.00"}</span>
          </div>
        </div>
      </div>

      <div className="tabs">
        {["overview", "active", "history", "by_bot"].map((tab) => (
          <button
            key={tab}
            className={`tab ${activeTab === tab ? "active" : ""}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab === "overview" ? "Overview" : tab === "active" ? `Active (${activeTrades.length})` : tab === "history" ? "History" : "By Bot"}
          </button>
        ))}
      </div>

      {activeTab === "overview" && (
        <div className="grid grid-2">
          <div className="card">
            <h3>Daily P&L</h3>
            <div className="chart-container">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={pnlByDate}>
                  <XAxis dataKey="date" stroke="#555" fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis stroke="#555" fontSize={11} tickLine={false} axisLine={false} />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar dataKey="pnl_usd" radius={[4, 4, 0, 0]}>
                    {pnlByDate.map((entry, i) => (
                      <Cell key={i} fill={entry.pnl_usd >= 0 ? "#00ff88" : "#ff4d6a"} fillOpacity={0.8} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="card">
            <h3>Performance Stats</h3>
            <div style={{ marginTop: "0.5rem" }}>
              {[
                { label: "Win Rate", value: `${wr?.win_rate?.toFixed(1) ?? 0}%` },
                { label: "Winning Trades", value: String(wr?.winning_trades ?? 0), cls: "positive" },
                { label: "Losing Trades", value: String(wr?.losing_trades ?? 0), cls: "negative" },
                { label: "Total Trades", value: String(s?.total_trades ?? 0) },
                { label: "Gross P&L", value: `$${s?.total_pnl_usd?.toFixed(2) ?? "0.00"}`, cls: (s?.total_pnl_usd ?? 0) >= 0 ? "positive" : "negative" },
                { label: "Net P&L (after fees)", value: `$${s?.net_pnl_usd?.toFixed(2) ?? "0.00"}`, cls: (s?.net_pnl_usd ?? 0) >= 0 ? "positive" : "negative" },
              ].map((row) => (
                <div className="flex-between" key={row.label} style={{ padding: "0.6rem 0", borderBottom: "1px solid var(--border)" }}>
                  <span className="text-sm text-secondary">{row.label}</span>
                  <span className={`text-sm font-semibold ${row.cls ?? ""}`}>{row.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === "active" && (
        <div>
          <div className="flex-between mb-md" style={{ alignItems: "center" }}>
            <span className="text-sm text-secondary">
              {activeTrades.length} open position{activeTrades.length !== 1 ? "s" : ""}
            </span>
            <button
              className="btn"
              onClick={() => setPnlMode(pnlMode === "usd" ? "pct" : "usd")}
              style={{
                padding: "0.35rem 0.75rem",
                fontSize: "0.75rem",
                background: "var(--bg-tertiary)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-full)",
              }}
            >
              Show {pnlMode === "usd" ? "%" : "$"}
            </button>
          </div>

          {activeTrades.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {activeTrades.map((t) => {
                const isUp = t.unrealized_pnl_usd >= 0;
                return (
                  <div className="card" key={t.id} style={{ padding: "1rem 1.25rem" }}>
                    <div className="flex-between" style={{ marginBottom: "0.75rem" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                        <div style={{
                          width: 36, height: 36, borderRadius: "50%",
                          background: t.side === "buy" ? "var(--green-dim)" : "var(--red-dim)",
                          display: "flex", alignItems: "center", justifyContent: "center",
                          fontSize: "0.7rem", fontWeight: 700,
                          color: t.side === "buy" ? "var(--green)" : "var(--red)",
                        }}>
                          {t.side === "buy" ? "LONG" : "SHRT"}
                        </div>
                        <div>
                          <div style={{ fontWeight: 700, fontSize: "1rem" }}>{t.symbol}</div>
                          <div className="text-sm text-secondary" style={{ textTransform: "capitalize" }}>
                            {(t.bot_type ?? "").replace("_", " ")} bot
                          </div>
                        </div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div style={{
                          fontSize: "1.25rem",
                          fontWeight: 800,
                          color: isUp ? "var(--green)" : "var(--red)",
                        }}>
                          {pnlMode === "usd" ? (
                            <>{isUp ? "+" : ""}${t.unrealized_pnl_usd.toFixed(2)}</>
                          ) : (
                            <>{isUp ? "+" : ""}{t.unrealized_pnl_pct.toFixed(2)}%</>
                          )}
                        </div>
                        <div className="text-sm text-secondary">
                          {pnlMode === "usd" ? (
                            <>{isUp ? "+" : ""}{t.unrealized_pnl_pct.toFixed(2)}%</>
                          ) : (
                            <>{isUp ? "+" : ""}${t.unrealized_pnl_usd.toFixed(2)}</>
                          )}
                        </div>
                      </div>
                    </div>

                    <div style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(4, 1fr)",
                      gap: "0.5rem",
                      padding: "0.75rem",
                      background: "var(--bg-secondary)",
                      borderRadius: "var(--radius-md)",
                      fontSize: "0.78rem",
                    }}>
                      <div>
                        <div className="text-tertiary" style={{ fontSize: "0.65rem", marginBottom: 2 }}>Entry</div>
                        <div className="font-semibold">${t.entry_price?.toLocaleString()}</div>
                      </div>
                      <div>
                        <div className="text-tertiary" style={{ fontSize: "0.65rem", marginBottom: 2 }}>Current</div>
                        <div className="font-semibold">${t.current_price?.toLocaleString()}</div>
                      </div>
                      <div>
                        <div className="text-tertiary" style={{ fontSize: "0.65rem", marginBottom: 2 }}>Position Value</div>
                        <div className="font-semibold">${t.current_value_usd?.toFixed(2)}</div>
                      </div>
                      <div>
                        <div className="text-tertiary" style={{ fontSize: "0.65rem", marginBottom: 2 }}>Qty</div>
                        <div className="font-semibold">{t.quantity?.toFixed(6)}</div>
                      </div>
                    </div>

                    <div style={{
                      display: "flex",
                      justifyContent: "space-between",
                      marginTop: "0.6rem",
                      fontSize: "0.75rem",
                    }}>
                      <span className="text-secondary">
                        SL: <span className="negative">${t.stop_loss_price?.toLocaleString()}</span>
                      </span>
                      <span className="text-secondary">
                        TP: <span className="positive">${t.take_profit_price?.toLocaleString()}</span>
                      </span>
                      <span className="text-secondary">
                        Opened: {t.opened_at ? new Date(t.opened_at).toLocaleString() : "—"}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="card" style={{ textAlign: "center", padding: "3rem", color: "var(--text-tertiary)", fontSize: "0.85rem" }}>
              No active trades. Start the bots from the Bots page to begin trading.
            </div>
          )}
        </div>
      )}

      {activeTab === "history" && (
        <div className="card">
          <div className="card-header">
            <h3>Trade History with Running Balance</h3>
          </div>
          {closedTrades.length > 0 ? (
            <div style={{ maxHeight: 600, overflow: "auto", marginTop: "0.5rem" }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Bot</th>
                    <th>Pair</th>
                    <th>Side</th>
                    <th>Entry</th>
                    <th>Exit</th>
                    <th>P&L</th>
                    <th>Balance (Open)</th>
                    <th>Balance (Close)</th>
                    <th>Fees</th>
                    <th>Status</th>
                    <th>Closed</th>
                  </tr>
                </thead>
                <tbody>
                  {closedTrades.map((t, i) => {
                    const totalFee = (t.entry_fee_usd ?? 0) + (t.exit_fee_usd ?? 0);
                    return (
                      <tr key={t.id ?? i}>
                        <td className="text-secondary">{i + 1}</td>
                        <td style={{ textTransform: "capitalize", fontSize: "0.8rem" }}>
                          {(t.bot_type ?? "").replace("_", " ")}
                        </td>
                        <td style={{ fontWeight: 600 }}>{t.symbol}</td>
                        <td>
                          <span className={`badge ${t.side === "buy" ? "badge-active" : "badge-stopped"}`} style={{ fontSize: "0.65rem" }}>
                            {t.side?.toUpperCase()}
                          </span>
                        </td>
                        <td>${t.entry_price?.toLocaleString()}</td>
                        <td>${t.exit_price?.toLocaleString() ?? "—"}</td>
                        <td className={(t.pnl_usd ?? 0) >= 0 ? "positive" : "negative"}>
                          {(t.pnl_usd ?? 0) >= 0 ? "+" : ""}${(t.pnl_usd ?? 0).toFixed(2)}
                          <div style={{ fontSize: "0.65rem", opacity: 0.7 }}>
                            {(t.pnl_pct ?? 0) >= 0 ? "+" : ""}{(t.pnl_pct ?? 0).toFixed(1)}%
                          </div>
                        </td>
                        <td style={{ fontFamily: "monospace", fontSize: "0.78rem" }}>
                          ${t.balance_at_entry?.toLocaleString("en", { minimumFractionDigits: 2 }) ?? "—"}
                        </td>
                        <td style={{ fontFamily: "monospace", fontSize: "0.78rem" }}>
                          <span className={(t.balance_at_exit ?? 0) >= (t.balance_at_entry ?? 0) ? "positive" : "negative"}>
                            ${t.balance_at_exit?.toLocaleString("en", { minimumFractionDigits: 2 }) ?? "—"}
                          </span>
                        </td>
                        <td className="negative" style={{ fontSize: "0.78rem" }}>
                          ${totalFee.toFixed(2)}
                        </td>
                        <td>
                          <span style={{
                            fontSize: "0.7rem",
                            padding: "0.15rem 0.5rem",
                            borderRadius: "var(--radius-full)",
                            background: t.status === "closed" ? "var(--green-dim)" : "var(--red-dim)",
                            color: t.status === "closed" ? "var(--green)" : "var(--red)",
                          }}>
                            {t.status?.replace("_", " ")}
                          </span>
                        </td>
                        <td className="text-secondary text-sm">
                          {t.closed_at ? new Date(t.closed_at).toLocaleString() : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ textAlign: "center", padding: "2rem", color: "var(--text-tertiary)", fontSize: "0.85rem" }}>
              Trade history will appear here once bots start trading
            </div>
          )}
        </div>
      )}

      {activeTab === "by_bot" && (
        <div className="card">
          <h3>Performance by Bot</h3>
          {Object.entries(byBot).length > 0 ? (
            Object.entries(byBot).map(([bot, data]) => (
              <div className="asset-row" key={bot}>
                <div className="asset-info">
                  <div className="asset-icon">
                    {bot === "scalper" ? "⚡" : bot === "swing" ? "〰" : "📈"}
                  </div>
                  <div>
                    <div className="asset-name" style={{ textTransform: "capitalize" }}>
                      {bot.replace("_", " ")}
                    </div>
                    <div className="asset-price">{data.trades} trades</div>
                  </div>
                </div>
                <div className="asset-value">
                  <div className={`asset-amount ${data.pnl_usd >= 0 ? "positive" : "negative"}`}>
                    {data.pnl_usd >= 0 ? "+" : ""}${data.pnl_usd?.toFixed(2)}
                  </div>
                  <div className="asset-usd">total P&L</div>
                </div>
              </div>
            ))
          ) : (
            <div style={{ textAlign: "center", padding: "2rem", color: "var(--text-tertiary)", fontSize: "0.85rem" }}>
              No trading data yet
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default Accounting;
