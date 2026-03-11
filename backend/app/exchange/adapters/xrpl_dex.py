import asyncio
import logging
import time
import json
from datetime import datetime, timezone
from typing import Optional
import pandas as pd
import aiohttp

from app.exchange.adapters.base import (
    BaseExchangeAdapter, ExchangeType, Chain, TokenInfo, TradingPair,
    OrderResult, TickerData,
)
from app.exchange.live_prices import live_prices

logger = logging.getLogger(__name__)

XRPL_TOKENS = {
    "XRP": TokenInfo(symbol="XRP", name="XRP", chain=Chain.XRPL, is_native=True, decimals=6, coingecko_id="ripple"),
    "SOLO": TokenInfo(symbol="SOLO", name="Sologenic", chain=Chain.XRPL, contract_address="rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz", decimals=15, tags=["xrpl", "defi"], coingecko_id="sologenic"),
    "CORE": TokenInfo(symbol="CORE", name="Coreum", chain=Chain.XRPL, contract_address="rcoreNywaoz2ZCQ8Lg2EbSLnGuRBmun6D", decimals=15, tags=["xrpl"], coingecko_id="coreum"),
    "CSC": TokenInfo(symbol="CSC", name="CasinoCoin", chain=Chain.XRPL, contract_address="rCSCManTZ8ME9EoLrSHHYKW8PPwWMgkwr", decimals=15, tags=["xrpl", "gaming"]),
    "ELS": TokenInfo(symbol="ELS", name="Elysian", chain=Chain.XRPL, contract_address="rHXuEaRYnnJHbDeuBH5w8yPh5uwNVh5zAg", decimals=15, tags=["xrpl"]),
}

XRPL_DEX_PAIRS = [
    {"base": "SOLO", "quote": "XRP", "issuer": "rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz", "currency": "534F4C4F00000000000000000000000000000000"},
    {"base": "CORE", "quote": "XRP", "issuer": "rcoreNywaoz2ZCQ8Lg2EbSLnGuRBmun6D", "currency": "434F524500000000000000000000000000000000"},
    {"base": "CSC", "quote": "XRP", "issuer": "rCSCManTZ8ME9EoLrSHHYKW8PPwWMgkwr", "currency": "CSC"},
]

HONEYCLUSTER_WSS = "wss://honeycluster.dev"
HONEYCLUSTER_RPC = "https://honeycluster.dev"

XRPL_CEX_PAIRS = ["XRP/USDT"]


