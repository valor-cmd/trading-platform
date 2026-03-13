import os
import logging
import asyncio
from typing import Optional
from datetime import datetime, timezone

from app.hummingbot.client import HummingbotAPIClient
from app.hummingbot.gateway_client import GatewayClient

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
        self._gateway: Optional[GatewayClient] = None
        self._gateway_url: Optional[str] = None
        self._connected = False
        self._gateway_connected = False
        self._paper_mode = True
        self._health_task: Optional[asyncio.Task] = None
        self._last_health: Optional[dict] = None
        self._rpc_configs: dict = {}

    @property
    def client(self) -> Optional[HummingbotAPIClient]:
        return self._client

    @property
    def gateway(self) -> Optional[GatewayClient]:
        return self._gateway

    @property
    def is_connected(self) -> bool:
        return self._connected or self._gateway_connected

    @property
    def is_gateway_connected(self) -> bool:
        return self._gateway_connected

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
        url = hbot_url or os.environ.get("HUMMINGBOT_API_URL", "")
        user = username or os.environ.get("HUMMINGBOT_USERNAME", "admin")
        pwd = password or os.environ.get("HUMMINGBOT_PASSWORD", "")
        gw_url = gateway_url or os.environ.get("HUMMINGBOT_GATEWAY_URL", "")
        self._gateway_url = gw_url

        if url:
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
                logger.info(f"Hummingbot API not available at {url}")
        else:
            self._connected = False
            logger.info("No HUMMINGBOT_API_URL configured, skipping Hummingbot API")

        if gw_url:
            if self._gateway:
                await self._gateway.close()
            self._gateway = GatewayClient(base_url=gw_url)
            gw_health = await self._gateway.health()
            if "error" not in gw_health:
                self._gateway_connected = True
                logger.info(f"Connected to Gateway at {gw_url}")
            else:
                self._gateway_connected = False
                logger.info(f"Gateway not available at {gw_url}")
        else:
            self._gateway_connected = False
            logger.info("No HUMMINGBOT_GATEWAY_URL configured, skipping Gateway")

        return {
            "connected": self._connected,
            "gateway_connected": self._gateway_connected,
            "health": self._last_health,
        }

    async def disconnect(self):
        if self._health_task:
            self._health_task.cancel()
        if self._client:
            await self._client.close()
        if self._gateway:
            await self._gateway.close()
        self._connected = False
        self._gateway_connected = False
        logger.info("Disconnected from Hummingbot services")

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

                    if self._gateway:
                        gw_health = await self._gateway.health()
                        was_gw = self._gateway_connected
                        self._gateway_connected = "error" not in gw_health
                        if not was_gw and self._gateway_connected:
                            logger.info("Gateway reconnected")
                        elif was_gw and not self._gateway_connected:
                            logger.warning("Gateway connection lost")
                except Exception as e:
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
                "rpc_configured": True,
                "gateway_update": result,
            }

        return {
            "chain": chain,
            "network": network,
            "provider": provider,
            "rpc_configured": True,
            "note": "Saved locally, will apply when gateway connects",
        }

    def get_rpc_configs(self) -> dict:
        safe = {}
        for k, v in self._rpc_configs.items():
            safe[k] = {
                "provider": v["provider"],
                "configured_at": v["configured_at"],
            }
        return safe

    async def status(self) -> dict:
        result = {
            "connected": self._connected,
            "gateway_connected": self._gateway_connected,
            "paper_mode": self._paper_mode,
            "rpc_configs": self.get_rpc_configs(),
        }
        if self._last_health:
            result["health"] = self._last_health

        if self._gateway and self._gateway_connected:
            try:
                connectors = await self._gateway.get_connectors()
                if "error" not in connectors:
                    result["gateway_connectors"] = connectors
            except Exception:
                pass

            try:
                chain_status = await self._gateway.get_chain_status()
                if "error" not in chain_status:
                    result["gateway_chains"] = chain_status
            except Exception:
                pass

        if self._client and self._connected:
            try:
                accounts = await self._client.get_accounts()
                if isinstance(accounts, list):
                    result["accounts"] = len(accounts)
                elif isinstance(accounts, dict) and "error" not in accounts:
                    result["accounts"] = accounts
            except Exception:
                pass

        return result


hbot_manager = HummingbotManager()
