from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trade import Trade, Deposit, Withdrawal, PortfolioSnapshot, TradeStatus


class AccountingTracker:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_trade_open(self, trade_data: dict) -> Trade:
        trade = Trade(**trade_data)
        self.db.add(trade)
        await self.db.commit()
        await self.db.refresh(trade)
        return trade

    async def record_trade_close(
        self, trade_id: int, exit_price: float, pnl_usd: float, exit_fee: float, status: TradeStatus
    ) -> Trade:
        result = await self.db.execute(select(Trade).where(Trade.id == trade_id))
        trade = result.scalar_one()
        trade.exit_price = exit_price
        trade.pnl_usd = pnl_usd
        trade.pnl_pct = (pnl_usd / (trade.entry_price * trade.quantity)) * 100
        trade.exit_fee_usd = exit_fee
        trade.status = status
        trade.closed_at = datetime.now(timezone.utc)
        await self.db.commit()
        return trade

    async def record_deposit(self, deposit_data: dict) -> Deposit:
        deposit = Deposit(**deposit_data)
        self.db.add(deposit)
        await self.db.commit()
        await self.db.refresh(deposit)
        return deposit

    async def record_withdrawal(self, withdrawal_data: dict) -> Withdrawal:
        withdrawal = Withdrawal(**withdrawal_data)
        self.db.add(withdrawal)
        await self.db.commit()
        await self.db.refresh(withdrawal)
        return withdrawal

    async def get_total_pnl(self, start: Optional[datetime] = None, end: Optional[datetime] = None) -> dict:
        query = select(
            func.sum(Trade.pnl_usd).label("total_pnl"),
            func.sum(Trade.entry_fee_usd + Trade.exit_fee_usd).label("total_fees"),
            func.count(Trade.id).label("total_trades"),
        ).where(Trade.status.in_([TradeStatus.CLOSED, TradeStatus.STOPPED_OUT]))

        if start:
            query = query.where(Trade.closed_at >= start)
        if end:
            query = query.where(Trade.closed_at <= end)

        result = await self.db.execute(query)
        row = result.one()
        return {
            "total_pnl_usd": row.total_pnl or 0.0,
            "total_fees_usd": row.total_fees or 0.0,
            "net_pnl_usd": (row.total_pnl or 0.0) - (row.total_fees or 0.0),
            "total_trades": row.total_trades or 0,
        }

    async def get_total_deposits(self) -> float:
        result = await self.db.execute(select(func.sum(Deposit.amount_usd)))
        return result.scalar() or 0.0

    async def get_total_withdrawals(self) -> float:
        result = await self.db.execute(select(func.sum(Withdrawal.amount_usd)))
        return result.scalar() or 0.0

    async def get_win_rate(self) -> dict:
        total = await self.db.execute(
            select(func.count(Trade.id)).where(
                Trade.status.in_([TradeStatus.CLOSED, TradeStatus.STOPPED_OUT])
            )
        )
        winners = await self.db.execute(
            select(func.count(Trade.id)).where(
                Trade.status.in_([TradeStatus.CLOSED, TradeStatus.STOPPED_OUT]),
                Trade.pnl_usd > 0,
            )
        )
        total_count = total.scalar() or 0
        win_count = winners.scalar() or 0
        return {
            "total_trades": total_count,
            "winning_trades": win_count,
            "losing_trades": total_count - win_count,
            "win_rate": (win_count / total_count * 100) if total_count > 0 else 0.0,
        }

    async def get_pnl_by_bot(self) -> dict:
        result = await self.db.execute(
            select(
                Trade.bot_type,
                func.sum(Trade.pnl_usd).label("pnl"),
                func.count(Trade.id).label("count"),
            )
            .where(Trade.status.in_([TradeStatus.CLOSED, TradeStatus.STOPPED_OUT]))
            .group_by(Trade.bot_type)
        )
        return {row.bot_type: {"pnl_usd": row.pnl, "trades": row.count} for row in result.all()}

    async def get_pnl_by_date(self, days: int = 30) -> list[dict]:
        start = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self.db.execute(
            select(
                func.date(Trade.closed_at).label("date"),
                func.sum(Trade.pnl_usd).label("pnl"),
                func.count(Trade.id).label("trades"),
            )
            .where(
                Trade.status.in_([TradeStatus.CLOSED, TradeStatus.STOPPED_OUT]),
                Trade.closed_at >= start,
            )
            .group_by(func.date(Trade.closed_at))
            .order_by(func.date(Trade.closed_at))
        )
        return [{"date": str(row.date), "pnl_usd": row.pnl, "trades": row.trades} for row in result.all()]

    async def take_portfolio_snapshot(self, total_value: float) -> PortfolioSnapshot:
        deposits = await self.get_total_deposits()
        withdrawals = await self.get_total_withdrawals()
        pnl_data = await self.get_total_pnl()
        open_count = await self.db.execute(
            select(func.count(Trade.id)).where(Trade.status == TradeStatus.OPEN)
        )
        snapshot = PortfolioSnapshot(
            total_value_usd=total_value,
            total_deposits_usd=deposits,
            total_withdrawals_usd=withdrawals,
            total_pnl_usd=pnl_data["total_pnl_usd"],
            total_fees_usd=pnl_data["total_fees_usd"],
            open_positions=open_count.scalar() or 0,
        )
        self.db.add(snapshot)
        await self.db.commit()
        return snapshot

    async def get_full_accounting(self) -> dict:
        pnl = await self.get_total_pnl()
        deposits = await self.get_total_deposits()
        withdrawals = await self.get_total_withdrawals()
        win_rate = await self.get_win_rate()
        by_bot = await self.get_pnl_by_bot()
        by_date = await self.get_pnl_by_date()

        return {
            "summary": {
                "total_deposits_usd": deposits,
                "total_withdrawals_usd": withdrawals,
                "net_deposits_usd": deposits - withdrawals,
                "total_pnl_usd": pnl["total_pnl_usd"],
                "total_fees_usd": pnl["total_fees_usd"],
                "net_pnl_usd": pnl["net_pnl_usd"],
                "total_trades": pnl["total_trades"],
                "account_value_usd": (deposits - withdrawals) + pnl["net_pnl_usd"],
            },
            "win_rate": win_rate,
            "pnl_by_bot": by_bot,
            "pnl_by_date": by_date,
        }
