import asyncio
import logging
import time
from typing import Optional
from dataclasses import dataclass, field

import aiohttp

from app.core.config import settings

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"

ACTORS = {
    "cryptopanic_news": "piotrv1001~cryptopanic-news-scraper",
    "crypto_signals": "cryptosignals~crypto-signals",
    "whale_tracker": "thrilled_estuary~whale-tracker",
    "coinmarketcap": "louisdeconinck~coinmarketcap-crypto-scraper",
    "yahoo_finance": "datastorm~market-data-api",
    "twitter_sentiment": "mikolabs~tweets-x-scraper",
    "finance_agent": "jakub.kopecky~finance-monitoring-agent",
    "kepler_insights": "adept-training-center~kepler-market-insights-analyst",
    "crypto_news_pro": "buseta~crypto-news",
    "token_scanner": "ntriqpro~crypto-token-scanner",
}

TWITTER_SSE_BASE = "https://muhammetakkurtt--crypto-twitter-tracker.apify.actor"

COINSKID_URLS = {
    "heatmap": "https://www.coinskid.com/buy-sell-heatmap.html",
    "ckr_index": "https://www.coinskid.com/crypto-top-and-bottom-indicator.html",
    "crypto_blocks": "https://www.coinskid.com/crypto-blocks.html",
    "sell_short": "https://www.coinskid.com/buy-sell-heatmap-sell-short-warning.html",
}


@dataclass
class SignalEntry:
    source: str
    signal_type: str
    symbol: str
    direction: str
    confidence: float
    detail: str
    timestamp: float = 0.0


