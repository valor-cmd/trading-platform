from dataclasses import dataclass
from typing import Optional
import json
import logging

from app.core.config import settings
from app.core.store import store

logger = logging.getLogger(__name__)


@dataclass
class RiskAssessment:
    approved: bool
    position_size_usd: float
    stop_loss_price: float
    take_profit_price: Optional[float]
    risk_reward_ratio: float
    max_loss_usd: float
    reasoning: str
    bucket: str


@dataclass
class BucketAllocation:
    scalper_pct: float = 10.0
    swing_pct: float = 12.0
    long_term_pct: float = 12.0
    arbitrage_pct: float = 10.0
    grid_pct: float = 18.0
    mean_reversion_pct: float = 14.0
    momentum_pct: float = 12.0
    dca_pct: float = 12.0
    scalper_used_usd: float = 0.0
    swing_used_usd: float = 0.0
    long_term_used_usd: float = 0.0
    arbitrage_used_usd: float = 0.0
    grid_used_usd: float = 0.0
    mean_reversion_used_usd: float = 0.0
    momentum_used_usd: float = 0.0
    dca_used_usd: float = 0.0
    total_capital_usd: float = 0.0


class RiskEngine:
    def __init__(self):
        self.max_daily_loss = settings.max_daily_loss_usd
        self.default_sl_pct = settings.default_stop_loss_pct
        self.max_leverage = settings.max_leverage
        self._paper_exchange = None

    def set_paper_exchange(self, exchange):
        self._paper_exchange = exchange

    def _get_real_usdt_balance(self) -> float:
        if self._paper_exchange:
            return self._paper_exchange.balances.get("USDT", 0)
        return 0.0

    async def get_daily_pnl(self) -> float:
        raw = await store.get("daily_pnl")
        return float(raw) if raw else 0.0

    async def update_daily_pnl(self, pnl: float):
        current = await self.get_daily_pnl()
        await store.set("daily_pnl", str(current + pnl))

    async def get_bucket_allocation(self) -> BucketAllocation:
        raw = await store.get("bucket_allocation")
        if raw:
            return BucketAllocation(**json.loads(raw))
        return BucketAllocation()

    async def save_bucket_allocation(self, allocation: BucketAllocation):
        await store.set("bucket_allocation", json.dumps(allocation.__dict__))

    async def check_circuit_breaker(self) -> bool:
        daily_pnl = await self.get_daily_pnl()
        return daily_pnl <= -self.max_daily_loss

    def calculate_position_size(
        self,
        capital_available: float,
        risk_per_trade_pct: float,
        entry_price: float,
        stop_loss_price: float,
        fee_rate: float = 0.001,
    ) -> float:
        if entry_price <= 0 or capital_available <= 0:
            return 0.0
        risk_amount = capital_available * (risk_per_trade_pct / 100)
        price_diff = abs(entry_price - stop_loss_price)
        sl_pct = price_diff / entry_price if entry_price > 0 else 0
        if sl_pct < 0.005:
            sl_pct = 0.02
        position_size = risk_amount / sl_pct
        total_fees = position_size * fee_rate * 2
        position_size -= total_fees
        position_size = min(position_size, capital_available)
        return max(round(position_size, 2), 0.0)

    def calculate_stop_loss(
        self, entry_price: float, side: str, atr: float, multiplier: float = 1.5
    ) -> float:
        if atr <= 0 or atr / entry_price > 0.5:
            atr = entry_price * 0.02
        sl_distance = atr * multiplier
        if side == "buy":
            return entry_price - sl_distance
        return entry_price + sl_distance

    def calculate_take_profit(
        self,
        entry_price: float,
        stop_loss_price: float,
        side: str,
        rr_ratio: float = 2.0,
    ) -> float:
        risk = abs(entry_price - stop_loss_price)
        reward = risk * rr_ratio
        if side == "buy":
            return entry_price + reward
        return entry_price - reward

    async def reserve_bucket(self, bot_type: str, amount_usd: float):
        allocation = await self.get_bucket_allocation()
        attr = f"{bot_type}_used_usd"
        if hasattr(allocation, attr):
            setattr(allocation, attr, getattr(allocation, attr) + amount_usd)
        await self.save_bucket_allocation(allocation)

    async def release_bucket(self, bot_type: str, amount_usd: float):
        allocation = await self.get_bucket_allocation()
        attr = f"{bot_type}_used_usd"
        if hasattr(allocation, attr):
            setattr(allocation, attr, max(0, getattr(allocation, attr) - amount_usd))
        await self.save_bucket_allocation(allocation)

    async def assess_trade(
        self,
        bot_type: str,
        entry_price: float,
        side: str,
        atr: float,
        signal_confidence: float,
        fee_rate: float = 0.001,
    ) -> RiskAssessment:
        if await self.check_circuit_breaker():
            return RiskAssessment(
                approved=False, position_size_usd=0, stop_loss_price=0,
                take_profit_price=None, risk_reward_ratio=0, max_loss_usd=0,
                reasoning="Circuit breaker triggered", bucket=bot_type,
            )

        real_balance = self._get_real_usdt_balance()
        allocation = await self.get_bucket_allocation()

        bucket_map = {
            "scalper": (allocation.scalper_pct, allocation.scalper_used_usd),
            "swing": (allocation.swing_pct, allocation.swing_used_usd),
            "long_term": (allocation.long_term_pct, allocation.long_term_used_usd),
            "arbitrage": (allocation.arbitrage_pct, allocation.arbitrage_used_usd),
            "grid": (allocation.grid_pct, allocation.grid_used_usd),
            "mean_reversion": (allocation.mean_reversion_pct, allocation.mean_reversion_used_usd),
            "momentum": (allocation.momentum_pct, allocation.momentum_used_usd),
            "dca": (allocation.dca_pct, allocation.dca_used_usd),
        }
        pct, used = bucket_map.get(bot_type, (12.0, 0.0))
        bucket_limit = allocation.total_capital_usd * (pct / 100)
        available = max(bucket_limit - used, 0)

        if available < 1.0:
            return RiskAssessment(
                approved=False, position_size_usd=0, stop_loss_price=0,
                take_profit_price=None, risk_reward_ratio=0, max_loss_usd=0,
                reasoning=f"Bucket {bot_type} fully allocated (${used:.2f}/${bucket_limit:.2f})", bucket=bot_type,
            )

        risk_pct_map = {
            "scalper": 8.0, "swing": 10.0, "long_term": 10.0,
            "grid": 8.0, "mean_reversion": 8.0, "momentum": 10.0, "dca": 8.0,
        }
        base_risk = risk_pct_map.get(bot_type, 8.0)
        risk_pct = base_risk * min(max(signal_confidence, 0.5), 1.0)

        sl_multiplier_map = {
            "scalper": 1.0, "swing": 1.5, "long_term": 2.0,
            "grid": 0.8, "mean_reversion": 1.0, "momentum": 1.2, "dca": 1.5,
        }
        sl_multiplier = sl_multiplier_map.get(bot_type, 1.5)

        stop_loss = self.calculate_stop_loss(entry_price, side, atr, sl_multiplier)
        position_size = self.calculate_position_size(available, risk_pct, entry_price, stop_loss, fee_rate)
        position_size = min(position_size, available)

        max_per_trade = allocation.total_capital_usd * 0.35
        position_size = min(position_size, max_per_trade)

        min_pos = 1.0
        if position_size < min_pos:
            return RiskAssessment(
                approved=False, position_size_usd=0, stop_loss_price=stop_loss,
                take_profit_price=None, risk_reward_ratio=0, max_loss_usd=0,
                reasoning="Position size too small", bucket=bot_type,
            )

        rr_ratio_map = {
            "scalper": 1.5, "swing": 2.0, "long_term": 3.0,
            "grid": 1.0, "mean_reversion": 1.5, "momentum": 2.5, "dca": 1.5,
        }
        rr_ratio = rr_ratio_map.get(bot_type, 2.0)
        take_profit = self.calculate_take_profit(entry_price, stop_loss, side, rr_ratio)

        sl_pct = abs(entry_price - stop_loss) / entry_price if entry_price > 0 else 0.02
        max_loss = position_size * sl_pct
        max_loss += position_size * fee_rate * 2

        await self.reserve_bucket(bot_type, position_size)

        logger.info(
            f"RISK: {bot_type} approved ${position_size:.2f} "
            f"(balance=${real_balance:.2f}, bucket_avail=${available:.2f}, "
            f"risk={risk_pct:.1f}%, max_loss=${max_loss:.2f})"
        )

        return RiskAssessment(
            approved=True,
            position_size_usd=round(position_size, 2),
            stop_loss_price=round(stop_loss, 8),
            take_profit_price=round(take_profit, 8),
            risk_reward_ratio=rr_ratio,
            max_loss_usd=round(max_loss, 2),
            reasoning=f"Approved: {risk_pct:.1f}% risk, RR {rr_ratio}, conf {signal_confidence:.2f}, pos ${position_size:.2f}",
            bucket=bot_type,
        )

    async def rebalance_buckets(self, total_capital: float, open_positions: dict):
        allocation = await self.get_bucket_allocation()
        allocation.total_capital_usd = total_capital

        from app.core.store import trade_store
        pnl_by_bot = trade_store.pnl_by_bot()
        bot_types = ["scalper", "swing", "long_term", "arbitrage", "grid", "mean_reversion", "momentum", "dca"]
        MIN_PCT = 5.0
        TOTAL_PCT = 100.0
        distributable = TOTAL_PCT - (MIN_PCT * len(bot_types))

        scores = {}
        for bt in bot_types:
            data = pnl_by_bot.get(bt, {"pnl_usd": 0, "trades": 0})
            pnl = data.get("pnl_usd", 0)
            trades = data.get("trades", 0)
            if trades > 0:
                win_count = sum(
                    1 for t in trade_store.get_closed_trades()
                    if t.get("bot_type") == bt and t.get("pnl_usd", 0) > 0
                )
                wr = win_count / trades
            else:
                wr = 0.0
            scores[bt] = max(pnl * (0.5 + wr), 0)

        total_score = sum(scores.values())
        if total_score > 0:
            for bt in bot_types:
                bonus = (scores[bt] / total_score) * distributable
                setattr(allocation, f"{bt}_pct", round(MIN_PCT + bonus, 1))
        else:
            equal_share = TOTAL_PCT / len(bot_types)
            for bt in bot_types:
                setattr(allocation, f"{bt}_pct", equal_share)

        assigned = sum(getattr(allocation, f"{bt}_pct") for bt in bot_types)
        if abs(assigned - TOTAL_PCT) > 0.1:
            diff = TOTAL_PCT - assigned
            best_bot = max(bot_types, key=lambda bt: scores.get(bt, 0))
            current = getattr(allocation, f"{best_bot}_pct")
            setattr(allocation, f"{best_bot}_pct", round(current + diff, 1))

        await self.save_bucket_allocation(allocation)
        logger.info(
            f"REBALANCE: total=${total_capital:.2f} "
            f"scalper={allocation.scalper_pct}% swing={allocation.swing_pct}% "
            f"long_term={allocation.long_term_pct}% arb={allocation.arbitrage_pct}%"
        )
        return allocation
