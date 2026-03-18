from app.bots.base import BaseBot
from app.indicators.technical import SignalResult, MarketRegime
from app.models.trade import BotType


class SwingBot(BaseBot):
    def __init__(self, exchange_manager, risk_engine, sentiment_analyzer):
        super().__init__(BotType.SWING, exchange_manager, risk_engine, sentiment_analyzer)

    def get_timeframes(self) -> list[str]:
        return ["1h", "4h"]

    def get_symbols(self) -> list[str]:
        return self._get_all_tradable_symbols()

    async def get_symbols_filtered(self) -> list[str]:
        return await self._get_filtered_symbols()

    async def evaluate_entry(self, symbol: str, signal: SignalResult, sentiment: dict) -> bool:
        if signal.confidence < 0.30:
            return False

        regime = signal.regime
        if regime and regime.regime == MarketRegime.CHAOTIC:
            return False

        if signal.overall_signal == "hold":
            return False

        score = 0.0

        if signal.ema_trend in ("strong_bullish", "strong_bearish"):
            score += 2.5
        elif signal.ema_trend in ("bullish", "bearish"):
            score += 1.0

        if signal.macd_signal in ("bullish_crossover", "bearish_crossover"):
            score += 2.0
        elif signal.macd_signal in ("bullish", "bearish"):
            score += 0.5

        if signal.rsi_signal in ("oversold", "overbought"):
            score += 1.5
        elif signal.rsi_signal in ("approaching_oversold", "approaching_overbought"):
            score += 0.5

        if signal.adx >= 25:
            score += 1.5
        elif signal.adx >= 20:
            score += 0.5

        if signal.psar_direction in ("bullish", "bearish"):
            score += 1.0

        if signal.obv_trend in ("bullish", "bearish"):
            score += 0.75

        if signal.vortex_signal in ("bullish", "bearish"):
            score += 0.5

        if signal.volume_trend in ("high", "very_high"):
            score += 0.5

        sentiment_bias = sentiment.get("bias", "neutral")
        if sentiment_bias in ("contrarian_buy", "contrarian_sell"):
            score += 1.5
        elif sentiment_bias in ("lean_buy", "lean_sell"):
            score += 0.5

        if regime and regime.regime == MarketRegime.RANGING:
            score -= 1.0

        if regime and regime.regime == MarketRegime.VOLATILE:
            if signal.adx < 25:
                score -= 1.0

        return score >= 6.5

    async def evaluate_exit(self, trade: dict, signal: SignalResult) -> bool:
        regime = signal.regime
        if regime and regime.regime == MarketRegime.CHAOTIC:
            return True

        if trade["side"] == "buy":
            if signal.ema_trend == "strong_bearish" and signal.adx >= 25:
                return True
            if signal.rsi > 75 and signal.macd_signal in ("bearish", "bearish_crossover"):
                return True
            if signal.psar_direction == "bearish" and signal.obv_trend == "bearish":
                return True
            if signal.overall_signal == "strong_sell" and signal.confirmation_score >= 5:
                return True
        else:
            if signal.ema_trend == "strong_bullish" and signal.adx >= 25:
                return True
            if signal.rsi < 25 and signal.macd_signal in ("bullish", "bullish_crossover"):
                return True
            if signal.psar_direction == "bullish" and signal.obv_trend == "bullish":
                return True
            if signal.overall_signal == "strong_buy" and signal.confirmation_score >= 5:
                return True
        return False
