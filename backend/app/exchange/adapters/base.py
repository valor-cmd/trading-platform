from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import pandas as pd


class ExchangeType(str, Enum):
    CEX = "cex"
    DEX = "dex"
    AGGREGATOR = "aggregator"


class Chain(str, Enum):
    ETHEREUM = "ethereum"
    SOLANA = "solana"
    XRPL = "xrpl"
    HEDERA = "hedera"
    POLYGON = "polygon"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"
    AVALANCHE = "avalanche"
    BSC = "bsc"
    BASE = "base"


@dataclass
class TokenInfo:
    symbol: str
    name: str
    chain: Chain
    contract_address: Optional[str] = None
    decimals: int = 18
    is_native: bool = False
    logo_url: Optional[str] = None
    coingecko_id: Optional[str] = None
    tags: list[str] = field(default_factory=list)


@dataclass
class TradingPair:
    base: TokenInfo
    quote: TokenInfo
    exchange_id: str
    exchange_symbol: str
    min_order_size: float = 0.0
    price_decimals: int = 8
    amount_decimals: int = 8
    fee_rate: float = 0.001
    is_active: bool = True


@dataclass
class OrderResult:
    order_id: str
    exchange_id: str
    symbol: str
    side: str
    amount: float
    price: float
    cost: float
    fee: float
    status: str
    timestamp: str
    tx_hash: Optional[str] = None
    is_paper: bool = True


@dataclass
class TickerData:
    symbol: str
    exchange_id: str
    last: float
    bid: float
    ask: float
    high_24h: float
    low_24h: float
    volume_24h: float
    change_pct_24h: float
    timestamp: str
    spread_pct: float = 0.0


class BaseExchangeAdapter(ABC):
    def __init__(self, exchange_id: str, exchange_type: ExchangeType, chain: Optional[Chain] = None):
        self.exchange_id = exchange_id
        self.exchange_type = exchange_type
        self.chain = chain
        self.connected = False
        self._pairs: dict[str, TradingPair] = {}

    @abstractmethod
    async def connect(self, **credentials) -> bool:
        pass

    @abstractmethod
    async def disconnect(self):
        pass

    @abstractmethod
    async def fetch_ticker(self, symbol: str) -> TickerData:
        pass

    @abstractmethod
    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 200) -> pd.DataFrame:
        pass

    @abstractmethod
    async def fetch_balance(self) -> dict:
        pass

    @abstractmethod
    async def create_order(self, symbol: str, side: str, amount: float, price: Optional[float] = None, order_type: str = "market") -> OrderResult:
        pass

    @abstractmethod
    async def fetch_trading_pairs(self) -> list[TradingPair]:
        pass

    @abstractmethod
    async def get_trading_fee(self, symbol: str) -> float:
        pass

    def get_pair(self, symbol: str) -> Optional[TradingPair]:
        return self._pairs.get(symbol)

    def get_all_symbols(self) -> list[str]:
        return list(self._pairs.keys())

    def is_connected(self) -> bool:
        return self.connected
