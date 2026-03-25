import pandas as pd
import numpy as np
import ta
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class MarketRegime(str, Enum):
    STRONG_TREND_UP = "strong_trend_up"
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    STRONG_TREND_DOWN = "strong_trend_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    CHAOTIC = "chaotic"


@dataclass
class RegimeData:
    regime: MarketRegime
    adx: float
    adx_plus_di: float
    adx_minus_di: float
    bb_width: float
    bb_width_percentile: float
    atr_pct: float
    atr_percentile: float
    keltner_width: float
    regime_confidence: float
    trend_strength: float
    volatility_level: str


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
    regime: Optional[RegimeData] = None
    adx: float = 0.0
    adx_plus_di: float = 0.0
    adx_minus_di: float = 0.0
    bb_width: float = 0.0
    stoch_rsi_k: float = 50.0
    stoch_rsi_d: float = 50.0
    williams_r: float = -50.0
    mfi: float = 50.0
    obv_trend: str = "neutral"
    psar_direction: str = "neutral"
    vortex_signal: str = "neutral"
    keltner_signal: str = "neutral"
    stoch_k: float = 50.0
    stoch_d: float = 50.0
    confirmation_score: float = 0.0
    required_score: float = 0.0
    confirmations: list = field(default_factory=list)
    zscore: float = 0.0
    vwap: float = 0.0
    vwap_signal: str = "neutral"
    squeeze_on: bool = False
    squeeze_momentum: float = 0.0
    cmf: float = 0.0
    pivot_support: float = 0.0
    pivot_resistance: float = 0.0
    sr_proximity: str = "middle"
    trend_consistency: float = 0.0
    candle_strength: str = "neutral"


