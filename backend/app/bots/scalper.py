from app.bots.base import BaseBot
from app.indicators.technical import SignalResult
from app.models.trade import BotType

TOP_PAIRS = [
    "BTC/USDT", "ETH/USDT", "XRP/USDT", "SOL/USDT", "DOGE/USDT",
    "ADA/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT", "MATIC/USDT",
    "NEAR/USDT", "SUI/USDT", "APT/USDT", "ARB/USDT", "OP/USDT",
    "ATOM/USDT", "UNI/USDT", "FIL/USDT", "LTC/USDT", "HBAR/USDT",
    "BONK/USDT", "WIF/USDT", "PEPE/USDT", "SHIB/USDT", "FET/USDT",
    "RENDER/USDT", "INJ/USDT", "TIA/USDT", "SEI/USDT", "JUP/USDT",
]


class ScalperBot(BaseBot):
    def __init__(self, exchange_manager, risk_engine, sentiment_analyzer):
        super().__init__(BotType.SCALPER, exchange_manager, risk_engine, sentiment_analyzer)

    def get_timeframes(self) -> list[str]:
        return ["5m", "15m"]

    def get_symbols(self) -> list[str]:
        available = set(self.exchange.get_all_symbols())
        return [s for s in TOP_PAIRS if s in available]

    async def evaluate_entry(self, symbol: str, signal: SignalResult, sentiment: dict) -> bool:
        if signal.confidence < 0.15:
            return False

        if signal.overall_signal == "hold":
            return False

        score = 0

        if signal.rsi_signal in ("oversold", "overbought"):
            score += 2
        elif signal.rsi_signal in ("approaching_oversold", "approaching_overbought"):
            score += 1

        if signal.macd_signal in ("bullish_crossover", "bearish_crossover"):
            score += 2
        elif signal.macd_signal in ("bullish", "bearish"):
            score += 1

        if signal.bollinger_signal in ("oversold", "overbought"):
            score += 1

        if signal.volume_trend == "high":
            score += 1

        return score >= 2

    async def evaluate_exit(self, trade: dict, signal: SignalResult) -> bool:
        if trade["side"] == "buy":
            if signal.rsi_signal == "overbought":
                return True
            if signal.macd_signal == "bearish_crossover":
                return True
            if signal.overall_signal in ("sell", "strong_sell"):
                return True
        else:
            if signal.rsi_signal == "oversold":
                return True
            if signal.macd_signal == "bullish_crossover":
                return True
            if signal.overall_signal in ("buy", "strong_buy"):
                return True
        return False
