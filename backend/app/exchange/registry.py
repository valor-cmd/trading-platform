import logging
from typing import Optional
from app.exchange.adapters.base import BaseExchangeAdapter, ExchangeType, TickerData

logger = logging.getLogger(__name__)


class ExchangeRegistry:
    def __init__(self):
        self._exchanges: dict[str, BaseExchangeAdapter] = {}

    def register(self, adapter: BaseExchangeAdapter):
        self._exchanges[adapter.exchange_id] = adapter
        logger.info(f"Registered exchange: {adapter.exchange_id} ({adapter.exchange_type.value})")

    def unregister(self, exchange_id: str):
        self._exchanges.pop(exchange_id, None)

    def get(self, exchange_id: str) -> Optional[BaseExchangeAdapter]:
        return self._exchanges.get(exchange_id)

    def get_all(self) -> dict[str, BaseExchangeAdapter]:
        return dict(self._exchanges)

    def get_connected(self) -> dict[str, BaseExchangeAdapter]:
        return {k: v for k, v in self._exchanges.items() if v.is_connected()}

    def get_by_type(self, exchange_type: ExchangeType) -> dict[str, BaseExchangeAdapter]:
        return {k: v for k, v in self._exchanges.items() if v.exchange_type == exchange_type}

    def get_all_symbols(self) -> dict[str, list[str]]:
        result = {}
        for eid, adapter in self._exchanges.items():
            if adapter.is_connected():
                result[eid] = adapter.get_all_symbols()
        return result

    def get_all_symbols_flat(self) -> list[tuple[str, str]]:
        result = []
        for eid, adapter in self._exchanges.items():
            if adapter.is_connected():
                for sym in adapter.get_all_symbols():
                    result.append((eid, sym))
        return result

    async def fetch_ticker_all_exchanges(self, symbol: str) -> list[TickerData]:
        tickers = []
        for eid, adapter in self._exchanges.items():
            if not adapter.is_connected():
                continue
            if symbol in adapter.get_all_symbols():
                try:
                    ticker = await adapter.fetch_ticker(symbol)
                    tickers.append(ticker)
                except Exception as e:
                    logger.debug(f"Ticker fetch failed for {symbol} on {eid}: {e}")
        return tickers

    def find_common_pairs(self) -> dict[str, list[str]]:
        pair_exchanges: dict[str, list[str]] = {}
        for eid, adapter in self._exchanges.items():
            if not adapter.is_connected():
                continue
            for sym in adapter.get_all_symbols():
                if sym not in pair_exchanges:
                    pair_exchanges[sym] = []
                pair_exchanges[sym].append(eid)
        return {sym: exs for sym, exs in pair_exchanges.items() if len(exs) > 1}

    def status(self) -> dict:
        return {
            eid: {
                "type": adapter.exchange_type.value,
                "chain": adapter.chain.value if adapter.chain else None,
                "connected": adapter.is_connected(),
                "pairs": len(adapter.get_all_symbols()),
            }
            for eid, adapter in self._exchanges.items()
        }


exchange_registry = ExchangeRegistry()
