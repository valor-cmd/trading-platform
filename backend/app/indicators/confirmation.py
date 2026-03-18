import logging
from dataclasses import dataclass
from typing import Optional

from app.indicators.technical import SignalResult, MarketRegime

logger = logging.getLogger(__name__)


@dataclass
class ConfirmationResult:
    approved: bool
    score: float
    required_score: float
    regime: str
    side: str
    confirmations: list
    rejection_reason: Optional[str] = None
    strategy_notes: str = ""


REGIME_MIN_SCORES = {
    "scalper": {
        MarketRegime.STRONG_TREND_UP: 5.0,
        MarketRegime.TREND_UP: 5.5,
        MarketRegime.TREND_DOWN: 5.5,
        MarketRegime.STRONG_TREND_DOWN: 5.0,
        MarketRegime.RANGING: 4.5,
        MarketRegime.VOLATILE: 6.0,
        MarketRegime.CHAOTIC: 99.0,
    },
    "swing": {
        MarketRegime.STRONG_TREND_UP: 5.0,
        MarketRegime.TREND_UP: 5.5,
        MarketRegime.TREND_DOWN: 5.5,
        MarketRegime.STRONG_TREND_DOWN: 5.0,
        MarketRegime.RANGING: 6.5,
        MarketRegime.VOLATILE: 6.0,
        MarketRegime.CHAOTIC: 99.0,
    },
    "long_term": {
        MarketRegime.STRONG_TREND_UP: 5.5,
        MarketRegime.TREND_UP: 6.0,
        MarketRegime.TREND_DOWN: 6.0,
        MarketRegime.STRONG_TREND_DOWN: 5.5,
        MarketRegime.RANGING: 7.0,
        MarketRegime.VOLATILE: 6.5,
        MarketRegime.CHAOTIC: 99.0,
    },
    "grid": {
        MarketRegime.STRONG_TREND_UP: 99.0,
        MarketRegime.TREND_UP: 99.0,
        MarketRegime.TREND_DOWN: 99.0,
        MarketRegime.STRONG_TREND_DOWN: 99.0,
        MarketRegime.RANGING: 3.0,
        MarketRegime.VOLATILE: 3.5,
        MarketRegime.CHAOTIC: 99.0,
    },
    "mean_reversion": {
        MarketRegime.STRONG_TREND_UP: 6.0,
        MarketRegime.TREND_UP: 5.0,
        MarketRegime.TREND_DOWN: 5.0,
        MarketRegime.STRONG_TREND_DOWN: 6.0,
        MarketRegime.RANGING: 4.0,
        MarketRegime.VOLATILE: 5.0,
        MarketRegime.CHAOTIC: 99.0,
    },
    "momentum": {
        MarketRegime.STRONG_TREND_UP: 4.5,
        MarketRegime.TREND_UP: 5.0,
        MarketRegime.TREND_DOWN: 5.0,
        MarketRegime.STRONG_TREND_DOWN: 4.5,
        MarketRegime.RANGING: 99.0,
        MarketRegime.VOLATILE: 5.5,
        MarketRegime.CHAOTIC: 99.0,
    },
    "dca": {
        MarketRegime.STRONG_TREND_UP: 3.0,
        MarketRegime.TREND_UP: 3.0,
        MarketRegime.TREND_DOWN: 3.5,
        MarketRegime.STRONG_TREND_DOWN: 4.0,
        MarketRegime.RANGING: 3.0,
        MarketRegime.VOLATILE: 4.0,
        MarketRegime.CHAOTIC: 99.0,
    },
}

MIN_CONFIRMATIONS = {
    "scalper": 3,
    "swing": 4,
    "long_term": 5,
    "grid": 2,
    "mean_reversion": 3,
    "momentum": 3,
    "dca": 2,
}


