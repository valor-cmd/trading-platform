import logging
import asyncio
from typing import Optional
from datetime import datetime, timezone

import aiohttp

logger = logging.getLogger(__name__)


class HummingbotAPIClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8001",
        username: str = "admin",
        password: str = "admin",
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self._auth = aiohttp.BasicAuth(username, password)
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                auth=self._auth,
                timeout=self._timeout,
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        session = await self._get_session()
        url = f"{self.base_url}{path}"
        try:
            async with session.request(method, url, **kwargs) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    logger.error(f"Hummingbot API {method} {path} -> {resp.status}: {text}")
                    return {"error": text, "status": resp.status}
                return await resp.json()
        except aiohttp.ClientError as e:
            logger.error(f"Hummingbot API connection error: {e}")
            return {"error": str(e), "status": 0}
        except asyncio.TimeoutError:
            logger.error(f"Hummingbot API timeout: {method} {path}")
            return {"error": "timeout", "status": 0}

    async def get(self, path: str, **kwargs) -> dict:
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> dict:
        return await self._request("POST", path, **kwargs)

    async def delete(self, path: str, **kwargs) -> dict:
        return await self._request("DELETE", path, **kwargs)

    async def health(self) -> dict:
        return await self.get("/health")

    async def add_account(self, account_name: str, connector: str, api_key: str, api_secret: str, **extra) -> dict:
        payload = {
            "account_name": account_name,
            "connector": connector,
            "api_key": api_key,
            "api_secret": api_secret,
            **extra,
        }
        return await self.post("/accounts", json=payload)

    async def get_accounts(self) -> dict:
        return await self.get("/accounts")

    async def delete_account(self, account_name: str) -> dict:
        return await self.delete(f"/accounts/{account_name}")

    async def get_connectors(self) -> dict:
        return await self.get("/connectors")

    async def get_portfolio(self, account_name: Optional[str] = None) -> dict:
        path = f"/portfolio/{account_name}" if account_name else "/portfolio"
        return await self.get(path)

    async def get_ticker(self, connector: str, pair: str) -> dict:
        return await self.get(f"/market-data/ticker/{connector}/{pair}")

    async def get_orderbook(self, connector: str, pair: str) -> dict:
        return await self.get(f"/market-data/orderbook/{connector}/{pair}")

    async def get_candles(self, connector: str, pair: str, interval: str = "1h", limit: int = 100) -> dict:
        return await self.get(
            f"/market-data/candles/{connector}/{pair}",
            params={"interval": interval, "limit": limit},
        )

    async def create_order(
        self,
        connector: str,
        trading_pair: str,
        order_type: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        account_name: Optional[str] = None,
    ) -> dict:
        payload = {
            "connector": connector,
            "trading_pair": trading_pair,
            "order_type": order_type,
            "side": side,
            "amount": amount,
        }
        if price is not None:
            payload["price"] = price
        if account_name:
            payload["account_name"] = account_name
        return await self.post("/trading/orders", json=payload)

    async def cancel_order(self, connector: str, trading_pair: str, order_id: str) -> dict:
        return await self.delete(
            f"/trading/orders/{order_id}",
            params={"connector": connector, "trading_pair": trading_pair},
        )

    async def get_open_orders(self, connector: Optional[str] = None) -> dict:
        params = {"connector": connector} if connector else {}
        return await self.get("/trading/orders", params=params)

    async def get_trade_history(self, connector: Optional[str] = None, limit: int = 100) -> dict:
        params = {"limit": limit}
        if connector:
            params["connector"] = connector
        return await self.get("/trading/trades", params=params)

    async def deploy_bot(self, bot_name: str, image: str = "hummingbot/hummingbot:latest", **config) -> dict:
        payload = {
            "bot_name": bot_name,
            "image": image,
            **config,
        }
        return await self.post("/bots/deploy", json=payload)

    async def start_bot(self, bot_name: str, script: str, config: Optional[dict] = None) -> dict:
        payload = {"script": script}
        if config:
            payload["config"] = config
        return await self.post(f"/bots/{bot_name}/start", json=payload)

    async def stop_bot(self, bot_name: str) -> dict:
        return await self.post(f"/bots/{bot_name}/stop")

    async def get_bot_status(self, bot_name: str) -> dict:
        return await self.get(f"/bots/{bot_name}/status")

    async def list_bots(self) -> dict:
        return await self.get("/bots")

    async def get_bot_history(self, bot_name: str) -> dict:
        return await self.get(f"/bots/{bot_name}/history")

    async def run_backtest(self, config: dict) -> dict:
        return await self.post("/backtesting/run", json=config)

    async def get_backtest_results(self, backtest_id: str) -> dict:
        return await self.get(f"/backtesting/{backtest_id}")

    async def gateway_status(self) -> dict:
        return await self.get("/gateway/status")

    async def gateway_get_chains(self) -> dict:
        return await self.get("/gateway/chains")

    async def gateway_get_connectors(self) -> dict:
        return await self.get("/gateway/connectors")

    async def gateway_get_tokens(self, chain: str, network: str) -> dict:
        return await self.get(f"/gateway/tokens/{chain}/{network}")

    async def gateway_get_balances(self, chain: str, network: str, address: str) -> dict:
        return await self.get(
            f"/gateway/balances",
            params={"chain": chain, "network": network, "address": address},
        )

    async def gateway_quote_swap(
        self,
        chain: str,
        network: str,
        connector: str,
        base_token: str,
        quote_token: str,
        amount: str,
        side: str = "buy",
        slippage: float = 1.0,
    ) -> dict:
        payload = {
            "chain": chain,
            "network": network,
            "connector": connector,
            "base": base_token,
            "quote": quote_token,
            "amount": amount,
            "side": side,
            "slippage": slippage,
        }
        return await self.post("/gateway/swaps/quote", json=payload)

    async def gateway_execute_swap(
        self,
        chain: str,
        network: str,
        connector: str,
        base_token: str,
        quote_token: str,
        amount: str,
        side: str = "buy",
        slippage: float = 1.0,
        address: Optional[str] = None,
    ) -> dict:
        payload = {
            "chain": chain,
            "network": network,
            "connector": connector,
            "base": base_token,
            "quote": quote_token,
            "amount": amount,
            "side": side,
            "slippage": slippage,
        }
        if address:
            payload["address"] = address
        return await self.post("/gateway/swaps/execute", json=payload)

    async def gateway_swap_status(self, chain: str, network: str, tx_hash: str) -> dict:
        return await self.get(
            f"/gateway/swaps/status",
            params={"chain": chain, "network": network, "txHash": tx_hash},
        )
