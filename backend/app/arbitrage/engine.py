import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.exchange.registry import ExchangeRegistry
from app.exchange.adapters.base import TickerData, ExchangeType

logger = logging.getLogger(__name__)

WITHDRAWAL_FEES_USD = {
    "binance": 1.0,
    "coinbase": 2.0,
    "kraken": 1.5,
    "kucoin": 1.0,
    "bybit": 1.0,
    "okx": 0.8,
    "gateio": 1.0,
    "bitget": 1.0,
    "mexc": 1.0,
    "htx": 1.5,
    "solana_dex": 0.01,
    "xrpl_dex": 0.001,
    "hedera_dex": 0.05,
}

MIN_VOLUME_24H_USD = 50_000


@dataclass
class ArbitrageOpportunity:
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    spread_pct: float
    estimated_profit_pct: float
    buy_fee_pct: float
    sell_fee_pct: float
    volume_ok: bool
    timestamp: str
    is_actionable: bool = False
    withdrawal_fee_usd: float = 0.0
    transfer_risk_pct: float = 0.0
    net_profit_usd: float = 0.0
    min_volume_24h: float = 0.0


@dataclass
class ArbitrageConfig:
    min_spread_pct: float = 1.5
    min_profit_after_fees_pct: float = 0.3
    max_position_usd: float = 500.0
    scan_interval_seconds: int = 10
    include_dex: bool = True
    slippage_buffer_pct: float = 0.8
    max_slippage_pct: float = 1.0
    transfer_risk_pct: float = 0.3
    min_volume_24h_usd: float = 50_000.0
    min_price_usd: float = 0.001


