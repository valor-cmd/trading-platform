import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router, risk_engine
from app.core.store import trade_store
from app.exchange.simulator import paper_exchange
from app.exchange.live_prices import live_prices
from app.exchange.registry import exchange_registry
from app.exchange.token_registry import token_registry
from app.exchange.adapters.paper import PaperAdapter
from app.exchange.adapters.ccxt_adapter import CCXTLiveAdapter
from app.exchange.adapters.xrpl_dex import XRPLDEXAdapter, XRPL_TOKENS
from app.exchange.adapters.solana_dex import SolanaDEXAdapter, SOLANA_TOKENS
from app.exchange.adapters.hedera_dex import HederaDEXAdapter, HEDERA_TOKENS
from app.bots.scalper import ScalperBot
from app.bots.swing import SwingBot
from app.bots.long_term import LongTermBot
from app.bots.arbitrage import ArbitrageBot
from app.arbitrage.engine import ArbitrageConfig
from app.indicators.sentiment import SentimentAnalyzer
from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

sentiment_analyzer = SentimentAnalyzer()
risk_engine.set_paper_exchange(paper_exchange)
scalper_bot = ScalperBot(paper_exchange, risk_engine, sentiment_analyzer)
swing_bot = SwingBot(paper_exchange, risk_engine, sentiment_analyzer)
long_term_bot = LongTermBot(paper_exchange, risk_engine, sentiment_analyzer)

arb_config = ArbitrageConfig(
    min_spread_pct=0.3,
    min_profit_after_fees_pct=0.05,
    max_position_usd=500.0,
    scan_interval_seconds=30,
)
arb_bot = ArbitrageBot(exchange_registry, risk_engine, arb_config)

_bot_tasks: dict[str, asyncio.Task] = {}

EXCHANGES_TO_LOAD = ["binance", "coinbase", "kraken", "kucoin", "bybit", "okx", "gateio", "bitget", "mexc"]


async def _init_exchanges():
    logger.info("Loading real market data from exchanges (no API keys needed for public data)...")
    await live_prices.initialize(EXCHANGES_TO_LOAD)

    for eid in live_prices.get_exchanges():
        adapter = CCXTLiveAdapter(eid)
        await adapter.connect()
        exchange_registry.register(adapter)

    xrpl_dex = XRPLDEXAdapter()
    await xrpl_dex.connect()
    exchange_registry.register(xrpl_dex)

    sol_dex = SolanaDEXAdapter()
    await sol_dex.connect()
    exchange_registry.register(sol_dex)

    hedera_dex = HederaDEXAdapter()
    await hedera_dex.connect()
    exchange_registry.register(hedera_dex)

    for token in XRPL_TOKENS.values():
        token_registry.register(token)
    for token in SOLANA_TOKENS.values():
        token_registry.register(token)
    for token in HEDERA_TOKENS.values():
        token_registry.register(token)

    status = exchange_registry.status()
    total_pairs = sum(s["pairs"] for s in status.values())
    logger.info(f"Exchanges initialized: {len(status)} adapters, {total_pairs} total pairs")
    for eid, s in status.items():
        logger.info(f"  {eid}: {s['type']} | {s['pairs']} pairs | chain={s['chain']}")

    common = exchange_registry.find_common_pairs()
    logger.info(f"Cross-exchange pairs (arb candidates): {len(common)}")


def _ensure_bot_running(name: str, coro, task_dict: dict):
    if name in task_dict:
        task = task_dict[name]
        if not task.done():
            return
        exc = task.exception() if not task.cancelled() else None
        if exc:
            logger.warning(f"Bot {name} died with: {exc}. Restarting...")
    task_dict[name] = asyncio.create_task(coro, name=f"bot_{name}")
    logger.info(f"Bot task created: {name}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Trading platform starting up with REAL market data...")
    logger.info(f"Paper trading: {settings.paper_trading}")

    await _init_exchanges()

    paper_exchange.connect("paper")
    balance = await paper_exchange.fetch_balance("paper")
    total_usdt = balance["total"].get("USDT", 0)
    await risk_engine.rebalance_buckets(total_usdt, {})
    logger.info(f"Initialized with ${total_usdt:.2f} USDT")

    yield

    logger.info("Shutting down bots...")
    scalper_bot.stop()
    swing_bot.stop()
    long_term_bot.stop()
    arb_bot.stop()
    for task in _bot_tasks.values():
        task.cancel()
    await paper_exchange.close_all()
    await live_prices.close()
    for adapter in exchange_registry.get_all().values():
        await adapter.disconnect()
    logger.info("Trading platform shut down.")


app = FastAPI(title="Trading Platform", version="3.0.0", lifespan=lifespan)

import os as _os

