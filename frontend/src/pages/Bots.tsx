import { useEffect, useState, useCallback, useRef } from "react";
import {
  getBotStatus, getBotsRunning, startBots, stopBots,
  getArbOpportunities, getArbStatus, getExchangesStatus,
  getExchangePairs, startAccountBots, stopAccountBots,
} from "../services/api";

interface BotTrade {
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
}

interface BotData {
  active_trades: number;
  trades: BotTrade[];
}

interface ArbOpp {
  symbol: string;
  buy_exchange: string;
  sell_exchange: string;
  buy_price: number;
  sell_price: number;
  spread_pct: number;
  estimated_profit_pct: number;
  is_actionable: boolean;
  timestamp: string;
}

interface ArbStatusData {
  running: boolean;
  cycles: number;
  trades_executed: number;
  current_opportunities: number;
  actionable: number;
  common_pairs: number;
  exchanges_connected: number;
}

interface ExchangeInfo {
  type: string;
  chain: string | null;
  connected: boolean;
  pairs: number;
}

interface LivePriceInfo {
  label: string;
  pairs: number;
  connected: boolean;
}

const botConfig: Record<string, { icon: string; label: string; timeframes: string; interval: string }> = {
  scalper: { icon: "S", label: "Scalper", timeframes: "5m · 15m", interval: "30s" },
  swing: { icon: "W", label: "Swing", timeframes: "1h · 4h", interval: "5m" },
  long_term: { icon: "L", label: "Long Term", timeframes: "1d · 1w", interval: "1h" },
  grid: { icon: "G", label: "Grid", timeframes: "1h · 4h", interval: "60s" },
  mean_reversion: { icon: "M", label: "Mean Reversion", timeframes: "1h · 4h", interval: "2m" },
  momentum: { icon: "P", label: "Momentum", timeframes: "4h · 1d", interval: "5m" },
  dca: { icon: "D", label: "DCA", timeframes: "1h · 4h", interval: "3m" },
};

