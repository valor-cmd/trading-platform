import logging
from app.bots.base import BaseBot
from app.exchange.simulator import PaperExchangeManager
from app.risk.engine import RiskEngine
from app.indicators.sentiment import SentimentAnalyzer
from app.indicators.technical import SignalResult, MarketRegime
from app.models.trade import BotType

logger = logging.getLogger(__name__)


class DCABot(BaseBot):
    def __init__(self, exchange: PaperExchangeManager, risk_engine: RiskEngine, sentiment_analyzer: SentimentAnalyzer):
        super().__init__(BotType.DCA, exchange, risk_engine, sentiment_analyzer)
        self._safety_order_counts: dict[str, int] = {}
        self._max_safety_orders = 5
        self._safety_deviation_pct = 2.0
        self._take_profit_pct = 1.5

    def get_timeframes(self) -> list[str]:
        return ["1h", "4h"]

    def get_symbols(self) -> list[str]:
        return self._get_all_tradable_symbols()

    async def evaluate_entry(self, symbol: str, signal: SignalResult, sentiment: dict) -> bool:
        regime = signal.regime
        if regime and regime.regime == MarketRegime.CHAOTIC:
            return False

        if regime and regime.regime == MarketRegime.STRONG_TREND_DOWN:
            return False

        if regime and regime.regime == MarketRegime.TREND_DOWN:
            if signal.adx >= 25:
                return False

        if signal.overall_signal in ("sell", "strong_sell"):
            if signal.ema_trend in ("bearish", "strong_bearish"):
                return False

        if signal.confidence < 0.15:
            return False

        score = 0.0

        if signal.rsi is not None and signal.rsi < 25:
            score += 3.5
        elif signal.rsi is not None and signal.rsi < 30:
            score += 2.5
        elif signal.rsi is not None and signal.rsi < 35:
            score += 1.5

        if signal.bollinger_signal == "oversold":
            score += 2.5

        if signal.ema_trend in ("bullish", "strong_bullish"):
            score += 2.5
        elif signal.ema_trend == "neutral":
            score += 0.5
        elif signal.ema_trend == "bearish":
            score -= 1.0
        elif signal.ema_trend == "strong_bearish":
            score -= 2.0

        if signal.macd_signal in ("bullish", "bullish_crossover"):
            score += 2.0
        elif signal.macd_signal in ("bearish", "bearish_crossover"):
            score -= 1.0

        if signal.volume_trend in ("high", "very_high"):
            score += 1.0

        if signal.mfi < 20:
            score += 1.5
        elif signal.mfi < 30:
            score += 1.0

        if signal.obv_trend == "bullish":
            score += 1.0
        elif signal.obv_trend == "bearish":
            score -= 0.5

        if signal.stoch_rsi_k < 15:
            score += 1.5
        elif signal.stoch_rsi_k < 25:
            score += 0.5

        if signal.zscore < -2.0:
            score += 2.0
        elif signal.zscore < -1.5:
            score += 1.0

        if signal.sr_proximity == "near_support":
            score += 1.5
        elif signal.sr_proximity == "near_resistance":
            score -= 1.0

        if signal.vwap_signal == "below":
            score += 0.5

        sentiment_bias = sentiment.get("bias", "neutral")
        if sentiment_bias in ("contrarian_buy",):
            score += 2.0
        elif sentiment_bias in ("lean_buy",):
            score += 1.0

        if regime and regime.regime == MarketRegime.RANGING:
            score += 0.5

        return score >= 7.0

    async def evaluate_exit(self, trade: dict, signal: SignalResult) -> bool:
        entry_price = trade.get("entry_price", 0)
        if entry_price <= 0:
            return False

        if trade["side"] == "buy":
            if signal.rsi is not None and signal.rsi > 70:
                return True
            if signal.rsi is not None and signal.rsi > 65 and signal.macd_signal in ("bearish", "bearish_crossover"):
                return True
            if signal.bollinger_signal == "overbought" and signal.rsi is not None and signal.rsi > 60:
                return True
            if signal.ema_trend == "strong_bearish" and signal.adx >= 30 and signal.rsi is not None and signal.rsi > 50:
                return True
        else:
            if signal.rsi is not None and signal.rsi < 30:
                return True

        regime = signal.regime
        if regime and regime.regime == MarketRegime.CHAOTIC:
            return True

        return False
