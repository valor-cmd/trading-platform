import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "/api",
});

export const connectExchange = (exchangeId: string, apiKey: string, apiSecret: string) =>
  api.post("/exchange/connect", { exchange_id: exchangeId, api_key: apiKey, api_secret: apiSecret });

export const getBalance = (exchangeId: string) =>
  api.get(`/exchange/${exchangeId}/balance`);

export const getTicker = (exchangeId: string, symbol: string) =>
  api.get(`/market/${exchangeId}/${symbol}/ticker`);

export const getAnalysis = (exchangeId: string, symbol: string, timeframe = "1h") =>
  api.get(`/market/${exchangeId}/${symbol}/analysis`, { params: { timeframe } });

export const getAccountingSummary = () => api.get("/accounting/summary");

export const getPnl = (days = 30) => api.get("/accounting/pnl", { params: { days } });

export const getWinRate = () => api.get("/accounting/win-rate");

export const getPnlByBot = () => api.get("/accounting/by-bot");

export const getTrades = (status = "all") => api.get("/accounting/trades", { params: { status } });

export const getTradesWithBalance = () => api.get("/accounting/trades/with-balance");

export const getActiveTradesLive = () => api.get("/accounting/active-trades-live");

export const getFees = () => api.get("/accounting/fees");

export const getLiveBalance = () => api.get("/accounting/live-balance");

export const recordDeposit = (data: {
  exchange: string;
  amount_usd: number;
  asset: string;
  asset_amount: number;
}) => api.post("/accounting/deposit", data);

export const recordWithdrawal = (data: {
  exchange: string;
  amount_usd: number;
  asset: string;
  asset_amount: number;
}) => api.post("/accounting/withdrawal", data);

export const rebalanceBuckets = (totalCapital?: number) =>
  api.post("/risk/rebalance", { total_capital: totalCapital ?? null });

export const runBacktest = (data: {
  exchange_id: string;
  symbol: string;
  timeframe: string;
  initial_capital: number;
  risk_per_trade_pct: number;
  limit: number;
}) => api.post("/backtest", data);

export const getRiskStatus = () => api.get("/risk/status");

export const getBotStatus = () => api.get("/bots/status");

export const getBotsRunning = () => api.get("/bots/running");

export const startBots = (exchangeId: string) => api.post(`/bots/start/${exchangeId}`);

export const stopBots = () => api.post("/bots/stop");

export const getConfig = () => api.get("/config");

export const getHealth = () => api.get("/health");

export const getExchangesStatus = () => api.get("/exchanges/status");

export const getExchangesPairs = () => api.get("/exchanges/pairs");

export const getExchangePairs = (exchangeId: string, q = "", limit = 200, offset = 0) =>
  api.get(`/exchanges/${exchangeId}/pairs`, { params: { q, limit, offset } });

export const getArbOpportunities = (minProfit = 0, limit = 50) =>
  api.get("/arbitrage/opportunities", { params: { min_profit: minProfit, limit } });

export const getArbHistory = (limit = 100) =>
  api.get("/arbitrage/history", { params: { limit } });

export const getArbStatus = () => api.get("/arbitrage/status");

export const searchTokens = (q = "") => api.get("/tokens/search", { params: { q } });

export const getTokensByChain = (chain: string) => api.get(`/tokens/by-chain/${chain}`);

export const getPortfolioChart = (limit = 200) => api.get("/portfolio/chart", { params: { limit } });

export default api;