class TechnicalAnalyzer:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self._calculate_all()

    def _calculate_all(self):
        close = self.df["close"]
        high = self.df["high"]
        low = self.df["low"]
        volume = self.df["volume"]

        self.df["rsi"] = ta.momentum.RSIIndicator(close, window=14).rsi()

        macd = ta.trend.MACD(close)
        self.df["macd"] = macd.macd()
        self.df["macd_signal"] = macd.macd_signal()
        self.df["macd_diff"] = macd.macd_diff()

        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        self.df["bb_upper"] = bb.bollinger_hband()
        self.df["bb_lower"] = bb.bollinger_lband()
        self.df["bb_middle"] = bb.bollinger_mavg()
        self.df["bb_width"] = (self.df["bb_upper"] - self.df["bb_lower"]) / self.df["bb_middle"]
        self.df["bb_pband"] = bb.bollinger_pband()

        self.df["ema_9"] = ta.trend.EMAIndicator(close, window=9).ema_indicator()
        self.df["ema_21"] = ta.trend.EMAIndicator(close, window=21).ema_indicator()
        self.df["ema_50"] = ta.trend.EMAIndicator(close, window=50).ema_indicator()
        self.df["ema_200"] = ta.trend.EMAIndicator(close, window=200).ema_indicator()

        self.df["atr"] = ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range()
        self.df["atr_pct"] = self.df["atr"] / close * 100

        self.df["volume_sma"] = volume.rolling(window=20).mean()

        stoch = ta.momentum.StochasticOscillator(high, low, close)
        self.df["stoch_k"] = stoch.stoch()
        self.df["stoch_d"] = stoch.stoch_signal()

        adx_ind = ta.trend.ADXIndicator(high, low, close, window=14)
        self.df["adx"] = adx_ind.adx()
        self.df["adx_plus_di"] = adx_ind.adx_pos()
        self.df["adx_minus_di"] = adx_ind.adx_neg()

        stoch_rsi = ta.momentum.StochRSIIndicator(close, window=14, smooth1=3, smooth2=3)
        self.df["stoch_rsi_k"] = stoch_rsi.stochrsi_k()
        self.df["stoch_rsi_d"] = stoch_rsi.stochrsi_d()

        self.df["williams_r"] = ta.momentum.WilliamsRIndicator(high, low, close, lbp=14).williams_r()

        self.df["mfi"] = ta.volume.MFIIndicator(high, low, close, volume, window=14).money_flow_index()

        self.df["obv"] = ta.volume.OnBalanceVolumeIndicator(close, volume).on_balance_volume()
        self.df["obv_ema"] = ta.trend.EMAIndicator(self.df["obv"], window=20).ema_indicator()

        kc = ta.volatility.KeltnerChannel(high, low, close, window=20, window_atr=14)
        self.df["kc_upper"] = kc.keltner_channel_hband()
        self.df["kc_lower"] = kc.keltner_channel_lband()
        self.df["kc_middle"] = kc.keltner_channel_mband()

        psar = ta.trend.PSARIndicator(high, low, close)
        self.df["psar_up"] = psar.psar_up()
        self.df["psar_down"] = psar.psar_down()

        vortex = ta.trend.VortexIndicator(high, low, close, window=14)
        self.df["vortex_pos"] = vortex.vortex_indicator_pos()
        self.df["vortex_neg"] = vortex.vortex_indicator_neg()

        self.df["cmf"] = ta.volume.ChaikinMoneyFlowIndicator(high, low, close, volume, window=20).chaikin_money_flow()

        mean_20 = close.rolling(window=20).mean()
        std_20 = close.rolling(window=20).std()
        self.df["zscore"] = (close - mean_20) / std_20.replace(0, np.nan)

        cum_vol = volume.cumsum()
        cum_vp = (close * volume).cumsum()
        self.df["vwap"] = cum_vp / cum_vol.replace(0, np.nan)

        self.df["squeeze_on"] = (self.df["bb_lower"] > self.df["kc_lower"]) & (self.df["bb_upper"] < self.df["kc_upper"])
        mid = (high.rolling(20).max() + low.rolling(20).min()) / 2
        self.df["squeeze_mom"] = close - (mid + mean_20) / 2

    def detect_regime(self) -> RegimeData:
        row = self.df.iloc[-1]
        adx = row.get("adx", 0) or 0
        plus_di = row.get("adx_plus_di", 0) or 0
        minus_di = row.get("adx_minus_di", 0) or 0
        bb_width = row.get("bb_width", 0) or 0
        atr_pct = row.get("atr_pct", 0) or 0

        bb_widths = self.df["bb_width"].dropna()
        bb_width_pctile = 50.0
        if len(bb_widths) > 10:
            bb_width_pctile = float((bb_widths < bb_width).sum() / len(bb_widths) * 100)

        atr_pcts = self.df["atr_pct"].dropna()
        atr_pctile = 50.0
        if len(atr_pcts) > 10:
            atr_pctile = float((atr_pcts < atr_pct).sum() / len(atr_pcts) * 100)

        kc_width = 0.0
        if row.get("kc_upper") and row.get("kc_lower") and row.get("kc_middle"):
            kc_width = (row["kc_upper"] - row["kc_lower"]) / row["kc_middle"] if row["kc_middle"] > 0 else 0

        trend_strength = adx / 100.0

        close_changes = self.df["close"].pct_change().tail(20).dropna()
        direction_changes = 0
        if len(close_changes) > 1:
            signs = np.sign(close_changes.values)
            direction_changes = int(np.sum(np.abs(np.diff(signs)) > 0))

        if atr_pctile > 90 and direction_changes > 14:
            regime = MarketRegime.CHAOTIC
            vol_level = "extreme"
            confidence = min(atr_pctile / 100, 0.95)
        elif atr_pctile > 80 and bb_width_pctile > 80:
            regime = MarketRegime.VOLATILE
            vol_level = "high"
            confidence = min((atr_pctile + bb_width_pctile) / 200, 0.95)
        elif adx >= 40 and plus_di > minus_di:
            regime = MarketRegime.STRONG_TREND_UP
            vol_level = "moderate"
            confidence = min(adx / 60, 0.95)
        elif adx >= 40 and minus_di > plus_di:
            regime = MarketRegime.STRONG_TREND_DOWN
            vol_level = "moderate"
            confidence = min(adx / 60, 0.95)
        elif adx >= 25 and plus_di > minus_di:
            regime = MarketRegime.TREND_UP
            vol_level = "moderate"
            confidence = min(adx / 50, 0.9)
        elif adx >= 25 and minus_di > plus_di:
            regime = MarketRegime.TREND_DOWN
            vol_level = "moderate"
            confidence = min(adx / 50, 0.9)
        elif adx < 20 and bb_width_pctile < 40:
            regime = MarketRegime.RANGING
            vol_level = "low"
            confidence = min((100 - adx) / 100 * (100 - bb_width_pctile) / 100, 0.9)
        elif adx < 25:
            regime = MarketRegime.RANGING
            vol_level = "low"
            confidence = 0.5
        else:
            regime = MarketRegime.VOLATILE
            vol_level = "moderate"
            confidence = 0.4

        return RegimeData(
            regime=regime,
            adx=round(adx, 2),
            adx_plus_di=round(plus_di, 2),
            adx_minus_di=round(minus_di, 2),
            bb_width=round(bb_width, 4),
            bb_width_percentile=round(bb_width_pctile, 1),
            atr_pct=round(atr_pct, 4),
            atr_percentile=round(atr_pctile, 1),
            keltner_width=round(kc_width, 4),
            regime_confidence=round(confidence, 3),
            trend_strength=round(trend_strength, 3),
            volatility_level=vol_level,
        )

    def get_rsi_signal(self) -> tuple[float, str]:
        rsi = self.df["rsi"].iloc[-1]
        if pd.isna(rsi):
            return 50.0, "neutral"
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
        if pd.isna(macd_diff) or pd.isna(prev_diff):
            return "neutral"
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
        if pd.isna(upper) or pd.isna(lower):
            return "neutral"
        if close <= lower:
            return "oversold"
        elif close >= upper:
            return "overbought"
        return "neutral"

    def get_ema_trend(self) -> str:
        row = self.df.iloc[-1]
        e9, e21, e50 = row.get("ema_9"), row.get("ema_21"), row.get("ema_50")
        if pd.isna(e9) or pd.isna(e21) or pd.isna(e50):
            return "neutral"
        if e9 > e21 > e50:
            return "strong_bullish"
        elif e9 > e21:
            return "bullish"
        elif e9 < e21 < e50:
            return "strong_bearish"
        elif e9 < e21:
            return "bearish"
        return "neutral"

    def get_volume_trend(self) -> str:
        vol = self.df["volume"].iloc[-1]
        avg = self.df["volume_sma"].iloc[-1]
        if pd.isna(avg) or avg <= 0:
            return "normal"
        ratio = vol / avg
        if ratio > 2.0:
            return "very_high"
        elif ratio > 1.5:
            return "high"
        elif ratio < 0.5:
            return "low"
        return "normal"

    def get_support_resistance(self, lookback: int = 50) -> tuple[float, float]:
        recent = self.df.tail(lookback)
        support = recent["low"].min()
        resistance = recent["high"].max()
        return support, resistance

    def get_pivot_sr(self, lookback: int = 20) -> tuple[float, float]:
        recent = self.df.tail(lookback)
        highs = recent["high"].values
        lows = recent["low"].values
        closes = recent["close"].values

        pivot_levels = []
        for i in range(2, len(highs) - 2):
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                pivot_levels.append(("R", highs[i]))
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                pivot_levels.append(("S", lows[i]))

        current = closes[-1]
        supports = sorted([p[1] for p in pivot_levels if p[0] == "S" and p[1] < current], reverse=True)
        resistances = sorted([p[1] for p in pivot_levels if p[0] == "R" and p[1] > current])
        nearest_s = supports[0] if supports else recent["low"].min()
        nearest_r = resistances[0] if resistances else recent["high"].max()
        return nearest_s, nearest_r

    def get_sr_proximity(self) -> str:
        row = self.df.iloc[-1]
        close = row["close"]
        support, resistance = self.get_pivot_sr()
        if resistance == support:
            return "middle"
        position = (close - support) / (resistance - support)
        if position < 0.2:
            return "near_support"
        elif position > 0.8:
            return "near_resistance"
        return "middle"

    def get_trend_consistency(self, lookback: int = 10) -> float:
        changes = self.df["close"].pct_change().tail(lookback).dropna()
        if len(changes) < 2:
            return 0.0
        positive = (changes > 0).sum()
        return abs(positive / len(changes) - 0.5) * 2.0

    def get_candle_strength(self) -> str:
        row = self.df.iloc[-1]
        body = abs(row["close"] - row["open"])
        total_range = row["high"] - row["low"]
        if total_range <= 0:
            return "neutral"
        body_pct = body / total_range
        avg_range = (self.df["high"] - self.df["low"]).rolling(20).mean().iloc[-1]
        if pd.isna(avg_range) or avg_range <= 0:
            return "neutral"
        size_ratio = total_range / avg_range
        if size_ratio >= 2.0 and body_pct >= 0.6:
            return "strong"
        elif size_ratio >= 1.5 and body_pct >= 0.5:
            return "moderate"
        elif size_ratio < 0.5:
            return "weak"
        return "neutral"

    def get_obv_trend(self) -> str:
        obv = self.df["obv"].iloc[-1]
        obv_ema = self.df["obv_ema"].iloc[-1]
        if pd.isna(obv) or pd.isna(obv_ema):
            return "neutral"
        if obv > obv_ema * 1.02:
            return "bullish"
        elif obv < obv_ema * 0.98:
            return "bearish"
        return "neutral"

    def get_psar_direction(self) -> str:
        row = self.df.iloc[-1]
        psar_up = row.get("psar_up")
        psar_down = row.get("psar_down")
        if not pd.isna(psar_up) and pd.isna(psar_down):
            return "bullish"
        elif pd.isna(psar_up) and not pd.isna(psar_down):
            return "bearish"
        return "neutral"

    def get_vortex_signal(self) -> str:
        row = self.df.iloc[-1]
        vp = row.get("vortex_pos")
        vn = row.get("vortex_neg")
        if pd.isna(vp) or pd.isna(vn):
            return "neutral"
        if vp > vn and vp > 1.0:
            return "bullish"
        elif vn > vp and vn > 1.0:
            return "bearish"
        return "neutral"

    def get_keltner_signal(self) -> str:
        row = self.df.iloc[-1]
        close = row["close"]
        kc_upper = row.get("kc_upper")
        kc_lower = row.get("kc_lower")
        if pd.isna(kc_upper) or pd.isna(kc_lower):
            return "neutral"
        if close >= kc_upper:
            return "overbought"
        elif close <= kc_lower:
            return "oversold"
        return "neutral"

    def get_stoch_rsi_signal(self) -> tuple[float, float, str]:
        row = self.df.iloc[-1]
        k = row.get("stoch_rsi_k", 50)
        d = row.get("stoch_rsi_d", 50)
        if pd.isna(k):
            k = 50.0
        if pd.isna(d):
            d = 50.0
        if k < 20 and d < 20:
            return k, d, "oversold"
        elif k > 80 and d > 80:
            return k, d, "overbought"
        elif k < 20:
            return k, d, "approaching_oversold"
        elif k > 80:
            return k, d, "approaching_overbought"
        return k, d, "neutral"

    def _bb_squeeze_active(self) -> bool:
        row = self.df.iloc[-1]
        bb_upper = row.get("bb_upper")
        bb_lower = row.get("bb_lower")
        kc_upper = row.get("kc_upper")
        kc_lower = row.get("kc_lower")
        if pd.isna(bb_upper) or pd.isna(kc_upper):
            return False
        return bb_lower > kc_lower and bb_upper < kc_upper

    def analyze(self) -> SignalResult:
        rsi, rsi_signal = self.get_rsi_signal()
        macd_signal = self.get_macd_signal()
        bb_signal = self.get_bollinger_signal()
        ema_trend = self.get_ema_trend()
        vol_trend = self.get_volume_trend()
        atr = self.df["atr"].iloc[-1]
        if pd.isna(atr):
            atr = 0.0
        support, resistance = self.get_support_resistance()

        regime = self.detect_regime()

        row = self.df.iloc[-1]
        adx_val = row.get("adx", 0) or 0
        plus_di = row.get("adx_plus_di", 0) or 0
        minus_di = row.get("adx_minus_di", 0) or 0
        bb_width = row.get("bb_width", 0) or 0
        stoch_rsi_k, stoch_rsi_d, _ = self.get_stoch_rsi_signal()
        williams_r = row.get("williams_r", -50) or -50
        mfi = row.get("mfi", 50) or 50
        stoch_k = row.get("stoch_k", 50) or 50
        stoch_d = row.get("stoch_d", 50) or 50
        obv_trend = self.get_obv_trend()
        psar_dir = self.get_psar_direction()
        vortex_sig = self.get_vortex_signal()
        keltner_sig = self.get_keltner_signal()
        cmf = row.get("cmf", 0) or 0

        bullish_points = 0.0
        bearish_points = 0.0
        confirmations = []

        if rsi_signal == "oversold":
            bullish_points += 1.5
            confirmations.append("RSI oversold (<30)")
        elif rsi_signal == "overbought":
            bearish_points += 1.5
            confirmations.append("RSI overbought (>70)")
        elif rsi_signal == "approaching_oversold":
            bullish_points += 0.5
        elif rsi_signal == "approaching_overbought":
            bearish_points += 0.5

        if macd_signal == "bullish_crossover":
            bullish_points += 2.0
            confirmations.append("MACD bullish crossover")
        elif macd_signal == "bearish_crossover":
            bearish_points += 2.0
            confirmations.append("MACD bearish crossover")
        elif macd_signal == "bullish":
            bullish_points += 0.5
        elif macd_signal == "bearish":
            bearish_points += 0.5

        if bb_signal == "oversold":
            bullish_points += 1.0
            confirmations.append("Price at lower Bollinger Band")
        elif bb_signal == "overbought":
            bearish_points += 1.0
            confirmations.append("Price at upper Bollinger Band")

        if ema_trend == "strong_bullish":
            bullish_points += 2.0
            confirmations.append("EMA(9>21>50) strong bullish alignment")
        elif ema_trend == "bullish":
            bullish_points += 1.0
            confirmations.append("EMA(9>21) bullish")
        elif ema_trend == "strong_bearish":
            bearish_points += 2.0
            confirmations.append("EMA(9<21<50) strong bearish alignment")
        elif ema_trend == "bearish":
            bearish_points += 1.0
            confirmations.append("EMA(9<21) bearish")

        if vol_trend in ("high", "very_high"):
            confirmations.append(f"Volume {vol_trend} (confirms momentum)")

        if adx_val >= 25:
            if plus_di > minus_di:
                bullish_points += 1.5
                confirmations.append(f"ADX {adx_val:.0f} trending up (+DI>{'-'}DI)")
            else:
                bearish_points += 1.5
                confirmations.append(f"ADX {adx_val:.0f} trending down ({'-'}DI>+DI)")

        if psar_dir == "bullish":
            bullish_points += 1.0
            confirmations.append("PSAR bullish (dots below price)")
        elif psar_dir == "bearish":
            bearish_points += 1.0
            confirmations.append("PSAR bearish (dots above price)")

        if vortex_sig == "bullish":
            bullish_points += 0.75
            confirmations.append("Vortex bullish (VI+ > VI-)")
        elif vortex_sig == "bearish":
            bearish_points += 0.75
            confirmations.append("Vortex bearish (VI- > VI+)")

        if obv_trend == "bullish":
            bullish_points += 0.75
            confirmations.append("OBV rising (accumulation)")
        elif obv_trend == "bearish":
            bearish_points += 0.75
            confirmations.append("OBV falling (distribution)")

        if mfi < 20:
            bullish_points += 1.0
            confirmations.append("MFI oversold (<20)")
        elif mfi > 80:
            bearish_points += 1.0
            confirmations.append("MFI overbought (>80)")

        if williams_r < -80:
            bullish_points += 0.5
            confirmations.append("Williams %R oversold")
        elif williams_r > -20:
            bearish_points += 0.5
            confirmations.append("Williams %R overbought")

        zscore = row.get("zscore", 0) or 0
        vwap_val = row.get("vwap", 0) or 0
        squeeze_active = bool(row.get("squeeze_on", False))
        squeeze_mom = row.get("squeeze_mom", 0) or 0

        current_close = row["close"]
        vwap_signal = "neutral"
        if vwap_val > 0:
            if current_close > vwap_val * 1.005:
                vwap_signal = "above"
            elif current_close < vwap_val * 0.995:
                vwap_signal = "below"

        pivot_s, pivot_r = self.get_pivot_sr()
        sr_prox = self.get_sr_proximity()
        trend_cons = self.get_trend_consistency()
        candle_str = self.get_candle_strength()

        if zscore < -2.0:
            bullish_points += 1.0
            confirmations.append(f"Z-score extreme low ({zscore:.2f})")
        elif zscore > 2.0:
            bearish_points += 1.0
            confirmations.append(f"Z-score extreme high ({zscore:.2f})")

        if vwap_signal == "above":
            bullish_points += 0.5
            confirmations.append("Price above VWAP")
        elif vwap_signal == "below":
            bearish_points += 0.5
            confirmations.append("Price below VWAP")

        if squeeze_active:
            confirmations.append("BB squeeze active (breakout imminent)")
            if squeeze_mom > 0:
                bullish_points += 0.75
                confirmations.append("Squeeze momentum bullish")
            elif squeeze_mom < 0:
                bearish_points += 0.75
                confirmations.append("Squeeze momentum bearish")

        if sr_prox == "near_support":
            bullish_points += 0.5
            confirmations.append("Near pivot support")
        elif sr_prox == "near_resistance":
            bearish_points += 0.5
            confirmations.append("Near pivot resistance")

        if candle_str == "strong":
            confirmations.append("Strong candle (2x avg range)")

        srsi_k, srsi_d, srsi_sig = self.get_stoch_rsi_signal()
        if srsi_sig == "oversold":
            bullish_points += 0.75
            confirmations.append("StochRSI oversold")
        elif srsi_sig == "overbought":
            bearish_points += 0.75
            confirmations.append("StochRSI overbought")

        if stoch_k < 20 and stoch_d < 20:
            bullish_points += 0.5
        elif stoch_k > 80 and stoch_d > 80:
            bearish_points += 0.5

        if keltner_sig == "oversold":
            bullish_points += 0.75
            confirmations.append("Price below Keltner Channel")
        elif keltner_sig == "overbought":
            bearish_points += 0.75
            confirmations.append("Price above Keltner Channel")

        if cmf > 0.1:
            bullish_points += 0.5
            confirmations.append("Chaikin MF positive (buying pressure)")
        elif cmf < -0.1:
            bearish_points += 0.5
            confirmations.append("Chaikin MF negative (selling pressure)")

        if vol_trend in ("high", "very_high"):
            net = bullish_points - bearish_points
            if net > 0:
                bullish_points += 0.5
            elif net < 0:
                bearish_points += 0.5

        total_possible = 18.0
        net = bullish_points - bearish_points
        confidence = min(abs(net) / total_possible, 1.0)

        if net >= 4:
            overall = "strong_buy"
        elif net >= 2:
            overall = "buy"
        elif net <= -4:
            overall = "strong_sell"
        elif net <= -2:
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
            regime=regime,
            adx=adx_val,
            adx_plus_di=plus_di,
            adx_minus_di=minus_di,
            bb_width=bb_width,
            stoch_rsi_k=stoch_rsi_k,
            stoch_rsi_d=stoch_rsi_d,
            williams_r=williams_r,
            mfi=mfi,
            obv_trend=obv_trend,
            psar_direction=psar_dir,
            vortex_signal=vortex_sig,
            keltner_signal=keltner_sig,
            stoch_k=stoch_k,
            stoch_d=stoch_d,
            confirmation_score=max(bullish_points, bearish_points),
            required_score=0.0,
            confirmations=confirmations,
            zscore=round(zscore, 3),
            vwap=round(vwap_val, 8),
            vwap_signal=vwap_signal,
            squeeze_on=squeeze_active,
            squeeze_momentum=round(squeeze_mom, 8),
            cmf=round(cmf, 4),
            pivot_support=round(pivot_s, 8),
            pivot_resistance=round(pivot_r, 8),
            sr_proximity=sr_prox,
            trend_consistency=round(trend_cons, 3),
            candle_strength=candle_str,
        )
