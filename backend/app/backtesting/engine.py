import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional

from app.indicators.technical import TechnicalAnalyzer, MarketRegime


@dataclass
class BacktestTrade:
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    entry_time: str
    exit_time: str
    pnl_usd: float
    pnl_pct: float
    fees_usd: float
    stop_loss: float
    take_profit: Optional[float]
    exit_reason: str


@dataclass
class BacktestResult:
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl_usd: float
    total_fees_usd: float
    max_drawdown_pct: float
    sharpe_ratio: float
    trades: list[BacktestTrade] = field(default_factory=list)


class BacktestEngine:
    def __init__(self, fee_rate: float = 0.001):
        self.fee_rate = fee_rate

    def run(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        initial_capital: float = 1000.0,
        risk_per_trade_pct: float = 2.0,
        sl_atr_multiplier: float = 1.5,
        tp_rr_ratio: float = 2.0,
        min_confidence: float = 0.15,
        min_confirmations: int = 3,
    ) -> BacktestResult:
        capital = initial_capital
        peak_capital = initial_capital
        max_drawdown = 0.0
        trades: list[BacktestTrade] = []
        returns: list[float] = []

        position = None
        trailing_high = 0.0
        trailing_low = float("inf")
        bars_in_trade = 0

        lookback = min(200, len(df) - 10)
        if lookback < 30:
            lookback = 30
        if len(df) <= lookback:
            return BacktestResult(
                symbol=symbol, timeframe=timeframe,
                start_date="", end_date="",
                initial_capital=initial_capital, final_capital=initial_capital,
                total_trades=0, winning_trades=0, losing_trades=0,
                win_rate=0.0, total_pnl_usd=0.0, total_fees_usd=0.0,
                max_drawdown_pct=0.0, sharpe_ratio=0.0, trades=[],
            )

        for i in range(lookback, len(df)):
            window = df.iloc[max(0, i - 200) : i + 1].copy()
            window = window.reset_index(drop=True)

            try:
                analyzer = TechnicalAnalyzer(window)
                signal = analyzer.analyze()
            except Exception:
                continue

            if position:
                bars_in_trade += 1
                current_price = df.iloc[i]["close"]
                current_high = df.iloc[i]["high"]
                current_low = df.iloc[i]["low"]

                if position["side"] == "buy":
                    trailing_high = max(trailing_high, current_high)
                else:
                    trailing_low = min(trailing_low, current_low)

                hit_sl = False
                hit_tp = False

                if position["side"] == "buy":
                    hit_sl = current_low <= position["stop_loss"]
                    hit_tp = position.get("take_profit") and current_high >= position["take_profit"]
                else:
                    hit_sl = current_high >= position["stop_loss"]
                    hit_tp = position.get("take_profit") and current_low <= position["take_profit"]

                trail_exit = False
                if bars_in_trade >= 3 and signal.atr > 0:
                    trail_mult = sl_atr_multiplier * 1.2
                    if position["side"] == "buy":
                        trail_stop = trailing_high - (signal.atr * trail_mult)
                        if trail_stop > position["stop_loss"] and current_low <= trail_stop:
                            trail_exit = True
                            position["stop_loss"] = trail_stop
                    else:
                        trail_stop = trailing_low + (signal.atr * trail_mult)
                        if trail_stop < position["stop_loss"] and current_high >= trail_stop:
                            trail_exit = True
                            position["stop_loss"] = trail_stop

                exit_reason = None
                exit_price = current_price

                if hit_tp:
                    exit_price = position["take_profit"]
                    exit_reason = "take_profit"
                elif hit_sl:
                    exit_price = position["stop_loss"]
                    exit_reason = "stop_loss"
                elif trail_exit:
                    exit_price = position["stop_loss"]
                    exit_reason = "trailing_stop"
                else:
                    regime = signal.regime
                    if regime and regime.regime == MarketRegime.CHAOTIC:
                        if position["side"] == "buy":
                            unrealised_pct = (current_price - position["entry_price"]) / position["entry_price"]
                        else:
                            unrealised_pct = (position["entry_price"] - current_price) / position["entry_price"]
                        if unrealised_pct > 0.005:
                            exit_reason = "regime_exit"

                    if position["side"] == "buy":
                        if signal.overall_signal == "strong_sell" and signal.confirmation_score >= 5:
                            exit_reason = "signal_reversal"
                        elif signal.psar_direction == "bearish" and signal.obv_trend == "bearish" and signal.adx >= 25:
                            unrealised_pct = (current_price - position["entry_price"]) / position["entry_price"]
                            if unrealised_pct > 0:
                                exit_reason = "trend_reversal"
                    elif position["side"] == "sell":
                        if signal.overall_signal == "strong_buy" and signal.confirmation_score >= 5:
                            exit_reason = "signal_reversal"
                        elif signal.psar_direction == "bullish" and signal.obv_trend == "bullish" and signal.adx >= 25:
                            unrealised_pct = (position["entry_price"] - current_price) / position["entry_price"]
                            if unrealised_pct > 0:
                                exit_reason = "trend_reversal"

                if exit_reason:
                    if position["side"] == "buy":
                        pnl = (exit_price - position["entry_price"]) * position["quantity"]
                    else:
                        pnl = (position["entry_price"] - exit_price) * position["quantity"]

                    fees = position["quantity"] * exit_price * self.fee_rate
                    pnl -= fees + position["entry_fee"]

                    pnl_pct = (pnl / (position["entry_price"] * position["quantity"])) * 100

                    trades.append(BacktestTrade(
                        symbol=symbol,
                        side=position["side"],
                        entry_price=position["entry_price"],
                        exit_price=exit_price,
                        quantity=position["quantity"],
                        entry_time=str(position["entry_time"]),
                        exit_time=str(df.iloc[i]["timestamp"]),
                        pnl_usd=round(pnl, 2),
                        pnl_pct=round(pnl_pct, 2),
                        fees_usd=round(fees + position["entry_fee"], 4),
                        stop_loss=position["stop_loss"],
                        take_profit=position.get("take_profit"),
                        exit_reason=exit_reason,
                    ))

                    capital += pnl
                    returns.append(pnl / capital if capital > 0 else 0)
                    peak_capital = max(peak_capital, capital)
                    drawdown = (peak_capital - capital) / peak_capital * 100
                    max_drawdown = max(max_drawdown, drawdown)
                    position = None
                    bars_in_trade = 0

            elif signal.overall_signal in ("buy", "strong_buy", "sell", "strong_sell"):
                regime = signal.regime

                if regime and regime.regime == MarketRegime.CHAOTIC:
                    continue

                if signal.confidence < min_confidence:
                    continue

                if len(signal.confirmations) < min_confirmations:
                    continue

                if signal.adx < 15 and signal.overall_signal not in ("strong_buy", "strong_sell"):
                    continue

                if signal.overall_signal in ("buy", "strong_buy"):
                    side = "buy"
                else:
                    side = "sell"

                directional_ok = False
                if side == "buy":
                    bull_inds = 0
                    if signal.ema_trend in ("bullish", "strong_bullish"):
                        bull_inds += 1
                    if signal.macd_signal in ("bullish", "bullish_crossover"):
                        bull_inds += 1
                    if signal.psar_direction == "bullish":
                        bull_inds += 1
                    if signal.obv_trend == "bullish":
                        bull_inds += 1
                    if signal.rsi_signal in ("oversold", "approaching_oversold"):
                        bull_inds += 1
                    if hasattr(signal, "vwap_signal") and signal.vwap_signal == "below_vwap":
                        bull_inds += 1
                    if hasattr(signal, "cmf") and signal.cmf > 0.05:
                        bull_inds += 1
                    directional_ok = bull_inds >= 3
                else:
                    bear_inds = 0
                    if signal.ema_trend in ("bearish", "strong_bearish"):
                        bear_inds += 1
                    if signal.macd_signal in ("bearish", "bearish_crossover"):
                        bear_inds += 1
                    if signal.psar_direction == "bearish":
                        bear_inds += 1
                    if signal.obv_trend == "bearish":
                        bear_inds += 1
                    if signal.rsi_signal in ("overbought", "approaching_overbought"):
                        bear_inds += 1
                    if hasattr(signal, "vwap_signal") and signal.vwap_signal == "above_vwap":
                        bear_inds += 1
                    if hasattr(signal, "cmf") and signal.cmf < -0.05:
                        bear_inds += 1
                    directional_ok = bear_inds >= 3

                if not directional_ok:
                    continue

                if regime and regime.regime == MarketRegime.RANGING:
                    if not (signal.bollinger_signal in ("oversold", "overbought") and signal.rsi_signal in ("oversold", "overbought")):
                        continue

                if regime and regime.regime == MarketRegime.VOLATILE:
                    if signal.confirmation_score < 5.0:
                        continue

                entry_price = df.iloc[i]["close"]
                atr = signal.atr

                if atr <= 0:
                    continue

                if side == "buy":
                    sl = entry_price - (atr * sl_atr_multiplier)
                    tp = entry_price + (atr * sl_atr_multiplier * tp_rr_ratio)
                else:
                    sl = entry_price + (atr * sl_atr_multiplier)
                    tp = entry_price - (atr * sl_atr_multiplier * tp_rr_ratio)

                risk_usd = capital * (risk_per_trade_pct / 100)
                price_risk = abs(entry_price - sl)
                if price_risk == 0:
                    continue
                quantity = risk_usd / price_risk
                position_value = quantity * entry_price
                entry_fee = position_value * self.fee_rate

                if position_value > capital:
                    quantity = (capital * 0.95) / entry_price
                    position_value = quantity * entry_price
                    entry_fee = position_value * self.fee_rate

                position = {
                    "side": side,
                    "entry_price": entry_price,
                    "quantity": quantity,
                    "stop_loss": sl,
                    "take_profit": tp,
                    "entry_fee": entry_fee,
                    "entry_time": df.iloc[i]["timestamp"],
                }
                trailing_high = entry_price
                trailing_low = entry_price
                bars_in_trade = 0

        if position:
            exit_price = df.iloc[-1]["close"]
            if position["side"] == "buy":
                pnl = (exit_price - position["entry_price"]) * position["quantity"]
            else:
                pnl = (position["entry_price"] - exit_price) * position["quantity"]
            fees = position["quantity"] * exit_price * self.fee_rate
            pnl -= fees + position["entry_fee"]
            pnl_pct = (pnl / (position["entry_price"] * position["quantity"])) * 100
            trades.append(BacktestTrade(
                symbol=symbol,
                side=position["side"],
                entry_price=position["entry_price"],
                exit_price=exit_price,
                quantity=position["quantity"],
                entry_time=str(position["entry_time"]),
                exit_time=str(df.iloc[-1]["timestamp"]),
                pnl_usd=round(pnl, 2),
                pnl_pct=round(pnl_pct, 2),
                fees_usd=round(fees + position["entry_fee"], 4),
                stop_loss=position["stop_loss"],
                take_profit=position.get("take_profit"),
                exit_reason="end_of_data",
            ))
            capital += pnl
            returns.append(pnl / capital if capital > 0 else 0)

        winning = [t for t in trades if t.pnl_usd > 0]
        losing = [t for t in trades if t.pnl_usd <= 0]
        total_pnl = sum(t.pnl_usd for t in trades)
        total_fees = sum(t.fees_usd for t in trades)

        sharpe = 0.0
        if returns:
            arr = np.array(returns)
            if arr.std() > 0:
                sharpe = float((arr.mean() / arr.std()) * (252 ** 0.5))

        peak_capital = max(peak_capital, capital)

        return BacktestResult(
            symbol=symbol,
            timeframe=timeframe,
            start_date=str(df.iloc[lookback]["timestamp"]) if lookback < len(df) else "",
            end_date=str(df.iloc[-1]["timestamp"]),
            initial_capital=initial_capital,
            final_capital=round(capital, 2),
            total_trades=len(trades),
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=round(len(winning) / len(trades) * 100, 1) if trades else 0.0,
            total_pnl_usd=round(total_pnl, 2),
            total_fees_usd=round(total_fees, 2),
            max_drawdown_pct=round(max_drawdown, 2),
            sharpe_ratio=round(sharpe, 2),
            trades=trades,
        )
