import random
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class SentimentData:
    fear_greed_value: int
    fear_greed_label: str
    timestamp: datetime


class SentimentAnalyzer:
    def __init__(self):
        self._cached_value = random.randint(25, 75)

    async def get_fear_greed_index(self) -> SentimentData:
        self._cached_value = max(5, min(95, self._cached_value + random.randint(-3, 3)))
        if self._cached_value <= 20:
            label = "Extreme Fear"
        elif self._cached_value <= 40:
            label = "Fear"
        elif self._cached_value <= 60:
            label = "Neutral"
        elif self._cached_value <= 80:
            label = "Greed"
        else:
            label = "Extreme Greed"
        return SentimentData(
            fear_greed_value=self._cached_value,
            fear_greed_label=label,
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
