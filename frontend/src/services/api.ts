import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "/api",
});

const API_TOKEN = import.meta.env.VITE_API_TOKEN || "";

api.interceptors.request.use((config) => {
  if (API_TOKEN) {
    config.headers.Authorization = `Bearer ${API_TOKEN}`;
  }
  return config;
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

export const resetAccount = () => api.post("/accounting/reset");

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

export const getLedger = () => api.get("/accounting/ledger");

export const hbotConnect = (data?: { hbot_url?: string; username?: string; password?: string }) =>
  api.post("/hummingbot/connect", data || {});

export const hbotDisconnect = () => api.post("/hummingbot/disconnect");

export const hbotStatus = () => api.get("/hummingbot/status");

export const hbotSetMode = (paper: boolean) => api.post("/hummingbot/mode", { paper });

export const hbotAddExchange = (data: {
  exchange: string;
  api_key: string;
  api_secret: string;
  account_name?: string;
  passphrase?: string;
}) => api.post("/hummingbot/exchange/add", data);

export const hbotListExchanges = () => api.get("/hummingbot/exchanges");

export const hbotGetPortfolio = (account?: string) =>
  api.get("/hummingbot/portfolio", { params: account ? { account } : {} });

export const hbotStartStrategy = (data: {
  strategy_type: string;
  bot_name?: string;
  params: Record<string, unknown>;
}) => api.post("/hummingbot/strategy/start", data);

export const hbotStopStrategy = (botName: string) =>
  api.post("/hummingbot/strategy/stop", null, { params: { bot_name: botName } });

export const hbotListBots = () => api.get("/hummingbot/bots");

export const hbotBotStatus = (botName: string) => api.get(`/hummingbot/bots/${botName}/status`);

export const hbotPlaceOrder = (data: {
  connector: string;
  trading_pair: string;
  order_type: string;
  side: string;
  amount: number;
  price?: number;
}) => api.post("/hummingbot/order", data);

export const hbotGetOrders = (connector?: string) =>
  api.get("/hummingbot/orders", { params: connector ? { connector } : {} });

export const hbotGetTrades = (connector?: string, limit = 100) =>
  api.get("/hummingbot/trades", { params: { connector, limit } });

export const hbotGetFees = () => api.get("/hummingbot/fees");

export const hbotGetRecentFees = (limit = 50) =>
  api.get("/hummingbot/fees/recent", { params: { limit } });

export const hbotEstimateFees = (exchange: string, amount: number, price: number, isMaker = false) =>
  api.get("/hummingbot/fees/estimate", { params: { exchange, amount, price, is_maker: isMaker } });

export const hbotConfigureRpc = (data: {
  chain: string;
  network?: string;
  provider: string;
  api_key?: string;
}) => api.post("/hummingbot/rpc/configure", data);

export const hbotGetRpcConfigs = () => api.get("/hummingbot/rpc/configs");

export const hbotGatewayStatus = () => api.get("/hummingbot/gateway/status");

export const hbotGatewayChains = () => api.get("/hummingbot/gateway/chains");

export const hbotGatewayConnectors = () => api.get("/hummingbot/gateway/connectors");

export const hbotSwapQuote = (data: {
  chain: string;
  network?: string;
  connector: string;
  base_token: string;
  quote_token: string;
  amount: string;
  side?: string;
  slippage?: number;
}) => api.post("/hummingbot/gateway/swap/quote", data);

export const hbotSwapExecute = (data: {
  chain: string;
  network?: string;
  connector: string;
  base_token: string;
  quote_token: string;
  amount: string;
  side?: string;
  slippage?: number;
  address?: string;
}) => api.post("/hummingbot/gateway/swap/execute", data);

export const hbotGetStrategyTypes = () => api.get("/hummingbot/strategy/types");

export default api;