def _score_scalper(signal: SignalResult, side: str, confs: list) -> float:
    s = 0.0
    if side == "buy":
        if signal.rsi_signal == "oversold":
            s += 2.5; confs.append("RSI oversold")
        elif signal.rsi_signal == "approaching_oversold":
            s += 0.5
        if signal.stoch_rsi_k < 15:
            s += 2.0; confs.append(f"StochRSI extreme low {signal.stoch_rsi_k:.0f}")
        elif signal.stoch_rsi_k < 25:
            s += 1.0
        if signal.bollinger_signal == "oversold":
            s += 1.5; confs.append("BB oversold")
        if signal.mfi < 20:
            s += 1.5; confs.append("MFI extreme low")
        elif signal.mfi < 35:
            s += 0.5
        if signal.williams_r < -85:
            s += 1.0; confs.append("Williams %R extreme")
        if signal.keltner_signal == "oversold":
            s += 1.0; confs.append("Keltner oversold")
        if signal.macd_signal == "bullish_crossover":
            s += 1.0; confs.append("MACD bull cross")
    else:
        if signal.rsi_signal == "overbought":
            s += 2.5; confs.append("RSI overbought")
        elif signal.rsi_signal == "approaching_overbought":
            s += 0.5
        if signal.stoch_rsi_k > 85:
            s += 2.0; confs.append(f"StochRSI extreme high {signal.stoch_rsi_k:.0f}")
        elif signal.stoch_rsi_k > 75:
            s += 1.0
        if signal.bollinger_signal == "overbought":
            s += 1.5; confs.append("BB overbought")
        if signal.mfi > 80:
            s += 1.5; confs.append("MFI extreme high")
        elif signal.mfi > 65:
            s += 0.5
        if signal.williams_r > -15:
            s += 1.0; confs.append("Williams %R extreme")
        if signal.keltner_signal == "overbought":
            s += 1.0; confs.append("Keltner overbought")
        if signal.macd_signal == "bearish_crossover":
            s += 1.0; confs.append("MACD bear cross")
    if signal.volume_trend in ("high", "very_high"):
        s += 1.0; confs.append(f"Volume {signal.volume_trend}")
    return s


def _score_swing(signal: SignalResult, side: str, confs: list) -> float:
    s = 0.0
    if side == "buy":
        if signal.ema_trend == "strong_bullish":
            s += 2.5; confs.append("Strong bullish EMA trend")
        elif signal.ema_trend == "bullish":
            s += 1.5; confs.append("Bullish EMA trend")
        if signal.macd_signal == "bullish_crossover":
            s += 2.5; confs.append("MACD bullish crossover")
        elif signal.macd_signal == "bullish":
            s += 0.75
        if signal.adx >= 25 and signal.adx_plus_di > signal.adx_minus_di:
            s += 2.0; confs.append(f"ADX {signal.adx:.0f} with +DI leading")
        elif signal.adx >= 20:
            s += 0.5
        if signal.psar_direction == "bullish":
            s += 1.0; confs.append("PSAR bullish")
        if signal.vortex_signal == "bullish":
            s += 1.0; confs.append("Vortex bullish")
        if signal.obv_trend == "bullish":
            s += 1.0; confs.append("OBV accumulation")
        if signal.rsi_signal == "oversold":
            s += 0.75
    else:
        if signal.ema_trend == "strong_bearish":
            s += 2.5; confs.append("Strong bearish EMA trend")
        elif signal.ema_trend == "bearish":
            s += 1.5; confs.append("Bearish EMA trend")
        if signal.macd_signal == "bearish_crossover":
            s += 2.5; confs.append("MACD bearish crossover")
        elif signal.macd_signal == "bearish":
            s += 0.75
        if signal.adx >= 25 and signal.adx_minus_di > signal.adx_plus_di:
            s += 2.0; confs.append(f"ADX {signal.adx:.0f} with -DI leading")
        elif signal.adx >= 20:
            s += 0.5
        if signal.psar_direction == "bearish":
            s += 1.0; confs.append("PSAR bearish")
        if signal.vortex_signal == "bearish":
            s += 1.0; confs.append("Vortex bearish")
        if signal.obv_trend == "bearish":
            s += 1.0; confs.append("OBV distribution")
        if signal.rsi_signal == "overbought":
            s += 0.75
    if signal.volume_trend in ("high", "very_high"):
        s += 0.5; confs.append(f"Volume {signal.volume_trend}")
    return s


