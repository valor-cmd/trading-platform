import logging
import random
import time
from datetime import datetime, timezone
from typing import Optional
import pandas as pd

from app.exchange.adapters.base import (
    BaseExchangeAdapter, ExchangeType, Chain, TokenInfo, TradingPair,
    OrderResult, TickerData,
)
from app.exchange.live_prices import live_prices

logger = logging.getLogger(__name__)


class CCXTLiveAdapter(BaseExchangeAdapter):
    def __init__(self, exchange_id: str):
        super().__init__(exchange_id, ExchangeType.CEX)
        self._has_credentials = False

    async def connect(self, **credentials) -> bool:
        if exchange_id := self.exchange_id:
            if exchange_id not in live_prices.get_exchanges():
                logger.warning(f"{exchange_id} not in live price provider")
                return False

        self._has_credentials = bool(credentials.get("api_key"))

        symbols = live_prices.get_symbols(self.exchange_id)
        for symbol in symbols:
            base_sym = symbol.split("/")[0] if "/" in symbol else symbol
            quote_sym = symbol.split("/")[1] if "/" in symbol else "USDT"
            fee = live_prices.get_fee(self.exchange_id, symbol)
            self._pairs[symbol] = TradingPair(
                base=TokenInfo(symbol=base_sym, name=base_sym, chain=Chain.ETHEREUM),
                quote=TokenInfo(symbol=quote_sym, name=quote_sym, chain=Chain.ETHEREUM),
                exchange_id=self.exchange_id,
                exchange_symbol=symbol,
                fee_rate=fee,
                is_active=True,
            )

        self.connected = True
        logger.info(f"CCXTLiveAdapter connected: {self.exchange_id} ({len(self._pairs)} pairs)")
        return True

    async def disconnect(self):
        self.connected = False

    async def fetch_ticker(self, symbol: str) -> TickerData:
        ticker = await live_prices.fetch_ticker(self.exchange_id, symbol)
        last = ticker.get("last", 0) or 0
        bid = ticker.get("bid", 0) or 0
        ask = ticker.get("ask", 0) or 0
        spread = ((ask - bid) / last * 100) if last > 0 else 0
        return TickerData(
            symbol=symbol,
            exchange_id=self.exchange_id,
            last=last,
            bid=bid,
            ask=ask,
            high_24h=ticker.get("high", 0) or 0,
            low_24h=ticker.get("low", 0) or 0,
            volume_24h=ticker.get("volume", 0) or 0,
            change_pct_24h=ticker.get("change", 0) or 0,
            timestamp=datetime.now(timezone.utc).isoformat(),
            spread_pct=round(spread, 4),
        )

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 200) -> pd.DataFrame:
        return await live_prices.fetch_ohlcv(self.exchange_id, symbol, timeframe, limit)

    async def fetch_balance(self) -> dict:
        return {"total": {}, "free": {}, "used": {}}

    async def create_order(self, symbol: str, side: str, amount: float, price: Optional[float] = None, order_type: str = "market") -> OrderResult:
        t = await self.fetch_ticker(symbol)
        if price is None:
            price = t.last
        bid = t.bid if t.bid > 0 else price
        ask = t.ask if t.ask > 0 else price
        additional_slip = random.uniform(0.0002, 0.001)
        if side == "buy":
            fill_price = ask * (1 + additional_slip)
        else:
            fill_price = bid * (1 - additional_slip)
        fee_rate = live_prices.get_fee(self.exchange_id, symbol)
        cost = amount * fill_price
        fee = cost * fee_rate
        return OrderResult(
            order_id=f"{self.exchange_id}_{int(time.time())}_{id(self)}",
            exchange_id=self.exchange_id,
            symbol=symbol,
            side=side,
            amount=amount,
            price=fill_price,
            cost=cost,
            fee=fee,
            status="filled",
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_paper=True,
        )

    async def fetch_trading_pairs(self) -> list[TradingPair]:
        return list(self._pairs.values())

    async def get_trading_fee(self, symbol: str) -> float:
        return live_prices.get_fee(self.exchange_id, symbol)
