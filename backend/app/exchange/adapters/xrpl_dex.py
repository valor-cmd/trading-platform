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

HONEYCLUSTER_RPC = "https://honeycluster.dev"

KNOWN_XRPL_ISSUERS = [
    {"issuer": "rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz", "currency_hex": "534F4C4F00000000000000000000000000000000", "symbol": "SOLO", "name": "Sologenic", "decimals": 15, "tags": ["defi"]},
    {"issuer": "rcoreNywaoz2ZCQ8Lg2EbSLnGuRBmun6D", "currency_hex": "434F524500000000000000000000000000000000", "symbol": "CORE", "name": "Coreum", "decimals": 15, "tags": []},
    {"issuer": "rCSCManTZ8ME9EoLrSHHYKW8PPwWMgkwr", "currency": "CSC", "symbol": "CSC", "name": "CasinoCoin", "decimals": 15, "tags": ["gaming"]},
    {"issuer": "rHXuEaRYnnJHbDeuBH5w8yPh5uwNVh5zAg", "currency_hex": "454C530000000000000000000000000000000000", "symbol": "ELS", "name": "Elysian", "decimals": 15, "tags": []},
    {"issuer": "rhub8VRN55s94qWKDv6jmDy1pUykJzF3wq", "currency": "USD", "symbol": "USD.gh", "name": "GateHub USD", "decimals": 15, "tags": ["stablecoin"]},
    {"issuer": "rhub8VRN55s94qWKDv6jmDy1pUykJzF3wq", "currency": "EUR", "symbol": "EUR.gh", "name": "GateHub EUR", "decimals": 15, "tags": ["stablecoin"]},
    {"issuer": "rvYAfWj5gh67oV6fW32ZzP3Aw4Eubs59B", "currency": "USD", "symbol": "USD.bs", "name": "Bitstamp USD", "decimals": 15, "tags": ["stablecoin"]},
    {"issuer": "rMwjYedjc7yvipFLRQFhbRi9cufhFiC2MU", "currency": "USD", "symbol": "USD.snap", "name": "SnapSwap USD", "decimals": 15, "tags": ["stablecoin"]},
    {"issuer": "rcEGR9s4zL6MCPB3QVroqCPwKsVr7ArLkp", "currency_hex": "584147000000000000000000000000000000000000000000", "symbol": "XAG", "name": "Silver (XAG)", "decimals": 15, "tags": []},
    {"issuer": "rG1QQv2nh2gr7RCZ1P8YYcBUKCCN633jCn", "currency_hex": "0158415344000000000000000000000000000000", "symbol": "XAU.gh", "name": "Gold (XAU)", "decimals": 15, "tags": []},
    {"issuer": "rcXY84C4g14iFp6taFXjjQGVeHqSCh9RX", "currency_hex": "4C50540000000000000000000000000000000000", "symbol": "LPT", "name": "Loop Token", "decimals": 15, "tags": ["defi"]},
    {"issuer": "rMJAXYsbNzhwp7FfYnAsYP5ty3R2GnysNy", "currency_hex": "4556520000000000000000000000000000000000", "symbol": "EVR", "name": "Evernode", "decimals": 15, "tags": ["hosting"]},
    {"issuer": "rHiPGSMBbzDGpoTPEV73FYMYHmyGzLhFwZ", "currency_hex": "5553445400000000000000000000000000000000", "symbol": "USDT.gh", "name": "GateHub USDT", "decimals": 15, "tags": ["stablecoin"]},
    {"issuer": "rLqUC2eCPohYvJCEBJ77eCCqVL2uEiczjA", "currency_hex": "4753580000000000000000000000000000000000", "symbol": "GSX", "name": "Gold Secured", "decimals": 15, "tags": []},
    {"issuer": "rfk9aFCCsNhBFGPgqWJxhLiGHqBaX3onus", "currency_hex": "584D414C4C000000000000000000000000000000", "symbol": "XMALL", "name": "XMall", "decimals": 15, "tags": []},
    {"issuer": "rPDwRR6rkii3DEbfCPy3DqauFb8nBcjCFa", "currency_hex": "584150500000000000000000000000000000000000000000", "symbol": "XAPP", "name": "XAPP", "decimals": 15, "tags": []},
    {"issuer": "rsA2LpzuawewSBQXkiju3YQTMzW13pAAdW", "currency_hex": "434E590000000000000000000000000000000000", "symbol": "CNY", "name": "RippleCN CNY", "decimals": 15, "tags": ["fiat"]},
    {"issuer": "rKiCet8SdvWxPXnAgYarFUXMh1zCPz432Y", "currency_hex": "434E590000000000000000000000000000000000", "symbol": "CNY.rc", "name": "RippleChina CNY", "decimals": 15, "tags": ["fiat"]},
    {"issuer": "rctArjqVvTHihekzDeecKo6mkTYTUSBNc", "currency_hex": "58525000000000000000000000000000000000000000000", "symbol": "XRP.pro", "name": "XRPayNet", "decimals": 15, "tags": []},
    {"issuer": "rXRPSAFT...", "skip": True},
    {"issuer": "rpXCfDds782Bd6eK3sFTGe4qdtPCRfyQL7", "currency_hex": "455155000000000000000000000000000000000000000000", "symbol": "EQU", "name": "Equilibrium", "decimals": 15, "tags": ["defi"]},
    {"issuer": "r3q4fSPUqhdSiZVDRNRiR6ggVJjHQkHge2", "currency_hex": "474245580000000000000000000000000000000000000000", "symbol": "GBEX", "name": "Globiance", "decimals": 15, "tags": []},
    {"issuer": "rswh1fvyLqHizBS2awu1vs6QcmwTBd9qnm", "currency_hex": "58525068616E746F6D0000000000000000000000", "symbol": "XRPhantom", "name": "XRPhantom", "decimals": 15, "tags": ["nft"]},
    {"issuer": "rEb8TK3gBgk5auZkwc6sHnwrGVJH8DuaLh", "currency_hex": "455448000000000000000000000000000000000000000000", "symbol": "ETH.gh", "name": "GateHub ETH", "decimals": 15, "tags": ["wrapped"]},
    {"issuer": "rchGBxcD1A1C2tdxF6papQYZ8kjRKMYcL", "currency_hex": "425443000000000000000000000000000000000000000000", "symbol": "BTC.gh", "name": "GateHub BTC", "decimals": 15, "tags": ["wrapped"]},
    {"issuer": "rcA8X3TVMST1n3CJeAdGk1RdRCHii7N2h", "currency_hex": "455843000000000000000000000000000000000000000000", "symbol": "EXC", "name": "EXC Token", "decimals": 15, "tags": []},
    {"issuer": "rXmAo1PtU6e2RgRkM2rFZDPR2hHbPvSqH", "currency_hex": "584C4D0000000000000000000000000000000000", "symbol": "XLM.gh", "name": "GateHub XLM", "decimals": 15, "tags": ["wrapped"]},
]

