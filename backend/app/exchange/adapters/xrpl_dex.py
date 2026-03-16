import asyncio
import logging
import time
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

XRPL_RPC_SERVERS = [
    "https://xrplcluster.com/",
    "https://s1.ripple.com:51234/",
    "https://s2.ripple.com:51234/",
]

XRPLDATA_API = "https://api.xrpldata.com/api/v1/tokens"
MIN_TRUSTLINES = 50

XRPL_TOKENS = {
    "XRP": TokenInfo(symbol="XRP", name="XRP", chain=Chain.XRPL, is_native=True, decimals=6, coingecko_id="ripple"),
}


import re

_VALID_SYMBOL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,19}$")
_VALID_SYMBOL_WITH_SUFFIX_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,14}(\.[A-Za-z0-9]{1,10})?$")


def _is_valid_symbol(sym: str) -> bool:
    return bool(sym and _VALID_SYMBOL_RE.match(sym) and all(ord(c) < 128 for c in sym))


def _decode_hex_currency(hex_str: str) -> Optional[str]:
    try:
        decoded = bytes.fromhex(hex_str).rstrip(b"\x00").decode("ascii", errors="ignore").strip()
        if decoded and _is_valid_symbol(decoded):
            return decoded
        return None
    except Exception:
        return None


class XRPLDEXAdapter(BaseExchangeAdapter):
    def __init__(self):
        super().__init__("xrpl_dex", ExchangeType.DEX, Chain.XRPL)
        self._fee_rate = 0.002
        self._rpc_servers = list(XRPL_RPC_SERVERS)
        self._active_rpc = XRPL_RPC_SERVERS[0]
        self._dex_price_cache: dict[str, dict] = {}
        self._cache_ttl = 15
        self._pair_defs: dict[str, dict] = {}
        self._seen_symbols: set[str] = set()

    async def connect(self, **credentials) -> bool:
        self.connected = True

        for sym_str in ["XRP/USDT", "XRP/USDC"]:
            base_sym, quote_sym = sym_str.split("/")
            for eid in live_prices.get_exchanges():
                if sym_str in live_prices.get_symbols(eid):
                    self._pairs[sym_str] = TradingPair(
                        base=XRPL_TOKENS["XRP"],
                        quote=TokenInfo(symbol=quote_sym, name=quote_sym, chain=Chain.XRPL),
                        exchange_id=self.exchange_id,
                        exchange_symbol=sym_str,
                        fee_rate=self._fee_rate,
                    )
                    break

        await self._load_xrpldata_tokens()

        logger.info(f"XRPL DEX adapter ready ({len(self._pairs)} pairs)")
        return True

    async def _load_xrpldata_tokens(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    XRPLDATA_API,
                    timeout=aiohttp.ClientTimeout(total=60),
                    headers={"Accept": "application/json", "User-Agent": "TradingPlatform/1.0"},
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"xrpldata API returned {resp.status}")
                        return
                    data = await resp.json()

            issuers = data.get("issuers", {})
            count = 0
            for issuer_addr, issuer_data in issuers.items():
                info = issuer_data.get("data", {})
                username = info.get("username", "")
                verified = info.get("verified", False)
                kyc = info.get("kyc", False)

                for token in issuer_data.get("tokens", []):
                    trustlines = token.get("trustlines", 0)
                    if trustlines < MIN_TRUSTLINES:
                        continue

                    currency_raw = token.get("currency", "")
                    if not currency_raw:
                        continue

                    if len(currency_raw) == 3:
                        symbol = currency_raw
                    elif len(currency_raw) == 40:
                        symbol = _decode_hex_currency(currency_raw)
                    else:
                        symbol = currency_raw[:10]

                    if not symbol or not _is_valid_symbol(symbol):
                        continue

                    unique_sym = symbol
                    if unique_sym in self._seen_symbols:
                        if username:
                            suffix = re.sub(r"[^A-Za-z0-9]", "", username)[:6].lower()
                        else:
                            suffix = issuer_addr[-6:]
                        unique_sym = f"{symbol}.{suffix}"
                    if unique_sym in self._seen_symbols:
                        continue
                    if not _VALID_SYMBOL_WITH_SUFFIX_RE.match(unique_sym):
                        continue
                    self._seen_symbols.add(unique_sym)

                    tags = ["xrpl"]
                    if verified:
                        tags.append("verified")
                    if kyc:
                        tags.append("kyc")
                    holders = token.get("holders", 0)
                    if holders >= 10000:
                        tags.append("popular")

                    token_name = username if username else symbol
                    token_info = TokenInfo(
                        symbol=unique_sym, name=token_name,
                        chain=Chain.XRPL, contract_address=issuer_addr,
                        decimals=15, tags=tags,
                    )
                    XRPL_TOKENS[unique_sym] = token_info

                    pair_sym = f"{unique_sym}/XRP"
                    self._pairs[pair_sym] = TradingPair(
                        base=token_info, quote=XRPL_TOKENS["XRP"],
                        exchange_id=self.exchange_id, exchange_symbol=pair_sym,
                        fee_rate=self._fee_rate,
                    )
                    self._pair_defs[pair_sym] = {
                        "base": unique_sym,
                        "quote": "XRP",
                        "issuer": issuer_addr,
                        "currency": currency_raw,
                    }
                    count += 1

            logger.info(f"Loaded {count} XRPL tokens from xrpldata (trustlines >= {MIN_TRUSTLINES})")
        except Exception as e:
            logger.warning(f"Failed to load xrpldata tokens: {e}")

    async def _rpc_call(self, method: str, params: list) -> Optional[dict]:
        payload = {"method": method, "params": params}
        for rpc_url in [self._active_rpc] + self._rpc_servers:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        rpc_url, json=payload,
                        timeout=aiohttp.ClientTimeout(total=10),
                        headers={"Content-Type": "application/json"},
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            self._active_rpc = rpc_url
                            return data.get("result", {})
            except Exception:
                continue
        return None

    async def disconnect(self):
        self.connected = False

    async def _get_dex_price(self, pair_def: dict) -> Optional[float]:
        cache_key = f"{pair_def['base']}/{pair_def['quote']}"
        cached = self._dex_price_cache.get(cache_key)
        if cached and (time.time() - cached["_fetched_at"]) < self._cache_ttl:
            return cached["price"]

        currency = pair_def["currency"]
        issuer = pair_def["issuer"]
        if len(currency) == 3:
            taker_pays = {"currency": currency, "issuer": issuer}
        else:
            taker_pays = {"currency": currency, "issuer": issuer}

        result = await self._rpc_call("book_offers", [{
            "taker_gets": {"currency": "XRP"},
            "taker_pays": taker_pays,
            "limit": 10,
        }])
        if not result:
            return None

        offers = result.get("offers", [])
        if not offers:
            return None

        try:
            best = offers[0]
            taker_pays_val = best.get("TakerPays", {})
            taker_gets_val = best.get("TakerGets", "0")

            if isinstance(taker_pays_val, dict):
                pays_amount = float(taker_pays_val.get("value", 0))
            else:
                pays_amount = float(taker_pays_val) / 1_000_000

            if isinstance(taker_gets_val, dict):
                gets_amount = float(taker_gets_val.get("value", 0))
            else:
                gets_amount = float(taker_gets_val) / 1_000_000

            if gets_amount > 0:
                price = pays_amount / gets_amount
                self._dex_price_cache[cache_key] = {"price": price, "_fetched_at": time.time()}
                return price
        except Exception as e:
            logger.debug(f"Price calc failed for {pair_def['base']}: {e}")
        return None

    async def fetch_ticker(self, symbol: str) -> TickerData:
        pair_def = self._pair_defs.get(symbol)
        if pair_def:
            price = await self._get_dex_price(pair_def)
            if price and price > 0:
                return TickerData(
                    symbol=symbol, exchange_id=self.exchange_id, last=price,
                    bid=price * 0.99, ask=price * 1.01,
                    high_24h=price * 1.05, low_24h=price * 0.95,
                    volume_24h=0, change_pct_24h=0,
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
                    high_24h=ticker.get("high", 0), low_24h=ticker.get("low", 0),
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
            cost=amount * price, fee=fee, status="filled",
            timestamp=datetime.now(timezone.utc).isoformat(), is_paper=True,
        )

    async def fetch_trading_pairs(self) -> list[TradingPair]:
        return list(self._pairs.values())

    async def get_trading_fee(self, symbol: str) -> float:
        return self._fee_rate
