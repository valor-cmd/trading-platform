import asyncio
import logging
from datetime import datetime, timezone

from app.core.store import store, trade_store
from app.exchange.registry import ExchangeRegistry
from app.arbitrage.engine import ArbitrageEngine, ArbitrageConfig
from app.risk.engine import RiskEngine

logger = logging.getLogger(__name__)


class ArbitrageBot:
    def __init__(self, registry: ExchangeRegistry, risk_engine: RiskEngine, config: ArbitrageConfig = None):
        self.registry = registry
        self.risk = risk_engine
        self.arb_engine = ArbitrageEngine(registry, config or ArbitrageConfig())
        self.running = False
        self.trades_executed = 0
        self._cycle_count = 0

    async def run_cycle(self):
        self._cycle_count += 1
        opportunities = await self.arb_engine.scan_all()
        actionable = [o for o in opportunities if o.is_actionable]

        if not actionable:
            return

        if await self.risk.check_circuit_breaker():
            logger.warning("ArbitrageBot: circuit breaker active, skipping")
            return

        for opp in actionable[:3]:
            try:
                await self.execute_arb(opp)
            except Exception as e:
                logger.error(f"ArbitrageBot execution error: {e}")

    async def execute_arb(self, opp):
        buy_adapter = self.registry.get(opp.buy_exchange)
        sell_adapter = self.registry.get(opp.sell_exchange)
        if not buy_adapter or not sell_adapter:
            return

        real_balance = self.risk._get_real_usdt_balance()
        allocation = await self.risk.get_bucket_allocation()
        cap = min(allocation.total_capital_usd, real_balance) if real_balance > 0 else allocation.total_capital_usd
        available = cap * 0.05
        if available < 1.0:
            return

        position_usd = min(available, self.arb_engine.config.max_position_usd)
        amount = position_usd / opp.buy_price

        max_slip = self.arb_engine.config.max_slippage_pct / 100.0

        buy_order = await buy_adapter.create_order(opp.symbol, "buy", amount, opp.buy_price)
        buy_slippage = abs(buy_order.price - opp.buy_price) / opp.buy_price if opp.buy_price > 0 else 0
        if buy_slippage > max_slip:
            logger.warning(f"ARB ABORTED: buy slippage {buy_slippage*100:.2f}% > max {self.arb_engine.config.max_slippage_pct}% for {opp.symbol}")
            return

        sell_order = await sell_adapter.create_order(opp.symbol, "sell", amount, opp.sell_price)
        sell_slippage = abs(opp.sell_price - sell_order.price) / opp.sell_price if opp.sell_price > 0 else 0
        if sell_slippage > max_slip:
            logger.warning(f"ARB ABORTED: sell slippage {sell_slippage*100:.2f}% > max {self.arb_engine.config.max_slippage_pct}% for {opp.symbol}")
            return

        revenue = sell_order.cost - sell_order.fee
        cost = buy_order.cost + buy_order.fee
        pnl = revenue - cost

        self.trades_executed += 1
        await self.risk.update_daily_pnl(pnl)

        trade_record = {
            "bot_type": "arbitrage",
            "exchange": f"{opp.buy_exchange}->{opp.sell_exchange}",
            "symbol": opp.symbol,
            "side": "arb",
            "entry_price": opp.buy_price,
            "exit_price": opp.sell_price,
            "quantity": amount,
            "leverage": 1.0,
            "stop_loss_price": 0,
            "take_profit_price": 0,
            "entry_fee_usd": buy_order.fee,
            "exit_fee_usd": sell_order.fee,
            "pnl_usd": round(pnl, 4),
            "bucket": "arbitrage",
            "slippage_buy_pct": round(buy_slippage * 100, 4),
            "slippage_sell_pct": round(sell_slippage * 100, 4),
            "reasoning": f"Arb: {opp.buy_exchange}->{opp.sell_exchange} spread={opp.spread_pct:.2f}% profit={opp.estimated_profit_pct:.2f}% slip={buy_slippage*100:.2f}%+{sell_slippage*100:.2f}%",
            "is_paper": True,
            "status": "closed",
        }
        t = trade_store.add_trade(trade_record)
        trade_store.close_trade(t["id"], opp.sell_price, round(pnl, 4), sell_order.fee, "closed")

        logger.info(
            f"ARB EXECUTED: {opp.symbol} buy@{opp.buy_exchange} ${opp.buy_price:.6f} -> "
            f"sell@{opp.sell_exchange} ${opp.sell_price:.6f} PnL=${pnl:.4f}"
        )

    async def start(self, interval_seconds: int = 10):
        self.running = True
        logger.info(f"ArbitrageBot STARTED (interval={interval_seconds}s)")
        while self.running:
            try:
                await self.run_cycle()
            except Exception as e:
                logger.error(f"ArbitrageBot cycle error: {e}")
            await asyncio.sleep(interval_seconds)
        logger.info("ArbitrageBot STOPPED")

    def stop(self):
        self.running = False

    def status(self) -> dict:
        return {
            "running": self.running,
            "cycles": self._cycle_count,
            "trades_executed": self.trades_executed,
            "current_opportunities": len(self.arb_engine.opportunities),
            "actionable": len([o for o in self.arb_engine.opportunities if o.is_actionable]),
        }