function ExchangeDropdown({ eid, label, pairCount, icon }: { eid: string; label: string; pairCount: number; icon: string }) {
  const [expanded, setExpanded] = useState(false);
  const [search, setSearch] = useState("");
  const [pairs, setPairs] = useState<string[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  const fetchPairs = useCallback(async (query: string) => {
    setLoading(true);
    try {
      const res = await getExchangePairs(eid, query, 100, 0);
      setPairs(res.data.pairs || []);
      setTotal(res.data.total || 0);
    } catch {
      setPairs([]);
      setTotal(0);
    }
    setLoading(false);
  }, [eid]);

  useEffect(() => {
    if (expanded && pairs.length === 0 && !search) {
      fetchPairs("");
    }
  }, [expanded, fetchPairs, pairs.length, search]);

  const handleSearch = (val: string) => {
    setSearch(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchPairs(val), 300);
  };

  return (
    <div className="asset-row" style={{ display: "block", padding: 0 }}>
      <div
        style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "0.75rem 1rem", cursor: "pointer", userSelect: "none",
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <div className="asset-info">
          <div className="asset-icon" style={{ fontSize: "0.7rem" }}>{icon}</div>
          <div>
            <div className="asset-name">{label || eid}</div>
            <div className="asset-price">
              {eid.includes("dex") ? "DEX" : "Real-time prices"} · {pairCount.toLocaleString()} pairs
            </div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div className="asset-value">
            <div className="asset-amount">{pairCount.toLocaleString()}</div>
            <div className="asset-usd">pairs</div>
          </div>
          <span style={{
            fontSize: "0.7rem", transition: "transform 0.2s",
            transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
          }}>
            ▼
          </span>
        </div>
      </div>

      {expanded && (
        <div style={{
          borderTop: "1px solid var(--border)", padding: "0.75rem 1rem",
          maxHeight: "320px", display: "flex", flexDirection: "column",
        }}>
          <input
            type="text"
            placeholder={`Search ${pairCount.toLocaleString()} pairs...`}
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
            style={{
              width: "100%", padding: "0.5rem 0.75rem",
              background: "var(--bg-secondary)", border: "1px solid var(--border)",
              borderRadius: "6px", color: "var(--text-primary)", fontSize: "0.8rem",
              marginBottom: "0.5rem", outline: "none",
            }}
          />
          {loading ? (
            <div style={{ textAlign: "center", padding: "1rem", color: "var(--text-tertiary)", fontSize: "0.8rem" }}>
              Loading...
            </div>
          ) : (
            <>
              <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", marginBottom: "0.4rem" }}>
                Showing {pairs.length} of {total.toLocaleString()} {search ? "matching" : "total"} pairs
              </div>
              <div style={{ overflowY: "auto", maxHeight: "220px" }}>
                <div style={{
                  display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))",
                  gap: "0.3rem",
                }}>
                  {pairs.map((p) => (
                    <div key={p} style={{
                      padding: "0.3rem 0.5rem", fontSize: "0.75rem",
                      background: "var(--bg-secondary)", borderRadius: "4px",
                      whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                      color: "var(--text-primary)",
                    }}>
                      {p}
                    </div>
                  ))}
                </div>
                {pairs.length === 0 && (
                  <div style={{ textAlign: "center", padding: "1rem", color: "var(--text-tertiary)", fontSize: "0.8rem" }}>
                    {search ? "No pairs match your search" : "No pairs available"}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

interface AccountInfo { name: string; label: string; daily_target_pct: number | null; target_hit: boolean; }

interface BotsProps {
  activeAccount: string;
  setActiveAccount: (name: string) => void;
  accounts: AccountInfo[];
}

function Bots({ activeAccount, setActiveAccount, accounts }: BotsProps) {
  const [bots, setBots] = useState<Record<string, BotData>>({});
  const [botRunning, setBotRunning] = useState<Record<string, { running: boolean; active_trades: number }>>({});
  const [arbStatus, setArbStatus] = useState<ArbStatusData | null>(null);
  const [arbOpps, setArbOpps] = useState<ArbOpp[]>([]);
  const [exchanges, setExchanges] = useState<Record<string, ExchangeInfo>>({});
  const [livePrices, setLivePrices] = useState<Record<string, LivePriceInfo>>({});
  const [totalSymbols, setTotalSymbols] = useState(0);
  const [commonPairs, setCommonPairs] = useState(0);
  const [running, setRunning] = useState(false);
  const [activeTab, setActiveTab] = useState("all");

  const load = async () => {
    try {
      const [botRes, runRes, arbStatRes, arbOppRes, exRes] = await Promise.all([
        getBotStatus(activeAccount),
        getBotsRunning(activeAccount),
        getArbStatus(),
        getArbOpportunities(0, 20),
        getExchangesStatus(),
      ]);
      setBots(botRes.data);
      setBotRunning(runRes.data);
      setArbStatus(arbStatRes.data);
      setArbOpps(arbOppRes.data);
      setExchanges(exRes.data.exchanges || {});
      setLivePrices(exRes.data.live_prices || {});
      setTotalSymbols(exRes.data.total_symbols || 0);
      setCommonPairs(exRes.data.common_pairs || 0);
      const anyRunning = Object.values(runRes.data).some((b: unknown) => {
        const bot = b as { running?: boolean };
        return bot?.running === true;
      });
      setRunning(anyRunning);
    } catch {
      /* API not connected */
    }
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, [activeAccount]);

  const handleStart = async () => {
    try {
      if (activeAccount !== "default") {
        await startAccountBots(activeAccount);
      } else {
        await startBots("paper");
      }
      setRunning(true);
      setTimeout(load, 2000);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      alert(`Failed to start bots: ${msg}`);
    }
  };

  const handleStop = async () => {
    if (activeAccount !== "default") {
      await stopAccountBots(activeAccount);
    } else {
      await stopBots();
    }
    setRunning(false);
  };

  const totalTrades = Object.values(bots).reduce((sum, b) => sum + (b?.active_trades ?? 0), 0)
    + (arbStatus?.trades_executed ?? 0);

  const liveExchangeEntries = Object.entries(livePrices).filter(([, v]) => v.connected);
  const dexEntries = Object.entries(exchanges).filter(([eid]) => eid.includes("dex"));

  return (
    <div>
      <div className="page-header" style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>Bot Management</h2>
        <span className="badge badge-active" style={{ fontSize: "0.7rem" }}>LIVE DATA</span>
        <span className={`badge ${running ? "badge-active" : "badge-stopped"}`}>
          <span className="badge-dot" />
          {running ? "Running" : "Stopped"}
        </span>
      </div>
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center", marginBottom: "1rem" }}>
        <select
          value={activeAccount}
          onChange={(e) => setActiveAccount(e.target.value)}
          style={{
            background: "var(--bg-secondary)", color: "var(--text-primary)", border: "1px solid var(--border)",
            borderRadius: 8, padding: "0.5rem 0.75rem", fontSize: "0.85rem", cursor: "pointer",
            flex: "1 1 auto", minWidth: 0,
          }}
        >
          {accounts.map((a) => (
            <option key={a.name} value={a.name}>
              {a.label}{a.daily_target_pct ? ` (${a.daily_target_pct}%)` : ""}{a.target_hit ? " HIT" : ""}
            </option>
          ))}
        </select>
      </div>

      <div className="card mb-md" style={{ textAlign: "center", padding: "1.5rem" }}>
        <div style={{ fontSize: "0.8rem", color: "var(--text-tertiary)", marginBottom: "0.4rem" }}>
          Total Active Positions
        </div>
        <div style={{ fontSize: "2rem", fontWeight: 800 }}>{totalTrades}</div>

        <div style={{
          display: "flex", gap: "0.75rem", justifyContent: "center",
          alignItems: "center", marginTop: "1.25rem", flexWrap: "wrap"
        }}>
          {!running ? (
            <button className="btn btn-success" onClick={handleStart}>
              Start All Bots
            </button>
          ) : (
            <button className="btn btn-danger" onClick={handleStop}>
              Stop All Bots
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-4 mb-md">
        <div className="card stat-card">
          <h3>Price Sources</h3>
          <div className="value">{liveExchangeEntries.length + dexEntries.length}</div>
          <div className="value-sm">Live Exchanges</div>
        </div>
        <div className="card stat-card">
          <h3>Total Pairs</h3>
          <div className="value">{totalSymbols.toLocaleString()}</div>
          <div className="value-sm">Real Market Data</div>
        </div>
        <div className="card stat-card">
          <h3>Cross-Exchange</h3>
          <div className="value">{commonPairs.toLocaleString()}</div>
          <div className="value-sm">Arb Candidates</div>
        </div>
        <div className="card stat-card green">
          <h3>Arb Trades</h3>
          <div className="value">{arbStatus?.trades_executed ?? 0}</div>
          <div className="value-sm">Executed</div>
        </div>
      </div>

      <div className="tabs mb-md">
        {["all", "scalper", "swing", "long_term", "grid", "mean_reversion", "momentum", "dca", "arbitrage"].map((tab) => (
          <button
            key={tab}
            className={`tab ${activeTab === tab ? "active" : ""}`}
            onClick={() => setActiveTab(tab)}
            style={{ fontSize: "0.75rem", padding: "0.4rem 0.6rem" }}
          >
            {tab === "all" ? "All" : tab === "arbitrage" ? "Arb" : botConfig[tab]?.label}
          </button>
        ))}
      </div>

      {(activeTab === "all" || activeTab === "arbitrage") && (
        <div className="card mb-md">
          <div className="card-header">
            <div className="flex gap-sm" style={{ alignItems: "center" }}>
              <div className="asset-icon" style={{ width: 36, height: 36, fontSize: "1rem" }}>
                🔄
              </div>
              <div>
                <div style={{ fontWeight: 600 }}>Arbitrage Bot</div>
                <div className="text-sm text-secondary">
                  {arbStatus?.exchanges_connected ?? 0} exchanges · {commonPairs.toLocaleString()} cross-pairs · 30s
                </div>
              </div>
            </div>
            <span className={`badge ${arbStatus?.running ? "badge-active" : "badge-stopped"}`}>
              <span className="badge-dot" />
              {arbStatus?.running ? "Hunting" : "Idle"}
            </span>
          </div>

          {arbOpps.length > 0 ? (
            <div style={{ overflowX: "auto" }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Pair</th>
                    <th>Buy At</th>
                    <th>Sell At</th>
                    <th>Spread</th>
                    <th>Est. Profit</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {arbOpps.slice(0, 10).map((opp, i) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 600 }}>{opp.symbol}</td>
                      <td>
                        <div className="text-sm">{opp.buy_exchange}</div>
                        <div>${opp.buy_price < 0.01 ? opp.buy_price.toExponential(3) : opp.buy_price.toFixed(6)}</div>
                      </td>
                      <td>
                        <div className="text-sm">{opp.sell_exchange}</div>
                        <div>${opp.sell_price < 0.01 ? opp.sell_price.toExponential(3) : opp.sell_price.toFixed(6)}</div>
                      </td>
                      <td className="positive">{opp.spread_pct.toFixed(2)}%</td>
                      <td className={opp.estimated_profit_pct > 0 ? "positive" : "negative"}>
                        {opp.estimated_profit_pct.toFixed(2)}%
                      </td>
                      <td>
                        <span className={`badge ${opp.is_actionable ? "badge-active" : "badge-stopped"}`}
                              style={{ fontSize: "0.65rem" }}>
                          {opp.is_actionable ? "Actionable" : "Watching"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{
              textAlign: "center", padding: "2rem",
              color: "var(--text-tertiary)", fontSize: "0.85rem",
            }}>
              {arbStatus?.running ? "Scanning real prices for arbitrage opportunities..." : "Start bots to scan for arbitrage"}
            </div>
          )}
        </div>
      )}

      {Object.entries(botConfig)
        .filter(([key]) => activeTab === "all" || activeTab === key)
        .map(([botType, cfg]) => {
          const bot = bots[botType];
          const isRunning = (botRunning[botType] as { running?: boolean })?.running ?? false;
          return (
            <div className="card mb-md" key={botType}>
              <div className="card-header">
                <div className="flex gap-sm" style={{ alignItems: "center" }}>
                  <div className="asset-icon" style={{ width: 36, height: 36, fontSize: "1rem" }}>
                    {cfg.icon}
                  </div>
                  <div>
                    <div style={{ fontWeight: 600 }}>{cfg.label} Bot</div>
                    <div className="text-sm text-secondary">{cfg.timeframes} · {cfg.interval}</div>
                  </div>
                </div>
                <span className={`badge ${isRunning ? "badge-active" : "badge-stopped"}`}>
                  <span className="badge-dot" />
                  {isRunning ? "Hunting" : "Idle"}
                </span>
              </div>

              {bot?.trades && bot.trades.length > 0 ? (
                <div style={{ overflowX: "auto" }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Pair</th>
                        <th>Side</th>
                        <th>Entry</th>
                        <th>Size</th>
                        <th>Stop Loss</th>
                        <th>Take Profit</th>
                        <th>Confidence</th>
                        <th>Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {bot.trades.map((trade) => (
                        <tr key={trade.order_id}>
                          <td style={{ fontWeight: 600 }}>{trade.symbol}</td>
                          <td>
                            <span
                              className={`badge ${trade.side === "buy" ? "badge-active" : "badge-stopped"}`}
                              style={{ fontSize: "0.7rem" }}
                            >
                              {trade.side.toUpperCase()}
                            </span>
                          </td>
                          <td>${trade.entry_price < 0.01 ? trade.entry_price.toExponential(3) : trade.entry_price.toLocaleString()}</td>
                          <td>${trade.position_usd.toFixed(2)}</td>
                          <td className="negative">${trade.stop_loss < 0.01 ? trade.stop_loss.toExponential(3) : trade.stop_loss.toLocaleString()}</td>
                          <td className="positive">
                            {trade.take_profit
                              ? `$${trade.take_profit < 0.01 ? trade.take_profit.toExponential(3) : trade.take_profit.toLocaleString()}`
                              : "—"}
                          </td>
                          <td>
                            <div className="flex gap-sm" style={{ alignItems: "center" }}>
                              <div className="progress-bar" style={{ width: 50, height: 4 }}>
                                <div
                                  className="progress-fill"
                                  style={{
                                    width: `${(trade.signal_confidence ?? 0) * 100}%`,
                                    background: "var(--accent)",
                                  }}
                                />
                              </div>
                              <span className="text-xs text-secondary">
                                {((trade.signal_confidence ?? 0) * 100).toFixed(0)}%
                              </span>
                            </div>
                          </td>
                          <td className="text-secondary text-sm">
                            {new Date(trade.opened_at).toLocaleTimeString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div style={{
                  textAlign: "center", padding: "2rem",
                  color: "var(--text-tertiary)", fontSize: "0.85rem",
                }}>
                  {isRunning ? "Analyzing real market data..." : "No active positions"}
                </div>
              )}
            </div>
          );
        })}

      <div className="card mb-md">
        <div className="card-header">
          <h3>Live Price Sources</h3>
          <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>
            Click to expand pairs · Search any asset
          </span>
        </div>
        {liveExchangeEntries.map(([eid, ex]) => (
          <ExchangeDropdown
            key={eid}
            eid={eid}
            label={ex.label || eid}
            pairCount={ex.pairs}
            icon="🏦"
          />
        ))}
        {dexEntries.map(([eid, ex]) => (
          <ExchangeDropdown
            key={eid}
            eid={eid}
            label={eid.replace("_", " ").replace("dex", "DEX")}
            pairCount={ex.pairs}
            icon="🔗"
          />
        ))}
      </div>
    </div>
  );
}

export default Bots;
