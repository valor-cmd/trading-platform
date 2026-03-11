import pandas as pd
import ta
from dataclasses import dataclass
from typing import Optional


@dataclass
class SignalResult:
    rsi: float
    rsi_signal: str
    macd_signal: str
    bollinger_signal: str
    ema_trend: str
    volume_trend: str
    atr: float
    support: float
    resistance: float
    overall_signal: str
    confidence: float


class TechnicalAnalyzer:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self._calculate_all()

    def _calculate_all(self):
        self.df["rsi"] = ta.momentum.RSIIndicator(self.df["close"], window=14).rsi()

        macd = ta.trend.MACD(self.df["close"])
        self.df["macd"] = macd.macd()
        self.df["macd_signal"] = macd.macd_signal()
        self.df["macd_diff"] = macd.macd_diff()

        bb = ta.volatility.BollingerBands(self.df["close"], window=20, window_dev=2)
        self.df["bb_upper"] = bb.bollinger_hband()
        self.df["bb_lower"] = bb.bollinger_lband()
        self.df["bb_middle"] = bb.bollinger_mavg()

        self.df["ema_9"] = ta.trend.EMAIndicator(self.df["close"], window=9).ema_indicator()
        self.df["ema_21"] = ta.trend.EMAIndicator(self.df["close"], window=21).ema_indicator()
        self.df["ema_50"] = ta.trend.EMAIndicator(self.df["close"], window=50).ema_indicator()
        self.df["ema_200"] = ta.trend.EMAIndicator(self.df["close"], window=200).ema_indicator()

        self.df["atr"] = ta.volatility.AverageTrueRange(
            self.df["high"], self.df["low"], self.df["close"], window=14
        ).average_true_range()

        self.df["volume_sma"] = self.df["volume"].rolling(window=20).mean()

        stoch = ta.momentum.StochasticOscillator(
            self.df["high"], self.df["low"], self.df["close"]
        )
        self.df["stoch_k"] = stoch.stoch()
        self.df["stoch_d"] = stoch.stoch_signal()

    def get_rsi_signal(self) -> tuple[float, str]:
        rsi = self.df["rsi"].iloc[-1]
        if rsi < 30:
            return rsi, "oversold"
        elif rsi > 70:
            return rsi, "overbought"
        elif rsi < 40:
            return rsi, "approaching_oversold"
        elif rsi > 60:
            return rsi, "approaching_overbought"
        return rsi, "neutral"

    def get_macd_signal(self) -> str:
        macd_diff = self.df["macd_diff"].iloc[-1]
        prev_diff = self.df["macd_diff"].iloc[-2]
        if macd_diff > 0 and prev_diff <= 0:
            return "bullish_crossover"
        elif macd_diff < 0 and prev_diff >= 0:
            return "bearish_crossover"
        elif macd_diff > 0:
            return "bullish"
        return "bearish"

    def get_bollinger_signal(self) -> str:
        close = self.df["close"].iloc[-1]
        upper = self.df["bb_upper"].iloc[-1]
        lower = self.df["bb_lower"].iloc[-1]
        if close <= lower:
            return "oversold"
        elif close >= upper:
            return "overbought"
        return "neutral"

    def get_ema_trend(self) -> str:
        row = self.df.iloc[-1]
        if row["ema_9"] > row["ema_21"] > row["ema_50"]:
            return "strong_bullish"
        elif row["ema_9"] > row["ema_21"]:
            return "bullish"
        elif row["ema_9"] < row["ema_21"] < row["ema_50"]:
            return "strong_bearish"
        elif row["ema_9"] < row["ema_21"]:
            return "bearish"
        return "neutral"

    def get_volume_trend(self) -> str:
        vol = self.df["volume"].iloc[-1]
        avg = self.df["volume_sma"].iloc[-1]
        if vol > avg * 1.5:
            return "high"
        elif vol < avg * 0.5:
            return "low"
        return "normal"

    def get_support_resistance(self, lookback: int = 50) -> tuple[float, float]:
        recent = self.df.tail(lookback)
        support = recent["low"].min()
        resistance = recent["high"].max()
        return support, resistance

    def analyze(self) -> SignalResult:
        rsi, rsi_signal = self.get_rsi_signal()
        macd_signal = self.get_macd_signal()
        bb_signal = self.get_bollinger_signal()
        ema_trend = self.get_ema_trend()
        vol_trend = self.get_volume_trend()
        atr = self.df["atr"].iloc[-1]
        support, resistance = self.get_support_resistance()

        bullish_score = 0
        bearish_score = 0
        total_factors = 5

        if rsi_signal == "oversold":
            bullish_score += 1
        elif rsi_signal == "overbought":
            bearish_score += 1

        if macd_signal in ("bullish_crossover", "bullish"):
            bullish_score += 1
        else:
            bearish_score += 1

        if bb_signal == "oversold":
            bullish_score += 1
        elif bb_signal == "overbought":
            bearish_score += 1

        if ema_trend in ("strong_bullish", "bullish"):
            bullish_score += 1
        elif ema_trend in ("strong_bearish", "bearish"):
            bearish_score += 1

        if vol_trend == "high":
            bullish_score += 0.5
            bearish_score += 0.5

        net = bullish_score - bearish_score
        confidence = abs(net) / total_factors

        if net > 1:
            overall = "strong_buy"
        elif net > 0:
            overall = "buy"
        elif net < -1:
            overall = "strong_sell"
        elif net < 0:
            overall = "sell"
        else:
            overall = "hold"

        return SignalResult(
            rsi=rsi,
            rsi_signal=rsi_signal,
            macd_signal=macd_signal,
            bollinger_signal=bb_signal,
            ema_trend=ema_trend,
            volume_trend=vol_trend,
            atr=atr,
            support=support,
            resistance=resistance,
            overall_signal=overall,
            confidence=confidence,
        )
