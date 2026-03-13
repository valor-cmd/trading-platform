import logging
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

EXCHANGE_FEE_TIERS = {
    "binance": {"maker": 0.001, "taker": 0.001, "bnb_discount": 0.00075},
    "coinbase": {"maker": 0.004, "taker": 0.006},
    "kraken": {"maker": 0.0016, "taker": 0.0026},
    "kucoin": {"maker": 0.001, "taker": 0.001},
    "okx": {"maker": 0.0008, "taker": 0.001},
    "bybit": {"maker": 0.001, "taker": 0.001},
    "gateio": {"maker": 0.002, "taker": 0.002},
    "bitget": {"maker": 0.001, "taker": 0.001},
    "mexc": {"maker": 0.0, "taker": 0.001},
}

DEX_GAS_ESTIMATES = {
    "ethereum": {
        "uniswap": {"gas_units": 150000, "priority_fee_gwei": 2},
        "sushiswap": {"gas_units": 160000, "priority_fee_gwei": 2},
        "0x": {"gas_units": 120000, "priority_fee_gwei": 2},
    },
    "solana": {
        "jupiter": {"lamports": 5000, "priority_fee": 0.00001},
        "raydium": {"lamports": 5000, "priority_fee": 0.00001},
    },
}


@dataclass
class TradeFeeSummary:
    exchange: str
    trading_pair: str
    side: str
    amount: float
    price: float
    maker_fee_rate: float
    taker_fee_rate: float
    actual_fee_usd: float
    fee_type: str
    gas_cost_usd: Optional[float] = None
    slippage_pct: Optional[float] = None
    slippage_usd: Optional[float] = None
    total_cost_usd: float = 0.0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        self.total_cost_usd = self.actual_fee_usd + (self.gas_cost_usd or 0) + (self.slippage_usd or 0)


class FeeTracker:
    def __init__(self):
        self._trade_fees: list[TradeFeeSummary] = []
        self._cumulative_fees_usd: float = 0.0
        self._cumulative_gas_usd: float = 0.0
        self._cumulative_slippage_usd: float = 0.0

    def get_exchange_fees(self, exchange: str) -> dict:
        return EXCHANGE_FEE_TIERS.get(exchange, {"maker": 0.001, "taker": 0.001})

    def estimate_cex_fee(
        self,
        exchange: str,
        amount: float,
        price: float,
        is_maker: bool = False,
    ) -> float:
        fees = self.get_exchange_fees(exchange)
        rate = fees.get("maker" if is_maker else "taker", 0.001)
        return amount * price * rate

    def estimate_dex_gas(
        self,
        chain: str,
        connector: str,
        gas_price_gwei: float = 30,
        eth_price_usd: float = 3000,
        sol_price_usd: float = 150,
    ) -> float:
        chain_estimates = DEX_GAS_ESTIMATES.get(chain, {})
        connector_est = chain_estimates.get(connector, {})

        if chain == "ethereum":
            gas_units = connector_est.get("gas_units", 150000)
            priority = connector_est.get("priority_fee_gwei", 2)
            total_gwei = gas_units * (gas_price_gwei + priority)
            eth_cost = total_gwei / 1e9
            return eth_cost * eth_price_usd
        elif chain == "solana":
            base_lamports = connector_est.get("lamports", 5000)
            priority = connector_est.get("priority_fee", 0.00001)
            sol_cost = (base_lamports / 1e9) + priority
            return sol_cost * sol_price_usd
        return 0.0

    def record_trade_fee(
        self,
        exchange: str,
        trading_pair: str,
        side: str,
        amount: float,
        price: float,
        actual_fee_usd: float,
        fee_type: str = "taker",
        gas_cost_usd: Optional[float] = None,
        slippage_pct: Optional[float] = None,
    ) -> TradeFeeSummary:
        fees = self.get_exchange_fees(exchange)
        slippage_usd = None
        if slippage_pct is not None:
            slippage_usd = amount * price * (slippage_pct / 100)

        summary = TradeFeeSummary(
            exchange=exchange,
            trading_pair=trading_pair,
            side=side,
            amount=amount,
            price=price,
            maker_fee_rate=fees.get("maker", 0.001),
            taker_fee_rate=fees.get("taker", 0.001),
            actual_fee_usd=actual_fee_usd,
            fee_type=fee_type,
            gas_cost_usd=gas_cost_usd,
            slippage_pct=slippage_pct,
            slippage_usd=slippage_usd,
        )

        self._trade_fees.append(summary)
        self._cumulative_fees_usd += actual_fee_usd
        self._cumulative_gas_usd += gas_cost_usd or 0
        self._cumulative_slippage_usd += slippage_usd or 0

        return summary

    def get_fee_summary(self) -> dict:
        by_exchange: dict[str, dict] = {}
        for tf in self._trade_fees:
            ex = tf.exchange
            if ex not in by_exchange:
                by_exchange[ex] = {
                    "trades": 0,
                    "total_fees_usd": 0,
                    "total_gas_usd": 0,
                    "total_slippage_usd": 0,
                    "total_cost_usd": 0,
                }
            by_exchange[ex]["trades"] += 1
            by_exchange[ex]["total_fees_usd"] += tf.actual_fee_usd
            by_exchange[ex]["total_gas_usd"] += tf.gas_cost_usd or 0
            by_exchange[ex]["total_slippage_usd"] += tf.slippage_usd or 0
            by_exchange[ex]["total_cost_usd"] += tf.total_cost_usd

        for v in by_exchange.values():
            for k in v:
                if k != "trades":
                    v[k] = round(v[k], 5)

        return {
            "total_trades": len(self._trade_fees),
            "cumulative_fees_usd": round(self._cumulative_fees_usd, 5),
            "cumulative_gas_usd": round(self._cumulative_gas_usd, 5),
            "cumulative_slippage_usd": round(self._cumulative_slippage_usd, 5),
            "cumulative_total_cost_usd": round(
                self._cumulative_fees_usd + self._cumulative_gas_usd + self._cumulative_slippage_usd, 5
            ),
            "by_exchange": by_exchange,
        }

    def get_recent_fees(self, limit: int = 50) -> list[dict]:
        recent = self._trade_fees[-limit:]
        return [
            {
                "exchange": f.exchange,
                "trading_pair": f.trading_pair,
                "side": f.side,
                "amount": f.amount,
                "price": f.price,
                "fee_usd": round(f.actual_fee_usd, 5),
                "gas_usd": round(f.gas_cost_usd, 5) if f.gas_cost_usd else None,
                "slippage_pct": f.slippage_pct,
                "slippage_usd": round(f.slippage_usd, 5) if f.slippage_usd else None,
                "total_cost_usd": round(f.total_cost_usd, 5),
                "fee_type": f.fee_type,
                "timestamp": f.timestamp,
            }
            for f in recent
        ]


fee_tracker = FeeTracker()
