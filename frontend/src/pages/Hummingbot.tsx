import { useState, useEffect, useCallback } from "react";
import {
  hbotStatus,
  hbotConnect,
  hbotDisconnect,
  hbotSetMode,
  hbotAddExchange,
  hbotListExchanges,
  hbotStartStrategy,
  hbotStopStrategy,
  hbotListBots,
  hbotGetFees,
  hbotGetRecentFees,
  hbotConfigureRpc,
  hbotGetRpcConfigs,
  hbotGatewayStatus,
  hbotGetStrategyTypes,
} from "../services/api";

type Tab = "overview" | "exchanges" | "strategies" | "fees" | "gateway";

interface StatusData {
  connected: boolean;
  gateway_connected: boolean;
  paper_mode: boolean;
  health?: Record<string, unknown>;
  accounts?: number | Record<string, unknown>;
  gateway_connectors?: Record<string, unknown>;
  gateway_chains?: Record<string, unknown>;
  rpc_configs?: Record<string, unknown>;
}

export default function Hummingbot() {
  const [tab, setTab] = useState<Tab>("overview");
  const [status, setStatus] = useState<StatusData | null>(null);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");

  const [connectUrl, setConnectUrl] = useState("");
  const [connectUser, setConnectUser] = useState("admin");
  const [connectPass, setConnectPass] = useState("admin");

  const [exExchange, setExExchange] = useState("binance");
  const [exKey, setExKey] = useState("");
  const [exSecret, setExSecret] = useState("");
  const [exchanges, setExchanges] = useState<Record<string, unknown> | null>(null);

  const [strategyTypes, setStrategyTypes] = useState<{ id: string; name: string; description: string; params: string[] }[]>([]);
  const [selectedStrategy, setSelectedStrategy] = useState("");
  const [strategyParams, setStrategyParams] = useState<Record<string, string>>({});
  const [bots, setBots] = useState<unknown[]>([]);

  const [fees, setFees] = useState<Record<string, unknown> | null>(null);
  const [recentFees, setRecentFees] = useState<unknown[]>([]);

  const [rpcChain, setRpcChain] = useState("ethereum");
  const [rpcProvider, setRpcProvider] = useState("flashbots");
  const [rpcApiKey, setRpcApiKey] = useState("");
  const [rpcConfigs, setRpcConfigs] = useState<Record<string, unknown>>({});
  const [gatewayStatus, setGatewayStatus] = useState<Record<string, unknown> | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      const r = await hbotStatus();
      setStatus(r.data);
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    loadStatus();
    const iv = setInterval(loadStatus, 15000);
    return () => clearInterval(iv);
  }, [loadStatus]);

  useEffect(() => {
    if (tab === "strategies") {
      hbotGetStrategyTypes().then((r) => setStrategyTypes(r.data.types || [])).catch(() => {});
      hbotListBots().then((r) => setBots(Array.isArray(r.data) ? r.data : [])).catch(() => {});
    }
    if (tab === "exchanges") {
      hbotListExchanges().then((r) => setExchanges(r.data)).catch(() => {});
    }
    if (tab === "fees") {
      hbotGetFees().then((r) => setFees(r.data)).catch(() => {});
      hbotGetRecentFees(20).then((r) => setRecentFees(Array.isArray(r.data) ? r.data : [])).catch(() => {});
    }
    if (tab === "gateway") {
      hbotGetRpcConfigs().then((r) => setRpcConfigs(r.data || {})).catch(() => {});
      hbotGatewayStatus().then((r) => setGatewayStatus(r.data)).catch(() => {});
    }
  }, [tab]);

  const doConnect = async () => {
    setLoading(true);
    try {
      const r = await hbotConnect({
        hbot_url: connectUrl || undefined,
        username: connectUser,
        password: connectPass,
      });
      setMsg(r.data.status === "connected" ? "Connected!" : "Connection failed");
      loadStatus();
    } catch (e: unknown) {
      setMsg(`Error: ${(e as Error).message}`);
    }
    setLoading(false);
  };

  const doDisconnect = async () => {
    await hbotDisconnect();
    setMsg("Disconnected");
    loadStatus();
  };

  const doToggleMode = async () => {
    if (!status) return;
    await hbotSetMode(!status.paper_mode);
    loadStatus();
  };

  const doAddExchange = async () => {
    setLoading(true);
    try {
      await hbotAddExchange({ exchange: exExchange, api_key: exKey, api_secret: exSecret });
      setMsg(`Added ${exExchange}`);
      setExKey("");
      setExSecret("");
      hbotListExchanges().then((r) => setExchanges(r.data)).catch(() => {});
    } catch (e: unknown) {
      setMsg(`Error: ${(e as Error).message}`);
    }
    setLoading(false);
  };

  const doStartStrategy = async () => {
    if (!selectedStrategy) return;
    setLoading(true);
    try {
      const params: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(strategyParams)) {
        const num = Number(v);
        params[k] = isNaN(num) ? v : num;
      }
      const r = await hbotStartStrategy({
        strategy_type: selectedStrategy,
        params,
      });
      setMsg(`Strategy started: ${r.data.bot_name || selectedStrategy}`);
      hbotListBots().then((r2) => setBots(Array.isArray(r2.data) ? r2.data : [])).catch(() => {});
    } catch (e: unknown) {
      setMsg(`Error: ${(e as Error).message}`);
    }
    setLoading(false);
  };

  const doStopBot = async (name: string) => {
    await hbotStopStrategy(name);
    setMsg(`Stopped ${name}`);
    hbotListBots().then((r) => setBots(Array.isArray(r.data) ? r.data : [])).catch(() => {});
  };

  const doConfigureRpc = async () => {
    setLoading(true);
    try {
      const r = await hbotConfigureRpc({
        chain: rpcChain,
        provider: rpcProvider,
        api_key: rpcApiKey || undefined,
      });
      setMsg(`RPC configured: ${r.data.provider} for ${r.data.chain}`);
      hbotGetRpcConfigs().then((r2) => setRpcConfigs(r2.data || {})).catch(() => {});
    } catch (e: unknown) {
      setMsg(`Error: ${(e as Error).message}`);
    }
    setLoading(false);
  };

  const tabClass = (t: Tab) => `card-tab${tab === t ? " active" : ""}`;

  return (
    <div>
      <div className="page-header">
        <h2>Hummingbot</h2>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span
            style={{
              width: 10,
              height: 10,
              borderRadius: "50%",
              background: status?.connected ? "var(--green)" : "var(--red)",
              display: "inline-block",
            }}
          />
          <span style={{ color: "var(--text-secondary)", fontSize: 13 }}>
            {status?.connected
              ? "API Connected"
              : status?.gateway_connected
                ? "Gateway Connected"
                : "Disconnected"}
          </span>
          {(status?.connected || status?.gateway_connected) && (
            <span
              style={{
                fontSize: 11,
                padding: "2px 8px",
                borderRadius: 4,
                background: status.paper_mode ? "rgba(255,193,7,0.15)" : "rgba(0,200,83,0.15)",
                color: status.paper_mode ? "var(--yellow)" : "var(--green)",
              }}
            >
              {status.paper_mode ? "PAPER" : "LIVE"}
            </span>
          )}
        </div>
      </div>

      {msg && (
        <div className="card" style={{ padding: "8px 16px", marginBottom: 12, fontSize: 13 }}>
          {msg}
          <span style={{ float: "right", cursor: "pointer" }} onClick={() => setMsg("")}>x</span>
        </div>
      )}

      <div className="card-tabs" style={{ marginBottom: 16 }}>
        <button className={tabClass("overview")} onClick={() => setTab("overview")}>Overview</button>
        <button className={tabClass("exchanges")} onClick={() => setTab("exchanges")}>Exchanges</button>
        <button className={tabClass("strategies")} onClick={() => setTab("strategies")}>Strategies</button>
        <button className={tabClass("fees")} onClick={() => setTab("fees")}>Fees</button>
        <button className={tabClass("gateway")} onClick={() => setTab("gateway")}>Gateway & RPC</button>
      </div>

      {tab === "overview" && (
        <div>
          <div className="card" style={{ padding: 20 }}>
            <h3 style={{ marginBottom: 16 }}>Connection</h3>
            {!status?.connected && !status?.gateway_connected ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 400 }}>
                <input
                  className="input"
                  placeholder="Hummingbot API URL (leave empty for default)"
                  value={connectUrl}
                  onChange={(e) => setConnectUrl(e.target.value)}
                />
                <div style={{ display: "flex", gap: 8 }}>
                  <input className="input" placeholder="Username" value={connectUser} onChange={(e) => setConnectUser(e.target.value)} />
                  <input className="input" type="password" placeholder="Password" value={connectPass} onChange={(e) => setConnectPass(e.target.value)} />
                </div>
                <button className="btn btn-primary" onClick={doConnect} disabled={loading}>
                  {loading ? "Connecting..." : "Connect to Hummingbot"}
                </button>
              </div>
            ) : (
              <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                <button className="btn btn-danger" onClick={doDisconnect}>Disconnect</button>
                <button className="btn" onClick={doToggleMode}>
                  Switch to {status?.paper_mode ? "LIVE" : "PAPER"} Mode
                </button>
              </div>
            )}
          </div>

          {(status?.connected || status?.gateway_connected) && (
            <div className="grid-3" style={{ marginTop: 16 }}>
              <div className="card stat-card">
                <div className="stat-label">Mode</div>
                <div className="stat-value" style={{ color: status?.paper_mode ? "var(--yellow)" : "var(--green)" }}>
                  {status?.paper_mode ? "Paper" : "Live"}
                </div>
              </div>
              <div className="card stat-card">
                <div className="stat-label">Hummingbot API</div>
                <div className="stat-value" style={{ fontSize: 14, color: status?.connected ? "var(--green)" : "var(--text-secondary)" }}>
                  {status?.connected ? "Connected" : "Offline"}
                </div>
              </div>
              <div className="card stat-card">
                <div className="stat-label">Gateway</div>
                <div className="stat-value" style={{ fontSize: 14, color: status?.gateway_connected ? "var(--green)" : "var(--text-secondary)" }}>
                  {status?.gateway_connected ? "Connected" : "Offline"}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === "exchanges" && (
        <div>
          <div className="card" style={{ padding: 20 }}>
            <h3 style={{ marginBottom: 16 }}>Add Exchange Credentials</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 500 }}>
              <select className="input" value={exExchange} onChange={(e) => setExExchange(e.target.value)}>
                {["binance", "coinbase", "kraken", "kucoin", "okx", "bybit", "gateio", "bitget", "mexc"].map((ex) => (
                  <option key={ex} value={ex}>{ex}</option>
                ))}
              </select>
              <input className="input" placeholder="API Key" value={exKey} onChange={(e) => setExKey(e.target.value)} />
              <input className="input" type="password" placeholder="API Secret" value={exSecret} onChange={(e) => setExSecret(e.target.value)} />
              <button className="btn btn-primary" onClick={doAddExchange} disabled={loading || !exKey || !exSecret}>
                Add Exchange
              </button>
            </div>
          </div>
          {exchanges && (
            <div className="card" style={{ padding: 20, marginTop: 16 }}>
              <h3>Connected Exchanges</h3>
              <pre style={{ fontSize: 12, color: "var(--text-secondary)", whiteSpace: "pre-wrap" }}>
                {JSON.stringify(exchanges, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}

      {tab === "strategies" && (
        <div>
          <div className="card" style={{ padding: 20 }}>
            <h3 style={{ marginBottom: 16 }}>Start Strategy</h3>
            <select
              className="input"
              style={{ marginBottom: 12 }}
              value={selectedStrategy}
              onChange={(e) => {
                setSelectedStrategy(e.target.value);
                setStrategyParams({});
              }}
            >
              <option value="">Select strategy...</option>
              {strategyTypes.map((st) => (
                <option key={st.id} value={st.id}>{st.name}</option>
              ))}
            </select>

            {selectedStrategy && (
              <>
                <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 12 }}>
                  {strategyTypes.find((s) => s.id === selectedStrategy)?.description}
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 400 }}>
                  {strategyTypes
                    .find((s) => s.id === selectedStrategy)
                    ?.params.map((p) => (
                      <input
                        key={p}
                        className="input"
                        placeholder={p}
                        value={strategyParams[p] || ""}
                        onChange={(e) => setStrategyParams({ ...strategyParams, [p]: e.target.value })}
                      />
                    ))}
                  <button className="btn btn-primary" onClick={doStartStrategy} disabled={loading}>
                    Start Strategy
                  </button>
                </div>
              </>
            )}
          </div>

          {bots.length > 0 && (
            <div className="card" style={{ padding: 20, marginTop: 16 }}>
              <h3>Running Bots</h3>
              <table className="table" style={{ marginTop: 8 }}>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {bots.map((b: unknown, i: number) => {
                    const bot = b as Record<string, unknown>;
                    return (
                      <tr key={i}>
                        <td>{String(bot.name || bot.bot_name || `bot-${i}`)}</td>
                        <td>{String(bot.status || "unknown")}</td>
                        <td>
                          <button
                            className="btn btn-danger"
                            style={{ fontSize: 11, padding: "2px 8px" }}
                            onClick={() => doStopBot(String(bot.name || bot.bot_name || ""))}
                          >
                            Stop
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === "fees" && (
        <div>
          {fees && (
            <div className="grid-3" style={{ marginBottom: 16 }}>
              <div className="card stat-card">
                <div className="stat-label">Total Fees</div>
                <div className="stat-value">${(fees as Record<string, unknown>).cumulative_fees_usd as string}</div>
              </div>
              <div className="card stat-card">
                <div className="stat-label">Total Gas</div>
                <div className="stat-value">${(fees as Record<string, unknown>).cumulative_gas_usd as string}</div>
              </div>
              <div className="card stat-card">
                <div className="stat-label">Total Slippage</div>
                <div className="stat-value">${(fees as Record<string, unknown>).cumulative_slippage_usd as string}</div>
              </div>
            </div>
          )}
          {recentFees.length > 0 && (
            <div className="card" style={{ padding: 20 }}>
              <h3>Recent Fee Events</h3>
              <div style={{ overflowX: "auto" }}>
                <table className="table" style={{ marginTop: 8, fontSize: 12 }}>
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Exchange</th>
                      <th>Pair</th>
                      <th>Side</th>
                      <th>Fee</th>
                      <th>Gas</th>
                      <th>Slippage</th>
                      <th>Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentFees.map((f: unknown, i: number) => {
                      const fee = f as Record<string, unknown>;
                      return (
                        <tr key={i}>
                          <td>{String(fee.timestamp || "").slice(11, 19)}</td>
                          <td>{String(fee.exchange)}</td>
                          <td>{String(fee.trading_pair)}</td>
                          <td>{String(fee.side)}</td>
                          <td>${String(fee.fee_usd)}</td>
                          <td>{fee.gas_usd ? `$${fee.gas_usd}` : "-"}</td>
                          <td>{fee.slippage_usd ? `$${fee.slippage_usd}` : "-"}</td>
                          <td>${String(fee.total_cost_usd)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === "gateway" && (
        <div>
          <div className="card" style={{ padding: 20, marginBottom: 16 }}>
            <h3 style={{ marginBottom: 16 }}>Private RPC Configuration</h3>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 12 }}>
              Configure private RPCs to protect against frontrunning and MEV attacks.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 500 }}>
              <select className="input" value={rpcChain} onChange={(e) => setRpcChain(e.target.value)}>
                <option value="ethereum">Ethereum</option>
                <option value="solana">Solana</option>
              </select>
              <select className="input" value={rpcProvider} onChange={(e) => setRpcProvider(e.target.value)}>
                {rpcChain === "ethereum" ? (
                  <>
                    <option value="flashbots">Flashbots Protect (MEV Protection)</option>
                    <option value="infura">Infura</option>
                  </>
                ) : (
                  <option value="helius">Helius (Jito MEV Protection)</option>
                )}
              </select>
              {rpcProvider !== "flashbots" && (
                <input
                  className="input"
                  placeholder="API Key"
                  value={rpcApiKey}
                  onChange={(e) => setRpcApiKey(e.target.value)}
                />
              )}
              <button className="btn btn-primary" onClick={doConfigureRpc} disabled={loading}>
                Configure RPC
              </button>
            </div>
          </div>

          {Object.keys(rpcConfigs).length > 0 && (
            <div className="card" style={{ padding: 20, marginBottom: 16 }}>
              <h3>Active RPC Configs</h3>
              {Object.entries(rpcConfigs).map(([chain, cfg]) => (
                <div key={chain} style={{ marginTop: 8, fontSize: 13 }}>
                  <strong>{chain}</strong>: {(cfg as Record<string, unknown>).provider as string} — {(cfg as Record<string, unknown>).url_preview as string}
                </div>
              ))}
            </div>
          )}

          <div className="card" style={{ padding: 20 }}>
            <h3>Gateway Status</h3>
            {gatewayStatus ? (
              <pre style={{ fontSize: 12, color: "var(--text-secondary)", whiteSpace: "pre-wrap" }}>
                {JSON.stringify(gatewayStatus, null, 2)}
              </pre>
            ) : (
              <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>Gateway not connected</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