XRPL_TOKENS = {
    "XRP": TokenInfo(symbol="XRP", name="XRP", chain=Chain.XRPL, is_native=True, decimals=6, coingecko_id="ripple"),
}


class XRPLDEXAdapter(BaseExchangeAdapter):
    def __init__(self):
        super().__init__("xrpl_dex", ExchangeType.DEX, Chain.XRPL)
        self._fee_rate = 0.002
        self._rpc_servers = list(XRPL_RPC_SERVERS)
        self._active_rpc = XRPL_RPC_SERVERS[0]
        self._dex_price_cache: dict[str, dict] = {}
        self._cache_ttl = 15
        self._pair_defs: dict[str, dict] = {}

    async def connect(self, **credentials) -> bool:
        self.connected = True

        for sym_str in ["XRP/USDT"]:
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

        for token_def in KNOWN_XRPL_ISSUERS:
            if token_def.get("skip"):
                continue
            sym = f"{token_def['symbol']}/XRP"
            currency = token_def.get("currency_hex") or token_def.get("currency")
            if not currency:
                continue
            token_info = TokenInfo(
                symbol=token_def["symbol"], name=token_def["name"],
                chain=Chain.XRPL, contract_address=token_def["issuer"],
                decimals=token_def.get("decimals", 15),
                tags=token_def.get("tags", []) + ["xrpl"],
            )
            XRPL_TOKENS[token_def["symbol"]] = token_info
            self._pairs[sym] = TradingPair(
                base=token_info, quote=XRPL_TOKENS["XRP"],
                exchange_id=self.exchange_id, exchange_symbol=sym,
                fee_rate=self._fee_rate,
            )
            self._pair_defs[sym] = {
                "base": token_def["symbol"],
                "quote": "XRP",
                "issuer": token_def["issuer"],
                "currency": currency,
            }

        await self._discover_amm_pairs()

        logger.info(f"XRPL DEX adapter ready via {self._active_rpc} ({len(self._pairs)} pairs)")
        return True

    async def _discover_amm_pairs(self):
        pass

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

        taker_pays = {"currency": pair_def["currency"], "issuer": pair_def["issuer"]}
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
