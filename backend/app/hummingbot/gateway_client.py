import os
import logging
import asyncio
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


class GatewayClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: int = 30,
    ):
        self.base_url = (base_url or os.environ.get(
            "HUMMINGBOT_GATEWAY_URL", "http://localhost:15888"
        )).rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None
        self._connected = False

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
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
                    logger.error(f"Gateway {method} {path} -> {resp.status}: {text}")
                    return {"error": text, "status": resp.status}
                return await resp.json()
        except aiohttp.ClientError as e:
            logger.error(f"Gateway connection error: {e}")
            return {"error": str(e), "status": 0}
        except asyncio.TimeoutError:
            logger.error(f"Gateway timeout: {method} {path}")
            return {"error": "timeout", "status": 0}

    async def get(self, path: str, **kwargs) -> dict:
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> dict:
        return await self._request("POST", path, **kwargs)

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def health(self) -> dict:
        result = await self.get("/")
        self._connected = "error" not in result
        return result

    async def get_connectors(self) -> dict:
        return await self.get("/config/connectors")

    async def get_chains(self) -> dict:
        return await self.get("/config/chains")

    async def get_chain_status(self) -> dict:
        chains = await self.get("/config/chains")
        result = {"chains": {}}
        if isinstance(chains, dict) and "error" not in chains:
            for chain_name in chains.get("chains", []):
                try:
                    status = await self.get(f"/chains/{chain_name}/status")
                    result["chains"][chain_name] = status
                except Exception:
                    result["chains"][chain_name] = {"error": "unavailable"}
        return result

    async def get_tokens(self, chain: str, network: str) -> dict:
        return await self.get("/tokens/")

    async def get_balances(self, chain: str, address: str, token_symbols: Optional[list] = None) -> dict:
        payload: dict = {"address": address}
        if token_symbols:
            payload["tokenSymbols"] = token_symbols
        return await self.post(f"/chains/{chain}/balances", json=payload)

    async def quote_swap(
        self,
        chain: str,
        connector: str,
        base_token: str,
        quote_token: str,
        amount: str,
        side: str = "BUY",
        network: Optional[str] = None,
        slippage: float = 1.0,
    ) -> dict:
        payload = {
            "chain": chain,
            "connector": connector,
            "baseToken": base_token,
            "quoteToken": quote_token,
            "amount": amount,
            "side": side,
            "allowedSlippage": str(slippage),
        }
        if network:
            payload["network"] = network
        return await self.post("/trading/swap/quote", json=payload)

    async def execute_swap(
        self,
        chain: str,
        connector: str,
        base_token: str,
        quote_token: str,
        amount: str,
        side: str = "BUY",
        network: Optional[str] = None,
        slippage: float = 1.0,
        address: Optional[str] = None,
        nonce: Optional[int] = None,
        max_fee_per_gas: Optional[str] = None,
        max_priority_fee_per_gas: Optional[str] = None,
    ) -> dict:
        payload = {
            "chain": chain,
            "connector": connector,
            "baseToken": base_token,
            "quoteToken": quote_token,
            "amount": amount,
            "side": side,
            "allowedSlippage": str(slippage),
        }
        if network:
            payload["network"] = network
        if address:
            payload["address"] = address
        if nonce is not None:
            payload["nonce"] = nonce
        if max_fee_per_gas:
            payload["maxFeePerGas"] = max_fee_per_gas
        if max_priority_fee_per_gas:
            payload["maxPriorityFeePerGas"] = max_priority_fee_per_gas
        return await self.post("/trading/swap/execute", json=payload)

    async def get_swap_status(self, chain: str, tx_hash: str, network: Optional[str] = None) -> dict:
        payload = {"txHash": tx_hash}
        return await self.post(f"/chains/{chain}/poll", json=payload)

    async def get_gas_estimate(self, chain: str) -> dict:
        return await self.post(f"/chains/{chain}/estimate-gas", json={})

    async def add_wallet(self, chain: str, private_key: str, network: Optional[str] = None) -> dict:
        if not private_key or len(private_key) < 32:
            return {"error": "Invalid private key format"}
        payload = {"chain": chain, "privateKey": private_key}
        if network:
            payload["network"] = network
        result = await self.post("/wallet/add", json=payload)
        if "address" in result:
            result.pop("privateKey", None)
        return result

    async def get_wallets(self) -> dict:
        return await self.get("/wallet")

    async def remove_wallet(self, chain: str, address: str) -> dict:
        return await self.post("/wallet/remove", json={"chain": chain, "address": address})


gateway_client = GatewayClient()
