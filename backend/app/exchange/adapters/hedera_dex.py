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

HEDERA_MIRROR_NODE = "https://mainnet.mirrornode.hedera.com"
SAUCERSWAP_API = "https://api.saucerswap.finance"

WELL_KNOWN_HEDERA_TOKENS = {
    "0.0.456858": {"symbol": "USDC", "name": "USD Coin", "decimals": 6, "tags": ["stablecoin"]},
    "0.0.731861": {"symbol": "SAUCE", "name": "SaucerSwap", "decimals": 6, "tags": ["defi"], "coingecko_id": "saucerswap"},
    "0.0.1462860": {"symbol": "HBARX", "name": "Stader HBAR", "decimals": 8, "tags": ["liquid-staking"], "coingecko_id": "stader-hbarx"},
    "0.0.3407403": {"symbol": "PACK", "name": "HashPack", "decimals": 6, "tags": ["wallet"]},
    "0.0.3229415": {"symbol": "DOVU", "name": "DOVU", "decimals": 8, "tags": ["carbon"], "coingecko_id": "dovu"},
    "0.0.786931": {"symbol": "JAM", "name": "JAM", "decimals": 8, "tags": ["meme"]},
    "0.0.2997373": {"symbol": "KARATE", "name": "Karate Combat", "decimals": 8, "tags": ["gaming"], "coingecko_id": "karate-combat"},
    "0.0.1460200": {"symbol": "HST", "name": "HeadStarter", "decimals": 8, "tags": ["launchpad"]},
    "0.0.1096625": {"symbol": "GRELF", "name": "Grelf", "decimals": 8, "tags": ["meme"]},
    "0.0.4367390": {"symbol": "STEAM", "name": "SteamCoin", "decimals": 6, "tags": []},
    "0.0.4500306": {"symbol": "HLQT", "name": "HeliSwap Liquity", "decimals": 8, "tags": ["defi"]},
    "0.0.834116": {"symbol": "USDT", "name": "Tether USD", "decimals": 6, "tags": ["stablecoin"]},
    "0.0.1456986": {"symbol": "DAI", "name": "DAI", "decimals": 8, "tags": ["stablecoin"]},
    "0.0.2060657": {"symbol": "DOVU2", "name": "DOVU v2", "decimals": 8, "tags": ["carbon"]},
    "0.0.1083100": {"symbol": "BSL", "name": "BankSocial", "decimals": 8, "tags": ["defi"]},
    "0.0.786931": {"symbol": "JAM", "name": "JAM", "decimals": 8, "tags": ["meme"]},
    "0.0.4603070": {"symbol": "XSAUCE", "name": "xSAUCE", "decimals": 6, "tags": ["defi"]},
    "0.0.3155170": {"symbol": "HASHINTEL", "name": "HashIntel", "decimals": 8, "tags": ["ai"]},
    "0.0.2279646": {"symbol": "BUZZ", "name": "BuzzBar", "decimals": 8, "tags": ["meme"]},
    "0.0.1270555": {"symbol": "PANGEA", "name": "Pangea", "decimals": 8, "tags": []},
    "0.0.2062508": {"symbol": "HELI", "name": "HeliSwap", "decimals": 8, "tags": ["defi"]},
    "0.0.3640227": {"symbol": "LUCKY", "name": "Lucky Token", "decimals": 8, "tags": ["gaming"]},
    "0.0.5023530": {"symbol": "DAVINCIJ15", "name": "DaVinciJ15", "decimals": 8, "tags": []},
    "0.0.4440608": {"symbol": "QUACK", "name": "Quack", "decimals": 8, "tags": ["meme"]},
}

HEDERA_TOKENS: dict[str, TokenInfo] = {
    "HBAR": TokenInfo(symbol="HBAR", name="Hedera", chain=Chain.HEDERA, is_native=True, decimals=8, coingecko_id="hedera-hashgraph"),
}


