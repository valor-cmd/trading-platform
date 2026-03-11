from web3 import Web3
from typing import Optional
import httpx

from app.core.config import settings


class MetaMaskWallet:
    def __init__(self, rpc_url: Optional[str] = None):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url or settings.metamask_rpc_url))

    def is_connected(self) -> bool:
        return self.w3.is_connected()

    def get_balance_eth(self, address: str) -> float:
        balance_wei = self.w3.eth.get_balance(address)
        return float(self.w3.from_wei(balance_wei, "ether"))

    async def get_balance_usd(self, address: str, eth_price: float) -> float:
        return self.get_balance_eth(address) * eth_price

    def get_token_balance(self, address: str, token_contract: str, abi: list) -> float:
        contract = self.w3.eth.contract(address=token_contract, abi=abi)
        balance = contract.functions.balanceOf(address).call()
        decimals = contract.functions.decimals().call()
        return balance / (10 ** decimals)


class XamanWallet:
    def __init__(self):
        self.api_key = settings.xaman_api_key
        self.api_secret = settings.xaman_api_secret
        self.base_url = "https://xumm.app/api/v1"

    async def get_xrp_balance(self, address: str) -> float:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://s1.ripple.com:51234",
                json={
                    "method": "account_info",
                    "params": [{"account": address, "ledger_index": "current"}],
                },
            )
            data = response.json()
            balance_drops = int(data["result"]["account_data"]["Balance"])
            return balance_drops / 1_000_000

    async def get_balance_usd(self, address: str, xrp_price: float) -> float:
        xrp = await self.get_xrp_balance(address)
        return xrp * xrp_price


class WalletManager:
    def __init__(self):
        self.metamask: Optional[MetaMaskWallet] = None
        self.xaman: Optional[XamanWallet] = None
        self.tracked_addresses: dict[str, dict] = {}

    def connect_metamask(self, rpc_url: Optional[str] = None) -> MetaMaskWallet:
        self.metamask = MetaMaskWallet(rpc_url)
        return self.metamask

    def connect_xaman(self) -> XamanWallet:
        self.xaman = XamanWallet()
        return self.xaman

    def track_address(self, label: str, address: str, chain: str):
        self.tracked_addresses[label] = {"address": address, "chain": chain}

    async def get_all_balances_usd(self, prices: dict) -> dict:
        balances = {}
        for label, info in self.tracked_addresses.items():
            address = info["address"]
            chain = info["chain"]
            try:
                if chain == "ethereum" and self.metamask:
                    balances[label] = await self.metamask.get_balance_usd(
                        address, prices.get("ETH", 0)
                    )
                elif chain == "xrpl" and self.xaman:
                    balances[label] = await self.xaman.get_balance_usd(
                        address, prices.get("XRP", 0)
                    )
            except Exception:
                balances[label] = 0.0
        return balances
