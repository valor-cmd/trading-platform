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
        return ["15m", "1h", "4h"]

    def get_symbols(self) -> list[str]:
        return self._get_all_tradable_symbols()

    async def evaluate_entry(self, symbol: str, signal: SignalResult, sentiment: dict) -> bool:
        regime = signal.regime
        if not regime:
            return False

        if regime.regime != MarketRegime.RANGING:
            return False

        if signal.bb_width <= 0:
            return False

        if signal.atr <= 0:
            return False

        if signal.adx >= 22:
            return False

        if signal.confidence < 0.20:
            return False

        if signal.overall_signal == "hold":
            return False

        score = 0.0

        score += 3.0

        if signal.bollinger_signal in ("oversold", "overbought"):
            score += 3.0
        elif signal.bollinger_signal in ("approaching_oversold", "approaching_overbought"):
            score += 1.0

        rsi_extreme = False
        if signal.rsi is not None:
            if signal.rsi < 25 or signal.rsi > 75:
                score += 3.0
                rsi_extreme = True
            elif signal.rsi < 30 or signal.rsi > 70:
                score += 1.5
                rsi_extreme = True

        if signal.stoch_rsi_k < 10 or signal.stoch_rsi_k > 90:
            score += 2.0
        elif signal.stoch_rsi_k < 20 or signal.stoch_rsi_k > 80:
            score += 1.0

        if signal.mfi < 20 or signal.mfi > 80:
            score += 1.5

        if signal.williams_r < -85 or signal.williams_r > -15:
            score += 1.0

        if signal.keltner_signal in ("oversold", "overbought"):
            score += 1.5

        if signal.volume_trend in ("high", "very_high"):
            score += 1.0

        if signal.adx < 12:
            score += 2.0
        elif signal.adx < 18:
            score += 1.0

        if abs(signal.zscore) >= 2.0:
            score += 2.0
        elif abs(signal.zscore) >= 1.5:
            score += 1.0

        if signal.sr_proximity == "near_support" and signal.overall_signal in ("buy", "strong_buy"):
            score += 1.5
        elif signal.sr_proximity == "near_resistance" and signal.overall_signal in ("sell", "strong_sell"):
            score += 1.5

        if not rsi_extreme and signal.bollinger_signal not in ("oversold", "overbought"):
            if abs(signal.zscore) < 1.5:
                return False

        return score >= 9.0

    async def evaluate_exit(self, trade: dict, signal: SignalResult) -> bool:
        regime = signal.regime
        if regime and regime.regime in (MarketRegime.STRONG_TREND_UP, MarketRegime.STRONG_TREND_DOWN):
            if signal.adx >= 35:
                return True

        if regime and regime.regime == MarketRegime.CHAOTIC:
            return True

        if signal.adx >= 40:
            return True

        if signal.ema_trend in ("strong_bullish", "strong_bearish") and signal.adx >= 30:
            if signal.trend_consistency > 0.7:
                return True

        return False
