import logging
from typing import Optional
from app.exchange.adapters.base import TokenInfo, Chain

logger = logging.getLogger(__name__)


MAJOR_TOKENS = [
    TokenInfo(symbol="BTC", name="Bitcoin", chain=Chain.ETHEREUM, coingecko_id="bitcoin", tags=["major", "l1"]),
    TokenInfo(symbol="ETH", name="Ethereum", chain=Chain.ETHEREUM, is_native=True, coingecko_id="ethereum", tags=["major", "l1"]),
    TokenInfo(symbol="XRP", name="XRP", chain=Chain.XRPL, is_native=True, coingecko_id="ripple", tags=["major", "l1"]),
    TokenInfo(symbol="SOL", name="Solana", chain=Chain.SOLANA, is_native=True, coingecko_id="solana", tags=["major", "l1"]),
    TokenInfo(symbol="HBAR", name="Hedera", chain=Chain.HEDERA, is_native=True, coingecko_id="hedera-hashgraph", tags=["major", "l1"]),
    TokenInfo(symbol="ADA", name="Cardano", chain=Chain.ETHEREUM, coingecko_id="cardano", tags=["major", "l1"]),
    TokenInfo(symbol="DOGE", name="Dogecoin", chain=Chain.ETHEREUM, coingecko_id="dogecoin", tags=["major", "meme"]),
    TokenInfo(symbol="AVAX", name="Avalanche", chain=Chain.AVALANCHE, is_native=True, coingecko_id="avalanche-2", tags=["major", "l1"]),
    TokenInfo(symbol="DOT", name="Polkadot", chain=Chain.ETHEREUM, coingecko_id="polkadot", tags=["major", "l1"]),
    TokenInfo(symbol="LINK", name="Chainlink", chain=Chain.ETHEREUM, coingecko_id="chainlink", tags=["major", "oracle"]),
    TokenInfo(symbol="MATIC", name="Polygon", chain=Chain.POLYGON, is_native=True, coingecko_id="matic-network", tags=["major", "l2"]),
    TokenInfo(symbol="UNI", name="Uniswap", chain=Chain.ETHEREUM, coingecko_id="uniswap", tags=["major", "defi"]),
    TokenInfo(symbol="ATOM", name="Cosmos", chain=Chain.ETHEREUM, coingecko_id="cosmos", tags=["major", "l1"]),
    TokenInfo(symbol="LTC", name="Litecoin", chain=Chain.ETHEREUM, coingecko_id="litecoin", tags=["major"]),
    TokenInfo(symbol="NEAR", name="NEAR Protocol", chain=Chain.ETHEREUM, coingecko_id="near", tags=["major", "l1"]),
    TokenInfo(symbol="FIL", name="Filecoin", chain=Chain.ETHEREUM, coingecko_id="filecoin", tags=["major", "storage"]),
    TokenInfo(symbol="ARB", name="Arbitrum", chain=Chain.ARBITRUM, is_native=True, coingecko_id="arbitrum", tags=["major", "l2"]),
    TokenInfo(symbol="OP", name="Optimism", chain=Chain.OPTIMISM, is_native=True, coingecko_id="optimism", tags=["major", "l2"]),
    TokenInfo(symbol="SUI", name="Sui", chain=Chain.ETHEREUM, coingecko_id="sui", tags=["major", "l1"]),
    TokenInfo(symbol="APT", name="Aptos", chain=Chain.ETHEREUM, coingecko_id="aptos", tags=["major", "l1"]),
]


class TokenRegistry:
    def __init__(self):
        self._tokens: dict[str, dict[str, TokenInfo]] = {}

    def register(self, token: TokenInfo):
        key = f"{token.symbol}_{token.chain.value}"
        if token.chain.value not in self._tokens:
            self._tokens[token.chain.value] = {}
        self._tokens[token.chain.value][token.symbol] = token

    def register_bulk(self, tokens: list[TokenInfo]):
        for t in tokens:
            self.register(t)

    def get(self, symbol: str, chain: Optional[Chain] = None) -> Optional[TokenInfo]:
        if chain:
            return self._tokens.get(chain.value, {}).get(symbol)
        for chain_tokens in self._tokens.values():
            if symbol in chain_tokens:
                return chain_tokens[symbol]
        return None

    def get_all_by_chain(self, chain: Chain) -> list[TokenInfo]:
        return list(self._tokens.get(chain.value, {}).values())

    def get_by_tag(self, tag: str) -> list[TokenInfo]:
        result = []
        for chain_tokens in self._tokens.values():
            for token in chain_tokens.values():
                if tag in token.tags:
                    result.append(token)
        return result

    def get_all(self) -> list[TokenInfo]:
        result = []
        for chain_tokens in self._tokens.values():
            result.extend(chain_tokens.values())
        return result

    def search(self, query: str) -> list[TokenInfo]:
        q = query.lower()
        result = []
        for chain_tokens in self._tokens.values():
            for token in chain_tokens.values():
                if q in token.symbol.lower() or q in token.name.lower():
                    result.append(token)
        return result

    def status(self) -> dict:
        return {
            chain: len(tokens) for chain, tokens in self._tokens.items()
        }


token_registry = TokenRegistry()
token_registry.register_bulk(MAJOR_TOKENS)
