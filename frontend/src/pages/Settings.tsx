import { useEffect, useState } from "react";
import { getConfig, getHealth, connectExchange } from "../services/api";
import api from "../services/api";

function Settings() {
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [health, setHealth] = useState<{ status: string; paper_trading: boolean } | null>(null);
  const [paperMode, setPaperMode] = useState(true);
  const [form, setForm] = useState({ exchange_id: "coinbase", api_key: "", api_secret: "" });
  const [walletForm, setWalletForm] = useState({ label: "", address: "", chain: "ethereum" });
  const [status, setStatus] = useState("");
  const [activeTab, setActiveTab] = useState("exchanges");

  useEffect(() => {
    const load = async () => {
      try {
        const [c, h] = await Promise.all([getConfig(), getHealth()]);
        setConfig(c.data);
        setHealth(h.data);
        setPaperMode(h.data.paper_trading);
      } catch {
        /* not connected */
      }
    };
    load();
  }, []);

  const handleConnect = async () => {
    try {
      await connectExchange(form.exchange_id, form.api_key, form.api_secret);
      setStatus(`Connected to ${form.exchange_id}`);
      setForm({ ...form, api_key: "", api_secret: "" });
    } catch {
      setStatus("Connection failed");
    }
  };

  const togglePaperMode = async () => {
    try {
      const newMode = !paperMode;
      await api.post("/toggle-paper-mode", { paper_trading: newMode });
      setPaperMode(newMode);
    } catch {
      setPaperMode(!paperMode);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h2>Settings</h2>
      </div>

      <div className="card mb-md" style={{ padding: "1.5rem" }}>
        <div className="flex-between">
          <div>
            <div style={{ fontWeight: 600, fontSize: "1rem" }}>Trading Mode</div>
            <div className="text-sm text-secondary mt-sm">
              {paperMode
                ? "Paper trading mode — no real funds will be used"
                : "Live trading mode — real orders will be placed"
              }
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <span className={`text-sm font-semibold ${paperMode ? "neutral" : "text-secondary"}`}>Paper</span>
            <button
              onClick={togglePaperMode}
              style={{
                width: 52,
                height: 28,
                borderRadius: 14,
                border: "none",
                cursor: "pointer",
                background: paperMode ? "var(--yellow)" : "var(--green)",
                position: "relative",
                transition: "background 0.3s ease",
              }}
            >
              <div style={{
                width: 22,
                height: 22,
                borderRadius: "50%",
                background: "#fff",
                position: "absolute",
                top: 3,
                left: paperMode ? 3 : 27,
                transition: "left 0.3s ease",
                boxShadow: "0 2px 4px rgba(0,0,0,0.3)",
              }} />
            </button>
            <span className={`text-sm font-semibold ${!paperMode ? "positive" : "text-secondary"}`}>Live</span>
          </div>
        </div>
      </div>

      <div className="grid grid-2 mb-md">
        <div className="card">
          <h3>System Status</h3>
          <div style={{ marginTop: "0.5rem" }}>
            {[
              {
                label: "API",
                value: health ? "Connected" : "Disconnected",
                cls: health ? "positive" : "negative",
              },
              {
                label: "Mode",
                value: paperMode ? "Paper Trading" : "Live Trading",
                cls: paperMode ? "neutral" : "positive",
              },
              {
                label: "Data Store",
                value: health ? "In-Memory (Active)" : "Offline",
                cls: health ? "positive" : "negative",
              },
              {
                label: "Price Engine",
                value: health ? "Simulated (Active)" : "Offline",
                cls: health ? "positive" : "negative",
              },
            ].map((row) => (
              <div className="flex-between" key={row.label} style={{ padding: "0.6rem 0", borderBottom: "1px solid var(--border)" }}>
                <span className="text-sm text-secondary">{row.label}</span>
                <span className="flex gap-sm" style={{ alignItems: "center" }}>
                  <span style={{
                    width: 6, height: 6, borderRadius: "50%",
                    background: row.cls === "positive" ? "var(--green)" : row.cls === "negative" ? "var(--red)" : "var(--yellow)",
                  }} />
                  <span className={`text-sm font-semibold ${row.cls}`}>{row.value}</span>
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h3>Risk Configuration</h3>
          <div style={{ marginTop: "0.5rem" }}>
            {config && Object.entries(config).map(([key, val]) => (
              <div className="flex-between" key={key} style={{ padding: "0.6rem 0", borderBottom: "1px solid var(--border)" }}>
                <span className="text-sm text-secondary">{key.replace(/_/g, " ")}</span>
                <span className="text-sm font-semibold">
                  {typeof val === "boolean" ? (
                    <span className={val ? "positive" : "negative"}>{String(val)}</span>
                  ) : typeof val === "number" ? (
                    key.includes("usd") ? `$${val}` : key.includes("pct") ? `${val}%` : `${val}x`
                  ) : String(val)}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="tabs">
        {["exchanges", "wallets"].map((tab) => (
          <button
            key={tab}
            className={`tab ${activeTab === tab ? "active" : ""}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab === "exchanges" ? "Connect Exchange" : "Connect Wallet"}
          </button>
        ))}
      </div>

      {activeTab === "exchanges" && (
        <div className="card">
          <div className="card-header">
            <h3>Exchange API</h3>
          </div>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            <div className="input-group" style={{ flex: 1, minWidth: 140 }}>
              <label className="input-label">Exchange</label>
              <select value={form.exchange_id} onChange={(e) => setForm({ ...form, exchange_id: e.target.value })}>
                <option value="coinbase">Coinbase</option>
                <option value="binance">Binance</option>
                <option value="kraken">Kraken</option>
                <option value="kucoin">KuCoin</option>
              </select>
            </div>
            <div className="input-group" style={{ flex: 2, minWidth: 200 }}>
              <label className="input-label">API Key</label>
              <input
                type="password"
                value={form.api_key}
                onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                placeholder="Enter your API key"
              />
            </div>
            <div className="input-group" style={{ flex: 2, minWidth: 200 }}>
              <label className="input-label">API Secret</label>
              <input
                type="password"
                value={form.api_secret}
                onChange={(e) => setForm({ ...form, api_secret: e.target.value })}
                placeholder="Enter your API secret"
              />
            </div>
            <button className="btn btn-primary" onClick={handleConnect} style={{ marginTop: "auto" }}>
              Connect
            </button>
          </div>
          {status && (
            <div style={{
              marginTop: "0.75rem",
              padding: "0.6rem 1rem",
              borderRadius: "var(--radius-md)",
              background: status.includes("fail") ? "var(--red-dim)" : "var(--green-dim)",
              color: status.includes("fail") ? "var(--red)" : "var(--green)",
              fontSize: "0.85rem",
              fontWeight: 500,
            }}>
              {status}
            </div>
          )}
        </div>
      )}

      {activeTab === "wallets" && (
        <div className="card">
          <div className="card-header">
            <h3>Self-Custody Wallets</h3>
          </div>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            <div className="input-group" style={{ flex: 1, minWidth: 120 }}>
              <label className="input-label">Label</label>
              <input
                value={walletForm.label}
                onChange={(e) => setWalletForm({ ...walletForm, label: e.target.value })}
                placeholder="My Wallet"
              />
            </div>
            <div className="input-group" style={{ flex: 1, minWidth: 120 }}>
              <label className="input-label">Chain</label>
              <select value={walletForm.chain} onChange={(e) => setWalletForm({ ...walletForm, chain: e.target.value })}>
                <option value="ethereum">Ethereum (MetaMask)</option>
                <option value="xrpl">XRPL (Xaman)</option>
              </select>
            </div>
            <div className="input-group" style={{ flex: 3, minWidth: 250 }}>
              <label className="input-label">Wallet Address</label>
              <input
                value={walletForm.address}
                onChange={(e) => setWalletForm({ ...walletForm, address: e.target.value })}
                placeholder="0x... or r..."
              />
            </div>
            <button className="btn btn-primary" style={{ marginTop: "auto" }}>
              Track Wallet
            </button>
          </div>

          <div className="divider" />

          <div style={{ textAlign: "center", padding: "1.5rem", color: "var(--text-tertiary)", fontSize: "0.85rem" }}>
            <div style={{ fontSize: "1.5rem", marginBottom: "0.5rem" }}>
              {walletForm.chain === "xrpl" ? "🔗" : "🦊"}
            </div>
            Connect your self-custody wallet to track balances in real-time.
            <br />
            Supports MetaMask (EVM) and Xaman (XRPL).
          </div>
        </div>
      )}
    </div>
  );
}

export default Settings;
