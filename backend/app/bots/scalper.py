from app.bots.base import BaseBot
from app.indicators.technical import SignalResult, MarketRegime
from app.models.trade import BotType


class ScalperBot(BaseBot):
    def __init__(self, exchange_manager, risk_engine, sentiment_analyzer):
        super().__init__(BotType.SCALPER, exchange_manager, risk_engine, sentiment_analyzer)

    def get_timeframes(self) -> list[str]:
        return ["5m", "15m"]

    def get_symbols(self) -> list[str]:
        return self._get_all_tradable_symbols()

    async def get_symbols_filtered(self) -> list[str]:
        return await self._get_filtered_symbols()

    async def evaluate_entry(self, symbol: str, signal: SignalResult, sentiment: dict) -> bool:
        if signal.confidence < 0.35:
            return False

        regime = signal.regime
        if regime and regime.regime == MarketRegime.CHAOTIC:
            return False

        if signal.overall_signal == "hold":
            return False

        score = 0.0

        if signal.rsi_signal in ("oversold", "overbought"):
            score += 2.0
        elif signal.rsi_signal in ("approaching_oversold", "approaching_overbought"):
            score += 0.5

        if signal.macd_signal in ("bullish_crossover", "bearish_crossover"):
            score += 2.0

        if signal.bollinger_signal in ("oversold", "overbought"):
            score += 1.0

        if signal.volume_trend in ("high", "very_high"):
            score += 1.0

        if signal.adx >= 25:
            score += 1.0

        if signal.psar_direction in ("bullish", "bearish"):
            score += 0.5

        if signal.stoch_rsi_k < 20 or signal.stoch_rsi_k > 80:
            score += 0.5

        if signal.mfi < 20 or signal.mfi > 80:
            score += 0.5

        if regime and regime.regime in (MarketRegime.RANGING,):
            if signal.bollinger_signal in ("oversold", "overbought"):
                score += 0.5
            else:
                score -= 1.0

        return score >= 6.0

    async def evaluate_exit(self, trade: dict, signal: SignalResult) -> bool:
        regime = signal.regime
        if regime and regime.regime == MarketRegime.CHAOTIC:
            return True

        if trade["side"] == "buy":
            if signal.rsi_signal == "overbought" and signal.macd_signal in ("bearish", "bearish_crossover"):
                return True
            if signal.psar_direction == "bearish" and signal.vortex_signal == "bearish":
                return True
            if signal.overall_signal in ("sell", "strong_sell") and signal.confirmation_score >= 4:
                return True
        else:
            if signal.rsi_signal == "oversold" and signal.macd_signal in ("bullish", "bullish_crossover"):
                return True
            if signal.psar_direction == "bullish" and signal.vortex_signal == "bullish":
                return True
            if signal.overall_signal in ("buy", "strong_buy") and signal.confirmation_score >= 4:
                return True
        return False
