import json
import os
import logging
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from app.indicators.technical import TechnicalAnalyzer, SignalResult

logger = logging.getLogger(__name__)

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")


@dataclass
class AutopsyFinding:
    factor: str
    at_entry: str
    at_exit: str
    optimal: str
    lesson: str
    weight: float


@dataclass
class TradeAutopsy:
    trade_id: int
    symbol: str
    bot_type: str
    side: str
    entry_price: float
    exit_price: float
    pnl_usd: float
    pnl_pct: float
    was_winner: bool
    status: str
    findings: list[AutopsyFinding] = field(default_factory=list)
    optimal_entry_bar: int = 0
    optimal_exit_bar: int = 0
    optimal_pnl_pct: float = 0.0
    regime_at_entry: str = ""
    regime_at_exit: str = ""
    timestamp: str = ""


@dataclass
class LearningAdjustment:
    min_rsi_buy: float = 0.0
    max_rsi_buy: float = 0.0
    min_rsi_sell: float = 0.0
    max_rsi_sell: float = 0.0
    min_adx: float = 0.0
    sl_atr_mult_adj: float = 0.0
    tp_atr_mult_adj: float = 0.0
    min_confidence_adj: float = 0.0
    avoid_regimes: list[str] = field(default_factory=list)
    prefer_regimes: list[str] = field(default_factory=list)
    min_volume_trend: str = ""
    require_macd_alignment: bool = False
    require_ema_alignment: bool = False
    sample_size: int = 0
    win_rate: float = 0.0
    last_updated: str = ""


