import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import {
  getAccountingSummary, getPnlByBot, recordDeposit, recordWithdrawal,
  getActiveTradesLive, getFees, getLiveBalance, getLedger,
} from "../services/api";

interface PnlDay { date: string; pnl_usd: number }

interface ActiveTrade {
  id: number;
  bot_type: string;
  symbol: string;
  side: string;
  entry_price: number;
  current_price: number;
  current_value_usd: number;
  unrealized_pnl_usd: number;
  unrealized_pnl_pct: number;
  quantity: number;
  stop_loss_price: number;
  take_profit_price: number;
  opened_at: string;
  status: string;
}

interface LedgerEntry {
  type: string;
  timestamp: string;
  description: string;
  asset: string;
  amount_usd: number;
  pnl_usd: number | null;
  fee_usd: number;
  running_balance: number;
  side: string;
  symbol: string | null;
  bot_type: string | null;
  trade_id?: number;
  status?: string;
  quantity?: number;
  price?: number;
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
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [activeTrades, setActiveTrades] = useState<ActiveTrade[]>([]);
  const [fees, setFees] = useState<FeeData | null>(null);
  const [liveBalance, setLiveBalance] = useState<LiveBalance | null>(null);
  const [activeTab, setActiveTab] = useState("ledger");
  const [showForm, setShowForm] = useState(false);
  const [pnlMode, setPnlMode] = useState<"usd" | "pct">("usd");
  const [ledgerFilter, setLedgerFilter] = useState("all");
  const [form, setForm] = useState({
    exchange: "paper", amount_usd: 0, asset: "USDT", asset_amount: 0, type: "deposit",
  });

