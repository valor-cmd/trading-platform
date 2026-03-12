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

JUPITER_TOKEN_LIST_URLS = [
    "https://token.jup.ag/all",
    "https://tokens.jup.ag/tokens?tags=verified",
    "https://tokens.jup.ag/tokens",
]
JUPITER_PRICE_URL = "https://api.jup.ag/price/v2"

WELL_KNOWN_SOLANA_MINTS = {
    "So11111111111111111111111111111111111111112": {"symbol": "SOL", "name": "Solana", "decimals": 9, "coingecko_id": "solana"},
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": {"symbol": "USDC", "name": "USD Coin", "decimals": 6},
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": {"symbol": "USDT", "name": "Tether USD", "decimals": 6},
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": {"symbol": "BONK", "name": "Bonk", "decimals": 5, "tags": ["meme"]},
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm": {"symbol": "WIF", "name": "dogwifhat", "decimals": 6, "tags": ["meme"]},
    "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL": {"symbol": "JTO", "name": "Jito", "decimals": 9, "tags": ["defi"]},
    "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3": {"symbol": "PYTH", "name": "Pyth Network", "decimals": 6, "tags": ["oracle"]},
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": {"symbol": "JUP", "name": "Jupiter", "decimals": 6, "tags": ["defi"]},
    "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R": {"symbol": "RAY", "name": "Raydium", "decimals": 6, "tags": ["defi"]},
    "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE": {"symbol": "ORCA", "name": "Orca", "decimals": 6, "tags": ["defi"]},
    "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof": {"symbol": "RENDER", "name": "Render", "decimals": 8, "tags": ["ai"]},
    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs": {"symbol": "WETH", "name": "Wrapped ETH (Wormhole)", "decimals": 8, "tags": ["wrapped"]},
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So": {"symbol": "mSOL", "name": "Marinade SOL", "decimals": 9, "tags": ["lst"]},
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn": {"symbol": "jitoSOL", "name": "Jito Staked SOL", "decimals": 9, "tags": ["lst"]},
    "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj": {"symbol": "stSOL", "name": "Lido Staked SOL", "decimals": 9, "tags": ["lst"]},
    "HeLp6NuQkmYB4pYWo2zYs22mESHXPQYzXbB8n4V98jwC": {"symbol": "AI16Z", "name": "ai16z", "decimals": 9, "tags": ["ai"]},
    "6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN": {"symbol": "TRUMP", "name": "Official Trump", "decimals": 6, "tags": ["meme"]},
    "CLoUDKc4Ane7HeQcPpE3YHnznRxhMimJ4MyaUqyHFzAu": {"symbol": "CLOUD", "name": "Cloud", "decimals": 9, "tags": []},
    "85VBFQZC9TZkfaptBWjvUw7YbZjy52A6mjtPGjstQAmQ": {"symbol": "W", "name": "Wormhole", "decimals": 6, "tags": ["infra"]},
    "TNSRxcUxoT9xBG3de7PiJyTDYu7kskLqcpddxnEJAS6": {"symbol": "TNSR", "name": "Tensor", "decimals": 9, "tags": ["nft"]},
    "MEW1gQWJ3nEXg2qgERiKu7FAFj79PHvQVREQUzScPP5": {"symbol": "MEW", "name": "cat in a dogs world", "decimals": 5, "tags": ["meme"]},
    "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr": {"symbol": "POPCAT", "name": "Popcat", "decimals": 9, "tags": ["meme"]},
    "DriFtupJYLTosbwoN8koMbEYSx54aFAVLddWsbksjwg7": {"symbol": "DRIFT", "name": "Drift", "decimals": 6, "tags": ["defi"]},
    "KMNo3nJsBXfcpJTVhZcXLW7RmTwTt4GVFE7suUBo9sS": {"symbol": "KMNO", "name": "Kamino", "decimals": 6, "tags": ["defi"]},
    "nosXBVoaCTtYdLvKY6Csb4AC8JCdQKKAaWYtx2ZMoo7": {"symbol": "NOS", "name": "Nosana", "decimals": 6, "tags": ["ai"]},
    "SHDWyBxihqiCj6YekG2GUr7wqKLeLAMK1gHZck9pL6y": {"symbol": "SHDW", "name": "Shadow Token", "decimals": 9, "tags": ["storage"]},
    "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1": {"symbol": "bSOL", "name": "BlazeStake SOL", "decimals": 9, "tags": ["lst"]},
    "MNDEFzGvMt87ueuHvVU9VcTqsAP5b3fTGPsHuuPA5ey": {"symbol": "MNDE", "name": "Marinade", "decimals": 9, "tags": ["defi"]},
    "A9mUU4qviSctJVPJdBJWkb28deg915LYJKrzQ19ji3FM": {"symbol": "USDCet", "name": "USDC (Wormhole)", "decimals": 6, "tags": ["stablecoin"]},
}

