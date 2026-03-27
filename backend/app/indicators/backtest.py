import logging
import time
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from app.indicators.technical import TechnicalAnalyzer, SignalResult

logger = logging.getLogger(__name__)

MIN_LOOKBACK_BARS = 100
MAX_LOOKBACK_BARS = 500
MIN_SIMULATED_TRADES = 5
CACHE_TTL_SECONDS = 300


@dataclass
class BacktestResult:
    win_rate: float
    total_trades: int
    wins: int
    losses: int
    avg_win_pct: float
    avg_loss_pct: float
    approved: bool
    reason: str


_cache: dict[str, tuple[float, BacktestResult]] = {}


def _cache_key(symbol: str, bot_type: str, side: str, timeframe: str) -> str:
    return f"{symbol}:{bot_type}:{side}:{timeframe}"


def get_cached(symbol: str, bot_type: str, side: str, timeframe: str) -> Optional[BacktestResult]:
    key = _cache_key(symbol, bot_type, side, timeframe)
    entry = _cache.get(key)
    if entry and (time.time() - entry[0]) < CACHE_TTL_SECONDS:
        return entry[1]
    return None


def set_cached(symbol: str, bot_type: str, side: str, timeframe: str, result: BacktestResult):
    key = _cache_key(symbol, bot_type, side, timeframe)
    _cache[key] = (time.time(), result)


SL_ATR_MULT = {
    "scalper": 1.5,
    "swing": 2.0,
    "long_term": 2.5,
    "grid": 2.5,
    "mean_reversion": 2.0,
    "momentum": 1.8,
    "dca": 2.0,
}

TP_ATR_MULT = {
    "scalper": 2.25,
    "swing": 5.0,
    "long_term": 7.5,
    "grid": 2.5,
    "mean_reversion": 3.0,
    "momentum": 3.6,
    "dca": 3.0,
}

ENTRY_SCORE_THRESHOLDS = {
    "scalper": 2.0,
    "swing": 2.0,
    "long_term": 2.0,
    "grid": 2.0,
    "mean_reversion": 2.0,
    "momentum": 2.0,
    "dca": 1.5,
}


