import asyncio
import json
import logging
import traceback
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

from app.core.store import store, trade_store
from app.exchange.simulator import PaperExchangeManager
from app.exchange.registry import exchange_registry
from app.indicators.technical import TechnicalAnalyzer, SignalResult, MarketRegime
from app.indicators.sentiment import SentimentAnalyzer
from app.indicators.confirmation import evaluate_confirmation, ConfirmationResult
from app.risk.engine import RiskEngine, RiskAssessment
from app.models.trade import BotType

logger = logging.getLogger(__name__)


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

    @abstractmethod
    def get_timeframes(self) -> list[str]:
        pass

    @abstractmethod
    def get_symbols(self) -> list[str]:
        pass

    def _get_all_tradable_symbols(self) -> list[str]:
        symbols = set()
        for eid, adapter in exchange_registry.get_all().items():
            if adapter.is_connected():
                for sym in adapter.get_all_symbols():
                    symbols.add(sym)
        cex_symbols = set(self.exchange.get_all_symbols())
        symbols.update(cex_symbols)
        return list(symbols)

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

        if signal.rsi is not None and signal.rsi < 45:
            return "buy"
        elif signal.rsi is not None and signal.rsi > 55:
            return "sell"
        elif signal.ema_trend in ("bullish", "strong_bullish"):
            return "buy"
        elif signal.ema_trend in ("bearish", "strong_bearish"):
            return "sell"
        elif signal.macd_signal in ("bullish", "bullish_crossover"):
            return "buy"
        return "buy"

    async def run_cycle(self, exchange_id: str):
        self._cycle_count += 1
        symbols = self.get_symbols()
        if not symbols:
            logger.warning(f"{self.bot_type.value} has no available symbols to scan")
            return

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

        for symbol in symbols:
            try:
                tf = self.get_timeframes()[0]
                df = await self.exchange.fetch_ohlcv(exchange_id, symbol, tf)
                if len(df) < 50:
                    continue

                analyzer = TechnicalAnalyzer(df)
                signal = analyzer.analyze()

                has_open = any(t["symbol"] == symbol for t in self.active_trades)
                if not has_open:
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

                        ticker = await self.exchange.fetch_ticker(exchange_id, symbol)
                        entry_price = ticker["last"]
                        fee_rate = await self.exchange.get_trading_fee(exchange_id, symbol)

                        assessment = await self.risk.assess_trade(
                            self.bot_type.value, entry_price, side,
                            signal.atr, signal.confidence, fee_rate,
                        )

                        if assessment.approved:
                            await self.execute_trade(
                                exchange_id, symbol, signal, assessment,
                                fee_rate, side, confirmation,
                            )
                            trades_opened += 1
                            logger.info(
                                f"{self.bot_type.value} TRADE OPENED: {side.upper()} {symbol} "
                                f"@ ${entry_price:.4f} | regime={confirmation.regime} "
                                f"score={confirmation.score:.1f}/{confirmation.required_score:.1f} "
                                f"confs={len(confirmation.confirmations)}"
                            )
                        else:
                            self._last_scan_results[symbol] = f"risk rejected: {assessment.reasoning}"

                for trade in list(self.active_trades):
                    if trade["symbol"] != symbol:
                        continue
                    ticker = await self.exchange.fetch_ticker(exchange_id, symbol)
                    current_price = ticker["last"]

                    hit_sl = False
                    hit_tp = False
                    if trade["side"] == "buy":
                        hit_sl = current_price <= trade["stop_loss"]
                        hit_tp = trade.get("take_profit") and current_price >= trade["take_profit"]
                    else:
                        hit_sl = current_price >= trade["stop_loss"]
                        hit_tp = trade.get("take_profit") and current_price <= trade["take_profit"]

                    if hit_sl:
                        logger.info(f"{self.bot_type.value} STOP LOSS hit on {symbol}")
                        await self.close_trade(exchange_id, trade, "stopped_out")
                        trades_closed += 1
                    elif hit_tp:
                        logger.info(f"{self.bot_type.value} TAKE PROFIT hit on {symbol}")
                        await self.close_trade(exchange_id, trade, "closed")
                        trades_closed += 1
                    else:
                        df2 = await self.exchange.fetch_ohlcv(exchange_id, symbol, tf)
                        analyzer2 = TechnicalAnalyzer(df2)
                        signal2 = analyzer2.analyze()
                        if await self.evaluate_exit(trade, signal2):
                            await self.close_trade(exchange_id, trade, "closed")
                            trades_closed += 1

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
        }
        self.active_trades.append(trade)

        trade_store.add_trade({
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
        })

        await store.hset(
            f"active_trades:{self.bot_type.value}",
            order["id"],
            json.dumps(trade, default=str),
        )

        trade_store.record_snapshot()

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

        open_trades = trade_store.get_open_trades()
        for ot in open_trades:
            if ot.get("symbol") == trade["symbol"] and ot.get("bot_type") == self.bot_type.value:
                trade_store.close_trade(
                    ot["id"], exit_price, round(net_pnl, 5),
                    round(exit_fee, 5), status,
                    exit_slippage_usd=round(exit_slippage, 8),
                )
                break

        if trade in self.active_trades:
            self.active_trades.remove(trade)
        await store.hdel(f"active_trades:{self.bot_type.value}", trade["order_id"])

        trade_store.record_snapshot()

        logger.info(
            f"{self.bot_type.value} CLOSED {trade['symbol']} @ ${exit_price:.8g} "
            f"gross=${gross_pnl:.5f} fees=${total_fees:.5f} net=${net_pnl:.5f} ({status})"
        )

    async def start(self, exchange_id: str, interval_seconds: int):
        self.running = True
        self._consecutive_errors = 0
        self._cycle_count = 0
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
