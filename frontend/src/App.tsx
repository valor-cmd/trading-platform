import { Routes, Route, NavLink, useSearchParams } from "react-router-dom";
import { useEffect, useState } from "react";
import Dashboard from "./pages/Dashboard";
import Bots from "./pages/Bots";
import Accounting from "./pages/Accounting";
import Backtest from "./pages/Backtest";
import Settings from "./pages/Settings";
import Hummingbot from "./pages/Hummingbot";
import { getHealth, getAccounts } from "./services/api";

interface AccountInfo { name: string; label: string; daily_target_pct: number | null; target_hit: boolean; }

function App() {
  const [paperMode, setPaperMode] = useState(true);
  const [searchParams, setSearchParams] = useSearchParams();
  const [accounts, setAccounts] = useState<AccountInfo[]>([]);
  const activeAccount = searchParams.get("account") || "default";

  const setActiveAccount = (name: string) => {
    const p = new URLSearchParams(searchParams);
    if (name === "default") p.delete("account"); else p.set("account", name);
    setSearchParams(p, { replace: true });
  };

  useEffect(() => {
    getHealth()
      .then((r) => setPaperMode(r.data.paper_trading))
      .catch(() => {});
    getAccounts()
      .then((r) => setAccounts(r.data || []))
      .catch(() => {});
  }, []);

  return (
    <div className="app">
      <nav className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-brand-icon">TB</div>
          <h1>TradeBot</h1>
        </div>

        <div className="sidebar-nav">
          <NavLink to="/" end>
            <span className="nav-icon">◎</span>
            Dashboard
          </NavLink>
          <NavLink to="/bots">
            <span className="nav-icon">⚡</span>
            Bots
          </NavLink>
          <NavLink to="/accounting">
            <span className="nav-icon">◈</span>
            Accounting
          </NavLink>
          <NavLink to="/backtest">
            <span className="nav-icon">▦</span>
            Backtest
          </NavLink>
          <NavLink to="/hummingbot">
            <span className="nav-icon">⬡</span>
            Hummingbot
          </NavLink>
          <NavLink to="/settings">
            <span className="nav-icon">⚙</span>
            Settings
          </NavLink>
        </div>

        <div className="sidebar-mode">
          <div className="sidebar-mode-label">Trading Mode</div>
          <div className="sidebar-mode-value">
            <span
              className="sidebar-mode-dot"
              style={{ background: paperMode ? "var(--yellow)" : "var(--green)" }}
            />
            {paperMode ? "Paper Trading" : "Live Trading"}
          </div>
        </div>
      </nav>

      <div className="mobile-nav">
        <div className="mobile-nav-inner">
          <NavLink to="/" end>
            <span className="mobile-nav-icon">◎</span>
            Home
          </NavLink>
          <NavLink to="/accounting">
            <span className="mobile-nav-icon">◈</span>
            P&L
          </NavLink>
          <NavLink to="/bots" className="trade-btn">
            <span>⚡</span>
          </NavLink>
          <NavLink to="/backtest">
            <span className="mobile-nav-icon">▦</span>
            Backtest
          </NavLink>
          <NavLink to="/hummingbot">
            <span className="mobile-nav-icon">⬡</span>
            HBot
          </NavLink>
          <NavLink to="/settings">
            <span className="mobile-nav-icon">⚙</span>
            Settings
          </NavLink>
        </div>
      </div>

      <main className="content">
        <Routes>
          <Route path="/" element={<Dashboard activeAccount={activeAccount} setActiveAccount={setActiveAccount} accounts={accounts} reloadAccounts={() => getAccounts().then(r => setAccounts(r.data || [])).catch(() => {})} />} />
          <Route path="/bots" element={<Bots activeAccount={activeAccount} setActiveAccount={setActiveAccount} accounts={accounts} />} />
          <Route path="/accounting" element={<Accounting />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/hummingbot" element={<Hummingbot />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
