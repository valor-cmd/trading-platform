import logging
import time
import aiohttp
from datetime import datetime, timezone
from typing import Optional
import pandas as pd

from app.exchange.adapters.base import (
    BaseExchangeAdapter, ExchangeType, Chain, TokenInfo, TradingPair,
    OrderResult, TickerData,
)
from app.exchange.live_prices import live_prices

logger = logging.getLogger(__name__)

SOLANA_TOKENS = {
    "SOL": TokenInfo(symbol="SOL", name="Solana", chain=Chain.SOLANA, is_native=True, decimals=9, coingecko_id="solana"),
    "USDC": TokenInfo(symbol="USDC", name="USD Coin", chain=Chain.SOLANA, contract_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", decimals=6),
    "BONK": TokenInfo(symbol="BONK", name="Bonk", chain=Chain.SOLANA, contract_address="DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", decimals=5, tags=["meme"]),
    "WIF": TokenInfo(symbol="WIF", name="dogwifhat", chain=Chain.SOLANA, contract_address="EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", decimals=6, tags=["meme"]),
    "JTO": TokenInfo(symbol="JTO", name="Jito", chain=Chain.SOLANA, contract_address="jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL", decimals=9, tags=["defi"]),
    "PYTH": TokenInfo(symbol="PYTH", name="Pyth Network", chain=Chain.SOLANA, contract_address="HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3", decimals=6, tags=["oracle"]),
    "JUP": TokenInfo(symbol="JUP", name="Jupiter", chain=Chain.SOLANA, contract_address="JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", decimals=6, tags=["defi"]),
    "RAY": TokenInfo(symbol="RAY", name="Raydium", chain=Chain.SOLANA, contract_address="4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R", decimals=6, tags=["defi"]),
    "ORCA": TokenInfo(symbol="ORCA", name="Orca", chain=Chain.SOLANA, contract_address="orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE", decimals=6, tags=["defi"]),
    "RENDER": TokenInfo(symbol="RENDER", name="Render", chain=Chain.SOLANA, contract_address="rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof", decimals=8, tags=["ai"]),
    "POPCAT": TokenInfo(symbol="POPCAT", name="Popcat", chain=Chain.SOLANA, decimals=9, tags=["meme"]),
    "MEW": TokenInfo(symbol="MEW", name="cat in a dogs world", chain=Chain.SOLANA, decimals=5, tags=["meme"]),
    "TRUMP": TokenInfo(symbol="TRUMP", name="Official Trump", chain=Chain.SOLANA, decimals=6, tags=["meme"]),
}

SOLANA_USDT_PAIRS = [
    "SOL/USDT", "BONK/USDT", "WIF/USDT", "JTO/USDT", "PYTH/USDT",
    "JUP/USDT", "RAY/USDT", "ORCA/USDT", "RENDER/USDT",
    "POPCAT/USDT", "MEW/USDT", "TRUMP/USDT",
]


class SolanaDEXAdapter(BaseExchangeAdapter):
    def __init__(self):
        super().__init__("solana_dex", ExchangeType.DEX, Chain.SOLANA)
        self._fee_rate = 0.0025

    async def connect(self, **credentials) -> bool:
        self.connected = True
        for sym_str in SOLANA_USDT_PAIRS:
            base_sym, quote_sym = sym_str.split("/")
            for eid in live_prices.get_exchanges():
                if sym_str in live_prices.get_symbols(eid):
                    base = SOLANA_TOKENS.get(base_sym, TokenInfo(symbol=base_sym, name=base_sym, chain=Chain.SOLANA))
                    quote = TokenInfo(symbol=quote_sym, name=quote_sym, chain=Chain.SOLANA)
                    self._pairs[sym_str] = TradingPair(
                        base=base, quote=quote,
                        exchange_id=self.exchange_id,
                        exchange_symbol=sym_str,
                        fee_rate=self._fee_rate,
                    )
                    break
        logger.info(f"Solana DEX adapter ready ({len(self._pairs)} pairs with real prices)")
        return True

    async def disconnect(self):
        self.connected = False

    async def fetch_ticker(self, symbol: str) -> TickerData:
        for eid in live_prices.get_exchanges():
            if symbol in live_prices.get_symbols(eid):
                ticker = await live_prices.fetch_ticker(eid, symbol)
                last = ticker.get("last", 0)
                bid = ticker.get("bid", 0) or last * 0.997
                ask = ticker.get("ask", 0) or last * 1.003
                spread = ((ask - bid) / last * 100) if last > 0 else 0
                return TickerData(
                    symbol=symbol, exchange_id=self.exchange_id, last=last,
                    bid=bid, ask=ask,
                    high_24h=ticker.get("high", 0),
                    low_24h=ticker.get("low", 0),
                    volume_24h=ticker.get("volume", 0),
                    change_pct_24h=ticker.get("change", 0),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    spread_pct=round(max(spread, 0.3), 4),
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
            order_id=f"sol_dex_{int(time.time())}_{id(self)}",
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
