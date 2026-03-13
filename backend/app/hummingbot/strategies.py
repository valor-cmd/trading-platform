import logging
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class StrategyType(str, Enum):
    PURE_MARKET_MAKING = "pure_market_making"
    GRID = "grid"
    DCA = "dca"
    ARBITRAGE = "arbitrage"
    DIRECTIONAL = "directional"


class ExecutorType(str, Enum):
    POSITION = "position_executor"
    GRID = "grid_executor"
    DCA = "dca_executor"
    ARBITRAGE = "arbitrage_executor"


@dataclass
class TripleBarrierConfig:
    stop_loss: float = 0.03
    take_profit: float = 0.06
    time_limit: int = 3600
    trailing_stop_activation_delta: Optional[float] = None
    trailing_stop_trailing_delta: Optional[float] = None


@dataclass
class PMMStrategyConfig:
    connector: str = "binance"
    trading_pair: str = "BTC-USDT"
    bid_spread: float = 0.01
    ask_spread: float = 0.01
    order_amount: float = 0.001
    order_refresh_time: int = 15
    order_levels: int = 1
    order_level_spread: float = 0.005
    inventory_skew_enabled: bool = True
    inventory_target_base_pct: float = 50.0
    add_transaction_costs: bool = True
    triple_barrier: TripleBarrierConfig = field(default_factory=TripleBarrierConfig)

    def to_hbot_config(self, paper: bool = True) -> dict:
        connector = f"{self.connector}_paper_trade" if paper else self.connector
        return {
            "strategy": "pure_market_making",
            "connector": connector,
            "market": self.trading_pair,
            "bid_spread": self.bid_spread,
            "ask_spread": self.ask_spread,
            "order_amount": self.order_amount,
            "order_refresh_time": self.order_refresh_time,
            "order_levels": self.order_levels,
            "order_level_spread": self.order_level_spread,
            "inventory_skew_enabled": self.inventory_skew_enabled,
            "inventory_target_base_pct": self.inventory_target_base_pct,
            "add_transaction_costs": self.add_transaction_costs,
        }


@dataclass
class GridStrategyConfig:
    connector: str = "binance"
    trading_pair: str = "BTC-USDT"
    start_price: float = 0.0
    end_price: float = 0.0
    total_amount_quote: float = 1000.0
    num_levels: int = 10
    min_spread: float = 0.005
    add_transaction_costs: bool = True
    triple_barrier: TripleBarrierConfig = field(default_factory=TripleBarrierConfig)

    def to_executor_config(self, paper: bool = True) -> dict:
        connector = f"{self.connector}_paper_trade" if paper else self.connector
        return {
            "type": "grid_executor",
            "connector_name": connector,
            "trading_pair": self.trading_pair,
            "start_price": self.start_price,
            "end_price": self.end_price,
            "total_amount_quote": self.total_amount_quote,
            "min_spread_between_orders": self.min_spread,
            "n_levels": self.num_levels,
        }


@dataclass
class DCAStrategyConfig:
    connector: str = "binance"
    trading_pair: str = "BTC-USDT"
    side: str = "buy"
    total_amount_quote: float = 1000.0
    num_orders: int = 5
    price_spread: float = 0.01
    time_limit: int = 86400
    stop_loss: float = 0.05
    take_profit: float = 0.10
    add_transaction_costs: bool = True

    def to_executor_config(self, paper: bool = True) -> dict:
        connector = f"{self.connector}_paper_trade" if paper else self.connector
        per_order = self.total_amount_quote / self.num_orders
        amounts = [per_order] * self.num_orders
        return {
            "type": "dca_executor",
            "connector_name": connector,
            "trading_pair": self.trading_pair,
            "side": self.side,
            "amounts_quote": amounts,
            "take_profit": self.take_profit,
            "stop_loss": self.stop_loss,
            "time_limit": self.time_limit,
        }


@dataclass
class ArbStrategyConfig:
    connector_1: str = "binance"
    connector_2: str = "kucoin"
    trading_pair: str = "BTC-USDT"
    min_profitability: float = 0.003
    order_amount: float = 0.001
    add_transaction_costs: bool = True

    def to_hbot_config(self, paper: bool = True) -> dict:
        c1 = f"{self.connector_1}_paper_trade" if paper else self.connector_1
        c2 = f"{self.connector_2}_paper_trade" if paper else self.connector_2
        return {
            "strategy": "arbitrage",
            "primary_market": c1,
            "secondary_market": c2,
            "primary_market_trading_pair": self.trading_pair,
            "secondary_market_trading_pair": self.trading_pair,
            "min_profitability": self.min_profitability,
            "order_amount": self.order_amount,
        }


@dataclass
class DirectionalStrategyConfig:
    connector: str = "binance"
    trading_pair: str = "BTC-USDT"
    side: str = "buy"
    order_amount: float = 0.001
    stop_loss: float = 0.03
    take_profit: float = 0.06
    trailing_stop: Optional[float] = None
    time_limit: int = 3600
    add_transaction_costs: bool = True

    def to_executor_config(self, paper: bool = True) -> dict:
        connector = f"{self.connector}_paper_trade" if paper else self.connector
        config = {
            "type": "position_executor",
            "connector_name": connector,
            "trading_pair": self.trading_pair,
            "side": self.side,
            "amount": self.order_amount,
            "triple_barrier_conf": {
                "stop_loss": self.stop_loss,
                "take_profit": self.take_profit,
                "time_limit": self.time_limit,
            },
        }
        if self.trailing_stop:
            config["triple_barrier_conf"]["trailing_stop_activation_price_delta"] = self.trailing_stop
            config["triple_barrier_conf"]["trailing_stop_trailing_delta"] = self.trailing_stop * 0.5
        return config


STRATEGY_CONFIGS = {
    StrategyType.PURE_MARKET_MAKING: PMMStrategyConfig,
    StrategyType.GRID: GridStrategyConfig,
    StrategyType.DCA: DCAStrategyConfig,
    StrategyType.ARBITRAGE: ArbStrategyConfig,
    StrategyType.DIRECTIONAL: DirectionalStrategyConfig,
}


def create_strategy_config(strategy_type: str, params: dict):
    st = StrategyType(strategy_type)
    config_cls = STRATEGY_CONFIGS.get(st)
    if not config_cls:
        raise ValueError(f"Unknown strategy type: {strategy_type}")

    valid_fields = {f.name for f in config_cls.__dataclass_fields__.values()}
    filtered = {k: v for k, v in params.items() if k in valid_fields}
    return config_cls(**filtered)
