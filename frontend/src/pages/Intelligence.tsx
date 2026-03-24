import { useEffect, useState, useCallback } from "react";
import {
  getIntelSummary,
  getIntelSignals,
  refreshIntel,
  getIntelCryptopanic,
  getIntelPumpDetector,
  getIntelWhaleTracker,
  getIntelTwitterSentiment,
  getIntelTwitterStream,
  getIntelCoinskid,
  getIntelCoinmarketcap,
  getIntelTokenScanner,
} from "../services/api";

interface Signal {
  source: string;
  signal_type: string;
  symbol: string;
  direction: string;
  confidence: number;
  detail: string;
  timestamp: number;
  age_seconds: number;
}

interface Summary {
  total_signals: number;
  bullish: number;
  bearish: number;
  neutral: number;
  pump_alerts: number;
  overall_sentiment: string;
  by_source: Record<string, number>;
  cached_sources: string[];
}

type SourceData = { items?: unknown[]; events?: unknown[]; data?: Record<string, unknown>; error?: string; fetched_at?: number };

function Intelligence() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");
  const [sourceData, setSourceData] = useState<Record<string, SourceData>>({});
  const [loadingSource, setLoadingSource] = useState("");
  const [tokenInput, setTokenInput] = useState("BTC");
  const [twitterQuery, setTwitterQuery] = useState("$BTC");

  const loadSummary = useCallback(async () => {
    try {
      const [s, sig] = await Promise.all([getIntelSummary(), getIntelSignals()]);
      setSummary(s.data);
      setSignals(sig.data || []);
    } catch { /* */ }
  }, []);

  useEffect(() => { loadSummary(); }, [loadSummary]);

  const handleRefreshAll = async () => {
    setRefreshing(true);
    try {
      await refreshIntel();
      await loadSummary();
    } catch { /* */ }
    setRefreshing(false);
  };

  const fetchSource = async (key: string, fn: () => Promise<{ data: SourceData }>) => {
    setLoadingSource(key);
    try {
      const r = await fn();
      setSourceData((prev) => ({ ...prev, [key]: r.data }));
    } catch (e: unknown) {
      setSourceData((prev) => ({ ...prev, [key]: { error: String(e) } }));
    }
    setLoadingSource("");
    await loadSummary();
  };

  const dirColor = (d: string) => {
    if (d === "bullish" || d === "pump_alert") return "var(--green)";
    if (d === "bearish") return "var(--red)";
    return "var(--text-secondary)";
  };

  const sentimentColor = (s: string) => {
    if (s === "bullish") return "var(--green)";
    if (s === "bearish") return "var(--red)";
    return "var(--yellow)";
  };

  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "signals", label: "Signals" },
    { id: "news", label: "News" },
    { id: "social", label: "Social" },
    { id: "whales", label: "Whales" },
    { id: "market", label: "Market" },
    { id: "coinskid", label: "CoinSkid" },
  ];

  return (
    <div>
      <div className="page-header">
        <h2>Intelligence Hub</h2>
        <button className="btn btn-primary" onClick={handleRefreshAll} disabled={refreshing}>
          {refreshing ? "Refreshing All Sources..." : "Refresh All"}
        </button>
      </div>

      {summary && (
        <div className="stats-grid" style={{ marginBottom: 24 }}>
          <div className="stat-card">
            <div className="stat-label">Overall Sentiment</div>
            <div className="stat-value" style={{ color: sentimentColor(summary.overall_sentiment) }}>
              {summary.overall_sentiment.toUpperCase()}
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Total Signals</div>
            <div className="stat-value">{summary.total_signals}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Bullish</div>
            <div className="stat-value" style={{ color: "var(--green)" }}>{summary.bullish}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Bearish</div>
            <div className="stat-value" style={{ color: "var(--red)" }}>{summary.bearish}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Pump Alerts</div>
            <div className="stat-value" style={{ color: "var(--yellow)" }}>{summary.pump_alerts}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Active Sources</div>
            <div className="stat-value">{summary.cached_sources.length}</div>
          </div>
        </div>
      )}

      <div className="tab-bar" style={{ marginBottom: 16 }}>
        {tabs.map((t) => (
          <button
            key={t.id}
            className={`tab-btn ${activeTab === t.id ? "active" : ""}`}
            onClick={() => setActiveTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === "overview" && summary && (
        <div className="card">
          <h3>Signal Sources</h3>
          <table className="data-table">
            <thead>
              <tr><th>Source</th><th>Signals</th></tr>
            </thead>
            <tbody>
              {Object.entries(summary.by_source).map(([src, cnt]) => (
                <tr key={src}><td>{src}</td><td>{cnt}</td></tr>
              ))}
              {Object.keys(summary.by_source).length === 0 && (
                <tr><td colSpan={2} style={{ textAlign: "center", opacity: 0.5 }}>No signals yet. Click "Refresh All" to fetch data from all sources.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {activeTab === "signals" && (
        <div className="card">
          <h3>Live Signals ({signals.length})</h3>
          <div style={{ overflowX: "auto" }}>
            <table className="data-table">
              <thead>
                <tr><th>Source</th><th>Type</th><th>Symbol</th><th>Direction</th><th>Confidence</th><th>Detail</th><th>Age</th></tr>
              </thead>
              <tbody>
                {signals.map((s, i) => (
                  <tr key={i}>
                    <td>{s.source}</td>
                    <td>{s.signal_type}</td>
                    <td style={{ fontWeight: 600 }}>{s.symbol}</td>
                    <td style={{ color: dirColor(s.direction), fontWeight: 600 }}>{s.direction}</td>
                    <td>{(s.confidence * 100).toFixed(0)}%</td>
                    <td style={{ maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.detail}</td>
                    <td>{s.age_seconds < 60 ? `${s.age_seconds}s` : `${Math.floor(s.age_seconds / 60)}m`}</td>
                  </tr>
                ))}
                {signals.length === 0 && (
                  <tr><td colSpan={7} style={{ textAlign: "center", opacity: 0.5 }}>No signals. Refresh sources to generate signals.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === "news" && (
        <div>
          <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            <button className="btn btn-primary" onClick={() => fetchSource("cryptopanic", () => getIntelCryptopanic(true))} disabled={loadingSource === "cryptopanic"}>
              {loadingSource === "cryptopanic" ? "Loading..." : "CryptoPanic News"}
            </button>
            <button className="btn btn-primary" onClick={() => fetchSource("newspro", () => getIntelPumpDetector(undefined, true) as Promise<{ data: SourceData }>)} disabled={loadingSource === "newspro"}>
              {loadingSource === "newspro" ? "Loading..." : "Crypto News Pro"}
            </button>
          </div>
          {renderSourceData("cryptopanic")}
          {renderSourceData("newspro")}
        </div>
      )}

      {activeTab === "social" && (
        <div>
          <div style={{ display: "flex", gap: 8, marginBottom: 16, alignItems: "center" }}>
            <input
              style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg-secondary)", color: "var(--text-primary)", width: 120 }}
              value={twitterQuery}
              onChange={(e) => setTwitterQuery(e.target.value)}
              placeholder="$BTC"
            />
            <button className="btn btn-primary" onClick={() => fetchSource("twitter_sentiment", () => getIntelTwitterSentiment(twitterQuery, true))} disabled={loadingSource === "twitter_sentiment"}>
              {loadingSource === "twitter_sentiment" ? "Loading..." : "Twitter Sentiment"}
            </button>
            <button className="btn btn-primary" onClick={() => fetchSource("twitter_stream", () => getIntelTwitterStream("", true))} disabled={loadingSource === "twitter_stream"}>
              {loadingSource === "twitter_stream" ? "Loading..." : "Twitter Stream"}
            </button>
          </div>
          {renderSourceData("twitter_sentiment")}
          {renderSourceData("twitter_stream")}
        </div>
      )}

      {activeTab === "whales" && (
        <div>
          <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            <button className="btn btn-primary" onClick={() => fetchSource("whale", () => getIntelWhaleTracker(true))} disabled={loadingSource === "whale"}>
              {loadingSource === "whale" ? "Loading..." : "Whale Tracker"}
            </button>
          </div>
          {renderSourceData("whale")}
        </div>
      )}

      {activeTab === "market" && (
        <div>
          <div style={{ display: "flex", gap: 8, marginBottom: 16, alignItems: "center", flexWrap: "wrap" }}>
            <button className="btn btn-primary" onClick={() => fetchSource("pump", () => getIntelPumpDetector(undefined, true) as Promise<{ data: SourceData }>)} disabled={loadingSource === "pump"}>
              {loadingSource === "pump" ? "Loading..." : "Pump Detector"}
            </button>
            <button className="btn btn-primary" onClick={() => fetchSource("cmc", () => getIntelCoinmarketcap(true))} disabled={loadingSource === "cmc"}>
              {loadingSource === "cmc" ? "Loading..." : "CoinMarketCap"}
            </button>
            <input
              style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg-secondary)", color: "var(--text-primary)", width: 80 }}
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              placeholder="BTC"
            />
            <button className="btn btn-primary" onClick={() => fetchSource("scanner", () => getIntelTokenScanner(tokenInput, true))} disabled={loadingSource === "scanner"}>
              {loadingSource === "scanner" ? "Loading..." : "Token Scanner"}
            </button>
          </div>
          {renderSourceData("pump")}
          {renderSourceData("cmc")}
          {renderSourceData("scanner")}
        </div>
      )}

      {activeTab === "coinskid" && (
        <div>
          <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
            <button className="btn btn-primary" onClick={() => fetchSource("ckr", () => getIntelCoinskid("ckr_index", true))} disabled={loadingSource === "ckr"}>
              {loadingSource === "ckr" ? "Loading..." : "CKR Index"}
            </button>
            <button className="btn btn-primary" onClick={() => fetchSource("heatmap", () => getIntelCoinskid("heatmap", true))} disabled={loadingSource === "heatmap"}>
              {loadingSource === "heatmap" ? "Loading..." : "Buy/Sell Heatmap"}
            </button>
            <button className="btn btn-primary" onClick={() => fetchSource("blocks", () => getIntelCoinskid("crypto_blocks", true))} disabled={loadingSource === "blocks"}>
              {loadingSource === "blocks" ? "Loading..." : "Crypto Blocks"}
            </button>
            <button className="btn btn-primary" onClick={() => fetchSource("sellshort", () => getIntelCoinskid("sell_short", true))} disabled={loadingSource === "sellshort"}>
              {loadingSource === "sellshort" ? "Loading..." : "Sell/Short Warnings"}
            </button>
          </div>
          {renderSourceData("ckr")}
          {renderSourceData("heatmap")}
          {renderSourceData("blocks")}
          {renderSourceData("sellshort")}
        </div>
      )}
    </div>
  );

  function renderSourceData(key: string) {
    const data = sourceData[key];
    if (!data) return null;
    if (data.error) return <div className="card" style={{ color: "var(--red)" }}>Error: {data.error}</div>;
    const items = data.items || data.events || (data.data ? [data.data] : []);
    if (!Array.isArray(items) || items.length === 0) {
      return <div className="card" style={{ opacity: 0.5 }}>No data returned. Check your Apify API token in Settings.</div>;
    }
    return (
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, opacity: 0.5, marginBottom: 8 }}>
          {key} -- {Array.isArray(items) ? items.length : 1} items
          {data.fetched_at && ` -- fetched ${new Date(data.fetched_at * 1000).toLocaleTimeString()}`}
        </div>
        <div style={{ maxHeight: 400, overflow: "auto" }}>
          <table className="data-table">
            <thead>
              <tr>
                {typeof items[0] === "object" && items[0] !== null
                  ? Object.keys(items[0] as Record<string, unknown>).slice(0, 8).map((k) => <th key={k}>{k}</th>)
                  : <th>Value</th>
                }
              </tr>
            </thead>
            <tbody>
              {(items as Record<string, unknown>[]).slice(0, 50).map((item, i) => (
                <tr key={i}>
                  {typeof item === "object" && item !== null
                    ? Object.values(item).slice(0, 8).map((v, j) => (
                        <td key={j} style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {typeof v === "object" ? JSON.stringify(v) : String(v ?? "")}
                        </td>
                      ))
                    : <td>{String(item)}</td>
                  }
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }
}

export default Intelligence;
