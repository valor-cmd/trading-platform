import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

EXCHANGE_CONFIGS = {
    "binance": {"class": "binance", "label": "Binance", "default_taker_fee": 0.001},
    "coinbase": {"class": "coinbaseexchange", "label": "Coinbase", "default_taker_fee": 0.006},
    "kraken": {"class": "kraken", "label": "Kraken", "default_taker_fee": 0.0026},
    "kucoin": {"class": "kucoin", "label": "KuCoin", "default_taker_fee": 0.001},
    "okx": {"class": "okx", "label": "OKX", "default_taker_fee": 0.001},
    "bybit": {"class": "bybit", "label": "Bybit", "default_taker_fee": 0.001},
    "gateio": {"class": "gateio", "label": "Gate.io", "default_taker_fee": 0.002},
    "bitget": {"class": "bitget", "label": "Bitget", "default_taker_fee": 0.001},
    "mexc": {"class": "mexc", "label": "MEXC", "default_taker_fee": 0.001},
}


class LivePriceProvider:
    def __init__(self):
        self._exchanges: dict = {}
        self._markets: dict[str, dict] = {}
        self._ticker_cache: dict[str, dict] = {}
        self._cache_ttl = 5
        self._ohlcv_cache: dict[str, dict] = {}
        self._ohlcv_ttl = 30
        self._initialized = False
        self._all_symbols: dict[str, list[str]] = {}
        self._fees: dict[str, dict[str, float]] = {}

    async def initialize(self, exchange_ids: list[str] = None):
        if exchange_ids is None:
            exchange_ids = ["binance", "coinbase", "kraken"]

        import ccxt.async_support as ccxt

        for eid in exchange_ids:
            cfg = EXCHANGE_CONFIGS.get(eid)
            if not cfg:
                logger.warning(f"Unknown exchange: {eid}")
                continue
            try:
                exchange_class = getattr(ccxt, cfg["class"])
                exchange = exchange_class({"enableRateLimit": True})
                await exchange.load_markets()
                self._exchanges[eid] = exchange
                self._markets[eid] = exchange.markets

                symbols = []
                fees = {}
                for symbol, market in exchange.markets.items():
                    if not market.get("active", True):
                        continue
                    if market.get("type") not in ("spot", None):
                        continue
                    if market.get("spot") is False:
                        continue
                    symbols.append(symbol)
                    taker = market.get("taker")
                    if taker is not None:
                        fees[symbol] = taker
                    else:
                        fees[symbol] = cfg["default_taker_fee"]

                self._all_symbols[eid] = symbols
                self._fees[eid] = fees
                logger.info(f"Loaded {eid}: {len(symbols)} spot pairs")
            except Exception as e:
                logger.error(f"Failed to load {eid}: {e}")

        self._initialized = True
        total = sum(len(s) for s in self._all_symbols.values())
        logger.info(f"LivePriceProvider ready: {len(self._exchanges)} exchanges, {total} total pairs")

    async def close(self):
        for exchange in self._exchanges.values():
            try:
                await exchange.close()
            except Exception:
                pass
        self._exchanges.clear()

    def get_exchanges(self) -> list[str]:
        return list(self._exchanges.keys())

    def get_symbols(self, exchange_id: str) -> list[str]:
        return self._all_symbols.get(exchange_id, [])

    def get_all_symbols_flat(self) -> list[tuple[str, str]]:
        result = []
        for eid, symbols in self._all_symbols.items():
            for sym in symbols:
                result.append((eid, sym))
        return result

    def get_total_pairs(self) -> int:
        return sum(len(s) for s in self._all_symbols.values())

    def get_fee(self, exchange_id: str, symbol: str) -> float:
        return self._fees.get(exchange_id, {}).get(
            symbol,
            EXCHANGE_CONFIGS.get(exchange_id, {}).get("default_taker_fee", 0.001),
        )

    def find_common_pairs(self) -> dict[str, list[str]]:
        pair_exchanges: dict[str, list[str]] = {}
        for eid, symbols in self._all_symbols.items():
            for sym in symbols:
                if sym not in pair_exchanges:
                    pair_exchanges[sym] = []
                pair_exchanges[sym].append(eid)
        return {sym: exs for sym, exs in pair_exchanges.items() if len(exs) > 1}

    async def fetch_ticker(self, exchange_id: str, symbol: str) -> dict:
        cache_key = f"{exchange_id}:{symbol}"
        cached = self._ticker_cache.get(cache_key)
        if cached and (time.time() - cached["_fetched_at"]) < self._cache_ttl:
            return cached

        exchange = self._exchanges.get(exchange_id)
        if not exchange:
            raise ValueError(f"Exchange {exchange_id} not loaded")

        try:
            ticker = await exchange.fetch_ticker(symbol)
            result = {
                "symbol": symbol,
                "exchange": exchange_id,
                "last": ticker.get("last") or 0,
                "bid": ticker.get("bid") or 0,
                "ask": ticker.get("ask") or 0,
                "high": ticker.get("high") or 0,
                "low": ticker.get("low") or 0,
                "volume": ticker.get("baseVolume") or 0,
                "quoteVolume": ticker.get("quoteVolume") or 0,
                "change": ticker.get("percentage") or 0,
                "percentage": ticker.get("percentage") or 0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "_fetched_at": time.time(),
            }
            self._ticker_cache[cache_key] = result
            return result
        except Exception as e:
            logger.debug(f"Ticker fetch failed {exchange_id}:{symbol}: {e}")
            if cached:
                return cached
            raise

    async def fetch_ohlcv(self, exchange_id: str, symbol: str, timeframe: str = "1h", limit: int = 200):
        cache_key = f"{exchange_id}:{symbol}:{timeframe}"
        cached = self._ohlcv_cache.get(cache_key)
        if cached and (time.time() - cached["_fetched_at"]) < self._ohlcv_ttl:
            return cached["data"]

        exchange = self._exchanges.get(exchange_id)
        if not exchange:
            raise ValueError(f"Exchange {exchange_id} not loaded")

        try:
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            import pandas as pd
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            self._ohlcv_cache[cache_key] = {"data": df, "_fetched_at": time.time()}
            return df
        except Exception as e:
            logger.debug(f"OHLCV fetch failed {exchange_id}:{symbol}:{timeframe}: {e}")
            if cached:
                return cached["data"]
            raise

    async def fetch_tickers_batch(self, exchange_id: str, symbols: list[str]) -> dict[str, dict]:
        exchange = self._exchanges.get(exchange_id)
        if not exchange:
            return {}

        try:
            if hasattr(exchange, "fetch_tickers"):
                tickers = await exchange.fetch_tickers(symbols[:100])
                results = {}
                now = time.time()
                for sym, ticker in tickers.items():
                    result = {
                        "symbol": sym,
                        "exchange": exchange_id,
                        "last": ticker.get("last") or 0,
                        "bid": ticker.get("bid") or 0,
                        "ask": ticker.get("ask") or 0,
                        "high": ticker.get("high") or 0,
                        "low": ticker.get("low") or 0,
                        "volume": ticker.get("baseVolume") or 0,
                        "change": ticker.get("percentage") or 0,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "_fetched_at": now,
                    }
                    self._ticker_cache[f"{exchange_id}:{sym}"] = result
                    results[sym] = result
                return results
        except Exception as e:
            logger.debug(f"Batch ticker fetch failed for {exchange_id}: {e}")
        return {}

    async def refresh_tickers_for_symbols(self, symbols: list[str], timeout: float = 10.0,
                                          dex_adapters: dict = None) -> int:
        by_exchange: dict[str, list[str]] = {}
        unresolved: list[str] = []
        for sym in symbols:
            found = False
            for eid, syms in self._all_symbols.items():
                if sym in syms:
                    by_exchange.setdefault(eid, []).append(sym)
                    found = True
                    break
            if not found:
                unresolved.append(sym)

        updated = 0

        async def _refresh_exchange(eid: str, syms: list[str]):
            nonlocal updated
            exchange = self._exchanges.get(eid)
            if not exchange:
                return
            try:
                tickers = await asyncio.wait_for(
                    exchange.fetch_tickers(syms),
                    timeout=timeout,
                )
                now = time.time()
                for sym, ticker in tickers.items():
                    result = {
                        "symbol": sym,
                        "exchange": eid,
                        "last": ticker.get("last") or 0,
                        "bid": ticker.get("bid") or 0,
                        "ask": ticker.get("ask") or 0,
                        "high": ticker.get("high") or 0,
                        "low": ticker.get("low") or 0,
                        "volume": ticker.get("baseVolume") or 0,
                        "change": ticker.get("percentage") or 0,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "_fetched_at": now,
                    }
                    self._ticker_cache[f"{eid}:{sym}"] = result
                    updated += 1
            except asyncio.TimeoutError:
                logger.warning(f"Ticker refresh timeout for {eid} ({len(syms)} symbols)")
            except Exception as e:
                logger.debug(f"Ticker refresh failed for {eid}: {e}")

        tasks = [_refresh_exchange(eid, syms) for eid, syms in by_exchange.items()]
        await asyncio.gather(*tasks, return_exceptions=True)

        if unresolved and dex_adapters:
            dex_by_adapter: dict[str, list[str]] = {}
            for sym in unresolved:
                for dex_id, adapter in dex_adapters.items():
                    if sym in adapter.get_all_symbols():
                        dex_by_adapter.setdefault(dex_id, []).append(sym)
                        break

            async def _refresh_dex_symbol(dex_id: str, sym: str, adapter):
                nonlocal updated
                try:
                    ticker = await asyncio.wait_for(adapter.fetch_ticker(sym), timeout=5.0)
                    if ticker and ticker.last > 0:
                        self._ticker_cache[f"{dex_id}:{sym}"] = {
                            "symbol": sym,
                            "exchange": dex_id,
                            "last": ticker.last,
                            "bid": ticker.bid,
                            "ask": ticker.ask,
                            "high": ticker.high_24h,
                            "low": ticker.low_24h,
                            "volume": ticker.volume_24h,
                            "change": ticker.change_pct_24h,
                            "timestamp": ticker.timestamp,
                            "_fetched_at": time.time(),
                        }
                        updated += 1
                except Exception:
                    pass

            dex_tasks = []
            for dex_id, syms in dex_by_adapter.items():
                adapter = dex_adapters[dex_id]
                for sym in syms[:20]:
                    dex_tasks.append(_refresh_dex_symbol(dex_id, sym, adapter))
            if dex_tasks:
                await asyncio.gather(*dex_tasks, return_exceptions=True)

        return updated

    def status(self) -> dict:
        return {
            eid: {
                "label": EXCHANGE_CONFIGS.get(eid, {}).get("label", eid),
                "pairs": len(self._all_symbols.get(eid, [])),
                "connected": True,
            }
            for eid in self._exchanges
        }


live_prices = LivePriceProvider()