SOLANA_TOKENS: dict[str, TokenInfo] = {}


class SolanaDEXAdapter(BaseExchangeAdapter):
    def __init__(self):
        super().__init__("solana_dex", ExchangeType.DEX, Chain.SOLANA)
        self._fee_rate = 0.0025
        self._mint_to_symbol: dict[str, str] = {}
        self._symbol_to_mint: dict[str, str] = {}
        self._price_cache: dict[str, dict] = {}
        self._price_cache_ttl = 15
        self._jupiter_available = False

    async def connect(self, **credentials) -> bool:
        self.connected = True

        for mint, info in WELL_KNOWN_SOLANA_MINTS.items():
            sym = info["symbol"]
            token_info = TokenInfo(
                symbol=sym, name=info["name"], chain=Chain.SOLANA,
                contract_address=mint, decimals=info.get("decimals", 9),
                tags=info.get("tags", []) + ["solana"],
                coingecko_id=info.get("coingecko_id"),
            )
            SOLANA_TOKENS[sym] = token_info
            self._mint_to_symbol[mint] = sym
            self._symbol_to_mint[sym] = mint

        await self._load_jupiter_tokens()

        usdc_mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        sol_mint = "So11111111111111111111111111111111111111112"
        for mint, sym in self._mint_to_symbol.items():
            if mint in (usdc_mint, "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"):
                continue
            pair_sym = f"{sym}/USDC"
            base = SOLANA_TOKENS.get(sym, TokenInfo(symbol=sym, name=sym, chain=Chain.SOLANA))
            quote = SOLANA_TOKENS.get("USDC", TokenInfo(symbol="USDC", name="USDC", chain=Chain.SOLANA))
            self._pairs[pair_sym] = TradingPair(
                base=base, quote=quote,
                exchange_id=self.exchange_id, exchange_symbol=pair_sym,
                fee_rate=self._fee_rate,
            )

        for sym_str in ["SOL/USDT", "BONK/USDT", "WIF/USDT", "JTO/USDT", "JUP/USDT",
                         "RAY/USDT", "RENDER/USDT", "PYTH/USDT", "TRUMP/USDT", "ORCA/USDT",
                         "POPCAT/USDT", "MEW/USDT", "DRIFT/USDT"]:
            base_sym = sym_str.split("/")[0]
            for eid in live_prices.get_exchanges():
                if sym_str in live_prices.get_symbols(eid):
                    base = SOLANA_TOKENS.get(base_sym, TokenInfo(symbol=base_sym, name=base_sym, chain=Chain.SOLANA))
                    quote = TokenInfo(symbol="USDT", name="Tether USD", chain=Chain.SOLANA)
                    self._pairs[sym_str] = TradingPair(
                        base=base, quote=quote,
                        exchange_id=self.exchange_id, exchange_symbol=sym_str,
                        fee_rate=self._fee_rate,
                    )
                    break

        logger.info(f"Solana DEX adapter ready ({len(self._pairs)} pairs, jupiter={self._jupiter_available})")
        return True

    async def _load_jupiter_tokens(self):
        for url in JUPITER_TOKEN_LIST_URLS:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=30),
                        headers={"User-Agent": "TradingPlatform/1.0", "Accept": "application/json"},
                    ) as resp:
                        if resp.status == 200:
                            tokens = await resp.json()
                            count = 0
                            seen_symbols = set(self._mint_to_symbol.values())
                            for t in tokens:
                                mint = t.get("address", "")
                                sym = t.get("symbol", "")
                                name = t.get("name", sym)
                                decimals = t.get("decimals", 9)
                                if not mint or not sym or mint in self._mint_to_symbol:
                                    continue
                                if len(sym) > 20:
                                    continue
                                unique_sym = sym
                                if unique_sym in seen_symbols:
                                    unique_sym = f"{sym}.{mint[:6].lower()}"
                                if unique_sym in seen_symbols:
                                    continue
                                seen_symbols.add(unique_sym)
                                tags = t.get("tags", []) + ["solana"]
                                if "verified" in str(t.get("tags", [])):
                                    tags.append("jupiter-verified")
                                token_info = TokenInfo(
                                    symbol=unique_sym, name=name, chain=Chain.SOLANA,
                                    contract_address=mint, decimals=decimals,
                                    tags=tags,
                                )
                                SOLANA_TOKENS[unique_sym] = token_info
                                self._mint_to_symbol[mint] = unique_sym
                                self._symbol_to_mint[unique_sym] = mint
                                count += 1
                            logger.info(f"Loaded {count} Solana tokens from {url} ({len(self._mint_to_symbol)} total)")
                            self._jupiter_available = True
                            return
                        else:
                            logger.warning(f"Jupiter {url} returned {resp.status}, trying next...")
            except Exception as e:
                logger.warning(f"Jupiter {url} failed: {e}, trying next...")
        logger.warning("All Jupiter token list URLs failed -- using hardcoded tokens only")

    async def _fetch_jupiter_prices(self, mints: list[str]) -> dict[str, float]:
        results = {}
        try:
            batch_size = 100
            for i in range(0, len(mints), batch_size):
                batch = mints[i:i + batch_size]
                ids_param = ",".join(batch)
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{JUPITER_PRICE_URL}?ids={ids_param}",
                        timeout=aiohttp.ClientTimeout(total=10),
                        headers={"User-Agent": "TradingPlatform/1.0", "Accept": "application/json"},
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            price_data = data.get("data", {})
                            for mint, info in price_data.items():
                                price = info.get("price")
                                if price:
                                    results[mint] = float(price)
        except Exception as e:
            logger.debug(f"Jupiter price fetch failed: {e}")
        return results

    async def disconnect(self):
        self.connected = False

    async def fetch_ticker(self, symbol: str) -> TickerData:
        cached = self._price_cache.get(symbol)
        if cached and (time.time() - cached["_fetched_at"]) < self._price_cache_ttl:
            last = cached["price"]
            return TickerData(
                symbol=symbol, exchange_id=self.exchange_id, last=last,
                bid=last * 0.998, ask=last * 1.002,
                high_24h=last * 1.05, low_24h=last * 0.95,
                volume_24h=0, change_pct_24h=0,
                timestamp=datetime.now(timezone.utc).isoformat(),
                spread_pct=0.4,
            )

        base_sym = symbol.split("/")[0]
        mint = self._symbol_to_mint.get(base_sym)
        if mint and self._jupiter_available:
            prices = await self._fetch_jupiter_prices([mint])
            if mint in prices:
                last = prices[mint]
                self._price_cache[symbol] = {"price": last, "_fetched_at": time.time()}
                return TickerData(
                    symbol=symbol, exchange_id=self.exchange_id, last=last,
                    bid=last * 0.998, ask=last * 1.002,
                    high_24h=last * 1.05, low_24h=last * 0.95,
                    volume_24h=0, change_pct_24h=0,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    spread_pct=0.4,
                )

        usdt_sym = f"{base_sym}/USDT"
        for eid in live_prices.get_exchanges():
            if usdt_sym in live_prices.get_symbols(eid):
                ticker = await live_prices.fetch_ticker(eid, usdt_sym)
                last = ticker.get("last", 0)
                bid = ticker.get("bid", 0) or last * 0.997
                ask = ticker.get("ask", 0) or last * 1.003
                spread = ((ask - bid) / last * 100) if last > 0 else 0
                self._price_cache[symbol] = {"price": last, "_fetched_at": time.time()}
                return TickerData(
                    symbol=symbol, exchange_id=self.exchange_id, last=last,
                    bid=bid, ask=ask,
                    high_24h=ticker.get("high", 0), low_24h=ticker.get("low", 0),
                    volume_24h=ticker.get("volume", 0),
                    change_pct_24h=ticker.get("change", 0),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    spread_pct=round(max(spread, 0.3), 4),
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
            order_id=f"sol_dex_{int(time.time())}_{id(self)}",
            exchange_id=self.exchange_id,
            symbol=symbol, side=side, amount=amount, price=price,
            cost=amount * price, fee=fee, status="filled",
            timestamp=datetime.now(timezone.utc).isoformat(), is_paper=True,
        )

    async def fetch_trading_pairs(self) -> list[TradingPair]:
        return list(self._pairs.values())

    async def get_trading_fee(self, symbol: str) -> float:
        return self._fee_rate