def simulate_trades_on_history(
    df: pd.DataFrame,
    bot_type: str,
    side: str,
    min_confidence: float = 0.30,
) -> BacktestResult:
    if len(df) < MIN_LOOKBACK_BARS:
        return BacktestResult(
            win_rate=0, total_trades=0, wins=0, losses=0,
            avg_win_pct=0, avg_loss_pct=0, approved=False,
            reason=f"Insufficient data: {len(df)} bars < {MIN_LOOKBACK_BARS}",
        )

    sl_mult = SL_ATR_MULT.get(bot_type, 2.0)
    tp_mult = TP_ATR_MULT.get(bot_type, 3.0)
    score_thresh = ENTRY_SCORE_THRESHOLDS.get(bot_type, 2.0)

    wins = 0
    losses = 0
    win_pcts: list[float] = []
    loss_pcts: list[float] = []

    window = 60
    step = max(len(df) // 80, 3)
    max_hold_bars = 48

    for i in range(window, len(df) - max_hold_bars, step):
        chunk = df.iloc[i - window:i + 1].copy().reset_index(drop=True)
        if len(chunk) < 50:
            continue

        try:
            analyzer = TechnicalAnalyzer(chunk)
            signal = analyzer.analyze()
        except Exception:
            continue

        if signal.confidence < min_confidence:
            continue

        if signal.overall_signal == "hold":
            continue

        net = 0
        if signal.overall_signal in ("buy", "strong_buy"):
            net = 1
        elif signal.overall_signal in ("sell", "strong_sell"):
            net = -1

        if side == "buy" and net < 0:
            continue
        if side == "sell" and net > 0:
            continue

        if abs(signal.confirmation_score) < score_thresh:
            continue

        entry_price = df.iloc[i]["close"]
        atr = signal.atr
        if atr <= 0 or atr / entry_price > 0.5:
            atr = entry_price * 0.02

        if side == "buy":
            sl = entry_price - atr * sl_mult
            tp = entry_price + atr * tp_mult
        else:
            sl = entry_price + atr * sl_mult
            tp = entry_price - atr * tp_mult

        fee_pct = 0.001 * 2

        hit_tp = False
        hit_sl = False
        for j in range(i + 1, min(i + max_hold_bars + 1, len(df))):
            bar = df.iloc[j]
            if side == "buy":
                if bar["low"] <= sl:
                    hit_sl = True
                    break
                if bar["high"] >= tp:
                    hit_tp = True
                    break
            else:
                if bar["high"] >= sl:
                    hit_sl = True
                    break
                if bar["low"] <= tp:
                    hit_tp = True
                    break

        if hit_tp:
            pnl_pct = abs(tp - entry_price) / entry_price * 100 - fee_pct * 100
            wins += 1
            win_pcts.append(pnl_pct)
        elif hit_sl:
            pnl_pct = abs(sl - entry_price) / entry_price * 100 + fee_pct * 100
            losses += 1
            loss_pcts.append(pnl_pct)
        else:
            exit_price = df.iloc[min(i + max_hold_bars, len(df) - 1)]["close"]
            if side == "buy":
                pnl_pct = (exit_price - entry_price) / entry_price * 100 - fee_pct * 100
            else:
                pnl_pct = (entry_price - exit_price) / entry_price * 100 - fee_pct * 100
            if pnl_pct >= 0:
                wins += 1
                win_pcts.append(pnl_pct)
            else:
                losses += 1
                loss_pcts.append(abs(pnl_pct))

    total = wins + losses
    if total < MIN_SIMULATED_TRADES:
        return BacktestResult(
            win_rate=0, total_trades=total, wins=wins, losses=losses,
            avg_win_pct=0, avg_loss_pct=0, approved=False,
            reason=f"Too few simulated trades: {total} < {MIN_SIMULATED_TRADES}",
        )

    wr = wins / total
    avg_win = sum(win_pcts) / len(win_pcts) if win_pcts else 0
    avg_loss = sum(loss_pcts) / len(loss_pcts) if loss_pcts else 0
    approved = wr >= 0.51

    return BacktestResult(
        win_rate=round(wr, 4),
        total_trades=total,
        wins=wins,
        losses=losses,
        avg_win_pct=round(avg_win, 3),
        avg_loss_pct=round(avg_loss, 3),
        approved=approved,
        reason=f"Backtest WR={wr*100:.1f}% ({wins}W/{losses}L) avg_win={avg_win:.2f}% avg_loss={avg_loss:.2f}%"
            + (" APPROVED" if approved else " REJECTED (<51%)"),
    )


async def check_historical_win_rate(
    exchange,
    exchange_id: str,
    symbol: str,
    bot_type: str,
    side: str,
    timeframe: str = "1h",
    min_confidence: float = 0.30,
) -> BacktestResult:
    cached = get_cached(symbol, bot_type, side, timeframe)
    if cached is not None:
        return cached

    try:
        df = await exchange.fetch_ohlcv(exchange_id, symbol, timeframe, MAX_LOOKBACK_BARS)
    except Exception as e:
        logger.debug(f"Backtest fetch failed for {symbol}: {e}")
        return BacktestResult(
            win_rate=0, total_trades=0, wins=0, losses=0,
            avg_win_pct=0, avg_loss_pct=0, approved=False,
            reason=f"Failed to fetch data: {e}",
        )

    result = simulate_trades_on_history(df, bot_type, side, min_confidence)

    set_cached(symbol, bot_type, side, timeframe, result)

    logger.info(
        f"BACKTEST {bot_type} {side} {symbol} [{timeframe}]: {result.reason}"
    )

    return result