class XRPLDEXAdapter(BaseExchangeAdapter):
    def __init__(self):
        super().__init__("xrpl_dex", ExchangeType.DEX, Chain.XRPL)
        self._fee_rate = 0.002
        self._rpc_url = HONEYCLUSTER_RPC
        self._wss_url = HONEYCLUSTER_WSS
        self._dex_price_cache: dict[str, dict] = {}
        self._cache_ttl = 15

    async def connect(self, **credentials) -> bool:
        self._rpc_url = credentials.get("rpc_url", HONEYCLUSTER_RPC)
        self._wss_url = credentials.get("wss_url", HONEYCLUSTER_WSS)
        self.connected = True

        for sym_str in XRPL_CEX_PAIRS:
            base_sym, quote_sym = sym_str.split("/")
            for eid in live_prices.get_exchanges():
                if sym_str in live_prices.get_symbols(eid):
                    base = XRPL_TOKENS.get(base_sym, TokenInfo(symbol=base_sym, name=base_sym, chain=Chain.XRPL))
                    quote = TokenInfo(symbol=quote_sym, name=quote_sym, chain=Chain.XRPL)
                    self._pairs[sym_str] = TradingPair(
                        base=base, quote=quote,
                        exchange_id=self.exchange_id,
                        exchange_symbol=sym_str,
                        fee_rate=self._fee_rate,
                    )
                    break

        for pair_def in XRPL_DEX_PAIRS:
            sym = f"{pair_def['base']}/{pair_def['quote']}"
            base = XRPL_TOKENS.get(pair_def["base"], TokenInfo(symbol=pair_def["base"], name=pair_def["base"], chain=Chain.XRPL))
            quote = XRPL_TOKENS.get(pair_def["quote"], TokenInfo(symbol=pair_def["quote"], name=pair_def["quote"], chain=Chain.XRPL))
            self._pairs[sym] = TradingPair(
                base=base, quote=quote,
                exchange_id=self.exchange_id,
                exchange_symbol=sym,
                fee_rate=self._fee_rate,
            )

        logger.info(f"XRPL DEX adapter ready via {self._rpc_url} ({len(self._pairs)} pairs)")
        return True

    async def disconnect(self):
        self.connected = False

    async def _fetch_book_offers(self, pair_def: dict) -> Optional[dict]:
        payload = {
            "method": "book_offers",
            "params": [{
                "taker_gets": {"currency": "XRP"},
                "taker_pays": {
                    "currency": pair_def["currency"],
                    "issuer": pair_def["issuer"],
                },
                "limit": 10,
            }]
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self._rpc_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("result", {})
        except Exception as e:
            logger.debug(f"HoneyCluster book_offers failed for {pair_def['base']}: {e}")
        return None

    async def _get_dex_price(self, pair_def: dict) -> Optional[float]:
        cache_key = f"{pair_def['base']}/{pair_def['quote']}"
        cached = self._dex_price_cache.get(cache_key)
        if cached and (time.time() - cached["_fetched_at"]) < self._cache_ttl:
            return cached["price"]

        result = await self._fetch_book_offers(pair_def)
        if not result:
            return None

        offers = result.get("offers", [])
        if not offers:
            return None

        try:
            best = offers[0]
            taker_pays = best.get("TakerPays", {})
            taker_gets = best.get("TakerGets", "0")

            if isinstance(taker_pays, dict):
                pays_amount = float(taker_pays.get("value", 0))
            else:
                pays_amount = float(taker_pays) / 1_000_000

            if isinstance(taker_gets, dict):
                gets_amount = float(taker_gets.get("value", 0))
            else:
                gets_amount = float(taker_gets) / 1_000_000

            if gets_amount > 0:
                price = pays_amount / gets_amount
                self._dex_price_cache[cache_key] = {"price": price, "_fetched_at": time.time()}
                return price
        except Exception as e:
            logger.debug(f"Price calc failed for {pair_def['base']}: {e}")
        return None

    async def fetch_ticker(self, symbol: str) -> TickerData:
        for pair_def in XRPL_DEX_PAIRS:
            if f"{pair_def['base']}/{pair_def['quote']}" == symbol:
                price = await self._get_dex_price(pair_def)
                if price and price > 0:
                    return TickerData(
                        symbol=symbol, exchange_id=self.exchange_id, last=price,
                        bid=price * 0.99, ask=price * 1.01,
                        high_24h=price * 1.05, low_24h=price * 0.95,
                        volume_24h=0,
                        change_pct_24h=0,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        spread_pct=2.0,
                    )

        for eid in live_prices.get_exchanges():
            if symbol in live_prices.get_symbols(eid):
                ticker = await live_prices.fetch_ticker(eid, symbol)
                last = ticker.get("last", 0)
                bid = ticker.get("bid", 0) or last * 0.995
                ask = ticker.get("ask", 0) or last * 1.005
                spread = ((ask - bid) / last * 100) if last > 0 else 0
                return TickerData(
                    symbol=symbol, exchange_id=self.exchange_id, last=last,
                    bid=bid, ask=ask,
                    high_24h=ticker.get("high", 0),
                    low_24h=ticker.get("low", 0),
                    volume_24h=ticker.get("volume", 0),
                    change_pct_24h=ticker.get("change", 0),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    spread_pct=round(max(spread, 0.5), 4),
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
            order_id=f"xrpl_{int(time.time())}_{id(self)}",
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
