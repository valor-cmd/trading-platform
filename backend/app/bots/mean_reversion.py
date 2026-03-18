import asyncio
import logging
from app.bots.base import BaseBot
from app.exchange.simulator import PaperExchangeManager
from app.risk.engine import RiskEngine
from app.indicators.sentiment import SentimentAnalyzer
from app.indicators.technical import SignalResult, MarketRegime
from app.models.trade import BotType

logger = logging.getLogger(__name__)


class MeanReversionBot(BaseBot):
    def __init__(self, exchange: PaperExchangeManager, risk_engine: RiskEngine, sentiment_analyzer: SentimentAnalyzer):
        super().__init__(BotType.MEAN_REVERSION, exchange, risk_engine, sentiment_analyzer)

    def get_timeframes(self) -> list[str]:
        return ["1h", "4h"]

    def get_symbols(self) -> list[str]:
        return self._get_all_tradable_symbols()

    async def evaluate_entry(self, symbol: str, signal: SignalResult, sentiment: dict) -> bool:
        if signal.confidence < 0.20:
            return False

        regime = signal.regime
        if regime and regime.regime == MarketRegime.CHAOTIC:
            return False

        if regime and regime.regime in (MarketRegime.STRONG_TREND_UP, MarketRegime.STRONG_TREND_DOWN):
            if signal.adx >= 35:
                return False

        if signal.overall_signal == "hold":
            return False

        score = 0.0

        rsi_extreme = False
        if signal.rsi is not None:
            if signal.rsi < 20:
                score += 3.0
                rsi_extreme = True
            elif signal.rsi < 30:
                score += 2.0
                rsi_extreme = True
            elif signal.rsi > 80:
                score += 3.0
                rsi_extreme = True
            elif signal.rsi > 70:
                score += 2.0
                rsi_extreme = True

        bb_extreme = False
        if signal.bollinger_signal in ("oversold", "overbought"):
            score += 2.5
            bb_extreme = True

        if not rsi_extreme and not bb_extreme:
            return False

        if rsi_extreme and bb_extreme:
            score += 1.5

        if signal.stoch_rsi_k < 10 or signal.stoch_rsi_k > 90:
            score += 2.0
        elif signal.stoch_rsi_k < 20 or signal.stoch_rsi_k > 80:
            score += 1.0

        if signal.mfi < 20 or signal.mfi > 80:
            score += 1.5

        if signal.williams_r < -90 or signal.williams_r > -10:
            score += 1.0
        elif signal.williams_r < -80 or signal.williams_r > -20:
            score += 0.5

        if signal.keltner_signal in ("oversold", "overbought"):
            score += 1.0

        if signal.volume_trend in ("high", "very_high"):
            score += 1.0

        if signal.macd_signal in ("bullish_crossover", "bearish_crossover"):
            score += 1.0

        if regime and regime.regime == MarketRegime.RANGING:
            score += 1.0

        return score >= 6.0

    async def evaluate_exit(self, trade: dict, signal: SignalResult) -> bool:
        if trade["side"] == "buy":
            if signal.rsi is not None and signal.rsi > 55:
                return True
            if signal.bollinger_signal == "overbought":
                return True
        else:
            if signal.rsi is not None and signal.rsi < 45:
                return True
            if signal.bollinger_signal == "oversold":
                return True

        if signal.rsi is not None and 45 <= signal.rsi <= 55:
            if signal.bollinger_signal not in ("oversold", "overbought"):
                return True

        return False
