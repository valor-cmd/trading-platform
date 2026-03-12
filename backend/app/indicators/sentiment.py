import logging
import time
import aiohttp
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

FEAR_GREED_API = "https://api.alternative.me/fng/?limit=1"


@dataclass
class SentimentData:
    fear_greed_value: int
    fear_greed_label: str
    timestamp: datetime


class SentimentAnalyzer:
    def __init__(self):
        self._cached_value: int = 50
        self._cached_label: str = "Neutral"
        self._last_fetch: float = 0
        self._cache_ttl: int = 300

    async def get_fear_greed_index(self) -> SentimentData:
        now = time.time()
        if now - self._last_fetch < self._cache_ttl and self._last_fetch > 0:
            return SentimentData(
                fear_greed_value=self._cached_value,
                fear_greed_label=self._cached_label,
                timestamp=datetime.now(timezone.utc),
            )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(FEAR_GREED_API, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        entry = data.get("data", [{}])[0]
                        self._cached_value = int(entry.get("value", 50))
                        self._cached_label = entry.get("value_classification", "Neutral")
                        self._last_fetch = now
                        logger.debug(f"Fear & Greed Index: {self._cached_value} ({self._cached_label})")
        except Exception as e:
            logger.debug(f"Fear & Greed API fetch failed: {e}")

        return SentimentData(
            fear_greed_value=self._cached_value,
            fear_greed_label=self._cached_label,
            timestamp=datetime.now(timezone.utc),
        )

    def interpret_sentiment(self, value: int) -> dict:
        if value <= 20:
            return {"signal": "extreme_fear", "bias": "contrarian_buy", "weight": 0.8}
        elif value <= 40:
            return {"signal": "fear", "bias": "lean_buy", "weight": 0.6}
        elif value <= 60:
            return {"signal": "neutral", "bias": "neutral", "weight": 0.3}
        elif value <= 80:
            return {"signal": "greed", "bias": "lean_sell", "weight": 0.6}
        else:
            return {"signal": "extreme_greed", "bias": "contrarian_sell", "weight": 0.8}
