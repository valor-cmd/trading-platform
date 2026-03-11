from app.bots.base import BaseBot
from app.indicators.technical import SignalResult
from app.models.trade import BotType

SWING_PAIRS = [
    "BTC/USDT", "ETH/USDT", "XRP/USDT", "SOL/USDT", "DOGE/USDT",
    "ADA/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT", "MATIC/USDT",
    "NEAR/USDT", "SUI/USDT", "APT/USDT", "ARB/USDT", "OP/USDT",
    "ATOM/USDT", "UNI/USDT", "FIL/USDT", "LTC/USDT", "HBAR/USDT",
    "BONK/USDT", "WIF/USDT", "PEPE/USDT", "SHIB/USDT", "FET/USDT",
    "RENDER/USDT", "INJ/USDT", "TIA/USDT", "SEI/USDT", "JUP/USDT",
    "TRUMP/USDT", "WLD/USDT", "STX/USDT", "IMX/USDT", "MANTA/USDT",
    "PYTH/USDT", "JTO/USDT", "ONDO/USDT", "ENA/USDT", "AAVE/USDT",
]


class SwingBot(BaseBot):
    def __init__(self, exchange_manager, risk_engine, sentiment_analyzer):
        super().__init__(BotType.SWING, exchange_manager, risk_engine, sentiment_analyzer)

    def get_timeframes(self) -> list[str]:
        return ["1h", "4h"]

    def get_symbols(self) -> list[str]:
        available = set(self.exchange.get_all_symbols())
        return [s for s in SWING_PAIRS if s in available]

    async def evaluate_entry(self, symbol: str, signal: SignalResult, sentiment: dict) -> bool:
        if signal.confidence < 0.05:
            return False

        score = 0

        if signal.overall_signal in ("buy", "strong_buy", "sell", "strong_sell"):
            score += 1

        if signal.ema_trend in ("strong_bullish", "strong_bearish"):
            score += 2
        elif signal.ema_trend in ("bullish", "bearish"):
            score += 1

        if signal.rsi_signal in ("oversold", "overbought"):
            score += 1.5
        elif signal.rsi_signal in ("approaching_oversold", "approaching_overbought"):
            score += 0.5

        if signal.macd_signal in ("bullish_crossover", "bearish_crossover"):
            score += 2
        elif signal.macd_signal in ("bullish", "bearish"):
            score += 1

        if signal.bollinger_signal in ("oversold", "overbought"):
            score += 1

        sentiment_bias = sentiment.get("bias", "neutral")
        if sentiment_bias in ("contrarian_buy", "contrarian_sell"):
            score += 1
        elif sentiment_bias in ("lean_buy", "lean_sell"):
            score += 0.5

        if signal.volume_trend == "high":
            score += 1

        return score >= 2

    async def evaluate_exit(self, trade: dict, signal: SignalResult) -> bool:
        if trade["side"] == "buy":
            if signal.ema_trend in ("bearish", "strong_bearish"):
                return True
            if signal.rsi > 75 and signal.macd_signal in ("bearish", "bearish_crossover"):
                return True
        else:
            if signal.ema_trend in ("bullish", "strong_bullish"):
                return True
            if signal.rsi < 25 and signal.macd_signal in ("bullish", "bullish_crossover"):
                return True
        return False