_cors_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
]
_extra_origins = _os.environ.get("CORS_ORIGINS", "")
if _extra_origins:
    _cors_origins.extend([o.strip() for o in _extra_origins.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.post("/api/bots/start/{exchange_id}")
async def start_bots(exchange_id: str):
    if not paper_exchange.is_connected(exchange_id):
        paper_exchange.connect(exchange_id)

    balance = await paper_exchange.fetch_balance(exchange_id)
    total = balance.get("total", {}).get("USDT", 0) or 0
    if total > 0:
        await risk_engine.rebalance_buckets(total, {})
    else:
        logger.warning("No USDT balance found -- deposit funds before starting bots")

    _ensure_bot_running("scalper", scalper_bot.start(exchange_id, interval_seconds=30), _bot_tasks)
    _ensure_bot_running("swing", swing_bot.start(exchange_id, interval_seconds=300), _bot_tasks)
    _ensure_bot_running("long_term", long_term_bot.start(exchange_id, interval_seconds=3600), _bot_tasks)
    _ensure_bot_running("arbitrage", arb_bot.start(interval_seconds=30), _bot_tasks)

    return {
        "status": "started",
        "bots": {
            "scalper": {"interval": "30s", "symbols": len(scalper_bot.get_symbols())},
            "swing": {"interval": "5m", "symbols": len(swing_bot.get_symbols())},
            "long_term": {"interval": "1h", "symbols": len(long_term_bot.get_symbols())},
            "arbitrage": {"interval": "30s", "exchanges": len(exchange_registry.get_connected())},
        },
        "exchanges": exchange_registry.status(),
    }


@app.post("/api/bots/stop")
async def stop_bots():
    scalper_bot.stop()
    swing_bot.stop()
    long_term_bot.stop()
    arb_bot.stop()
    return {"status": "stopped"}


@app.get("/api/bots/running")
async def bots_running():
    return {
        "scalper": {"running": scalper_bot.running, "active_trades": len(scalper_bot.active_trades)},
        "swing": {"running": swing_bot.running, "active_trades": len(swing_bot.active_trades)},
        "long_term": {"running": long_term_bot.running, "active_trades": len(long_term_bot.active_trades)},
        "arbitrage": arb_bot.status(),
    }


@app.get("/api/exchanges/status")
async def exchanges_status():
    return {
        "exchanges": exchange_registry.status(),
        "live_prices": live_prices.status(),
        "tokens": token_registry.status(),
        "common_pairs": len(exchange_registry.find_common_pairs()),
        "total_symbols": sum(len(syms) for syms in exchange_registry.get_all_symbols().values()),
    }


@app.get("/api/exchanges/pairs")
async def all_pairs():
    return exchange_registry.get_all_symbols()


@app.get("/api/exchanges/{exchange_id}/pairs")
async def exchange_pairs(exchange_id: str, q: str = "", limit: int = 200, offset: int = 0):
    adapter = exchange_registry.get(exchange_id)
    if not adapter:
        return {"exchange_id": exchange_id, "pairs": [], "total": 0}
    all_syms = adapter.get_all_symbols()
    if q:
        q_upper = q.upper()
        all_syms = [s for s in all_syms if q_upper in s.upper()]
    total = len(all_syms)
    page = sorted(all_syms)[offset:offset + limit]
    return {"exchange_id": exchange_id, "pairs": page, "total": total}


@app.get("/api/arbitrage/opportunities")
async def arb_opportunities(min_profit: float = 0.0, limit: int = 50):
    return arb_bot.arb_engine.get_opportunities(min_profit, limit)


@app.get("/api/arbitrage/history")
async def arb_history(limit: int = 100):
    return arb_bot.arb_engine.get_history(limit)


@app.get("/api/arbitrage/status")
async def arb_status():
    return {
        **arb_bot.status(),
        "common_pairs": len(exchange_registry.find_common_pairs()),
        "exchanges_connected": len(exchange_registry.get_connected()),
    }


@app.get("/api/tokens/search")
async def search_tokens(q: str = ""):
    if not q:
        tokens = token_registry.get_all()
    else:
        tokens = token_registry.search(q)
    return [
        {"symbol": t.symbol, "name": t.name, "chain": t.chain.value, "tags": t.tags}
        for t in tokens[:100]
    ]


@app.get("/api/tokens/by-chain/{chain}")
async def tokens_by_chain(chain: str):
    from app.exchange.adapters.base import Chain
    try:
        c = Chain(chain)
    except ValueError:
        return []
    tokens = token_registry.get_all_by_chain(c)
    return [
        {"symbol": t.symbol, "name": t.name, "chain": t.chain.value, "tags": t.tags, "contract": t.contract_address}
        for t in tokens
    ]


@app.get("/api/portfolio/chart")
async def portfolio_chart(limit: int = 200):
    return trade_store.get_portfolio_chart(limit)


@app.post("/api/toggle-paper-mode")
async def toggle_paper_mode(body: dict):
    new_mode = body.get("paper_trading", True)
    settings.paper_trading = new_mode
    logger.info(f"Trading mode switched to: {'PAPER' if new_mode else 'LIVE'}")
    return {"paper_trading": settings.paper_trading}


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "paper_trading": settings.paper_trading,
        "exchanges": len(exchange_registry.get_connected()),
        "total_pairs": sum(len(syms) for syms in exchange_registry.get_all_symbols().values()),
        "live_price_sources": len(live_prices.get_exchanges()),
    }
