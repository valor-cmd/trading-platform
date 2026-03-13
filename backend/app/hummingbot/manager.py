import os
import logging
import asyncio
from typing import Optional
from datetime import datetime, timezone

from app.hummingbot.client import HummingbotAPIClient

logger = logging.getLogger(__name__)

PRIVATE_RPCS = {
    "ethereum": {
        "mainnet": {
            "flashbots": "https://rpc.flashbots.net/fast",
            "infura": "https://mainnet.infura.io/v3/{api_key}",
        },
        "goerli": {
            "infura": "https://goerli.infura.io/v3/{api_key}",
        },
    },
    "solana": {
        "mainnet": {
            "helius": "https://mainnet.helius-rpc.com/?api-key={api_key}",
        },
    },
}


class HummingbotManager:
    def __init__(self):
        self._client: Optional[HummingbotAPIClient] = None
        self._gateway_url: Optional[str] = None
        self._connected = False
        self._paper_mode = True
        self._health_task: Optional[asyncio.Task] = None
        self._last_health: Optional[dict] = None
        self._rpc_configs: dict = {}

    @property
    def client(self) -> Optional[HummingbotAPIClient]:
        return self._client

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_paper_mode(self) -> bool:
        return self._paper_mode

    async def connect(
        self,
        hbot_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        gateway_url: Optional[str] = None,
    ):
        url = hbot_url or os.environ.get("HUMMINGBOT_API_URL", "http://localhost:8001")
        user = username or os.environ.get("HUMMINGBOT_USERNAME", "admin")
        pwd = password or os.environ.get("HUMMINGBOT_PASSWORD", "admin")
        self._gateway_url = gateway_url or os.environ.get("HUMMINGBOT_GATEWAY_URL", "http://localhost:15888")

        if self._client:
            await self._client.close()

        self._client = HummingbotAPIClient(
            base_url=url,
            username=user,
            password=pwd,
        )

        health = await self._client.health()
        if "error" not in health:
            self._connected = True
            self._last_health = health
            logger.info(f"Connected to Hummingbot API at {url}")
        else:
            self._connected = False
            logger.warning(f"Hummingbot API not available at {url}: {health.get('error')}")

        return {"connected": self._connected, "health": health}

    async def disconnect(self):
        if self._health_task:
            self._health_task.cancel()
        if self._client:
            await self._client.close()
        self._connected = False
        logger.info("Disconnected from Hummingbot API")

    async def start_health_monitor(self, interval: int = 30):
        async def _monitor():
            while True:
                try:
                    if self._client:
                        health = await self._client.health()
                        was_connected = self._connected
                        self._connected = "error" not in health
                        self._last_health = health
                        if not was_connected and self._connected:
                            logger.info("Hummingbot API reconnected")
                        elif was_connected and not self._connected:
                            logger.warning("Hummingbot API connection lost")
                except Exception as e:
                    self._connected = False
                    logger.debug(f"Health check failed: {e}")
                await asyncio.sleep(interval)

        self._health_task = asyncio.create_task(_monitor(), name="hbot_health")

    def set_mode(self, paper: bool):
        self._paper_mode = paper
        logger.info(f"Hummingbot mode set to: {'PAPER' if paper else 'LIVE'}")

    def get_connector_name(self, exchange: str) -> str:
        if self._paper_mode:
            return f"{exchange}_paper_trade"
        return exchange

    async def add_exchange_credentials(
        self,
        exchange: str,
        api_key: str,
        api_secret: str,
        account_name: Optional[str] = None,
        **extra,
    ) -> dict:
        if not self._client or not self._connected:
            return {"error": "Not connected to Hummingbot API"}

        name = account_name or exchange
        return await self._client.add_account(
            account_name=name,
            connector=exchange,
            api_key=api_key,
            api_secret=api_secret,
            **extra,
        )

    async def configure_private_rpc(
        self,
        chain: str,
        network: str = "mainnet",
        provider: str = "flashbots",
        api_key: Optional[str] = None,
    ) -> dict:
        chain_rpcs = PRIVATE_RPCS.get(chain, {}).get(network, {})
        rpc_template = chain_rpcs.get(provider)
        if not rpc_template:
            return {"error": f"No RPC template for {chain}/{network}/{provider}"}

        rpc_url = rpc_template
        if "{api_key}" in rpc_url:
            if not api_key:
                return {"error": f"API key required for {provider}"}
            rpc_url = rpc_url.replace("{api_key}", api_key)

        self._rpc_configs[f"{chain}:{network}"] = {
            "provider": provider,
            "url": rpc_url,
            "configured_at": datetime.now(timezone.utc).isoformat(),
        }

        if self._client and self._connected:
            result = await self._client.post(
                f"/gateway/config/{chain}/update",
                json={"nodeURL": rpc_url, "rpcProvider": provider},
            )
            return {
                "chain": chain,
                "network": network,
                "provider": provider,
                "rpc_url": rpc_url[:40] + "...",
                "gateway_update": result,
            }

        return {
            "chain": chain,
            "network": network,
            "provider": provider,
            "rpc_url": rpc_url[:40] + "...",
            "note": "Saved locally, will apply when gateway connects",
        }

    def get_rpc_configs(self) -> dict:
        safe = {}
        for k, v in self._rpc_configs.items():
            safe[k] = {
                "provider": v["provider"],
                "configured_at": v["configured_at"],
                "url_preview": v["url"][:30] + "...",
            }
        return safe

    async def status(self) -> dict:
        result = {
            "connected": self._connected,
            "paper_mode": self._paper_mode,
            "gateway_url": self._gateway_url,
            "rpc_configs": self.get_rpc_configs(),
        }
        if self._last_health:
            result["health"] = self._last_health

        if self._client and self._connected:
            try:
                accounts = await self._client.get_accounts()
                if isinstance(accounts, list):
                    result["accounts"] = len(accounts)
                elif isinstance(accounts, dict) and "error" not in accounts:
                    result["accounts"] = accounts
            except Exception:
                pass

            try:
                gw = await self._client.gateway_status()
                if "error" not in gw:
                    result["gateway"] = gw
            except Exception:
                pass

        return result


hbot_manager = HummingbotManager()