class ArbitrageEngine:
    def __init__(self, registry: ExchangeRegistry, config: Optional[ArbitrageConfig] = None):
        self.registry = registry
        self.config = config or ArbitrageConfig()
        self.opportunities: list[ArbitrageOpportunity] = []
        self._history: list[ArbitrageOpportunity] = []
        self.running = False
        self._scan_count = 0

    async def scan_pair(self, symbol: str) -> list[ArbitrageOpportunity]:
        tickers = await self.registry.fetch_ticker_all_exchanges(symbol)
        if len(tickers) < 2:
            return []

        opps = []
        for i, t1 in enumerate(tickers):
            for t2 in tickers[i + 1:]:
                opp = self._evaluate_pair(symbol, t1, t2)
                if opp:
                    opps.append(opp)
        return opps

    def _get_withdrawal_fee(self, exchange_id: str) -> float:
        return WITHDRAWAL_FEES_USD.get(exchange_id, 2.0)

    def _evaluate_pair(self, symbol: str, t1: TickerData, t2: TickerData) -> Optional[ArbitrageOpportunity]:
        if t1.last <= 0 or t2.last <= 0:
            return None

        if t1.last < self.config.min_price_usd or t2.last < self.config.min_price_usd:
            return None

        price_ratio = max(t1.last, t2.last) / min(t1.last, t2.last)
        if price_ratio > 1.5:
            return None

        min_vol = min(t1.volume_24h, t2.volume_24h)
        avg_price = (t1.last + t2.last) / 2
        volume_usd = min_vol * avg_price if avg_price > 0 else 0
        volume_ok = volume_usd >= self.config.min_volume_24h_usd

        if not volume_ok:
            return None

        if t1.ask > 0 and t2.bid > 0:
            buy_at_1_sell_at_2 = (t2.bid - t1.ask) / t1.ask * 100
        else:
            buy_at_1_sell_at_2 = (t2.last - t1.last) / t1.last * 100

        if t2.ask > 0 and t1.bid > 0:
            buy_at_2_sell_at_1 = (t1.bid - t2.ask) / t2.ask * 100
        else:
            buy_at_2_sell_at_1 = (t1.last - t2.last) / t2.last * 100

        if buy_at_1_sell_at_2 > buy_at_2_sell_at_1:
            spread = buy_at_1_sell_at_2
            buy_exchange = t1.exchange_id
            sell_exchange = t2.exchange_id
            buy_price = t1.ask if t1.ask > 0 else t1.last
            sell_price = t2.bid if t2.bid > 0 else t2.last
        else:
            spread = buy_at_2_sell_at_1
            buy_exchange = t2.exchange_id
            sell_exchange = t1.exchange_id
            buy_price = t2.ask if t2.ask > 0 else t2.last
            sell_price = t1.bid if t1.bid > 0 else t1.last

        if spread < self.config.min_spread_pct:
            return None

        if spread > 8.0:
            return None

        buy_adapter = self.registry.get(buy_exchange)
        sell_adapter = self.registry.get(sell_exchange)
        buy_fee = 0.001
        sell_fee = 0.001
        if buy_adapter:
            pair = buy_adapter.get_pair(symbol)
            if pair:
                buy_fee = pair.fee_rate
        if sell_adapter:
            pair = sell_adapter.get_pair(symbol)
            if pair:
                sell_fee = pair.fee_rate

        total_fees_pct = (buy_fee + sell_fee) * 100
        slippage = self.config.slippage_buffer_pct
        transfer_risk = self.config.transfer_risk_pct

        withdrawal_fee = self._get_withdrawal_fee(buy_exchange)
        position_usd = min(self.config.max_position_usd, 100.0)
        withdrawal_fee_pct = (withdrawal_fee / position_usd) * 100 if position_usd > 0 else 0

        is_cross_type = False
        if buy_adapter and sell_adapter:
            is_cross_type = buy_adapter.exchange_type != sell_adapter.exchange_type
        if is_cross_type:
            slippage += 0.5
            transfer_risk += 0.3

        profit_after = spread - total_fees_pct - slippage - transfer_risk - withdrawal_fee_pct

        net_profit_usd = position_usd * (profit_after / 100)

        is_actionable = profit_after >= self.config.min_profit_after_fees_pct and net_profit_usd > 0.10

        return ArbitrageOpportunity(
            symbol=symbol,
            buy_exchange=buy_exchange,
            sell_exchange=sell_exchange,
            buy_price=buy_price,
            sell_price=sell_price,
            spread_pct=round(spread, 4),
            estimated_profit_pct=round(profit_after, 4),
            buy_fee_pct=round(buy_fee * 100, 4),
            sell_fee_pct=round(sell_fee * 100, 4),
            volume_ok=volume_ok,
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_actionable=is_actionable,
            withdrawal_fee_usd=withdrawal_fee,
            transfer_risk_pct=round(transfer_risk, 4),
            net_profit_usd=round(net_profit_usd, 4),
            min_volume_24h=round(volume_usd, 2),
        )

    async def scan_all(self) -> list[ArbitrageOpportunity]:
        common_pairs = self.registry.find_common_pairs()
        all_opps = []

        tasks = []
        for symbol in common_pairs:
            tasks.append(self.scan_pair(symbol))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                all_opps.extend(result)

        all_opps.sort(key=lambda o: o.estimated_profit_pct, reverse=True)
        self.opportunities = all_opps
        self._history.extend([o for o in all_opps if o.is_actionable])
        if len(self._history) > 1000:
            self._history = self._history[-500:]
        self._scan_count += 1

        actionable = [o for o in all_opps if o.is_actionable]
        if actionable:
            logger.info(f"Arb scan #{self._scan_count}: {len(all_opps)} opportunities, {len(actionable)} actionable")
            for o in actionable[:3]:
                logger.info(
                    f"  {o.symbol}: buy@{o.buy_exchange} ${o.buy_price:.6f} -> sell@{o.sell_exchange} ${o.sell_price:.6f} "
                    f"(spread={o.spread_pct:.2f}% net={o.estimated_profit_pct:.2f}% ~${o.net_profit_usd:.2f} "
                    f"vol24h=${o.min_volume_24h:.0f} wd_fee=${o.withdrawal_fee_usd:.2f})"
                )

        return all_opps

    async def run(self):
        self.running = True
        logger.info(f"Arbitrage engine STARTED (scan every {self.config.scan_interval_seconds}s)")
        while self.running:
            try:
                await self.scan_all()
            except Exception as e:
                logger.error(f"Arbitrage scan error: {e}")
            await asyncio.sleep(self.config.scan_interval_seconds)
        logger.info("Arbitrage engine STOPPED")

    def stop(self):
        self.running = False

    def get_opportunities(self, min_profit: float = 0.0, limit: int = 50) -> list[dict]:
        return [
            {
                "symbol": o.symbol,
                "buy_exchange": o.buy_exchange,
                "sell_exchange": o.sell_exchange,
                "buy_price": o.buy_price,
                "sell_price": o.sell_price,
                "spread_pct": o.spread_pct,
                "estimated_profit_pct": o.estimated_profit_pct,
                "buy_fee_pct": o.buy_fee_pct,
                "sell_fee_pct": o.sell_fee_pct,
                "is_actionable": o.is_actionable,
                "timestamp": o.timestamp,
                "withdrawal_fee_usd": o.withdrawal_fee_usd,
                "transfer_risk_pct": o.transfer_risk_pct,
                "net_profit_usd": o.net_profit_usd,
                "volume_24h_usd": o.min_volume_24h,
            }
            for o in self.opportunities
            if o.estimated_profit_pct >= min_profit
        ][:limit]

    def get_history(self, limit: int = 100) -> list[dict]:
        return [
            {
                "symbol": o.symbol,
                "buy_exchange": o.buy_exchange,
                "sell_exchange": o.sell_exchange,
                "spread_pct": o.spread_pct,
                "estimated_profit_pct": o.estimated_profit_pct,
                "net_profit_usd": o.net_profit_usd,
                "timestamp": o.timestamp,
            }
            for o in self._history[-limit:]
        ]