def _score_long_term(signal: SignalResult, side: str, confs: list) -> float:
    s = 0.0
    if side == "buy":
        if signal.ema_trend == "strong_bullish":
            s += 3.0; confs.append("Strong bullish macro trend")
        elif signal.ema_trend == "bullish":
            s += 1.5; confs.append("Bullish macro trend")
        else:
            s -= 2.0
        if signal.adx >= 30:
            s += 2.0; confs.append(f"Strong trend ADX={signal.adx:.0f}")
        elif signal.adx >= 25:
            s += 1.0
        else:
            s -= 1.0
        if signal.rsi_signal == "oversold" and signal.macd_signal in ("bullish", "bullish_crossover"):
            s += 2.0; confs.append("RSI oversold + MACD bullish convergence")
        if signal.macd_signal == "bullish_crossover":
            s += 1.5; confs.append("MACD bullish crossover")
        if signal.obv_trend == "bullish":
            s += 1.5; confs.append("OBV long-term accumulation")
        if signal.psar_direction == "bullish" and signal.vortex_signal == "bullish":
            s += 1.0; confs.append("PSAR+Vortex aligned bullish")
    else:
        if signal.ema_trend == "strong_bearish":
            s += 3.0; confs.append("Strong bearish macro trend")
        elif signal.ema_trend == "bearish":
            s += 1.5; confs.append("Bearish macro trend")
        else:
            s -= 2.0
        if signal.adx >= 30:
            s += 2.0; confs.append(f"Strong trend ADX={signal.adx:.0f}")
        elif signal.adx >= 25:
            s += 1.0
        else:
            s -= 1.0
        if signal.rsi_signal == "overbought" and signal.macd_signal in ("bearish", "bearish_crossover"):
            s += 2.0; confs.append("RSI overbought + MACD bearish convergence")
        if signal.macd_signal == "bearish_crossover":
            s += 1.5; confs.append("MACD bearish crossover")
        if signal.obv_trend == "bearish":
            s += 1.5; confs.append("OBV long-term distribution")
        if signal.psar_direction == "bearish" and signal.vortex_signal == "bearish":
            s += 1.0; confs.append("PSAR+Vortex aligned bearish")
    return s