class ApifyIntelligence:
    def __init__(self):
        self._token: str = getattr(settings, "apify_api_token", "")
        self._cache: dict[str, dict] = {}
        self._cache_ttl: dict[str, int] = {
            "cryptopanic_news": 300,
            "crypto_signals": 120,
            "whale_tracker": 600,
            "coinmarketcap": 1800,
            "yahoo_finance": 900,
            "twitter_sentiment": 300,
            "finance_agent": 3600,
            "kepler_insights": 3600,
            "crypto_news_pro": 300,
            "token_scanner": 600,
            "coinskid_ckr": 600,
            "twitter_stream": 60,
            "unified_signals": 60,
        }
        self._last_fetch: dict[str, float] = {}
        self._signals: list[SignalEntry] = []

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _is_cached(self, key: str) -> bool:
        if key not in self._cache:
            return False
        ttl = self._cache_ttl.get(key, 300)
        return (time.time() - self._last_fetch.get(key, 0)) < ttl

    def _set_cache(self, key: str, data: dict):
        self._cache[key] = data
        self._last_fetch[key] = time.time()

    async def _run_actor_sync(self, actor_id: str, run_input: dict, timeout: int = 120) -> list:
        if not self._token:
            return [{"error": "APIFY_API_TOKEN not configured"}]
        url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
        params = {"token": self._token, "timeout": timeout}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=run_input, params=params,
                    timeout=aiohttp.ClientTimeout(total=timeout + 30),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    text = await resp.text()
                    logger.warning(f"Apify actor {actor_id} returned {resp.status}: {text[:200]}")
                    return [{"error": f"HTTP {resp.status}", "detail": text[:200]}]
        except Exception as e:
            logger.warning(f"Apify actor {actor_id} failed: {e}")
            return [{"error": str(e)}]

    async def _run_actor_async(self, actor_id: str, run_input: dict) -> dict:
        if not self._token:
            return {"error": "APIFY_API_TOKEN not configured"}
        url = f"{APIFY_BASE}/acts/{actor_id}/runs"
        params = {"token": self._token}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=run_input, params=params,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status in (200, 201):
                        return await resp.json()
                    text = await resp.text()
                    return {"error": f"HTTP {resp.status}", "detail": text[:200]}
        except Exception as e:
            return {"error": str(e)}

    async def get_cryptopanic_news(self, force: bool = False) -> dict:
        key = "cryptopanic_news"
        if not force and self._is_cached(key):
            return self._cache[key]
        data = await self._run_actor_sync(ACTORS["cryptopanic_news"], {})
        result = {"items": data, "fetched_at": time.time(), "source": "cryptopanic"}
        self._set_cache(key, result)
        self._extract_news_signals(data)
        return result

    async def get_crypto_signals(self, symbol: Optional[str] = None, force: bool = False) -> dict:
        key = "crypto_signals"
        if not force and self._is_cached(key):
            return self._cache[key]
        run_input = {}
        if symbol:
            run_input["symbol"] = symbol
        data = await self._run_actor_sync(ACTORS["crypto_signals"], run_input, timeout=60)
        result = {"items": data, "fetched_at": time.time(), "source": "crypto_signals_pump_detect"}
        self._set_cache(key, result)
        self._extract_pump_signals(data)
        return result

    async def get_whale_tracker(self, force: bool = False) -> dict:
        key = "whale_tracker"
        if not force and self._is_cached(key):
            return self._cache[key]
        data = await self._run_actor_sync(ACTORS["whale_tracker"], {})
        result = {"items": data, "fetched_at": time.time(), "source": "whale_tracker"}
        self._set_cache(key, result)
        self._extract_whale_signals(data)
        return result

    async def get_coinmarketcap(self, force: bool = False) -> dict:
        key = "coinmarketcap"
        if not force and self._is_cached(key):
            return self._cache[key]
        data = await self._run_actor_sync(ACTORS["coinmarketcap"], {}, timeout=180)
        result = {"items": data[:100] if isinstance(data, list) else data, "fetched_at": time.time(), "source": "coinmarketcap"}
        self._set_cache(key, result)
        return result

    async def get_yahoo_finance(self, symbols: list[str], days: str = "7", interval: str = "1d", force: bool = False) -> dict:
        key = "yahoo_finance"
        if not force and self._is_cached(key):
            return self._cache[key]
        run_input = {"symbols": symbols, "days": days, "interval": interval}
        data = await self._run_actor_sync(ACTORS["yahoo_finance"], run_input)
        result = {"items": data, "fetched_at": time.time(), "source": "yahoo_finance"}
        self._set_cache(key, result)
        return result

    async def get_twitter_sentiment(self, query: str = "$BTC", force: bool = False) -> dict:
        key = "twitter_sentiment"
        if not force and self._is_cached(key):
            return self._cache[key]
        run_input = {"searchTerms": [query], "maxTweets": 50}
        data = await self._run_actor_sync(ACTORS["twitter_sentiment"], run_input, timeout=120)
        result = {"items": data, "fetched_at": time.time(), "source": "twitter_sentiment", "query": query}
        self._set_cache(key, result)
        self._extract_twitter_signals(data)
        return result

    async def get_finance_agent(self, ticker: str = "BTC-USD", openai_key: str = "", force: bool = False) -> dict:
        key = "finance_agent"
        if not force and self._is_cached(key):
            return self._cache[key]
        run_input = {"ticker": ticker, "model": "gpt-4o-mini"}
        if openai_key:
            run_input["openai_api_key"] = openai_key
        data = await self._run_actor_sync(ACTORS["finance_agent"], run_input, timeout=180)
        result = {"items": data, "fetched_at": time.time(), "source": "finance_agent", "ticker": ticker}
        self._set_cache(key, result)
        return result

    async def get_kepler_insights(self, force: bool = False) -> dict:
        key = "kepler_insights"
        if not force and self._is_cached(key):
            return self._cache[key]
        data = await self._run_actor_sync(ACTORS["kepler_insights"], {}, timeout=120)
        result = {"items": data, "fetched_at": time.time(), "source": "kepler_insights"}
        self._set_cache(key, result)
        return result

    async def get_crypto_news_pro(self, force: bool = False) -> dict:
        key = "crypto_news_pro"
        if not force and self._is_cached(key):
            return self._cache[key]
        data = await self._run_actor_sync(ACTORS["crypto_news_pro"], {})
        result = {"items": data, "fetched_at": time.time(), "source": "crypto_news_pro"}
        self._set_cache(key, result)
        self._extract_news_signals(data)
        return result

    async def get_token_scanner(self, symbol: str = "BTC", force: bool = False) -> dict:
        key = "token_scanner"
        if not force and self._is_cached(key):
            return self._cache[key]
        run_input = {"symbol": symbol}
        data = await self._run_actor_sync(ACTORS["token_scanner"], run_input, timeout=120)
        result = {"items": data, "fetched_at": time.time(), "source": "token_scanner", "symbol": symbol}
        self._set_cache(key, result)
        return result

    async def get_twitter_stream_snapshot(self, users: str = "", force: bool = False) -> dict:
        key = "twitter_stream"
        if not force and self._is_cached(key):
            return self._cache[key]
        url = f"{TWITTER_SSE_BASE}/events/twitter/tweets"
        params = {}
        if users:
            params["users"] = users
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        events = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, params=params, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        async for line in resp.content:
                            decoded = line.decode("utf-8", errors="ignore").strip()
                            if decoded.startswith("data:"):
                                events.append(decoded[5:].strip())
                                if len(events) >= 20:
                                    break
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            logger.debug(f"Twitter stream error: {e}")
        result = {"events": events, "fetched_at": time.time(), "source": "twitter_stream"}
        self._set_cache(key, result)
        return result

    async def scrape_coinskid(self, page: str = "ckr_index", force: bool = False) -> dict:
        key = f"coinskid_{page}"
        if not force and self._is_cached(key):
            return self._cache[key]
        url = COINSKID_URLS.get(page)
        if not url:
            return {"error": f"Unknown CoinSkid page: {page}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        data = self._parse_coinskid_html(page, html)
                        result = {"data": data, "fetched_at": time.time(), "source": f"coinskid_{page}", "url": url}
                        self._set_cache(key, result)
                        return result
                    return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"error": str(e)}

    def _parse_coinskid_html(self, page: str, html: str) -> dict:
        import re
        data: dict = {"raw_length": len(html)}
        title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
        if title_match:
            data["title"] = title_match.group(1)
        numbers = re.findall(r'(?:rating|ckr|index|score|value)["\s:=]+(\d+(?:\.\d+)?)', html, re.IGNORECASE)
        if numbers:
            data["extracted_values"] = [float(n) for n in numbers[:10]]
        btc_blocks = re.findall(r'(?:btc|bitcoin)["\s:=]*(\d+(?:\.\d+)?)', html, re.IGNORECASE)
        if btc_blocks:
            data["btc_values"] = [float(n) for n in btc_blocks[:10]]
        usd_blocks = re.findall(r'(?:usd|dollar)["\s:=]*(\d+(?:\.\d+)?)', html, re.IGNORECASE)
        if usd_blocks:
            data["usd_values"] = [float(n) for n in usd_blocks[:10]]
        buy_signals = len(re.findall(r'(?:buy|bullish|long)', html, re.IGNORECASE))
        sell_signals = len(re.findall(r'(?:sell|bearish|short)', html, re.IGNORECASE))
        data["buy_mentions"] = buy_signals
        data["sell_mentions"] = sell_signals
        if buy_signals + sell_signals > 0:
            data["sentiment_ratio"] = round(buy_signals / (buy_signals + sell_signals), 3)
        fear_matches = re.findall(r'(?:fear|greed)["\s:=]*(\d+)', html, re.IGNORECASE)
        if fear_matches:
            data["fear_greed_values"] = [int(n) for n in fear_matches[:5]]
        script_data = re.findall(r'(?:var|let|const)\s+\w+\s*=\s*(\[.*?\]);', html, re.DOTALL)
        if script_data:
            data["embedded_arrays"] = len(script_data)
        return data

    def _extract_news_signals(self, items: list):
        if not isinstance(items, list):
            return
        for item in items[:20]:
            if not isinstance(item, dict):
                continue
            title = item.get("title", "") or item.get("headline", "") or ""
            title_lower = title.lower()
            coins = item.get("currencies", []) or item.get("coins", []) or []
            symbol = ""
            if isinstance(coins, list) and coins:
                if isinstance(coins[0], dict):
                    symbol = coins[0].get("code", "") or coins[0].get("symbol", "")
                elif isinstance(coins[0], str):
                    symbol = coins[0]
            direction = "neutral"
            confidence = 0.3
            if any(w in title_lower for w in ["surge", "rally", "soar", "bull", "breakout", "pump", "moon", "ath"]):
                direction = "bullish"
                confidence = 0.6
            elif any(w in title_lower for w in ["crash", "dump", "bear", "plunge", "sell", "drop", "fear", "hack"]):
                direction = "bearish"
                confidence = 0.6
            votes = item.get("votes", {})
            if isinstance(votes, dict):
                pos = votes.get("positive", 0) or votes.get("liked", 0) or 0
                neg = votes.get("negative", 0) or votes.get("disliked", 0) or 0
                if pos + neg > 5:
                    vote_ratio = pos / (pos + neg)
                    if vote_ratio > 0.7:
                        direction = "bullish"
                        confidence = min(0.8, confidence + 0.2)
                    elif vote_ratio < 0.3:
                        direction = "bearish"
                        confidence = min(0.8, confidence + 0.2)
            self._signals.append(SignalEntry(
                source="news",
                signal_type="news_sentiment",
                symbol=symbol or "MARKET",
                direction=direction,
                confidence=confidence,
                detail=title[:120],
                timestamp=time.time(),
            ))

    def _extract_pump_signals(self, items: list):
        if not isinstance(items, list):
            return
        for item in items[:20]:
            if not isinstance(item, dict):
                continue
            symbol = item.get("symbol", "") or item.get("id", "") or ""
            anomaly = item.get("anomaly_level", "") or ""
            vol_ratio = item.get("vol_mcap_ratio", 0) or 0
            if anomaly in ("CRITICAL", "HIGH") or vol_ratio > 15:
                direction = "pump_alert"
                confidence = 0.7 if anomaly == "CRITICAL" else 0.5
                self._signals.append(SignalEntry(
                    source="pump_detector",
                    signal_type="volume_anomaly",
                    symbol=symbol.upper(),
                    direction=direction,
                    confidence=confidence,
                    detail=f"Vol/MCap ratio: {vol_ratio:.1f}%, anomaly: {anomaly}",
                    timestamp=time.time(),
                ))

    def _extract_whale_signals(self, items: list):
        if not isinstance(items, list):
            return
        for item in items[:20]:
            if not isinstance(item, dict):
                continue
            action = item.get("action", "") or item.get("signal", "") or item.get("type", "")
            symbol = item.get("symbol", "") or item.get("token", "") or item.get("asset", "")
            amount = item.get("amount", 0) or item.get("value_usd", 0) or 0
            direction = "neutral"
            if any(w in str(action).lower() for w in ["buy", "accumulate", "deposit"]):
                direction = "bullish"
            elif any(w in str(action).lower() for w in ["sell", "dump", "withdraw", "transfer_out"]):
                direction = "bearish"
            if amount or action:
                self._signals.append(SignalEntry(
                    source="whale_tracker",
                    signal_type="whale_movement",
                    symbol=str(symbol).upper(),
                    direction=direction,
                    confidence=0.5,
                    detail=f"Action: {action}, Amount: ${amount:,.0f}" if isinstance(amount, (int, float)) else f"Action: {action}",
                    timestamp=time.time(),
                ))

    def _extract_twitter_signals(self, items: list):
        if not isinstance(items, list):
            return
        bullish_count = 0
        bearish_count = 0
        for item in items[:50]:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "") or item.get("full_text", "") or "").lower()
            if any(w in text for w in ["bull", "moon", "pump", "buy", "long", "breakout", "ath", "🚀"]):
                bullish_count += 1
            elif any(w in text for w in ["bear", "dump", "sell", "short", "crash", "fear", "rekt"]):
                bearish_count += 1
        total = bullish_count + bearish_count
        if total > 3:
            ratio = bullish_count / total
            direction = "bullish" if ratio > 0.6 else ("bearish" if ratio < 0.4 else "neutral")
            self._signals.append(SignalEntry(
                source="twitter",
                signal_type="social_sentiment",
                symbol="MARKET",
                direction=direction,
                confidence=min(0.7, 0.3 + (total / 50)),
                detail=f"Bullish: {bullish_count}, Bearish: {bearish_count}, Ratio: {ratio:.2f}",
                timestamp=time.time(),
            ))

    def get_unified_signals(self, max_age_seconds: int = 600) -> list[dict]:
        cutoff = time.time() - max_age_seconds
        signals = [
            {
                "source": s.source,
                "signal_type": s.signal_type,
                "symbol": s.symbol,
                "direction": s.direction,
                "confidence": s.confidence,
                "detail": s.detail,
                "timestamp": s.timestamp,
                "age_seconds": round(time.time() - s.timestamp),
            }
            for s in self._signals
            if s.timestamp > cutoff
        ]
        signals.sort(key=lambda x: x["timestamp"], reverse=True)
        return signals[:100]

    def get_signal_summary(self) -> dict:
        signals = self.get_unified_signals()
        bullish = sum(1 for s in signals if s["direction"] == "bullish")
        bearish = sum(1 for s in signals if s["direction"] == "bearish")
        neutral = sum(1 for s in signals if s["direction"] == "neutral")
        pump_alerts = sum(1 for s in signals if s["direction"] == "pump_alert")
        total = len(signals)
        by_source: dict[str, int] = {}
        for s in signals:
            by_source[s["source"]] = by_source.get(s["source"], 0) + 1
        overall = "neutral"
        if total > 0:
            bull_ratio = bullish / total
            if bull_ratio > 0.6:
                overall = "bullish"
            elif bull_ratio < 0.3:
                overall = "bearish"
        return {
            "total_signals": total,
            "bullish": bullish,
            "bearish": bearish,
            "neutral": neutral,
            "pump_alerts": pump_alerts,
            "overall_sentiment": overall,
            "by_source": by_source,
            "cached_sources": list(self._cache.keys()),
        }

    async def refresh_all(self) -> dict:
        results = {}
        tasks = {
            "cryptopanic_news": self.get_cryptopanic_news(force=True),
            "crypto_signals": self.get_crypto_signals(force=True),
            "whale_tracker": self.get_whale_tracker(force=True),
            "crypto_news_pro": self.get_crypto_news_pro(force=True),
            "twitter_stream": self.get_twitter_stream_snapshot(force=True),
            "coinskid_ckr": self.scrape_coinskid("ckr_index", force=True),
            "coinskid_heatmap": self.scrape_coinskid("heatmap", force=True),
            "coinskid_blocks": self.scrape_coinskid("crypto_blocks", force=True),
        }
        gathered = await asyncio.gather(
            *[asyncio.ensure_future(t) for t in tasks.values()],
            return_exceptions=True,
        )
        for name, result in zip(tasks.keys(), gathered):
            if isinstance(result, Exception):
                results[name] = {"error": str(result)}
            else:
                results[name] = {"ok": True, "items_count": len(result.get("items", result.get("events", result.get("data", []))))}
        results["signal_summary"] = self.get_signal_summary()
        return results

    def get_bot_signal_boost(self, symbol: str, bot_type: str) -> dict:
        signals = self.get_unified_signals(max_age_seconds=900)
        relevant = []
        sym_upper = symbol.split("/")[0].upper() if "/" in symbol else symbol.upper()
        for s in signals:
            if s["symbol"] == sym_upper or s["symbol"] == "MARKET":
                relevant.append(s)
        if not relevant:
            return {"boost": 0.0, "direction": "neutral", "signals_used": 0}
        bull_weight = 0.0
        bear_weight = 0.0
        for s in relevant:
            w = s["confidence"]
            if s["symbol"] == sym_upper:
                w *= 1.5
            if s["direction"] == "bullish":
                bull_weight += w
            elif s["direction"] == "bearish":
                bear_weight += w
            elif s["direction"] == "pump_alert":
                bull_weight += w * 0.5
        net = bull_weight - bear_weight
        direction = "bullish" if net > 0.3 else ("bearish" if net < -0.3 else "neutral")
        boost = max(-0.3, min(0.3, net * 0.1))
        return {
            "boost": round(boost, 3),
            "direction": direction,
            "bull_weight": round(bull_weight, 2),
            "bear_weight": round(bear_weight, 2),
            "signals_used": len(relevant),
        }


apify_intel = ApifyIntelligence()