class AdaptiveMemory:
    def __init__(self, persist_path: Optional[str] = None):
        self._path = persist_path or os.path.join(DATA_DIR, "adaptive_memory.json")
        self._lock = threading.Lock()
        self.autopsies: list[dict] = []
        self.adjustments: dict[str, dict] = {}
        self._load()

    def _load(self):
        try:
            if os.path.exists(self._path):
                with open(self._path, "r") as f:
                    data = json.load(f)
                self.autopsies = data.get("autopsies", [])
                self.adjustments = data.get("adjustments", {})
                logger.info(f"Loaded adaptive memory: {len(self.autopsies)} autopsies, {len(self.adjustments)} adjustment profiles")
        except Exception as e:
            logger.error(f"Failed to load adaptive memory: {e}")

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            data = {
                "autopsies": self.autopsies[-500:],
                "adjustments": self.adjustments,
            }
            with self._lock:
                tmp = self._path + ".tmp"
                with open(tmp, "w") as f:
                    json.dump(data, f)
                os.replace(tmp, self._path)
        except Exception as e:
            logger.error(f"Failed to save adaptive memory: {e}")

    def _key(self, bot_type: str, symbol: str = "") -> str:
        if symbol:
            base = symbol.split("/")[0] if "/" in symbol else symbol
            return f"{bot_type}:{base}"
        return bot_type

    def get_adjustment(self, bot_type: str, symbol: str = "") -> LearningAdjustment:
        specific = self.adjustments.get(self._key(bot_type, symbol))
        general = self.adjustments.get(bot_type)
        raw = specific or general
        if raw:
            try:
                return LearningAdjustment(**{k: v for k, v in raw.items() if k in LearningAdjustment.__dataclass_fields__})
            except Exception:
                pass
        return LearningAdjustment()

    def record_autopsy(self, autopsy: TradeAutopsy):
        self.autopsies.append(asdict(autopsy))
        self._recompute_adjustments(autopsy.bot_type, autopsy.symbol)
        self._save()

    def _recompute_adjustments(self, bot_type: str, symbol: str):
        base = symbol.split("/")[0] if "/" in symbol else symbol
        keys_to_update = [bot_type, f"{bot_type}:{base}"]

        for key in keys_to_update:
            if ":" in key:
                relevant = [a for a in self.autopsies if a.get("bot_type") == bot_type and base in a.get("symbol", "")]
            else:
                relevant = [a for a in self.autopsies if a.get("bot_type") == bot_type]

            if len(relevant) < 3:
                continue

            winners = [a for a in relevant if a.get("was_winner")]
            losers = [a for a in relevant if not a.get("was_winner")]
            total = len(relevant)
            wr = len(winners) / total if total > 0 else 0

            adj = LearningAdjustment()
            adj.sample_size = total
            adj.win_rate = round(wr, 3)
            adj.last_updated = datetime.now(timezone.utc).isoformat()

            losing_regimes: dict[str, int] = {}
            winning_regimes: dict[str, int] = {}
            for a in losers:
                r = a.get("regime_at_entry", "")
                if r:
                    losing_regimes[r] = losing_regimes.get(r, 0) + 1
            for a in winners:
                r = a.get("regime_at_entry", "")
                if r:
                    winning_regimes[r] = winning_regimes.get(r, 0) + 1

            for regime, loss_count in losing_regimes.items():
                win_count = winning_regimes.get(regime, 0)
                regime_total = loss_count + win_count
                if regime_total >= 3 and win_count / regime_total < 0.3:
                    adj.avoid_regimes.append(regime)

            for regime, win_count in winning_regimes.items():
                loss_count = losing_regimes.get(regime, 0)
                regime_total = win_count + loss_count
                if regime_total >= 3 and win_count / regime_total > 0.7:
                    adj.prefer_regimes.append(regime)

            sl_lessons = []
            tp_lessons = []
            conf_lessons = []
            for a in relevant:
                for f in a.get("findings", []):
                    factor = f.get("factor", "")
                    lesson = f.get("lesson", "")
                    weight = f.get("weight", 0)
                    if "stop_loss" in factor and "tighter" in lesson:
                        sl_lessons.append(-0.1 * weight)
                    elif "stop_loss" in factor and "wider" in lesson:
                        sl_lessons.append(0.1 * weight)
                    if "take_profit" in factor and "earlier" in lesson:
                        tp_lessons.append(-0.15 * weight)
                    elif "take_profit" in factor and "later" in lesson:
                        tp_lessons.append(0.1 * weight)
                    if "confidence" in factor:
                        conf_lessons.append(weight * 0.02)

            if sl_lessons:
                adj.sl_atr_mult_adj = round(max(-0.5, min(0.5, sum(sl_lessons) / len(sl_lessons))), 3)
            if tp_lessons:
                adj.tp_atr_mult_adj = round(max(-0.5, min(0.5, sum(tp_lessons) / len(tp_lessons))), 3)
            if conf_lessons and wr < 0.5:
                adj.min_confidence_adj = round(min(0.15, sum(conf_lessons) / len(conf_lessons)), 3)

            rsi_at_entry_winners = []
            rsi_at_entry_losers = []
            adx_at_entry_winners = []
            for a in relevant:
                for f in a.get("findings", []):
                    if f.get("factor") == "rsi":
                        try:
                            val = float(f["at_entry"])
                            if a.get("was_winner"):
                                rsi_at_entry_winners.append(val)
                            else:
                                rsi_at_entry_losers.append(val)
                        except (ValueError, KeyError):
                            pass
                    if f.get("factor") == "adx":
                        try:
                            val = float(f["at_entry"])
                            if a.get("was_winner"):
                                adx_at_entry_winners.append(val)
                        except (ValueError, KeyError):
                            pass

            if len(rsi_at_entry_winners) >= 3:
                avg_rsi_win = sum(rsi_at_entry_winners) / len(rsi_at_entry_winners)
                if avg_rsi_win < 40:
                    adj.max_rsi_buy = round(avg_rsi_win + 10, 1)
                elif avg_rsi_win > 60:
                    adj.min_rsi_sell = round(avg_rsi_win - 10, 1)

            if len(adx_at_entry_winners) >= 3:
                adj.min_adx = round(sum(adx_at_entry_winners) / len(adx_at_entry_winners) * 0.8, 1)

            macd_aligned_wins = 0
            macd_aligned_losses = 0
            ema_aligned_wins = 0
            ema_aligned_losses = 0
            for a in relevant:
                for f in a.get("findings", []):
                    if f.get("factor") == "macd_alignment":
                        if f.get("at_entry") == "aligned":
                            if a.get("was_winner"):
                                macd_aligned_wins += 1
                            else:
                                macd_aligned_losses += 1
                    if f.get("factor") == "ema_alignment":
                        if f.get("at_entry") == "aligned":
                            if a.get("was_winner"):
                                ema_aligned_wins += 1
                            else:
                                ema_aligned_losses += 1

            macd_total = macd_aligned_wins + macd_aligned_losses
            if macd_total >= 3 and macd_aligned_wins / macd_total > 0.7:
                adj.require_macd_alignment = True
            ema_total = ema_aligned_wins + ema_aligned_losses
            if ema_total >= 3 and ema_aligned_wins / ema_total > 0.7:
                adj.require_ema_alignment = True

            vol_wins = {"low": 0, "normal": 0, "high": 0, "very_high": 0}
            vol_losses = {"low": 0, "normal": 0, "high": 0, "very_high": 0}
            for a in relevant:
                for f in a.get("findings", []):
                    if f.get("factor") == "volume":
                        v = f.get("at_entry", "normal")
                        if a.get("was_winner"):
                            vol_wins[v] = vol_wins.get(v, 0) + 1
                        else:
                            vol_losses[v] = vol_losses.get(v, 0) + 1

            for vol_level in ["low", "normal"]:
                vw = vol_wins.get(vol_level, 0)
                vl = vol_losses.get(vol_level, 0)
                if vw + vl >= 3 and vl / (vw + vl) > 0.7:
                    adj.min_volume_trend = "high"
                    break

            self.adjustments[key] = asdict(adj)
            logger.info(
                f"LEARNING [{key}]: updated from {total} trades (WR={wr*100:.0f}%) "
                f"sl_adj={adj.sl_atr_mult_adj:+.3f} tp_adj={adj.tp_atr_mult_adj:+.3f} "
                f"conf_adj={adj.min_confidence_adj:+.3f} avoid={adj.avoid_regimes}"
            )

    def get_stats(self) -> dict:
        return {
            "total_autopsies": len(self.autopsies),
            "adjustment_profiles": len(self.adjustments),
            "profiles": {k: {"sample_size": v.get("sample_size", 0), "win_rate": v.get("win_rate", 0)} for k, v in self.adjustments.items()},
        }


