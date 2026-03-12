from app.bots.base import BaseBot
from app.indicators.technical import SignalResult
from app.models.trade import BotType


class LongTermBot(BaseBot):
    def __init__(self, exchange_manager, risk_engine, sentiment_analyzer):
        super().__init__(BotType.LONG_TERM, exchange_manager, risk_engine, sentiment_analyzer)

    def get_timeframes(self) -> list[str]:
        return ["1d", "1w"]

    def get_symbols(self) -> list[str]:
        return self._get_all_tradable_symbols()

    async def evaluate_entry(self, symbol: str, signal: SignalResult, sentiment: dict) -> bool:
        if signal.confidence < 0.05:
            return False

        score = 0

        if signal.overall_signal in ("buy", "strong_buy", "sell", "strong_sell"):
            score += 1

        if signal.ema_trend == "strong_bullish":
            score += 2
        elif signal.ema_trend == "bullish":
            score += 1
        elif signal.ema_trend == "strong_bearish":
            score += 2
        elif signal.ema_trend == "bearish":
            score += 1

        sentiment_bias = sentiment.get("bias", "neutral")
        sentiment_weight = sentiment.get("weight", 0)
        if sentiment_bias in ("contrarian_buy", "contrarian_sell"):
            score += max(sentiment_weight * 3, 1)
        elif sentiment_bias in ("lean_buy", "lean_sell"):
            score += 1

        if signal.rsi_signal == "oversold" and signal.overall_signal in ("buy", "strong_buy"):
            score += 2
        elif signal.rsi_signal == "overbought" and signal.overall_signal in ("sell", "strong_sell"):
            score += 2
        elif signal.rsi_signal in ("oversold", "overbought"):
            score += 1
        elif signal.rsi_signal in ("approaching_oversold", "approaching_overbought"):
            score += 0.5

        if signal.macd_signal in ("bullish_crossover", "bearish_crossover"):
            score += 1
        elif signal.macd_signal in ("bullish", "bearish"):
            score += 0.5

        return score >= 2

    async def evaluate_exit(self, trade: dict, signal: SignalResult) -> bool:
        if trade["side"] == "buy":
            if signal.ema_trend == "strong_bearish" and signal.rsi > 60:
                return True
            if signal.macd_signal == "bearish_crossover" and signal.ema_trend == "bearish":
                return True
        else:
            if signal.ema_trend == "strong_bullish" and signal.rsi < 40:
                return True
            if signal.macd_signal == "bullish_crossover" and signal.ema_trend == "bullish":
                return True
        return False
