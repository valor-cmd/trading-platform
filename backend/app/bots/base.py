import asyncio
import json
import logging
import re
import time
import traceback
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from app.core.store import store, trade_store
from app.exchange.simulator import PaperExchangeManager
from app.exchange.registry import exchange_registry
from app.indicators.technical import TechnicalAnalyzer, SignalResult, MarketRegime
from app.indicators.sentiment import SentimentAnalyzer
from app.indicators.confirmation import evaluate_confirmation, ConfirmationResult
from app.indicators.backtest import check_historical_win_rate
from app.risk.engine import RiskEngine, RiskAssessment
from app.models.trade import BotType

logger = logging.getLogger(__name__)

QUALITY_BASES = {
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "AVAX", "DOT", "MATIC", "LINK",
    "UNI", "ATOM", "LTC", "BCH", "NEAR", "FIL", "APT", "ARB", "OP", "INJ",
    "SUI", "SEI", "TIA", "DOGE", "SHIB", "PEPE", "WIF", "BONK", "FLOKI",
    "FET", "RNDR", "TAO", "AAVE", "MKR", "CRV", "LDO", "RUNE", "DYDX",
    "SNX", "COMP", "SUSHI", "IMX", "MANA", "SAND", "AXS", "GALA", "ENJ",
    "ALGO", "ICP", "HBAR", "VET", "EOS", "XLM", "TRX", "TON", "FTM",
    "THETA", "GRT", "STX", "ENS", "BLUR", "JUP", "W", "PYTH", "JTO",
    "PENDLE", "ENA", "ETHFI", "WLD", "STRK", "ZK", "EIGEN", "RENDER",
    "ORDI", "1000SATS", "PEOPLE", "NOT", "JASMY", "LUNC", "CHZ", "CKB",
    "FLOW", "MINA", "ZIL", "ONE", "CELO", "ROSE", "KAS", "XTZ",
    "EGLD", "QNT", "KDA", "CFX", "AGIX", "OCEAN", "RPL", "SSV",
    "GMX", "CAKE", "JOE", "RAY", "ORCA", "OSMO",
}

LEVERAGED_PATTERN = re.compile(
    r"(\d+[SL]|UP|DOWN|BULL|BEAR|HALF|HEDGE)",
    re.IGNORECASE,
)

MIN_PRICE_USD = 0.0001
CEX_ONLY_EXCHANGES = {"binance", "coinbase", "kraken", "kucoin", "okx", "bybit", "gateio", "bitget", "mexc"}

MAX_OPEN_TRADES = {
    "scalper": 8,
    "swing": 6,
    "long_term": 6,
    "grid": 6,
    "mean_reversion": 6,
    "momentum": 6,
    "dca": 8,
}
GLOBAL_MAX_OPEN = 60
SYMBOL_COOLDOWN_SECONDS = {
    "scalper": 600,
    "swing": 3600,
    "long_term": 7200,
    "grid": 600,
    "mean_reversion": 600,
    "momentum": 900,
    "dca": 900,
}
MIN_CONFIDENCE = {
    "scalper": 0.35,
    "swing": 0.35,
    "long_term": 0.30,
    "grid": 0.30,
    "mean_reversion": 0.30,
    "momentum": 0.35,
    "dca": 0.25,
}
MIN_POSITION_USD = 1.0

MIN_HOLD_SECONDS = {
    "scalper": 120,
    "swing": 3600,
    "long_term": 14400,
    "grid": 300,
    "mean_reversion": 600,
    "momentum": 300,
    "dca": 1800,
}

MIN_PROFIT_BEFORE_EXIT_PCT = {
    "scalper": 0.3,
    "swing": 0.5,
    "long_term": 1.0,
    "grid": 0.2,
    "mean_reversion": 0.5,
    "momentum": 0.4,
    "dca": 0.3,
}

