import time
from datetime import datetime, timezone
from typing import Optional
import pandas as pd

from app.exchange.adapters.base import (
    BaseExchangeAdapter, ExchangeType, Chain, TokenInfo, TradingPair,
    OrderResult, TickerData,
)
from app.exchange.live_prices import live_prices


class PaperAdapter(BaseExchangeAdapter):
    def __init__(self, source_exchange_id: str = "binance", chain: Optional[Chain] = None):
        super().__init__(f"paper_{source_exchange_id}", ExchangeType.CEX, chain)
        self.balances: dict[str, float] = {}
        self.order_count = 0
        self._source = source_exchange_id

    async def connect(self, **credentials) -> bool:
        self.connected = True
        symbols = live_prices.get_symbols(self._source)
        for symbol in symbols:
            base_sym = symbol.split("/")[0] if "/" in symbol else symbol
            quote_sym = symbol.split("/")[1] if "/" in symbol else "USDT"
            fee = live_prices.get_fee(self._source, symbol)
            self._pairs[symbol] = TradingPair(
                base=TokenInfo(symbol=base_sym, name=base_sym, chain=Chain.ETHEREUM),
                quote=TokenInfo(symbol=quote_sym, name=quote_sym, chain=Chain.ETHEREUM),
                exchange_id=self.exchange_id,
                exchange_symbol=symbol,
                fee_rate=fee,
            )
        return True

    async def disconnect(self):
        self.connected = False

    async def fetch_ticker(self, symbol: str) -> TickerData:
        ticker = await live_prices.fetch_ticker(self._source, symbol)
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
            timestamp=ticker.get("timestamp", datetime.now(timezone.utc).isoformat()),
            spread_pct=round(spread, 4),
        )

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 200) -> pd.DataFrame:
        return await live_prices.fetch_ohlcv(self._source, symbol, timeframe, limit)

    async def fetch_balance(self) -> dict:
        return {"total": dict(self.balances), "free": dict(self.balances), "used": {k: 0 for k in self.balances}}

    async def create_order(self, symbol: str, side: str, amount: float, price: Optional[float] = None, order_type: str = "market") -> OrderResult:
        self.order_count += 1
        if price is None:
            t = await self.fetch_ticker(symbol)
            price = t.last

        base = symbol.split("/")[0]
        quote = symbol.split("/")[1] if "/" in symbol else "USDT"
        fee_rate = live_prices.get_fee(self._source, symbol)
        fee = amount * price * fee_rate

        if side == "buy":
            self.balances[quote] = self.balances.get(quote, 0) - (amount * price) - fee
            self.balances[base] = self.balances.get(base, 0) + amount
        else:
            self.balances[base] = self.balances.get(base, 0) - amount
            self.balances[quote] = self.balances.get(quote, 0) + (amount * price) - fee

        return OrderResult(
            order_id=f"paper_{self.order_count}_{int(time.time())}",
            exchange_id=self.exchange_id,
            symbol=symbol,
            side=side,
            amount=amount,
            price=price,
            cost=amount * price,
            fee=fee,
            status="filled",
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_paper=True,
        )

    async def fetch_trading_pairs(self) -> list[TradingPair]:
        return list(self._pairs.values())

    async def get_trading_fee(self, symbol: str) -> float:
        return live_prices.get_fee(self._source, symbol)
