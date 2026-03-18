import asyncio
import logging
from app.bots.base import BaseBot
from app.exchange.simulator import PaperExchangeManager
from app.risk.engine import RiskEngine
from app.indicators.sentiment import SentimentAnalyzer
from app.indicators.technical import SignalResult, MarketRegime
from app.models.trade import BotType

logger = logging.getLogger(__name__)


class MomentumBot(BaseBot):
    def __init__(self, exchange: PaperExchangeManager, risk_engine: RiskEngine, sentiment_analyzer: SentimentAnalyzer):
        super().__init__(BotType.MOMENTUM, exchange, risk_engine, sentiment_analyzer)

    def get_timeframes(self) -> list[str]:
        return ["4h", "1d"]

    def get_symbols(self) -> list[str]:
        return self._get_all_tradable_symbols()

    async def evaluate_entry(self, symbol: str, signal: SignalResult, sentiment: dict) -> bool:
        if signal.confidence < 0.30:
            return False

        regime = signal.regime
        if regime and regime.regime in (MarketRegime.RANGING, MarketRegime.CHAOTIC):
            return False

        if signal.overall_signal == "hold":
            return False

        score = 0.0

        has_ema_trend = False
        if signal.ema_trend in ("strong_bullish", "strong_bearish"):
            score += 3.0
            has_ema_trend = True
        elif signal.ema_trend in ("bullish", "bearish"):
            score += 1.5
            has_ema_trend = True

        has_macd = False
        if signal.macd_signal in ("bullish_crossover", "bearish_crossover"):
            score += 2.5
            has_macd = True
        elif signal.macd_signal in ("bullish", "bearish"):
            score += 1.0
            has_macd = True

        if not has_ema_trend and not has_macd:
            return False

        if has_ema_trend and has_macd:
            ema_bullish = signal.ema_trend in ("bullish", "strong_bullish")
            macd_bullish = signal.macd_signal in ("bullish", "bullish_crossover")
            if ema_bullish == macd_bullish:
                score += 1.5

        has_volume = False
        if signal.volume_trend == "very_high":
            score += 2.0
            has_volume = True
        elif signal.volume_trend == "high":
            score += 1.0
            has_volume = True

        if signal.adx >= 30:
            score += 2.0
        elif signal.adx >= 25:
            score += 1.0
        elif signal.adx < 20:
            return False

        if signal.psar_direction in ("bullish", "bearish"):
            if signal.ema_trend and signal.ema_trend.replace("strong_", "") == signal.psar_direction:
                score += 1.5

        if signal.vortex_signal in ("bullish", "bearish"):
            score += 0.5

        if signal.obv_trend in ("bullish", "bearish"):
            if signal.ema_trend and signal.ema_trend.replace("strong_", "") == signal.obv_trend:
                score += 1.0

        sentiment_bias = sentiment.get("bias", "neutral")
        if sentiment_bias in ("lean_buy",) and signal.ema_trend in ("bullish", "strong_bullish"):
            score += 0.5
        elif sentiment_bias in ("lean_sell",) and signal.ema_trend in ("bearish", "strong_bearish"):
            score += 0.5

        return score >= 7.0

    async def evaluate_exit(self, trade: dict, signal: SignalResult) -> bool:
        if trade["side"] == "buy":
            if signal.macd_signal in ("bearish_crossover",):
                return True
            if signal.ema_trend in ("bearish", "strong_bearish") and signal.adx >= 25:
                return True
            if signal.psar_direction == "bearish" and signal.vortex_signal == "bearish":
                return True
        else:
            if signal.macd_signal in ("bullish_crossover",):
                return True
            if signal.ema_trend in ("bullish", "strong_bullish") and signal.adx >= 25:
                return True
            if signal.psar_direction == "bullish" and signal.vortex_signal == "bullish":
                return True

        if signal.adx < 15:
            return True

        regime = signal.regime
        if regime and regime.regime in (MarketRegime.RANGING, MarketRegime.CHAOTIC):
            return True

        return False
