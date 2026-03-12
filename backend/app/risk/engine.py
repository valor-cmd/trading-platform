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
    scalper_pct: float = 20.0
    swing_pct: float = 40.0
    long_term_pct: float = 40.0
    scalper_used_usd: float = 0.0
    swing_used_usd: float = 0.0
    long_term_used_usd: float = 0.0
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
        if bot_type == "scalper":
            allocation.scalper_used_usd += amount_usd
        elif bot_type == "swing":
            allocation.swing_used_usd += amount_usd
        elif bot_type == "long_term":
            allocation.long_term_used_usd += amount_usd
        await self.save_bucket_allocation(allocation)

    async def release_bucket(self, bot_type: str, amount_usd: float):
        allocation = await self.get_bucket_allocation()
        if bot_type == "scalper":
            allocation.scalper_used_usd = max(0, allocation.scalper_used_usd - amount_usd)
        elif bot_type == "swing":
            allocation.swing_used_usd = max(0, allocation.swing_used_usd - amount_usd)
        elif bot_type == "long_term":
            allocation.long_term_used_usd = max(0, allocation.long_term_used_usd - amount_usd)
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
        if real_balance > 0:
            allocation.total_capital_usd = min(allocation.total_capital_usd, real_balance)

        bucket_map = {
            "scalper": (allocation.scalper_pct, allocation.scalper_used_usd),
            "swing": (allocation.swing_pct, allocation.swing_used_usd),
            "long_term": (allocation.long_term_pct, allocation.long_term_used_usd),
        }
        pct, used = bucket_map.get(bot_type, (20.0, 0.0))
        bucket_limit = allocation.total_capital_usd * (pct / 100)
        available = max(bucket_limit - used, 0)

        if real_balance > 0:
            available = min(available, max(real_balance * 0.9, 0))

        if available < 1.0:
            return RiskAssessment(
                approved=False, position_size_usd=0, stop_loss_price=0,
                take_profit_price=None, risk_reward_ratio=0, max_loss_usd=0,
                reasoning=f"Bucket {bot_type} fully allocated (${used:.2f}/${bucket_limit:.2f})", bucket=bot_type,
            )

        risk_pct_map = {"scalper": 0.5, "swing": 1.0, "long_term": 1.5}
        risk_pct = risk_pct_map.get(bot_type, 1.0) * min(max(signal_confidence, 0.3), 1.0)

        sl_multiplier_map = {"scalper": 1.0, "swing": 1.5, "long_term": 2.0}
        sl_multiplier = sl_multiplier_map.get(bot_type, 1.5)

        stop_loss = self.calculate_stop_loss(entry_price, side, atr, sl_multiplier)
        position_size = self.calculate_position_size(available, risk_pct, entry_price, stop_loss, fee_rate)
        position_size = min(position_size, available)

        max_per_trade = allocation.total_capital_usd * 0.05
        position_size = min(position_size, max_per_trade)

        if position_size < 0.01:
            return RiskAssessment(
                approved=False, position_size_usd=0, stop_loss_price=stop_loss,
                take_profit_price=None, risk_reward_ratio=0, max_loss_usd=0,
                reasoning="Position size too small", bucket=bot_type,
            )

        rr_ratio_map = {"scalper": 1.5, "swing": 2.0, "long_term": 3.0}
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
        real_balance = self._get_real_usdt_balance()
        if real_balance > 0:
            total_capital = min(total_capital, real_balance)

        allocation = await self.get_bucket_allocation()
        allocation.total_capital_usd = total_capital
        allocation.scalper_pct = 20.0
        allocation.swing_pct = 40.0
        allocation.long_term_pct = 40.0
        await self.save_bucket_allocation(allocation)
        return allocation