TRAILING_STOP_ATR_MULT = {
    "scalper": 2.0,
    "swing": 2.5,
    "long_term": 3.0,
    "grid": 2.5,
    "mean_reversion": 2.0,
    "momentum": 2.5,
    "dca": 2.5,
}

MAX_HOLD_SECONDS = {
    "scalper": 3600,
    "swing": 604800,
    "long_term": 2592000,
    "grid": 86400,
    "mean_reversion": 86400,
    "momentum": 259200,
    "dca": 2592000,
}


class BaseBot(ABC):
    def __init__(
        self,
        bot_type: BotType,
        exchange: PaperExchangeManager,
        risk_engine: RiskEngine,
        sentiment_analyzer: SentimentAnalyzer,
    ):
        self.bot_type = bot_type
        self.exchange = exchange
        self.risk = risk_engine
        self.sentiment = sentiment_analyzer
        self.running = False
        self.active_trades: list[dict] = []
        self._cycle_count = 0
        self._last_scan_results: dict[str, str] = {}
        self._symbol_cooldowns: dict[str, float] = {}
        self._account = None
        self._trade_store = None
        self._kv_store = None
        self._trailing_stops: dict[str, float] = {}
        self._best_prices: dict[str, float] = {}
        self._consecutive_errors = 0

    async def _sync_active_trades(self):
        ts = self._get_trade_store()
        kv = self._get_kv_store()
        store_open = ts.get_open_trades()
        store_ids = {str(ot.get("id", "")) for ot in store_open if ot.get("bot_type") == self.bot_type.value}
        stale = [t for t in self.active_trades if t.get("order_id") not in store_ids]
        for t in stale:
            self.active_trades.remove(t)
            await kv.hdel(f"active_trades:{self.bot_type.value}", t["order_id"])
        if stale:
            logger.info(f"{self.bot_type.value} cleared {len(stale)} stale trades after account sync")

    async def resume_open_trades(self):
        ts = self._get_trade_store()
        kv = self._get_kv_store()
        open_trades = ts.get_open_trades()
        resumed = 0
        for ot in open_trades:
            if ot.get("bot_type") != self.bot_type.value:
                continue
            order_id = ot.get("id", f"resumed_{ot.get('symbol', 'UNK')}_{ot.get('entry_price', 0)}")
            trade = {
                "order_id": str(order_id),
                "symbol": ot.get("symbol", ""),
                "side": ot.get("side", "buy"),
                "entry_price": ot.get("entry_price", 0),
                "amount": ot.get("quantity", 0),
                "position_usd": ot.get("entry_price", 0) * ot.get("quantity", 0),
                "stop_loss": ot.get("stop_loss_price", 0),
                "take_profit": ot.get("take_profit_price", 0),
                "fee_rate": 0.001,
                "entry_fee_usd": ot.get("entry_fee_usd", 0),
                "slippage_usd": ot.get("slippage_usd", 0),
                "spread_pct": ot.get("spread_pct", 0),
                "opened_at": ot.get("opened_at", ""),
                "reasoning": ot.get("reasoning", "resumed after restart"),
                "signal_confidence": ot.get("signal_confidence", 0),
                "bot_type": self.bot_type.value,
                "regime": ot.get("regime", "unknown"),
                "strategy": ot.get("strategy", ""),
                "signal_score": ot.get("signal_score", 0),
                "confirmations": [],
            }
            already = any(t.get("symbol") == trade["symbol"] and t.get("side") == trade["side"] for t in self.active_trades)
            if not already:
                self.active_trades.append(trade)
                await kv.hset(
                    f"active_trades:{self.bot_type.value}",
                    str(order_id),
                    json.dumps(trade, default=str),
                )
                resumed += 1
        if resumed > 0:
            logger.info(f"{self.bot_type.value} resumed {resumed} open trades from trade store")
        return resumed

    @abstractmethod
    def get_timeframes(self) -> list[str]:
        pass

    @abstractmethod
    def get_symbols(self) -> list[str]:
        pass

    def _get_all_tradable_symbols(self) -> list[str]:
        symbols = set(self.exchange.get_all_symbols())
        return list(symbols)

    async def _get_filtered_symbols(self) -> list[str]:
        raw = self._get_all_tradable_symbols()
        filtered = []
        for sym in raw:
            if "/" not in sym:
                continue
            base, quote = sym.split("/", 1)
            if quote not in ("USDT", "USDC", "USD", "BUSD"):
                continue
            if LEVERAGED_PATTERN.search(base):
                continue
            if base not in QUALITY_BASES:
                continue
            filtered.append(sym)
        return filtered

    def _check_cooldown(self, symbol: str) -> bool:
        cooldown = SYMBOL_COOLDOWN_SECONDS.get(self.bot_type.value, 3600)
        last_trade = self._symbol_cooldowns.get(symbol, 0)
        return (time.time() - last_trade) >= cooldown

    def _record_cooldown(self, symbol: str):
        self._symbol_cooldowns[symbol] = time.time()

    def _get_trade_store(self):
        if self._trade_store:
            return self._trade_store
        if self._account:
            return self._account.trade_store
        return trade_store

    def _get_kv_store(self):
        if self._kv_store:
            return self._kv_store
        return store

    def _get_global_open_count(self) -> int:
        return len(self._get_trade_store().get_open_trades())

    @abstractmethod
    async def evaluate_entry(self, symbol: str, signal: SignalResult, sentiment: dict) -> bool:
        pass

    @abstractmethod
    async def evaluate_exit(self, trade: dict, signal: SignalResult) -> bool:
        pass

    def _determine_side(self, signal: SignalResult) -> str:
        if signal.overall_signal in ("sell", "strong_sell"):
            return "sell"
        elif signal.overall_signal in ("buy", "strong_buy"):
            return "buy"

        regime = signal.regime
        if regime and regime.regime in (MarketRegime.STRONG_TREND_UP, MarketRegime.TREND_UP):
            return "buy"
        if regime and regime.regime in (MarketRegime.STRONG_TREND_DOWN, MarketRegime.TREND_DOWN):
            return "sell"

        if signal.adx >= 25:
            if signal.adx_plus_di > signal.adx_minus_di:
                return "buy"
            else:
                return "sell"

        if signal.rsi is not None and signal.rsi < 35:
            return "buy"
        elif signal.rsi is not None and signal.rsi > 65:
            return "sell"
        elif signal.ema_trend in ("bullish", "strong_bullish"):
            return "buy"
        elif signal.ema_trend in ("bearish", "strong_bearish"):
            return "sell"
        elif signal.macd_signal in ("bullish", "bullish_crossover"):
            return "buy"
        elif signal.macd_signal in ("bearish", "bearish_crossover"):
            return "sell"
        if signal.cmf > 0.05:
            return "buy"
        elif signal.cmf < -0.05:
            return "sell"
        return "buy" if signal.zscore < 0 else "sell"

    async def run_cycle(self, exchange_id: str):
        self._cycle_count += 1

        if self._cycle_count % 5 == 1:
            try:
                await self._sync_active_trades()
            except Exception:
                pass

        if self._account and self._account.check_daily_target():
            if self._cycle_count % 60 == 1:
                logger.info(f"{self.bot_type.value} daily target hit for account '{self._account.config.name}' -- skipping new trades")
            for trade in list(self.active_trades):
                try:
                    await self.close_trade(exchange_id, trade, "closed")
                except Exception:
                    pass
            return

        if self._cycle_count % 10 == 1:
            try:
                ts = self._get_trade_store()
                pe = self.exchange
                usdt = pe.balances.get("USDT", 0)
                open_trades = ts.get_open_trades()
                open_by_bot: dict[str, float] = {}
                for ot in open_trades:
                    bt = ot.get("bot_type", "")
                    open_by_bot[bt] = open_by_bot.get(bt, 0) + (ot.get("entry_price", 0) * ot.get("quantity", 0))
                from app.exchange.live_prices import live_prices as _lp
                for ot in open_trades:
                    sym = ot.get("symbol", "")
                    qty = ot.get("quantity", 0)
                    bt = ot.get("bot_type", "")
                    for ck, cv in _lp._ticker_cache.items():
                        if cv and sym in ck and cv.get("last", 0) > 0:
                            open_by_bot[bt] = open_by_bot.get(bt, 0) - (ot.get("entry_price", 0) * qty) + (cv["last"] * qty)
                            break
                total_cap = usdt + sum(open_by_bot.values())
                if total_cap > 1:
                    await self.risk.rebalance_buckets(total_cap, open_by_bot)
            except Exception as e:
                logger.debug(f"{self.bot_type.value} periodic rebalance failed: {e}")

        symbols = await self._get_filtered_symbols()
        if not symbols:
            logger.warning(f"{self.bot_type.value} has no available symbols to scan")
            return

        bot_max = MAX_OPEN_TRADES.get(self.bot_type.value, 3)
        global_open = self._get_global_open_count()
        bot_open = len(self.active_trades)
        can_open = bot_open < bot_max and global_open < GLOBAL_MAX_OPEN

        sentiment_data = None
        sentiment_interp = {"bias": "neutral", "weight": 0}
        try:
            sentiment_data = await self.sentiment.get_fear_greed_index()
            sentiment_interp = self.sentiment.interpret_sentiment(sentiment_data.fear_greed_value)
        except Exception as e:
            logger.debug(f"{self.bot_type.value} sentiment fetch failed: {e}")

        trades_opened = 0
        trades_closed = 0
        regime_rejections = 0
        confirmation_rejections = 0
        min_conf = MIN_CONFIDENCE.get(self.bot_type.value, 0.25)

        for symbol in symbols:
            try:
                all_tfs = self.get_timeframes()
                tf = all_tfs[0]
                df = await self.exchange.fetch_ohlcv(exchange_id, symbol, tf)
                if len(df) < 50:
                    continue

                analyzer = TechnicalAnalyzer(df)
                signal = analyzer.analyze()

                try:
                    from app.services.apify_intel import apify_intel
                    intel_boost = apify_intel.get_bot_signal_boost(symbol, self.bot_type.value)
                    signal.confidence = min(1.0, max(0.0, signal.confidence + intel_boost["boost"]))
                except Exception:
                    pass

                strategy_advice = None
                try:
                    from app.services.strategy_intel import strategy_intel
                    signal_data = {
                        "side": self._determine_side(signal),
                        "bb_upper": getattr(signal, "bb_upper", 0) or 0,
                        "bb_lower": getattr(signal, "bb_lower", 0) or 0,
                        "price": df.iloc[-1]["close"] if len(df) > 0 else 0,
                        "atr": signal.atr or 0,
                        "adx": signal.adx or 0,
                    }
                    strategy_advice = strategy_intel.get_advice(self.bot_type.value, symbol, signal_data)
                    signal.confidence = min(1.0, max(0.0, signal.confidence + strategy_advice.confidence_boost))
                except Exception:
                    pass

                has_open = any(t["symbol"] == symbol for t in self.active_trades)
                if not has_open and can_open:
                    if signal.confidence < min_conf:
                        continue

                    if not self._check_cooldown(symbol):
                        continue

                    if await self.evaluate_entry(symbol, signal, sentiment_interp):
                        side = self._determine_side(signal)

                        confirmation = evaluate_confirmation(
                            self.bot_type.value, signal, sentiment_interp, side,
                        )

                        if not confirmation.approved:
                            self._last_scan_results[symbol] = (
                                f"confirmation rejected: {confirmation.rejection_reason} "
                                f"(score={confirmation.score:.1f}/{confirmation.required_score:.1f}, "
                                f"regime={confirmation.regime})"
                            )
                            if "chaotic" in (confirmation.regime or ""):
                                regime_rejections += 1
                            else:
                                confirmation_rejections += 1
                            continue

                        best_bt = None
                        best_tf = tf
                        for try_tf in all_tfs:
                            try:
                                bt_result = await check_historical_win_rate(
                                    self.exchange, exchange_id, symbol,
                                    self.bot_type.value, side, try_tf,
                                )
                                if bt_result.approved:
                                    if best_bt is None or bt_result.win_rate > best_bt.win_rate:
                                        best_bt = bt_result
                                        best_tf = try_tf
                            except Exception:
                                pass

                        if best_bt is None:
                            self._last_scan_results[symbol] = f"backtest rejected on all timeframes {all_tfs}"
                            continue

                        tf = best_tf

                        ticker = await self.exchange.fetch_ticker(exchange_id, symbol)
                        entry_price = ticker["last"]
                        if entry_price < MIN_PRICE_USD:
                            self._last_scan_results[symbol] = f"price too low: ${entry_price}"
                            continue

                        bid = ticker.get("bid") or entry_price
                        ask = ticker.get("ask") or entry_price
                        spread_pct = (ask - bid) / entry_price * 100 if entry_price > 0 else 0
                        if spread_pct > 1.0:
                            self._last_scan_results[symbol] = f"spread too wide: {spread_pct:.2f}%"
                            continue

                        fee_rate = await self.exchange.get_trading_fee(exchange_id, symbol)

                        assessment = await self.risk.assess_trade(
                            self.bot_type.value, entry_price, side,
                            signal.atr, signal.confidence, fee_rate,
                        )

                        if assessment.approved and assessment.position_size_usd < MIN_POSITION_USD:
                            self._last_scan_results[symbol] = f"position too small: ${assessment.position_size_usd:.2f} < ${MIN_POSITION_USD}"
                            continue

                        if assessment.approved:
                            usdt_balance = self.exchange.balances.get("USDT", 0)
                            needed = assessment.position_size_usd * 1.002
                            if usdt_balance < needed:
                                self._last_scan_results[symbol] = f"insufficient USDT: ${usdt_balance:.2f} < ${needed:.2f}"
                                await self.risk.release_bucket(self.bot_type.value, assessment.position_size_usd)
                                continue

                            sl_pct = abs(entry_price - assessment.stop_loss_price) / entry_price * 100 if entry_price > 0 else 0
                            if sl_pct < spread_pct * 2:
                                self._last_scan_results[symbol] = f"SL too tight vs spread: SL={sl_pct:.3f}% < 2*spread={spread_pct*2:.3f}%"
                                await self.risk.release_bucket(self.bot_type.value, assessment.position_size_usd)
                                continue
                            await self.execute_trade(
                                exchange_id, symbol, signal, assessment,
                                fee_rate, side, confirmation,
                                backtest_win_rate=best_bt.win_rate if best_bt else 0.0,
                                backtest_timeframe=best_tf,
                            )
                            trades_opened += 1
                            self._record_cooldown(symbol)
                            bot_open += 1
                            global_open += 1
                            can_open = bot_open < bot_max and global_open < GLOBAL_MAX_OPEN
                            logger.info(
                                f"{self.bot_type.value} TRADE OPENED: {side.upper()} {symbol} "
                                f"@ ${entry_price:.4f} pos=${assessment.position_size_usd:.2f} "
                                f"| regime={confirmation.regime} "
                                f"score={confirmation.score:.1f}/{confirmation.required_score:.1f} "
                                f"confs={len(confirmation.confirmations)} "
                                f"[{bot_open}/{bot_max} bot, {global_open}/{GLOBAL_MAX_OPEN} global]"
                            )
                        else:
                            self._last_scan_results[symbol] = f"risk rejected: {assessment.reasoning}"

                for trade in list(self.active_trades):
                    if trade["symbol"] != symbol:
                        continue
                    ticker = await self.exchange.fetch_ticker(exchange_id, symbol)
                    current_price = ticker["last"]

                    opened_at = trade.get("opened_at", "")
                    hold_seconds = 0
                    if opened_at:
                        try:
                            from datetime import datetime as _dt
                            ot = _dt.fromisoformat(opened_at.replace("Z", "+00:00"))
                            hold_seconds = (datetime.now(timezone.utc) - ot).total_seconds()
                        except Exception:
                            hold_seconds = 9999

                    min_hold = MIN_HOLD_SECONDS.get(self.bot_type.value, 300)

                    order_id = trade["order_id"]
                    trail_mult = TRAILING_STOP_ATR_MULT.get(self.bot_type.value, 2.0)

                    if order_id not in self._best_prices:
                        self._best_prices[order_id] = trade["entry_price"]
                    if trade["side"] == "buy":
                        if current_price > self._best_prices[order_id]:
                            self._best_prices[order_id] = current_price
                    else:
                        if current_price < self._best_prices[order_id]:
                            self._best_prices[order_id] = current_price

                    atr_val = 0
                    try:
                        atr_val = df.iloc[-1].get("atr", 0) if len(df) > 0 else 0
                        if pd.isna(atr_val):
                            atr_val = 0
                    except Exception:
                        pass

                    if atr_val > 0:
                        best = self._best_prices[order_id]
                        entry_p = trade["entry_price"]
                        if entry_p > 0:
                            if trade["side"] == "buy":
                                profit_pct = (best - entry_p) / entry_p
                            else:
                                profit_pct = (entry_p - best) / entry_p
                        else:
                            profit_pct = 0
                        if profit_pct > 0.02:
                            trail_mult *= 0.5
                        elif profit_pct > 0.01:
                            trail_mult *= 0.7
                        elif profit_pct > 0.005:
                            trail_mult *= 0.85
                        if trade["side"] == "buy":
                            new_trail = best - (atr_val * trail_mult)
                            old_trail = self._trailing_stops.get(order_id, trade["stop_loss"])
                            self._trailing_stops[order_id] = max(new_trail, old_trail)
                        else:
                            new_trail = best + (atr_val * trail_mult)
                            old_trail = self._trailing_stops.get(order_id, trade["stop_loss"])
                            self._trailing_stops[order_id] = min(new_trail, old_trail)

                    effective_sl = self._trailing_stops.get(order_id, trade["stop_loss"])

                    hit_sl = False
                    hit_tp = False
                    if trade["side"] == "buy":
                        hit_sl = current_price <= effective_sl
                        hit_tp = trade.get("take_profit") and current_price >= trade["take_profit"]
                    else:
                        hit_sl = current_price >= effective_sl
                        hit_tp = trade.get("take_profit") and current_price <= trade["take_profit"]

                    max_hold = MAX_HOLD_SECONDS.get(self.bot_type.value, 604800)

                    if hit_sl:
                        trail_info = f" (trailing={effective_sl:.6f})" if order_id in self._trailing_stops else ""
                        logger.info(f"{self.bot_type.value} STOP LOSS hit on {symbol}{trail_info}")
                        self._trailing_stops.pop(order_id, None)
                        self._best_prices.pop(order_id, None)
                        await self.close_trade(exchange_id, trade, "stopped_out")
                        trades_closed += 1
                    elif hit_tp:
                        logger.info(f"{self.bot_type.value} TAKE PROFIT hit on {symbol}")
                        self._trailing_stops.pop(order_id, None)
                        self._best_prices.pop(order_id, None)
                        await self.close_trade(exchange_id, trade, "closed")
                        trades_closed += 1
                    elif hold_seconds >= max_hold:
                        logger.info(f"{self.bot_type.value} MAX HOLD TIME reached on {symbol} ({hold_seconds:.0f}s)")
                        self._trailing_stops.pop(order_id, None)
                        self._best_prices.pop(order_id, None)
                        await self.close_trade(exchange_id, trade, "closed")
                        trades_closed += 1
                    elif hold_seconds >= min_hold:
                        entry_p = trade["entry_price"]
                        if entry_p > 0:
                            if trade["side"] == "buy":
                                move_pct = (current_price - entry_p) / entry_p * 100
                            else:
                                move_pct = (entry_p - current_price) / entry_p * 100
                            fee_cost_pct = trade.get("fee_rate", 0.001) * 2 * 100
                            min_profit_pct = max(fee_cost_pct + MIN_PROFIT_BEFORE_EXIT_PCT.get(self.bot_type.value, 0.3), 0.3)
                        else:
                            move_pct = 0
                            min_profit_pct = 0.3

                        df2 = await self.exchange.fetch_ohlcv(exchange_id, symbol, tf)
                        analyzer2 = TechnicalAnalyzer(df2)
                        signal2 = analyzer2.analyze()
                        if await self.evaluate_exit(trade, signal2):
                            if move_pct >= min_profit_pct or move_pct < -min_profit_pct:
                                self._trailing_stops.pop(order_id, None)
                                self._best_prices.pop(order_id, None)
                                await self.close_trade(exchange_id, trade, "closed")
                                trades_closed += 1
                            else:
                                self._last_scan_results[symbol] = (
                                    f"exit signal but move {move_pct:+.2f}% in dead zone (hold {hold_seconds:.0f}s)"
                                )

            except Exception as e:
                logger.debug(f"{self.bot_type.value} error on {symbol}: {e}")

        if self._cycle_count % 10 == 0 or trades_opened > 0 or trades_closed > 0:
            logger.info(
                f"{self.bot_type.value} cycle #{self._cycle_count}: "
                f"scanned {len(symbols)} symbols, opened {trades_opened}, "
                f"closed {trades_closed}, active {len(self.active_trades)}, "
                f"regime_blocked={regime_rejections}, conf_blocked={confirmation_rejections}"
            )

    async def execute_trade(
        self, exchange_id: str, symbol: str, signal: SignalResult,
        assessment: RiskAssessment, fee_rate: float, side: str,
        confirmation: Optional[ConfirmationResult] = None,
        backtest_win_rate: float = 0.0,
        backtest_timeframe: str = "",
    ):
        ticker = await self.exchange.fetch_ticker(exchange_id, symbol)
        amount = assessment.position_size_usd / ticker["last"]

        order = await self.exchange.create_order(exchange_id, symbol, side, amount)

        fill_price = order["price"]
        actual_fee = order["fee"]
        actual_fee_rate = order.get("fee_rate", fee_rate)

        strategy_desc = ""
        signal_score = signal.confirmation_score
        if confirmation:
            strategy_desc = confirmation.strategy_notes
            signal_score = confirmation.score

        trade = {
            "order_id": order["id"],
            "symbol": symbol,
            "side": side,
            "entry_price": fill_price,
            "amount": amount,
            "position_usd": fill_price * amount,
            "stop_loss": assessment.stop_loss_price,
            "take_profit": assessment.take_profit_price,
            "fee_rate": actual_fee_rate,
            "entry_fee_usd": actual_fee,
            "slippage_usd": order.get("slippage_usd", 0),
            "spread_pct": order.get("spread_pct", 0),
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "reasoning": assessment.reasoning,
            "signal_confidence": signal.confidence,
            "bot_type": self.bot_type.value,
            "regime": signal.regime.regime.value if signal.regime else "unknown",
            "strategy": strategy_desc,
            "signal_score": signal_score,
            "confirmations": confirmation.confirmations if confirmation else [],
            "backtest_win_rate": backtest_win_rate,
            "backtest_timeframe": backtest_timeframe,
        }
        self.active_trades.append(trade)

        ts = self._get_trade_store()
        kv = self._get_kv_store()

        ts.add_trade({
            "bot_type": self.bot_type.value,
            "exchange": exchange_id,
            "symbol": symbol,
            "side": side,
            "entry_price": fill_price,
            "quantity": amount,
            "leverage": 1.0,
            "stop_loss_price": assessment.stop_loss_price,
            "take_profit_price": assessment.take_profit_price,
            "entry_fee_usd": actual_fee,
            "exit_fee_usd": 0,
            "slippage_usd": order.get("slippage_usd", 0),
            "spread_pct": order.get("spread_pct", 0),
            "bucket": self.bot_type.value,
            "reasoning": assessment.reasoning,
            "is_paper": True,
            "regime": signal.regime.regime.value if signal.regime else "unknown",
            "strategy": strategy_desc,
            "signal_score": signal_score,
            "signal_confidence": signal.confidence,
            "backtest_win_rate": backtest_win_rate,
            "backtest_timeframe": backtest_timeframe,
        })

        await kv.hset(
            f"active_trades:{self.bot_type.value}",
            order["id"],
            json.dumps(trade, default=str),
        )

        ts.record_snapshot()

    async def close_trade(self, exchange_id: str, trade: dict, status: str = "closed"):
        close_side = "sell" if trade["side"] == "buy" else "buy"

        exit_order = await self.exchange.create_order(
            exchange_id, trade["symbol"], close_side, trade["amount"]
        )

        exit_price = exit_order["price"]
        exit_fee = exit_order["fee"]
        exit_slippage = exit_order.get("slippage_usd", 0)
        entry_fee = trade.get("entry_fee_usd", 0)

        if trade["side"] == "buy":
            gross_pnl = (exit_price - trade["entry_price"]) * trade["amount"]
        else:
            gross_pnl = (trade["entry_price"] - exit_price) * trade["amount"]

        total_fees = entry_fee + exit_fee
        net_pnl = gross_pnl - total_fees

        await self.risk.update_daily_pnl(net_pnl)
        await self.risk.release_bucket(self.bot_type.value, trade["position_usd"])

        ts = self._get_trade_store()
        kv = self._get_kv_store()

        open_trades = ts.get_open_trades()
        for ot in open_trades:
            if ot.get("symbol") == trade["symbol"] and ot.get("bot_type") == self.bot_type.value:
                ts.close_trade(
                    ot["id"], exit_price, round(net_pnl, 5),
                    round(exit_fee, 5), status,
                    exit_slippage_usd=round(exit_slippage, 8),
                )
                break

        if trade in self.active_trades:
            self.active_trades.remove(trade)
        await kv.hdel(f"active_trades:{self.bot_type.value}", trade["order_id"])

        ts.record_snapshot()

        logger.info(
            f"{self.bot_type.value} CLOSED {trade['symbol']} @ ${exit_price:.8g} "
            f"gross=${gross_pnl:.5f} fees=${total_fees:.5f} net=${net_pnl:.5f} ({status})"
        )

    async def start(self, exchange_id: str, interval_seconds: int):
        self.running = True
        self._consecutive_errors = 0
        self._cycle_count = 0
        try:
            await self.resume_open_trades()
        except Exception as e:
            logger.warning(f"{self.bot_type.value} failed to resume trades: {e}")
        logger.info(f"{self.bot_type.value} bot STARTED (interval={interval_seconds}s, symbols={len(self.get_symbols())})")
        while self.running:
            try:
                await self.run_cycle(exchange_id)
                self._consecutive_errors = 0
            except asyncio.CancelledError:
                logger.info(f"{self.bot_type.value} bot task cancelled")
                break
            except Exception as e:
                self._consecutive_errors += 1
                logger.error(f"{self.bot_type.value} cycle error #{self._consecutive_errors}: {e}")
                logger.debug(traceback.format_exc())
                if self._consecutive_errors >= 10:
                    backoff = min(interval_seconds * 2, 300)
                    logger.warning(f"{self.bot_type.value} backing off {backoff}s after {self._consecutive_errors} errors")
                    await asyncio.sleep(backoff)
                    self._consecutive_errors = 0
            await asyncio.sleep(interval_seconds)
        logger.info(f"{self.bot_type.value} bot STOPPED")

    def stop(self):
        self.running = False
