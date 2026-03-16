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
        MarketRegime.STRONG_TREND_UP: 4.0,
        MarketRegime.TREND_UP: 4.5,
        MarketRegime.TREND_DOWN: 4.5,
        MarketRegime.STRONG_TREND_DOWN: 4.0,
        MarketRegime.RANGING: 5.0,
        MarketRegime.VOLATILE: 5.5,
        MarketRegime.CHAOTIC: 99.0,
    },
    "swing": {
        MarketRegime.STRONG_TREND_UP: 3.5,
        MarketRegime.TREND_UP: 4.0,
        MarketRegime.TREND_DOWN: 4.0,
        MarketRegime.STRONG_TREND_DOWN: 3.5,
        MarketRegime.RANGING: 5.0,
        MarketRegime.VOLATILE: 5.5,
        MarketRegime.CHAOTIC: 99.0,
    },
    "long_term": {
        MarketRegime.STRONG_TREND_UP: 3.0,
        MarketRegime.TREND_UP: 3.5,
        MarketRegime.TREND_DOWN: 3.5,
        MarketRegime.STRONG_TREND_DOWN: 3.0,
        MarketRegime.RANGING: 4.5,
        MarketRegime.VOLATILE: 5.0,
        MarketRegime.CHAOTIC: 99.0,
    },
}

MIN_CONFIRMATIONS = {
    "scalper": 3,
    "swing": 3,
    "long_term": 3,
}


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

    directional_score = 0.0
    if side == "buy":
        if signal.rsi_signal in ("oversold",):
            directional_score += 1.5
        elif signal.rsi_signal == "approaching_oversold":
            directional_score += 0.5
        if signal.macd_signal == "bullish_crossover":
            directional_score += 2.0
        elif signal.macd_signal == "bullish":
            directional_score += 0.5
        if signal.bollinger_signal == "oversold":
            directional_score += 1.0
        if signal.ema_trend in ("strong_bullish",):
            directional_score += 2.0
        elif signal.ema_trend == "bullish":
            directional_score += 1.0
        if signal.adx >= 25 and signal.adx_plus_di > signal.adx_minus_di:
            directional_score += 1.5
        if signal.psar_direction == "bullish":
            directional_score += 1.0
        if signal.vortex_signal == "bullish":
            directional_score += 0.75
        if signal.obv_trend == "bullish":
            directional_score += 0.75
        if signal.mfi < 20:
            directional_score += 1.0
        elif signal.mfi < 40:
            directional_score += 0.25
        if signal.williams_r < -80:
            directional_score += 0.5
        if signal.stoch_rsi_k < 20:
            directional_score += 0.75
        if signal.keltner_signal == "oversold":
            directional_score += 0.75
    else:
        if signal.rsi_signal in ("overbought",):
            directional_score += 1.5
        elif signal.rsi_signal == "approaching_overbought":
            directional_score += 0.5
        if signal.macd_signal == "bearish_crossover":
            directional_score += 2.0
        elif signal.macd_signal == "bearish":
            directional_score += 0.5
        if signal.bollinger_signal == "overbought":
            directional_score += 1.0
        if signal.ema_trend in ("strong_bearish",):
            directional_score += 2.0
        elif signal.ema_trend == "bearish":
            directional_score += 1.0
        if signal.adx >= 25 and signal.adx_minus_di > signal.adx_plus_di:
            directional_score += 1.5
        if signal.psar_direction == "bearish":
            directional_score += 1.0
        if signal.vortex_signal == "bearish":
            directional_score += 0.75
        if signal.obv_trend == "bearish":
            directional_score += 0.75
        if signal.mfi > 80:
            directional_score += 1.0
        elif signal.mfi > 60:
            directional_score += 0.25
        if signal.williams_r > -20:
            directional_score += 0.5
        if signal.stoch_rsi_k > 80:
            directional_score += 0.75
        if signal.keltner_signal == "overbought":
            directional_score += 0.75

    if signal.volume_trend in ("high", "very_high"):
        directional_score += 0.5
        relevant_confirmations.append(f"Volume {signal.volume_trend}")

    sentiment_bias = sentiment.get("bias", "neutral")
    sentiment_weight = sentiment.get("weight", 0)
    if bot_type in ("swing", "long_term"):
        if side == "buy" and sentiment_bias in ("contrarian_buy", "lean_buy"):
            directional_score += sentiment_weight * (2.0 if bot_type == "long_term" else 1.0)
            relevant_confirmations.append(f"Sentiment {sentiment_bias} (weight={sentiment_weight:.1f})")
        elif side == "sell" and sentiment_bias in ("contrarian_sell", "lean_sell"):
            directional_score += sentiment_weight * (2.0 if bot_type == "long_term" else 1.0)
            relevant_confirmations.append(f"Sentiment {sentiment_bias} (weight={sentiment_weight:.1f})")

    regime_str = regime.regime.value
    trending = regime.regime in (
        MarketRegime.STRONG_TREND_UP, MarketRegime.TREND_UP,
        MarketRegime.STRONG_TREND_DOWN, MarketRegime.TREND_DOWN,
    )
    ranging = regime.regime == MarketRegime.RANGING

    if trending and bot_type == "scalper":
        if (side == "buy" and regime.regime in (MarketRegime.STRONG_TREND_UP, MarketRegime.TREND_UP)):
            directional_score += 0.5
        elif (side == "sell" and regime.regime in (MarketRegime.STRONG_TREND_DOWN, MarketRegime.TREND_DOWN)):
            directional_score += 0.5

    if ranging and bot_type == "scalper":
        if signal.bollinger_signal in ("oversold", "overbought"):
            directional_score += 0.5

    if ranging and bot_type in ("swing", "long_term"):
        required += 0.5

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