  const load = async () => {
    try {
      const [s, b, l, at, f, lb] = await Promise.all([
        getAccountingSummary(),
        getPnlByBot(),
        getLedger(),
        getActiveTradesLive(),
        getFees(),
        getLiveBalance(),
      ]);
      setSummary(s.data);
      setByBot(b.data);
      setLedger(Array.isArray(l.data) ? l.data : []);
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

  const filteredLedger = ledger.filter((e) => {
    if (ledgerFilter === "all") return true;
    if (ledgerFilter === "deposits") return e.type === "deposit";
    if (ledgerFilter === "withdrawals") return e.type === "withdrawal";
    if (ledgerFilter === "entries") return e.type === "trade_entry";
    if (ledgerFilter === "exits") return e.type === "trade_exit";
    return true;
  });

  const typeIcon = (type: string, side: string) => {
    if (type === "deposit") return { icon: "↓", color: "var(--green)", bg: "var(--green-dim)", label: "DEPOSIT" };
    if (type === "withdrawal") return { icon: "↑", color: "var(--red)", bg: "var(--red-dim)", label: "WITHDRAW" };
    if (type === "trade_entry") {
      return side === "buy"
        ? { icon: "⟶", color: "#3b82f6", bg: "rgba(59,130,246,0.1)", label: "BUY" }
        : { icon: "⟵", color: "#a855f7", bg: "rgba(168,85,247,0.1)", label: "SELL" };
    }
    if (type === "trade_exit") {
      return { icon: "✓", color: "var(--yellow)", bg: "var(--yellow-dim)", label: "CLOSE" };
    }
    return { icon: "•", color: "var(--text-secondary)", bg: "var(--bg-elevated)", label: type };
  };

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
        {["ledger", "active", "overview", "by_bot"].map((tab) => (
          <button
            key={tab}
            className={`tab ${activeTab === tab ? "active" : ""}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab === "ledger"
              ? `Statement (${ledger.length})`
              : tab === "active"
                ? `Active (${activeTrades.length})`
                : tab === "overview"
                  ? "Overview"
                  : "By Bot"}
          </button>
        ))}
      </div>

      {activeTab === "ledger" && (
        <div>
          <div className="flex-between mb-md" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
            <div style={{ display: "flex", gap: "0.25rem", flexWrap: "wrap" }}>
              {[
                { key: "all", label: "All" },
                { key: "deposits", label: "Deposits" },
                { key: "withdrawals", label: "Withdrawals" },
                { key: "entries", label: "Entries" },
                { key: "exits", label: "Exits" },
              ].map((f) => (
                <button
                  key={f.key}
                  className={`tab ${ledgerFilter === f.key ? "active" : ""}`}
                  onClick={() => setLedgerFilter(f.key)}
                  style={{ padding: "0.35rem 0.75rem", fontSize: "0.75rem", borderBottom: "none" }}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <span className="text-sm text-secondary">
              {filteredLedger.length} entries
            </span>
          </div>

          {filteredLedger.length > 0 ? (
            <div className="card" style={{ padding: 0, overflow: "hidden" }}>
              <div style={{ maxHeight: 600, overflow: "auto" }}>
                <table className="table" style={{ fontSize: "0.82rem" }}>
                  <thead>
                    <tr>
                      <th style={{ width: 50 }}>Type</th>
                      <th>Date</th>
                      <th>Description</th>
                      <th style={{ textAlign: "right" }}>Amount</th>
                      <th style={{ textAlign: "right" }}>P&L</th>
                      <th style={{ textAlign: "right" }}>Fee</th>
                      <th style={{ textAlign: "right" }}>Balance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...filteredLedger].reverse().map((entry, i) => {
                      const t = typeIcon(entry.type, entry.side);
                      return (
                        <tr key={i}>
                          <td>
                            <div style={{
                              display: "flex", alignItems: "center", gap: "0.4rem",
                            }}>
                              <span style={{
                                width: 28, height: 28, borderRadius: "50%",
                                background: t.bg, color: t.color,
                                display: "flex", alignItems: "center", justifyContent: "center",
                                fontSize: "0.75rem", fontWeight: 700, flexShrink: 0,
                              }}>
                                {t.icon}
                              </span>
                              <span style={{ fontSize: "0.65rem", fontWeight: 600, color: t.color }}>
                                {t.label}
                              </span>
                            </div>
                          </td>
                          <td style={{ whiteSpace: "nowrap", fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                            {entry.timestamp ? new Date(entry.timestamp).toLocaleString([], {
                              month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                            }) : "—"}
                          </td>
                          <td>
                            <div style={{ fontWeight: 600, fontSize: "0.82rem" }}>
                              {entry.description}
                            </div>
                            {entry.bot_type && (
                              <div style={{ fontSize: "0.68rem", color: "var(--text-tertiary)", textTransform: "capitalize" }}>
                                {entry.bot_type.replace("_", " ")} bot
                                {entry.quantity ? ` · ${entry.quantity.toFixed(6)} units` : ""}
                              </div>
                            )}
                          </td>
                          <td style={{
                            textAlign: "right", fontFamily: "monospace", fontWeight: 600,
                            color: entry.amount_usd >= 0 ? "var(--green)" : "var(--red)",
                          }}>
                            {entry.amount_usd >= 0 ? "+" : ""}{entry.amount_usd < 0.01 && entry.amount_usd > -0.01
                              ? entry.amount_usd.toFixed(6)
                              : `$${Math.abs(entry.amount_usd).toFixed(2)}`}
                            {entry.amount_usd < 0 && entry.amount_usd <= -0.01 ? "" : ""}
                          </td>
                          <td style={{
                            textAlign: "right", fontFamily: "monospace",
                            color: entry.pnl_usd !== null
                              ? (entry.pnl_usd >= 0 ? "var(--green)" : "var(--red)")
                              : "var(--text-tertiary)",
                          }}>
                            {entry.pnl_usd !== null
                              ? `${entry.pnl_usd >= 0 ? "+" : ""}$${entry.pnl_usd.toFixed(4)}`
                              : "—"}
                          </td>
                          <td style={{
                            textAlign: "right", fontFamily: "monospace", fontSize: "0.78rem",
                            color: entry.fee_usd > 0 ? "var(--red)" : "var(--text-tertiary)",
                          }}>
                            {entry.fee_usd > 0 ? `-$${entry.fee_usd.toFixed(4)}` : "—"}
                          </td>
                          <td style={{
                            textAlign: "right", fontFamily: "monospace", fontWeight: 700,
                            fontSize: "0.85rem",
                          }}>
                            ${entry.running_balance?.toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="card" style={{ textAlign: "center", padding: "3rem", color: "var(--text-tertiary)", fontSize: "0.85rem" }}>
              No transactions yet. Deposit funds or start bots to see your statement.
            </div>
          )}
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
                { label: "Open Trades", value: String(s?.open_trades ?? 0) },
                { label: "Closed Trades", value: String(s?.closed_trades ?? 0) },
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

      {activeTab === "by_bot" && (
        <div className="card">
          <h3>Performance by Bot</h3>
          {Object.entries(byBot).length > 0 ? (
            Object.entries(byBot).map(([bot, data]) => (
              <div className="asset-row" key={bot}>
                <div className="asset-info">
                  <div className="asset-icon">
                    {bot === "scalper" ? "⚡" : bot === "swing" ? "〰" : bot === "arbitrage" ? "⇄" : "📈"}
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
