import asyncio
import logging
from app.bots.base import BaseBot
from app.exchange.simulator import PaperExchangeManager
from app.risk.engine import RiskEngine
from app.indicators.sentiment import SentimentAnalyzer
from app.indicators.technical import SignalResult, MarketRegime
from app.models.trade import BotType

logger = logging.getLogger(__name__)


class GridBot(BaseBot):
    def __init__(self, exchange: PaperExchangeManager, risk_engine: RiskEngine, sentiment_analyzer: SentimentAnalyzer):
        super().__init__(BotType.GRID, exchange, risk_engine, sentiment_analyzer)

    def get_timeframes(self) -> list[str]:
        return ["1h", "4h"]

    def get_symbols(self) -> list[str]:
        return self._get_all_tradable_symbols()

    async def evaluate_entry(self, symbol: str, signal: SignalResult, sentiment: dict) -> bool:
        regime = signal.regime
        if not regime:
            return False

        if regime.regime not in (MarketRegime.RANGING, MarketRegime.VOLATILE):
            return False

        if regime.regime == MarketRegime.VOLATILE and signal.adx >= 30:
            return False

        if signal.bb_width <= 0:
            return False

        score = 0.0

        if regime.regime == MarketRegime.RANGING:
            score += 3.0

        if signal.bollinger_signal in ("oversold", "overbought"):
            score += 2.5

        if signal.rsi is not None:
            if signal.rsi < 25 or signal.rsi > 75:
                score += 2.0
            elif signal.rsi < 35 or signal.rsi > 65:
                score += 1.0

        if signal.stoch_rsi_k < 15 or signal.stoch_rsi_k > 85:
            score += 1.5

        if signal.mfi < 25 or signal.mfi > 75:
            score += 1.0

        if signal.williams_r < -80 or signal.williams_r > -20:
            score += 1.0

        if signal.keltner_signal in ("oversold", "overbought"):
            score += 1.0

        if signal.volume_trend in ("high", "very_high"):
            score += 0.5

        if signal.adx < 20:
            score += 1.0
        elif signal.adx < 25:
            score += 0.5

        return score >= 5.0

    async def evaluate_exit(self, trade: dict, signal: SignalResult) -> bool:
        regime = signal.regime
        if regime and regime.regime in (MarketRegime.STRONG_TREND_UP, MarketRegime.STRONG_TREND_DOWN):
            return True

        if regime and regime.regime == MarketRegime.CHAOTIC:
            return True

        if signal.adx >= 35:
            return True

        return False