class HederaDEXAdapter(BaseExchangeAdapter):
    def __init__(self):
        super().__init__("hedera_dex", ExchangeType.DEX, Chain.HEDERA)
        self._fee_rate = 0.003
        self._token_id_to_symbol: dict[str, str] = {}
        self._symbol_to_token_id: dict[str, str] = {}
        self._price_cache: dict[str, dict] = {}
        self._price_cache_ttl = 15
        self._saucerswap_available = False

    async def connect(self, **credentials) -> bool:
        self.connected = True

        for token_id, info in WELL_KNOWN_HEDERA_TOKENS.items():
            sym = info["symbol"]
            token_info = TokenInfo(
                symbol=sym, name=info["name"], chain=Chain.HEDERA,
                contract_address=token_id, decimals=info.get("decimals", 8),
                tags=info.get("tags", []) + ["hedera"],
                coingecko_id=info.get("coingecko_id"),
            )
            HEDERA_TOKENS[sym] = token_info
            self._token_id_to_symbol[token_id] = sym
            self._symbol_to_token_id[sym] = token_id

        await self._load_mirror_node_tokens()
        await self._load_saucerswap_prices()

        hbar = HEDERA_TOKENS["HBAR"]
        for sym, token_info in HEDERA_TOKENS.items():
            if sym == "HBAR":
                continue
            pair_sym = f"{sym}/HBAR"
            self._pairs[pair_sym] = TradingPair(
                base=token_info, quote=hbar,
                exchange_id=self.exchange_id, exchange_symbol=pair_sym,
                fee_rate=self._fee_rate,
            )

        for sym_str in ["HBAR/USDT", "HBAR/USDC"]:
            base_sym = sym_str.split("/")[0]
            quote_sym = sym_str.split("/")[1]
            for eid in live_prices.get_exchanges():
                if sym_str in live_prices.get_symbols(eid):
                    self._pairs[sym_str] = TradingPair(
                        base=HEDERA_TOKENS["HBAR"],
                        quote=TokenInfo(symbol=quote_sym, name=quote_sym, chain=Chain.HEDERA),
                        exchange_id=self.exchange_id, exchange_symbol=sym_str,
                        fee_rate=self._fee_rate,
                    )
                    break

        logger.info(f"Hedera DEX adapter ready ({len(self._pairs)} pairs, saucerswap={self._saucerswap_available})")
        return True

    async def _load_mirror_node_tokens(self):
        try:
            url = f"{HEDERA_MIRROR_NODE}/api/v1/tokens?type=FUNGIBLE_COMMON&limit=100&order=desc"
            count = 0
            pages = 0
            max_pages = 50
            async with aiohttp.ClientSession() as session:
                while url and pages < max_pages:
                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=15),
                        headers={"Accept": "application/json"},
                    ) as resp:
                        if resp.status != 200:
                            logger.warning(f"Mirror node returned {resp.status}")
                            break
                        data = await resp.json()
                        tokens = data.get("tokens", [])
                        for t in tokens:
                            token_id = t.get("token_id", "")
                            sym = t.get("symbol", "")
                            name = t.get("name", sym)
                            decimals = int(t.get("decimals", "8") or "8")
                            if not token_id or not sym or token_id in self._token_id_to_symbol:
                                continue
                            if len(sym) > 20 or sym.startswith("0x"):
                                continue
                            token_info = TokenInfo(
                                symbol=sym, name=name, chain=Chain.HEDERA,
                                contract_address=token_id, decimals=decimals,
                                tags=["hedera", "mirror-node"],
                            )
                            if sym not in HEDERA_TOKENS:
                                HEDERA_TOKENS[sym] = token_info
                            self._token_id_to_symbol[token_id] = sym
                            self._symbol_to_token_id[sym] = token_id
                            count += 1
                        next_link = data.get("links", {}).get("next")
                        if next_link:
                            url = f"{HEDERA_MIRROR_NODE}{next_link}"
                        else:
                            url = None
                        pages += 1
            logger.info(f"Loaded {count} additional tokens from Hedera Mirror Node ({len(self._token_id_to_symbol)} total)")
        except Exception as e:
            logger.warning(f"Failed to load Mirror Node tokens: {e}")

    async def _load_saucerswap_prices(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{SAUCERSWAP_API}/tokens",
                    timeout=aiohttp.ClientTimeout(total=10),
                    headers={"Accept": "application/json"},
                ) as resp:
                    if resp.status == 200:
                        tokens = await resp.json()
                        now = time.time()
                        for t in tokens:
                            token_id = t.get("id", "")
                            price_usd = t.get("priceUsd")
                            sym = self._token_id_to_symbol.get(token_id)
                            if sym and price_usd:
                                try:
                                    self._price_cache[sym] = {"price_usd": float(price_usd), "_fetched_at": now}
                                except (ValueError, TypeError):
                                    pass
                        self._saucerswap_available = True
                        logger.info(f"Loaded {len(self._price_cache)} prices from SaucerSwap")
                    else:
                        logger.warning(f"SaucerSwap tokens returned {resp.status}")
        except Exception as e:
            logger.warning(f"Failed to load SaucerSwap prices: {e}")

    async def _refresh_saucerswap_prices(self):
        oldest = min(
            (v["_fetched_at"] for v in self._price_cache.values()),
            default=0,
        )
        if time.time() - oldest < self._price_cache_ttl:
            return
        await self._load_saucerswap_prices()

    async def disconnect(self):
        self.connected = False

    async def fetch_ticker(self, symbol: str) -> TickerData:
        base_sym = symbol.split("/")[0]

        if self._saucerswap_available:
            await self._refresh_saucerswap_prices()
            cached = self._price_cache.get(base_sym)
            if cached and (time.time() - cached["_fetched_at"]) < self._price_cache_ttl * 4:
                last = cached["price_usd"]
                if last and last > 0:
                    return TickerData(
                        symbol=symbol, exchange_id=self.exchange_id, last=last,
                        bid=last * 0.997, ask=last * 1.003,
                        high_24h=last * 1.05, low_24h=last * 0.95,
                        volume_24h=0, change_pct_24h=0,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        spread_pct=0.6,
                    )

        usdt_sym = f"{base_sym}/USDT"
        for eid in live_prices.get_exchanges():
            if usdt_sym in live_prices.get_symbols(eid):
                ticker = await live_prices.fetch_ticker(eid, usdt_sym)
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
        base_sym = symbol.split("/")[0]
        usdt_sym = f"{base_sym}/USDT"
        for eid in live_prices.get_exchanges():
            if usdt_sym in live_prices.get_symbols(eid):
                return await live_prices.fetch_ohlcv(eid, usdt_sym, timeframe, limit)
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
