import json
import os
import time
import logging
import random
import threading
import pandas as pd
from datetime import datetime, timezone
from typing import Optional

from app.exchange.live_prices import live_prices

logger = logging.getLogger(__name__)

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")


class PaperExchangeManager:
    def __init__(self, persist_path: Optional[str] = None):
        self.balances: dict[str, float] = {}
        self.connected_exchanges: set[str] = set()
        self.order_count = 0
        self._primary_exchange = "binance"
        self._persist_path = persist_path or os.path.join(DATA_DIR, "paper_exchange.json")
        self._save_lock = threading.Lock()
        self._load()

    def _load(self):
        try:
            if os.path.exists(self._persist_path):
                with open(self._persist_path, "r") as f:
                    data = json.load(f)
                self.balances = data.get("balances", {})
                self.order_count = data.get("order_count", 0)
                logger.info(f"Loaded paper exchange: balances={self.balances}, orders={self.order_count}")
        except Exception as e:
            logger.error(f"Failed to load paper exchange: {e}")

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
            data = {
                "balances": self.balances,
                "order_count": self.order_count,
            }
            with self._save_lock:
                tmp = self._persist_path + ".tmp"
                with open(tmp, "w") as f:
                    json.dump(data, f)
                os.replace(tmp, self._persist_path)
        except Exception as e:
            logger.error(f"Failed to save paper exchange: {e}")

    def connect(self, exchange_id: str):
        self.connected_exchanges.add(exchange_id)

    def is_connected(self, exchange_id: str) -> bool:
        return exchange_id in self.connected_exchanges

    def get_all_symbols(self) -> list[str]:
        all_syms = set()
        for eid in live_prices.get_exchanges():
            all_syms.update(live_prices.get_symbols(eid))
        if not all_syms:
            return []
        if not any(eid == self._primary_exchange for eid in live_prices.get_exchanges()):
            exchanges = live_prices.get_exchanges()
            if exchanges:
                self._primary_exchange = exchanges[0]
        return list(all_syms)

    def get_symbols_for_exchange(self, exchange_id: str) -> list[str]:
        return live_prices.get_symbols(exchange_id)

    async def fetch_ohlcv(self, exchange_id: str, symbol: str, timeframe: str = "1h", limit: int = 200) -> pd.DataFrame:
        if exchange_id and symbol in live_prices.get_symbols(exchange_id):
            ex = exchange_id
        else:
            ex = self._resolve_exchange(symbol)
        return await live_prices.fetch_ohlcv(ex, symbol, timeframe, limit)

    async def fetch_ticker(self, exchange_id: str, symbol: str) -> dict:
        ex = self._resolve_exchange(symbol)
        return await live_prices.fetch_ticker(ex, symbol)

    async def fetch_balance(self, exchange_id: str) -> dict:
        total = {}
        for asset, amount in self.balances.items():
            total[asset] = amount
        return {
            "total": total,
            "free": dict(total),
            "used": {k: 0 for k in total},
        }

    async def get_trading_fee(self, exchange_id: str, symbol: str) -> float:
        ex = self._resolve_exchange(symbol)
        return live_prices.get_fee(ex, symbol)

    async def create_order(
        self,
        exchange_id: str,
        symbol: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        order_type: str = "market",
    ) -> dict:
        self.order_count += 1

        ex = self._resolve_exchange(symbol)
        ticker = await live_prices.fetch_ticker(ex, symbol)

        if price is None:
            price = ticker["last"]

        bid = ticker.get("bid") or price
        ask = ticker.get("ask") or price
        spread = (ask - bid) / price if price > 0 else 0

        additional_slip = random.uniform(0.0001, 0.0003)
        if side == "buy":
            fill_price = ask if ask > 0 else price
            fill_price *= (1 + additional_slip)
        else:
            fill_price = bid if bid > 0 else price
            fill_price *= (1 - additional_slip)

        base = symbol.split("/")[0]
        quote = symbol.split("/")[1] if "/" in symbol else "USDT"
        fee_rate = await self.get_trading_fee(exchange_id, symbol)

        if side == "buy":
            cost = amount * fill_price
            fee = cost * fee_rate
            required = cost + fee
            available_quote = self.balances.get(quote, 0)
            if available_quote < required:
                if available_quote < 1.0:
                    raise ValueError(f"Insufficient {quote} balance: have {available_quote:.4f}, need {required:.4f}")
                amount = (available_quote * 0.999) / (fill_price * (1 + fee_rate))
                cost = amount * fill_price
                fee = cost * fee_rate
            self.balances[quote] = self.balances.get(quote, 0) - cost - fee
            self.balances[base] = self.balances.get(base, 0) + amount
        else:
            available_base = self.balances.get(base, 0)
            if available_base < amount:
                amount = available_base
            if amount <= 0:
                raise ValueError(f"Insufficient {base} balance for sell")
            revenue = amount * fill_price
            fee = revenue * fee_rate
            self.balances[base] = self.balances.get(base, 0) - amount
            self.balances[quote] = self.balances.get(quote, 0) + revenue - fee

        slippage_usd = abs(fill_price - price) * amount
        self._save()

        return {
            "id": f"paper_{self.order_count}_{int(time.time())}",
            "exchange": exchange_id,
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": fill_price,
            "requested_price": price,
            "bid": bid,
            "ask": ask,
            "spread_pct": round(spread * 100, 6),
            "slippage_usd": round(slippage_usd, 8),
            "cost": cost if side == "buy" else revenue,
            "fee": fee,
            "fee_rate": fee_rate,
            "type": order_type,
            "status": "filled",
            "paper": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def close_all(self):
        self.connected_exchanges.clear()

    def _resolve_exchange(self, symbol: str) -> str:
        for eid in [self._primary_exchange] + list(live_prices.get_exchanges()):
            if symbol in live_prices.get_symbols(eid):
                return eid
        return self._primary_exchange


paper_exchange = PaperExchangeManager()
