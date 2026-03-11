import pandas as pd
from dataclasses import dataclass, field
from typing import Optional

from app.indicators.technical import TechnicalAnalyzer


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
        min_confidence: float = 0.3,
    ) -> BacktestResult:
        capital = initial_capital
        peak_capital = initial_capital
        max_drawdown = 0.0
        trades: list[BacktestTrade] = []
        returns: list[float] = []

        position = None
        lookback = 200

        for i in range(lookback, len(df)):
            window = df.iloc[i - lookback : i + 1].copy()
            window = window.reset_index(drop=True)

            try:
                analyzer = TechnicalAnalyzer(window)
                signal = analyzer.analyze()
            except Exception:
                continue

            if position:
                current_price = df.iloc[i]["close"]
                hit_sl = False
                hit_tp = False

                if position["side"] == "buy":
                    hit_sl = df.iloc[i]["low"] <= position["stop_loss"]
                    hit_tp = position.get("take_profit") and df.iloc[i]["high"] >= position["take_profit"]
                else:
                    hit_sl = df.iloc[i]["high"] >= position["stop_loss"]
                    hit_tp = position.get("take_profit") and df.iloc[i]["low"] <= position["take_profit"]

                exit_reason = None
                exit_price = current_price

                if hit_sl:
                    exit_price = position["stop_loss"]
                    exit_reason = "stop_loss"
                elif hit_tp:
                    exit_price = position["take_profit"]
                    exit_reason = "take_profit"
                elif position["side"] == "buy" and signal.overall_signal in ("sell", "strong_sell"):
                    exit_reason = "signal_reversal"
                elif position["side"] == "sell" and signal.overall_signal in ("buy", "strong_buy"):
                    exit_reason = "signal_reversal"

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

            elif signal.confidence >= min_confidence and signal.overall_signal in (
                "buy", "strong_buy", "sell", "strong_sell"
            ):
                entry_price = df.iloc[i]["close"]
                atr = signal.atr

                if signal.overall_signal in ("buy", "strong_buy"):
                    side = "buy"
                    sl = entry_price - (atr * sl_atr_multiplier)
                    tp = entry_price + (atr * sl_atr_multiplier * tp_rr_ratio)
                else:
                    side = "sell"
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

        winning = [t for t in trades if t.pnl_usd > 0]
        losing = [t for t in trades if t.pnl_usd <= 0]
        total_pnl = sum(t.pnl_usd for t in trades)
        total_fees = sum(t.fees_usd for t in trades)

        import numpy as np
        sharpe = 0.0
        if returns:
            arr = np.array(returns)
            if arr.std() > 0:
                sharpe = float((arr.mean() / arr.std()) * (252 ** 0.5))

        return BacktestResult(
            symbol=symbol,
            timeframe=timeframe,
            start_date=str(df.iloc[lookback]["timestamp"]),
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
