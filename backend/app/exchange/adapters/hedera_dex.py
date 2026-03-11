import logging
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

HEDERA_TOKENS = {
    "HBAR": TokenInfo(symbol="HBAR", name="Hedera", chain=Chain.HEDERA, is_native=True, decimals=8, coingecko_id="hedera-hashgraph"),
    "USDC": TokenInfo(symbol="USDC", name="USD Coin", chain=Chain.HEDERA, contract_address="0.0.456858", decimals=6),
    "SAUCE": TokenInfo(symbol="SAUCE", name="SaucerSwap", chain=Chain.HEDERA, contract_address="0.0.731861", decimals=6, tags=["defi"]),
    "HBARX": TokenInfo(symbol="HBARX", name="Stader HBAR", chain=Chain.HEDERA, contract_address="0.0.1462860", decimals=8, tags=["liquid-staking"]),
    "PACK": TokenInfo(symbol="PACK", name="HashPack", chain=Chain.HEDERA, contract_address="0.0.3407403", decimals=6, tags=["wallet"]),
    "DOVU": TokenInfo(symbol="DOVU", name="DOVU", chain=Chain.HEDERA, contract_address="0.0.3229415", decimals=8, tags=["carbon"]),
    "JAM": TokenInfo(symbol="JAM", name="JAM", chain=Chain.HEDERA, decimals=8, tags=["meme"]),
    "KARATE": TokenInfo(symbol="KARATE", name="Karate Combat", chain=Chain.HEDERA, decimals=8, tags=["gaming"]),
}

HEDERA_PAIRS = ["HBAR/USDT"]


class HederaDEXAdapter(BaseExchangeAdapter):
    def __init__(self):
        super().__init__("hedera_dex", ExchangeType.DEX, Chain.HEDERA)
        self._fee_rate = 0.003

    async def connect(self, **credentials) -> bool:
        self.connected = True
        for sym_str in HEDERA_PAIRS:
            base_sym, quote_sym = sym_str.split("/")
            for eid in live_prices.get_exchanges():
                if sym_str in live_prices.get_symbols(eid):
                    base = HEDERA_TOKENS.get(base_sym, TokenInfo(symbol=base_sym, name=base_sym, chain=Chain.HEDERA))
                    quote = TokenInfo(symbol=quote_sym, name=quote_sym, chain=Chain.HEDERA)
                    self._pairs[sym_str] = TradingPair(
                        base=base, quote=quote,
                        exchange_id=self.exchange_id,
                        exchange_symbol=sym_str,
                        fee_rate=self._fee_rate,
                    )
                    break
        logger.info(f"Hedera DEX adapter ready ({len(self._pairs)} pairs with real prices)")
        return True

    async def disconnect(self):
        self.connected = False

    async def fetch_ticker(self, symbol: str) -> TickerData:
        for eid in live_prices.get_exchanges():
            if symbol in live_prices.get_symbols(eid):
                ticker = await live_prices.fetch_ticker(eid, symbol)
                last = ticker.get("last", 0)
                bid = ticker.get("bid", 0) or last * 0.996
                ask = ticker.get("ask", 0) or last * 1.004
                spread = ((ask - bid) / last * 100) if last > 0 else 0
                return TickerData(
                    symbol=symbol, exchange_id=self.exchange_id, last=last,
                    bid=bid, ask=ask,
                    high_24h=ticker.get("high", 0),
                    low_24h=ticker.get("low", 0),
                    volume_24h=ticker.get("volume", 0),
                    change_pct_24h=ticker.get("change", 0),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    spread_pct=round(max(spread, 0.4), 4),
                )
        raise ValueError(f"No price source for {symbol}")

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 200) -> pd.DataFrame:
        for eid in live_prices.get_exchanges():
            if symbol in live_prices.get_symbols(eid):
                return await live_prices.fetch_ohlcv(eid, symbol, timeframe, limit)
        raise ValueError(f"No OHLCV source for {symbol}")

    async def fetch_balance(self) -> dict:
        return {"total": {}, "free": {}, "used": {}}

    async def create_order(self, symbol: str, side: str, amount: float, price: Optional[float] = None, order_type: str = "market") -> OrderResult:
        if price is None:
            t = await self.fetch_ticker(symbol)
            price = t.last
        fee = amount * price * self._fee_rate
        return OrderResult(
            order_id=f"hbar_dex_{int(time.time())}_{id(self)}",
            exchange_id=self.exchange_id,
            symbol=symbol, side=side, amount=amount, price=price,
            cost=amount * price, fee=fee,
            status="filled",
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_paper=True,
        )

    async def fetch_trading_pairs(self) -> list[TradingPair]:
        return list(self._pairs.values())

    async def get_trading_fee(self, symbol: str) -> float:
        return self._fee_rate
