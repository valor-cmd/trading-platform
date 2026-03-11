import ccxt.async_support as ccxt
import pandas as pd
from typing import Optional
from datetime import datetime, timezone

from app.core.config import settings


class ExchangeManager:
    def __init__(self):
        self.exchanges: dict[str, ccxt.Exchange] = {}

    async def connect_coinbase(self) -> ccxt.Exchange:
        exchange = ccxt.coinbase({
            "apiKey": settings.coinbase_api_key,
            "secret": settings.coinbase_api_secret,
            "enableRateLimit": True,
        })
        self.exchanges["coinbase"] = exchange
        return exchange

    async def connect_exchange(self, exchange_id: str, api_key: str, api_secret: str, **kwargs) -> ccxt.Exchange:
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            **kwargs,
        })
        self.exchanges[exchange_id] = exchange
        return exchange

    def get_exchange(self, exchange_id: str) -> Optional[ccxt.Exchange]:
        return self.exchanges.get(exchange_id)

    async def fetch_ohlcv(
        self, exchange_id: str, symbol: str, timeframe: str = "1h", limit: int = 200
    ) -> pd.DataFrame:
        exchange = self.get_exchange(exchange_id)
        if not exchange:
            raise ValueError(f"Exchange {exchange_id} not connected")
        raw = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df

    async def fetch_ticker(self, exchange_id: str, symbol: str) -> dict:
        exchange = self.get_exchange(exchange_id)
        if not exchange:
            raise ValueError(f"Exchange {exchange_id} not connected")
        return await exchange.fetch_ticker(symbol)

    async def fetch_balance(self, exchange_id: str) -> dict:
        exchange = self.get_exchange(exchange_id)
        if not exchange:
            raise ValueError(f"Exchange {exchange_id} not connected")
        return await exchange.fetch_balance()

    async def create_order(
        self,
        exchange_id: str,
        symbol: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        order_type: str = "market",
        params: Optional[dict] = None,
    ) -> dict:
        if settings.paper_trading:
            return self._paper_order(exchange_id, symbol, side, amount, price, order_type)
        exchange = self.get_exchange(exchange_id)
        if not exchange:
            raise ValueError(f"Exchange {exchange_id} not connected")
        return await exchange.create_order(
            symbol, order_type, side, amount, price, params or {}
        )

    def _paper_order(
        self, exchange_id: str, symbol: str, side: str, amount: float, price: float, order_type: str
    ) -> dict:
        return {
            "id": f"paper_{datetime.now(timezone.utc).timestamp()}",
            "exchange": exchange_id,
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": price,
            "type": order_type,
            "status": "filled",
            "paper": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def get_trading_fee(self, exchange_id: str, symbol: str) -> float:
        exchange = self.get_exchange(exchange_id)
        if not exchange:
            return 0.001
        try:
            fees = await exchange.fetch_trading_fee(symbol)
            return fees.get("taker", 0.001)
        except Exception:
            return 0.001

    async def close_all(self):
        for exchange in self.exchanges.values():
            await exchange.close()
        self.exchanges.clear()
