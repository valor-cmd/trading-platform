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
        return ["15m", "1h", "4h"]

    def get_symbols(self) -> list[str]:
        return self._get_all_tradable_symbols()

    async def evaluate_entry(self, symbol: str, signal: SignalResult, sentiment: dict) -> bool:
        if signal.confidence < 0.20:
            return False

        regime = signal.regime
        if regime and regime.regime == MarketRegime.CHAOTIC:
            return False

        if regime and regime.regime in (MarketRegime.STRONG_TREND_UP, MarketRegime.STRONG_TREND_DOWN):
            return False

        if regime and regime.regime in (MarketRegime.TREND_UP, MarketRegime.TREND_DOWN):
            if signal.adx >= 25:
                return False

        if signal.overall_signal == "hold":
            return False

        if signal.adx >= 22:
            return False

        score = 0.0

        zscore_extreme = False
        if abs(signal.zscore) >= 2.0:
            score += 3.0
            zscore_extreme = True
        elif abs(signal.zscore) >= 1.5:
            score += 1.5
            zscore_extreme = True

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

        if not rsi_extreme and not bb_extreme and not zscore_extreme:
            return False

        extremes_count = sum([rsi_extreme, bb_extreme, zscore_extreme])
        if extremes_count >= 2:
            score += 3.0
        elif extremes_count == 1:
            score += 0.5

        if extremes_count < 2:
            return False

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
            score += 1.5

        if signal.sr_proximity == "near_support" and signal.overall_signal in ("buy", "strong_buy"):
            score += 1.5
        elif signal.sr_proximity == "near_resistance" and signal.overall_signal in ("sell", "strong_sell"):
            score += 1.5

        if regime and regime.regime == MarketRegime.RANGING:
            score += 1.0

        return score >= 9.0

    async def evaluate_exit(self, trade: dict, signal: SignalResult) -> bool:
        if abs(signal.zscore) < 0.5:
            if trade["side"] == "buy" and signal.rsi is not None and signal.rsi > 50:
                return True
            if trade["side"] == "sell" and signal.rsi is not None and signal.rsi < 50:
                return True

        if trade["side"] == "buy":
            if signal.rsi is not None and signal.rsi > 65:
                return True
            if signal.bollinger_signal == "overbought" and signal.rsi is not None and signal.rsi > 55:
                return True
            if signal.macd_signal in ("bearish", "bearish_crossover") and signal.rsi is not None and signal.rsi > 55:
                return True
            if signal.zscore > 1.5:
                return True
        else:
            if signal.rsi is not None and signal.rsi < 35:
                return True
            if signal.bollinger_signal == "oversold" and signal.rsi is not None and signal.rsi < 45:
                return True
            if signal.macd_signal in ("bullish", "bullish_crossover") and signal.rsi is not None and signal.rsi < 45:
                return True
            if signal.zscore < -1.5:
                return True

        return False