def perform_autopsy(
    trade: dict,
    entry_df: Optional[pd.DataFrame],
    exit_df: Optional[pd.DataFrame],
) -> TradeAutopsy:
    trade_id = trade.get("id", 0)
    symbol = trade.get("symbol", "?")
    bot_type = trade.get("bot_type", "?")
    side = trade.get("side", "buy")
    entry_price = trade.get("entry_price", 0)
    exit_price = trade.get("exit_price", 0)
    pnl_usd = trade.get("pnl_usd", 0)
    pnl_pct = trade.get("pnl_pct", 0)
    status = trade.get("status", "closed")

    autopsy = TradeAutopsy(
        trade_id=trade_id,
        symbol=symbol,
        bot_type=bot_type,
        side=side,
        entry_price=entry_price,
        exit_price=exit_price,
        pnl_usd=pnl_usd,
        pnl_pct=pnl_pct,
        was_winner=pnl_usd > 0,
        status=status,
        regime_at_entry=trade.get("regime", ""),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    if exit_df is None or len(exit_df) < 50:
        return autopsy

    try:
        entry_signal = None
        exit_signal = None

        if entry_df is not None and len(entry_df) >= 50:
            entry_signal = TechnicalAnalyzer(entry_df).analyze()

        exit_signal = TechnicalAnalyzer(exit_df).analyze()
        autopsy.regime_at_exit = exit_signal.regime.regime.value if exit_signal.regime else ""

        if entry_signal:
            _analyze_rsi(autopsy, entry_signal, exit_signal, side)
            _analyze_macd(autopsy, entry_signal, exit_signal, side)
            _analyze_ema(autopsy, entry_signal, exit_signal, side)
            _analyze_volume(autopsy, entry_signal, exit_signal)
            _analyze_adx(autopsy, entry_signal, exit_signal)
            _analyze_regime(autopsy, entry_signal, exit_signal, side)
            _analyze_bollinger(autopsy, entry_signal, exit_signal, side)
            _analyze_confidence(autopsy, entry_signal, trade)

        _analyze_stop_loss(autopsy, trade, exit_df, side)
        _analyze_take_profit(autopsy, trade, exit_df, side)
        _find_optimal_trade(autopsy, exit_df, entry_price, side)

    except Exception as e:
        logger.debug(f"Autopsy analysis error for trade {trade_id}: {e}")

    return autopsy


def _analyze_rsi(autopsy: TradeAutopsy, entry_sig: SignalResult, exit_sig: SignalResult, side: str):
    entry_rsi = entry_sig.rsi or 50
    exit_rsi = exit_sig.rsi or 50
    optimal = ""
    lesson = ""
    weight = 0.0

    if not autopsy.was_winner:
        if side == "buy" and entry_rsi > 60:
            optimal = "<40"
            lesson = "entered buy with RSI too high, wait for oversold"
            weight = 1.0
        elif side == "sell" and entry_rsi < 40:
            optimal = ">60"
            lesson = "entered sell with RSI too low, wait for overbought"
            weight = 1.0
        elif side == "buy" and entry_rsi > 45:
            optimal = "<35"
            lesson = "RSI not oversold enough for reliable buy entry"
            weight = 0.5
        elif side == "sell" and entry_rsi < 55:
            optimal = ">65"
            lesson = "RSI not overbought enough for reliable sell entry"
            weight = 0.5

    if lesson:
        autopsy.findings.append(AutopsyFinding(
            factor="rsi",
            at_entry=f"{entry_rsi:.1f}",
            at_exit=f"{exit_rsi:.1f}",
            optimal=optimal,
            lesson=lesson,
            weight=weight,
        ))


def _analyze_macd(autopsy: TradeAutopsy, entry_sig: SignalResult, exit_sig: SignalResult, side: str):
    aligned = False
    if side == "buy" and entry_sig.macd_signal in ("bullish", "bullish_crossover"):
        aligned = True
    elif side == "sell" and entry_sig.macd_signal in ("bearish", "bearish_crossover"):
        aligned = True

    lesson = ""
    weight = 0.0
    if not autopsy.was_winner and not aligned:
        lesson = "MACD not aligned with trade direction at entry"
        weight = 1.0

    autopsy.findings.append(AutopsyFinding(
        factor="macd_alignment",
        at_entry="aligned" if aligned else "misaligned",
        at_exit=exit_sig.macd_signal,
        optimal="aligned with side",
        lesson=lesson,
        weight=weight,
    ))


def _analyze_ema(autopsy: TradeAutopsy, entry_sig: SignalResult, exit_sig: SignalResult, side: str):
    aligned = False
    if side == "buy" and entry_sig.ema_trend in ("bullish", "strong_bullish"):
        aligned = True
    elif side == "sell" and entry_sig.ema_trend in ("bearish", "strong_bearish"):
        aligned = True

    lesson = ""
    weight = 0.0
    if not autopsy.was_winner and not aligned:
        lesson = "EMA trend not aligned with trade direction"
        weight = 0.8

    autopsy.findings.append(AutopsyFinding(
        factor="ema_alignment",
        at_entry="aligned" if aligned else "misaligned",
        at_exit=exit_sig.ema_trend,
        optimal="aligned with side",
        lesson=lesson,
        weight=weight,
    ))


def _analyze_volume(autopsy: TradeAutopsy, entry_sig: SignalResult, exit_sig: SignalResult):
    lesson = ""
    weight = 0.0
    if not autopsy.was_winner and entry_sig.volume_trend in ("low", "normal"):
        lesson = "entered on low volume, wait for volume confirmation"
        weight = 0.7

    autopsy.findings.append(AutopsyFinding(
        factor="volume",
        at_entry=entry_sig.volume_trend,
        at_exit=exit_sig.volume_trend,
        optimal="high or very_high",
        lesson=lesson,
        weight=weight,
    ))


def _analyze_adx(autopsy: TradeAutopsy, entry_sig: SignalResult, exit_sig: SignalResult):
    lesson = ""
    weight = 0.0
    if not autopsy.was_winner and entry_sig.adx < 20:
        lesson = "weak trend (ADX<20), avoid entries without clear trend"
        weight = 0.6

    autopsy.findings.append(AutopsyFinding(
        factor="adx",
        at_entry=f"{entry_sig.adx:.1f}",
        at_exit=f"{exit_sig.adx:.1f}",
        optimal=">25",
        lesson=lesson,
        weight=weight,
    ))


def _analyze_regime(autopsy: TradeAutopsy, entry_sig: SignalResult, exit_sig: SignalResult, side: str):
    entry_regime = entry_sig.regime.regime.value if entry_sig.regime else "unknown"
    exit_regime = exit_sig.regime.regime.value if exit_sig.regime else "unknown"

    lesson = ""
    weight = 0.0
    if not autopsy.was_winner:
        if entry_regime == "chaotic":
            lesson = "entered during chaotic regime, avoid these conditions"
            weight = 1.5
        elif side == "buy" and entry_regime in ("strong_trend_down", "trend_down"):
            lesson = "bought during downtrend regime, consider shorting instead"
            weight = 1.2
        elif side == "sell" and entry_regime in ("strong_trend_up", "trend_up"):
            lesson = "shorted during uptrend regime, consider buying instead"
            weight = 1.2
        elif entry_regime == "ranging" and autopsy.bot_type in ("momentum", "swing"):
            lesson = "momentum/swing entry during ranging market"
            weight = 0.8

    autopsy.findings.append(AutopsyFinding(
        factor="regime",
        at_entry=entry_regime,
        at_exit=exit_regime,
        optimal="aligned with side",
        lesson=lesson,
        weight=weight,
    ))


def _analyze_bollinger(autopsy: TradeAutopsy, entry_sig: SignalResult, exit_sig: SignalResult, side: str):
    lesson = ""
    weight = 0.0
    if not autopsy.was_winner:
        if side == "buy" and entry_sig.bollinger_signal == "overbought":
            lesson = "bought at upper Bollinger band, price likely to revert"
            weight = 0.9
        elif side == "sell" and entry_sig.bollinger_signal == "oversold":
            lesson = "shorted at lower Bollinger band, price likely to bounce"
            weight = 0.9

    if lesson:
        autopsy.findings.append(AutopsyFinding(
            factor="bollinger",
            at_entry=entry_sig.bollinger_signal,
            at_exit=exit_sig.bollinger_signal,
            optimal="oversold for buy, overbought for sell",
            lesson=lesson,
            weight=weight,
        ))


def _analyze_confidence(autopsy: TradeAutopsy, entry_sig: SignalResult, trade: dict):
    conf = trade.get("signal_confidence", entry_sig.confidence)
    lesson = ""
    weight = 0.0
    if not autopsy.was_winner and conf < 0.4:
        lesson = "low confidence entry, require higher signal quality"
        weight = 0.6

    if lesson:
        autopsy.findings.append(AutopsyFinding(
            factor="confidence",
            at_entry=f"{conf:.3f}",
            at_exit="",
            optimal=">0.45",
            lesson=lesson,
            weight=weight,
        ))


def _analyze_stop_loss(autopsy: TradeAutopsy, trade: dict, df: pd.DataFrame, side: str):
    sl = trade.get("stop_loss_price") or trade.get("stop_loss", 0)
    entry_price = trade.get("entry_price", 0)
    status = trade.get("status", "")

    if not sl or not entry_price:
        return

    sl_pct = abs(entry_price - sl) / entry_price * 100 if entry_price > 0 else 0

    lesson = ""
    weight = 0.0
    optimal = ""

    if status == "stopped_out":
        close = df["close"].values
        if side == "buy":
            post_sl_max = max(close[-20:]) if len(close) >= 20 else max(close)
            recovery_pct = (post_sl_max - sl) / sl * 100 if sl > 0 else 0
            if recovery_pct > sl_pct * 0.5:
                lesson = "stop_loss too tight, price recovered after stop — use wider stop"
                weight = 1.0
                optimal = f"SL at {sl_pct * 1.5:.1f}% instead of {sl_pct:.1f}%"
        else:
            post_sl_min = min(close[-20:]) if len(close) >= 20 else min(close)
            recovery_pct = (sl - post_sl_min) / sl * 100 if sl > 0 else 0
            if recovery_pct > sl_pct * 0.5:
                lesson = "stop_loss too tight, price recovered after stop — use wider stop"
                weight = 1.0
                optimal = f"SL at {sl_pct * 1.5:.1f}% instead of {sl_pct:.1f}%"
    elif not autopsy.was_winner and status == "closed":
        lesson = "stop_loss could have been tighter to limit loss"
        weight = 0.5
        optimal = f"SL at {sl_pct * 0.7:.1f}% instead of {sl_pct:.1f}%"

    if lesson:
        autopsy.findings.append(AutopsyFinding(
            factor="stop_loss",
            at_entry=f"{sl_pct:.2f}%",
            at_exit=status,
            optimal=optimal,
            lesson=lesson,
            weight=weight,
        ))


def _analyze_take_profit(autopsy: TradeAutopsy, trade: dict, df: pd.DataFrame, side: str):
    tp = trade.get("take_profit_price") or trade.get("take_profit", 0)
    entry_price = trade.get("entry_price", 0)

    if not tp or not entry_price:
        return

    tp_pct = abs(tp - entry_price) / entry_price * 100 if entry_price > 0 else 0
    close = df["close"].values

    lesson = ""
    weight = 0.0
    optimal = ""

    if autopsy.was_winner:
        if side == "buy":
            max_price = max(close[-30:]) if len(close) >= 30 else max(close)
            missed_pct = (max_price - tp) / entry_price * 100 if entry_price > 0 else 0
            if missed_pct > tp_pct * 0.5:
                lesson = "take_profit could have been set later to capture more upside"
                weight = 0.3
                optimal = f"TP at {tp_pct + missed_pct * 0.5:.1f}% instead of {tp_pct:.1f}%"
        else:
            min_price = min(close[-30:]) if len(close) >= 30 else min(close)
            missed_pct = (tp - min_price) / entry_price * 100 if entry_price > 0 else 0
            if missed_pct > tp_pct * 0.5:
                lesson = "take_profit could have been set later to capture more downside"
                weight = 0.3
                optimal = f"TP at {tp_pct + missed_pct * 0.5:.1f}% instead of {tp_pct:.1f}%"
    elif not autopsy.was_winner:
        if side == "buy":
            max_price = max(close) if len(close) > 0 else entry_price
            if max_price > entry_price:
                best_pct = (max_price - entry_price) / entry_price * 100
                if best_pct > 0.3:
                    lesson = "take_profit was set earlier but price reached profitable level first"
                    weight = 0.7
                    optimal = f"TP at {best_pct * 0.8:.1f}% (price reached {best_pct:.1f}%)"


    if lesson:
        autopsy.findings.append(AutopsyFinding(
            factor="take_profit",
            at_entry=f"{tp_pct:.2f}%",
            at_exit="",
            optimal=optimal,
            lesson=lesson,
            weight=weight,
        ))


def _find_optimal_trade(autopsy: TradeAutopsy, df: pd.DataFrame, entry_price: float, side: str):
    if len(df) < 20:
        return

    close = df["close"].values

    if side == "buy":
        min_idx = 0
        min_price = close[0]
        for i, p in enumerate(close):
            if p < min_price:
                min_price = p
                min_idx = i
        max_after = max(close[min_idx:]) if min_idx < len(close) - 1 else close[min_idx]
        autopsy.optimal_entry_bar = min_idx
        autopsy.optimal_pnl_pct = round((max_after - min_price) / min_price * 100, 2) if min_price > 0 else 0
    else:
        max_idx = 0
        max_price = close[0]
        for i, p in enumerate(close):
            if p > max_price:
                max_price = p
                max_idx = i
        min_after = min(close[max_idx:]) if max_idx < len(close) - 1 else close[max_idx]
        autopsy.optimal_entry_bar = max_idx
        autopsy.optimal_pnl_pct = round((max_price - min_after) / max_price * 100, 2) if max_price > 0 else 0


adaptive_memory = AdaptiveMemory()
