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

        if regime and regime.regime == MarketRegime.RANGING:
            if signal.adx < 15 and signal.bb_width < 0.02:
                return False

        if signal.overall_signal == "hold":
            return False

        if signal.volume_trend in ("low", "normal"):
            return False

        score = 0.0

        if signal.rsi_signal in ("oversold", "overbought"):
            score += 2.5
        elif signal.rsi_signal in ("approaching_oversold", "approaching_overbought"):
            score += 0.5

        if signal.macd_signal in ("bullish_crossover", "bearish_crossover"):
            score += 2.5

        if signal.bollinger_signal in ("oversold", "overbought"):
            score += 1.5

        if signal.volume_trend == "very_high":
            score += 2.0
        elif signal.volume_trend == "high":
            score += 1.0

        if signal.adx >= 25:
            score += 1.5
        elif signal.adx >= 20:
            score += 0.5

        if signal.psar_direction in ("bullish", "bearish"):
            if signal.ema_trend and signal.ema_trend.replace("strong_", "") == signal.psar_direction:
                score += 1.5
            else:
                score += 0.5

        if signal.stoch_rsi_k < 15 or signal.stoch_rsi_k > 85:
            score += 1.5
        elif signal.stoch_rsi_k < 20 or signal.stoch_rsi_k > 80:
            score += 0.5

        if signal.mfi < 20 or signal.mfi > 80:
            score += 1.0

        if signal.squeeze_on and signal.squeeze_momentum != 0:
            score += 1.0

        if signal.candle_strength == "strong":
            score += 1.0

        if signal.sr_proximity == "near_support" and signal.overall_signal in ("buy", "strong_buy"):
            score += 1.0
        elif signal.sr_proximity == "near_resistance" and signal.overall_signal in ("sell", "strong_sell"):
            score += 1.0

        return score >= 7.0

    async def evaluate_exit(self, trade: dict, signal: SignalResult) -> bool:
        regime = signal.regime
        if regime and regime.regime == MarketRegime.CHAOTIC:
            return True

        if trade["side"] == "buy":
            if signal.rsi_signal == "overbought" and signal.macd_signal in ("bearish", "bearish_crossover"):
                return True
            if signal.psar_direction == "bearish" and signal.vortex_signal == "bearish":
                return True
            if signal.overall_signal in ("sell", "strong_sell") and signal.confirmation_score >= 5:
                return True
            if signal.stoch_rsi_k > 90 and signal.mfi > 80:
                return True
        else:
            if signal.rsi_signal == "oversold" and signal.macd_signal in ("bullish", "bullish_crossover"):
                return True
            if signal.psar_direction == "bullish" and signal.vortex_signal == "bullish":
                return True
            if signal.overall_signal in ("buy", "strong_buy") and signal.confirmation_score >= 5:
                return True
            if signal.stoch_rsi_k < 10 and signal.mfi < 20:
                return True
        return False