def evaluate_confirmation(
    bot_type: str,
    signal: SignalResult,
    sentiment: dict,
    side: str,
) -> ConfirmationResult:
    regime = signal.regime
    if not regime:
        return ConfirmationResult(
            approved=False, score=0, required_score=0,
            regime="unknown", side=side, confirmations=[],
            rejection_reason="No regime data available",
        )

    if regime.regime == MarketRegime.CHAOTIC:
        return ConfirmationResult(
            approved=False, score=signal.confirmation_score,
            required_score=99, regime=regime.regime.value, side=side,
            confirmations=signal.confirmations,
            rejection_reason="Market is chaotic — no trading",
            strategy_notes="Chaotic regime detected: high volatility with rapid direction changes. Sitting out.",
        )

    scores = REGIME_MIN_SCORES.get(bot_type, REGIME_MIN_SCORES["swing"])
    required = scores.get(regime.regime, 5.0)

    if regime.regime == MarketRegime.VOLATILE:
        required += 0.5

    bullish_confirmations = []
    bearish_confirmations = []
    for c in signal.confirmations:
        c_lower = c.lower()
        if any(w in c_lower for w in ["bullish", "oversold", "rising", "accumulation", "buying", "below"]):
            bullish_confirmations.append(c)
        elif any(w in c_lower for w in ["bearish", "overbought", "falling", "distribution", "selling", "above"]):
            bearish_confirmations.append(c)
        else:
            bullish_confirmations.append(c)
            bearish_confirmations.append(c)

    if side == "buy":
        relevant_confirmations = bullish_confirmations
    else:
        relevant_confirmations = bearish_confirmations

    if bot_type == "scalper":
        directional_score = _score_scalper(signal, side, relevant_confirmations)
    elif bot_type == "swing":
        directional_score = _score_swing(signal, side, relevant_confirmations)
    elif bot_type in ("mean_reversion", "grid"):
        directional_score = _score_scalper(signal, side, relevant_confirmations)
    elif bot_type == "momentum":
        directional_score = _score_swing(signal, side, relevant_confirmations)
    elif bot_type == "dca":
        directional_score = _score_long_term(signal, side, relevant_confirmations)
    else:
        directional_score = _score_long_term(signal, side, relevant_confirmations)

    sentiment_bias = sentiment.get("bias", "neutral")
    sentiment_weight = sentiment.get("weight", 0)
    if bot_type == "long_term":
        if side == "buy" and sentiment_bias in ("contrarian_buy", "lean_buy"):
            directional_score += sentiment_weight * 3.0
            relevant_confirmations.append(f"Sentiment {sentiment_bias} (weight={sentiment_weight:.1f})")
        elif side == "sell" and sentiment_bias in ("contrarian_sell", "lean_sell"):
            directional_score += sentiment_weight * 3.0
            relevant_confirmations.append(f"Sentiment {sentiment_bias} (weight={sentiment_weight:.1f})")
    elif bot_type == "swing":
        if side == "buy" and sentiment_bias in ("contrarian_buy", "lean_buy"):
            directional_score += sentiment_weight * 1.0
            relevant_confirmations.append(f"Sentiment {sentiment_bias}")
        elif side == "sell" and sentiment_bias in ("contrarian_sell", "lean_sell"):
            directional_score += sentiment_weight * 1.0
            relevant_confirmations.append(f"Sentiment {sentiment_bias}")

    regime_str = regime.regime.value
    ranging = regime.regime == MarketRegime.RANGING

    if ranging and bot_type in ("swing", "long_term"):
        required += 1.0

    min_confs = MIN_CONFIRMATIONS.get(bot_type, 3)
    has_enough_confirmations = len(relevant_confirmations) >= min_confs

    contradiction = False
    if side == "buy":
        if signal.ema_trend in ("strong_bearish",) and signal.adx >= 30:
            contradiction = True
        if signal.psar_direction == "bearish" and signal.vortex_signal == "bearish" and signal.obv_trend == "bearish":
            contradiction = True
    else:
        if signal.ema_trend in ("strong_bullish",) and signal.adx >= 30:
            contradiction = True
        if signal.psar_direction == "bullish" and signal.vortex_signal == "bullish" and signal.obv_trend == "bullish":
            contradiction = True

    if contradiction:
        return ConfirmationResult(
            approved=False, score=directional_score,
            required_score=required, regime=regime_str, side=side,
            confirmations=relevant_confirmations,
            rejection_reason="Major contradictory signals detected",
            strategy_notes=f"Regime: {regime_str}, but strong opposing trend indicators block {side}",
        )

    approved = directional_score >= required and has_enough_confirmations

    if not approved:
        reasons = []
        if directional_score < required:
            reasons.append(f"Score {directional_score:.1f} < required {required:.1f}")
        if not has_enough_confirmations:
            reasons.append(f"Only {len(relevant_confirmations)} confirmations (need {min_confs})")
        rejection = "; ".join(reasons)
    else:
        rejection = None

    strategy_notes = (
        f"Regime: {regime_str} (ADX={regime.adx}, BB_width_pctile={regime.bb_width_percentile}%, "
        f"ATR_pctile={regime.atr_percentile}%). "
        f"Score: {directional_score:.1f}/{required:.1f} with {len(relevant_confirmations)} confirmations."
    )

    return ConfirmationResult(
        approved=approved,
        score=round(directional_score, 2),
        required_score=round(required, 2),
        regime=regime_str,
        side=side,
        confirmations=relevant_confirmations,
        rejection_reason=rejection,
        strategy_notes=strategy_notes,
    )
