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

export const getOHLCV = (exchangeId: string, symbol: string, timeframe = "1h", limit = 100) =>
  api.get(`/market/${exchangeId}/${symbol}/ohlcv`, { params: { timeframe, limit } });

export const getAccountingSummary = (account = "default") => api.get("/accounting/summary", { params: { account } });

export const getPnl = (days = 30, account = "default") => api.get("/accounting/pnl", { params: { days, account } });

export const getWinRate = (account = "default") => api.get("/accounting/win-rate", { params: { account } });

export const getPnlByBot = (account = "default") => api.get("/accounting/by-bot", { params: { account } });

export const getTrades = (status = "all", account = "default") => api.get("/accounting/trades", { params: { status, account } });

export const getTradesWithBalance = (account = "default") => api.get("/accounting/trades/with-balance", { params: { account } });

export const getActiveTradesLive = (account = "default") => api.get("/accounting/active-trades-live", { params: { account } });

export const getFees = (account = "default") => api.get("/accounting/fees", { params: { account } });

export const getLiveBalance = (account = "default") => api.get("/accounting/live-balance", { params: { account } });

export const recordDeposit = (data: {
  exchange: string;
  amount_usd: number;
  asset: string;
  asset_amount: number;
}, account = "default") => api.post("/accounting/deposit", data, { params: { account } });

export const recordWithdrawal = (data: {
  exchange: string;
  amount_usd: number;
  asset: string;
  asset_amount: number;
}, account = "default") => api.post("/accounting/withdrawal", data, { params: { account } });

export const resetAccount = (account = "default") => api.post("/accounting/reset", null, { params: { account } });

export const rebalanceBuckets = (totalCapital?: number) =>
  api.post("/risk/rebalance", { total_capital: totalCapital ?? null });

export const runBacktest = (data: {
  exchange_id: string;
  symbol: string;
  timeframe: string;
  initial_capital: number;
  risk_per_trade_pct: number;
  limit: number;
  sl_atr_multiplier?: number;
  tp_rr_ratio?: number;
  min_confidence?: number;
  min_confirmations?: number;
}) => api.post("/backtest", data);

export const getRiskStatus = () => api.get("/risk/status");

export const getBotStatus = (account = "default") => api.get("/bots/status", { params: { account } });

export const getBotsRunning = (account = "default") => api.get("/bots/running", { params: { account } });

export const startBots = (exchangeId: string) => api.post(`/bots/start/${exchangeId}`);

export const stopBots = () => api.post("/bots/stop");

export const getConfig = () => api.get("/config");

export const updateConfig = (data: {
  max_daily_loss_usd?: number;
  max_position_size_usd?: number;
  default_stop_loss_pct?: number;
  max_leverage?: number;
}) => api.post("/config", data);

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

export const getPortfolioChart = (limit = 200, account = "default") => api.get("/portfolio/chart", { params: { limit, account } });

export const getLedger = (account = "default") => api.get("/accounting/ledger", { params: { account } });

export const closeTrade = (tradeRef: string | number, account = "default") =>
  api.post(`/accounting/trades/${tradeRef}/close`, null, { params: { account } });

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

export const getAccounts = () => api.get("/accounts");

export const createAccount = (data: {
  name: string;
  label?: string;
  daily_target_pct?: number;
  max_daily_loss_usd?: number;
  auto_stop_on_target?: boolean;
  initial_deposit_usd?: number;
}) => api.post("/accounts", data);

export const updateAccountConfig = (name: string, data: {
  label?: string;
  daily_target_pct?: number;
  max_daily_loss_usd?: number;
  auto_stop_on_target?: boolean;
}) => api.put(`/accounts/${name}`, data);

export const deleteAccount = (name: string) => api.delete(`/accounts/${name}`);

export const startAccountBots = (name: string) => api.post(`/accounts/${name}/start-bots`);

export const stopAccountBots = (name: string) => api.post(`/accounts/${name}/stop-bots`);

export const getIntelSignals = (maxAge = 600) => api.get("/intel/signals", { params: { max_age: maxAge } });

export const getIntelSummary = () => api.get("/intel/summary");

export const getIntelBotBoost = (symbol: string, botType = "momentum") =>
  api.get("/intel/bot-boost", { params: { symbol, bot_type: botType } });

export const refreshIntel = () => api.post("/intel/refresh");

export const getIntelCryptopanic = (force = false) => api.get("/intel/news/cryptopanic", { params: { force } });

export const getIntelNewsPro = (force = false) => api.get("/intel/news/pro", { params: { force } });

export const getIntelPumpDetector = (symbol?: string, force = false) =>
  api.get("/intel/pump-detector", { params: { symbol, force } });

export const getIntelWhaleTracker = (force = false) => api.get("/intel/whale-tracker", { params: { force } });

export const getIntelCoinmarketcap = (force = false) => api.get("/intel/coinmarketcap", { params: { force } });

export const getIntelYahoo = (symbols = "BTC-USD,ETH-USD,SOL-USD", days = "7", interval = "1d", force = false) =>
  api.get("/intel/yahoo-finance", { params: { symbols, days, interval, force } });

export const getIntelTwitterSentiment = (query = "$BTC", force = false) =>
  api.get("/intel/twitter/sentiment", { params: { query, force } });

export const getIntelTwitterStream = (users = "", force = false) =>
  api.get("/intel/twitter/stream", { params: { users, force } });

export const getIntelFinanceAgent = (ticker = "BTC-USD", force = false) =>
  api.get("/intel/finance-agent", { params: { ticker, force } });

export const getIntelKepler = (force = false) => api.get("/intel/kepler", { params: { force } });

export const getIntelTokenScanner = (symbol = "BTC", force = false) =>
  api.get("/intel/token-scanner", { params: { symbol, force } });

export const getIntelCoinskid = (page = "ckr_index", force = false) =>
  api.get(`/intel/coinskid/${page}`, { params: { force } });

export default api;
