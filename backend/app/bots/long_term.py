from app.bots.base import BaseBot
from app.indicators.technical import SignalResult, MarketRegime
from app.models.trade import BotType


class LongTermBot(BaseBot):
    def __init__(self, exchange_manager, risk_engine, sentiment_analyzer):
        super().__init__(BotType.LONG_TERM, exchange_manager, risk_engine, sentiment_analyzer)

    def get_timeframes(self) -> list[str]:
        return ["1d", "1w"]

    def get_symbols(self) -> list[str]:
        return self._get_all_tradable_symbols()

    async def evaluate_entry(self, symbol: str, signal: SignalResult, sentiment: dict) -> bool:
        if signal.confidence < 0.1:
            return False

        regime = signal.regime
        if regime and regime.regime == MarketRegime.CHAOTIC:
            return False

        if signal.overall_signal == "hold":
            return False

        score = 0.0

        if signal.ema_trend == "strong_bullish":
            score += 2.5
        elif signal.ema_trend == "bullish":
            score += 1.5
        elif signal.ema_trend == "strong_bearish":
            score += 2.5
        elif signal.ema_trend == "bearish":
            score += 1.5

        sentiment_bias = sentiment.get("bias", "neutral")
        sentiment_weight = sentiment.get("weight", 0)
        if sentiment_bias in ("contrarian_buy", "contrarian_sell"):
            score += max(sentiment_weight * 3, 1.5)
        elif sentiment_bias in ("lean_buy", "lean_sell"):
            score += 1.0

        if signal.rsi_signal == "oversold" and signal.overall_signal in ("buy", "strong_buy"):
            score += 2.0
        elif signal.rsi_signal == "overbought" and signal.overall_signal in ("sell", "strong_sell"):
            score += 2.0
        elif signal.rsi_signal in ("oversold", "overbought"):
            score += 1.0

        if signal.macd_signal in ("bullish_crossover", "bearish_crossover"):
            score += 1.5

        if signal.adx >= 25:
            score += 1.0

        if signal.obv_trend in ("bullish", "bearish"):
            score += 0.75

        if signal.psar_direction in ("bullish", "bearish"):
            score += 0.5

        if signal.mfi < 20 or signal.mfi > 80:
            score += 0.75

        if regime and regime.regime == MarketRegime.RANGING:
            score -= 1.5

        if regime and regime.regime == MarketRegime.VOLATILE:
            if signal.adx < 25:
                score -= 0.5

        return score >= 3.5

    async def evaluate_exit(self, trade: dict, signal: SignalResult) -> bool:
        regime = signal.regime
        if regime and regime.regime == MarketRegime.CHAOTIC:
            return True

        if trade["side"] == "buy":
            if signal.ema_trend == "strong_bearish" and signal.rsi > 60 and signal.adx >= 25:
                return True
            if signal.macd_signal == "bearish_crossover" and signal.ema_trend in ("bearish", "strong_bearish"):
                return True
            if signal.psar_direction == "bearish" and signal.obv_trend == "bearish" and signal.vortex_signal == "bearish":
                return True
            if signal.overall_signal == "strong_sell" and signal.confirmation_score >= 6:
                return True
        else:
            if signal.ema_trend == "strong_bullish" and signal.rsi < 40 and signal.adx >= 25:
                return True
            if signal.macd_signal == "bullish_crossover" and signal.ema_trend in ("bullish", "strong_bullish"):
                return True
            if signal.psar_direction == "bullish" and signal.obv_trend == "bullish" and signal.vortex_signal == "bullish":
                return True
            if signal.overall_signal == "strong_buy" and signal.confirmation_score >= 6:
                return True
        return False
