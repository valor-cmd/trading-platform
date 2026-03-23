import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.core.security import require_auth, RateLimitMiddleware

from app.api.routes import router, risk_engine, _fast_live_balance
from app.api.hummingbot_routes import hbot_router
from app.hummingbot.manager import hbot_manager
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
from app.bots.grid import GridBot
from app.bots.mean_reversion import MeanReversionBot
from app.bots.momentum import MomentumBot
from app.bots.dca import DCABot
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
grid_bot = GridBot(paper_exchange, risk_engine, sentiment_analyzer)
mean_reversion_bot = MeanReversionBot(paper_exchange, risk_engine, sentiment_analyzer)
momentum_bot = MomentumBot(paper_exchange, risk_engine, sentiment_analyzer)
dca_bot = DCABot(paper_exchange, risk_engine, sentiment_analyzer)

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

    async def _price_refresh_loop():
        dex_adapters = {
            eid: adapter for eid, adapter in exchange_registry.get_all().items()
            if adapter.exchange_type.value == "dex" and adapter.is_connected()
        }
        while True:
            await asyncio.sleep(15)
            try:
                open_trades = trade_store.get_open_trades()
                symbols = list({t.get("symbol", "") for t in open_trades if t.get("symbol")})
                if symbols:
                    count = await live_prices.refresh_tickers_for_symbols(
                        symbols, timeout=12.0, dex_adapters=dex_adapters,
                    )
                    if count > 0:
                        logger.debug(f"Price refresh: updated {count}/{len(symbols)} open position prices")
            except Exception as e:
                logger.debug(f"Price refresh error: {e}")

    price_refresh_task = asyncio.create_task(_price_refresh_loop(), name="price_refresh")

    async def _snapshot_loop():
        _snap_count = 0
        while True:
            await asyncio.sleep(15)
            try:
                live_balance = _fast_live_balance()
                trade_store.snapshots.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "balance": live_balance,
                    "open_trades": len(trade_store.get_open_trades()),
                    "total_trades": len(trade_store.trades),
                })
                _snap_count += 1
                if _snap_count % 20 == 0:
                    trade_store._save()
            except Exception:
                pass

    snapshot_task = asyncio.create_task(_snapshot_loop(), name="snapshot_loop")

    async def _rebalance_loop():
        while True:
            await asyncio.sleep(300)
            try:
                total_val = _fast_live_balance()
                if total_val > 0:
                    alloc = await risk_engine.rebalance_buckets(total_val, {})
                    logger.info(
                        f"Auto-rebalance: scalper={alloc.scalper_pct}% swing={alloc.swing_pct}% "
                        f"long_term={alloc.long_term_pct}% arb={alloc.arbitrage_pct}% "
                        f"grid={alloc.grid_pct}% mr={alloc.mean_reversion_pct}% "
                        f"mom={alloc.momentum_pct}% dca={alloc.dca_pct}%"
                    )
            except Exception as e:
                logger.debug(f"Auto-rebalance error: {e}")

    rebalance_task = asyncio.create_task(_rebalance_loop(), name="rebalance_loop")

    try:
        await hbot_manager.connect()
        if hbot_manager.is_connected:
            await hbot_manager.start_health_monitor()
            logger.info("Hummingbot API connected")
        else:
            logger.info("Hummingbot API not available (will connect on demand)")
    except Exception as e:
        logger.info(f"Hummingbot API not available: {e}")

    if total_usdt > 0:
        exchange_id = "paper"
        _ensure_bot_running("scalper", scalper_bot.start(exchange_id, interval_seconds=30), _bot_tasks)
        _ensure_bot_running("swing", swing_bot.start(exchange_id, interval_seconds=300), _bot_tasks)
        _ensure_bot_running("long_term", long_term_bot.start(exchange_id, interval_seconds=3600), _bot_tasks)
        _ensure_bot_running("arbitrage", arb_bot.start(interval_seconds=30), _bot_tasks)
        _ensure_bot_running("grid", grid_bot.start(exchange_id, interval_seconds=60), _bot_tasks)
        _ensure_bot_running("mean_reversion", mean_reversion_bot.start(exchange_id, interval_seconds=120), _bot_tasks)
        _ensure_bot_running("momentum", momentum_bot.start(exchange_id, interval_seconds=300), _bot_tasks)
        _ensure_bot_running("dca", dca_bot.start(exchange_id, interval_seconds=180), _bot_tasks)
        logger.info(f"Auto-started all bots with ${total_usdt:.2f} USDT")

    yield

    price_refresh_task.cancel()
    snapshot_task.cancel()
    rebalance_task.cancel()

    await hbot_manager.disconnect()
    logger.info("Shutting down bots...")
    scalper_bot.stop()
    swing_bot.stop()
    long_term_bot.stop()
    arb_bot.stop()
    grid_bot.stop()
    mean_reversion_bot.stop()
    momentum_bot.stop()
    dca_bot.stop()
    for task in _bot_tasks.values():
        task.cancel()
    await paper_exchange.close_all()
    await live_prices.close()
    for adapter in exchange_registry.get_all().values():
        await adapter.disconnect()
    logger.info("Trading platform shut down.")


app = FastAPI(title="Trading Platform", version="4.0.0", lifespan=lifespan)

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

app.add_middleware(RateLimitMiddleware, max_requests=120, window_seconds=60)

app.include_router(router, prefix="/api")
app.include_router(hbot_router, prefix="/api")


@app.post("/api/bots/start/{exchange_id}")
async def start_bots(exchange_id: str, _auth=Depends(require_auth)):
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
    _ensure_bot_running("grid", grid_bot.start(exchange_id, interval_seconds=60), _bot_tasks)
    _ensure_bot_running("mean_reversion", mean_reversion_bot.start(exchange_id, interval_seconds=120), _bot_tasks)
    _ensure_bot_running("momentum", momentum_bot.start(exchange_id, interval_seconds=300), _bot_tasks)
    _ensure_bot_running("dca", dca_bot.start(exchange_id, interval_seconds=180), _bot_tasks)

    return {
        "status": "started",
        "bots": {
            "scalper": {"interval": "30s", "symbols": len(scalper_bot.get_symbols())},
            "swing": {"interval": "5m", "symbols": len(swing_bot.get_symbols())},
            "long_term": {"interval": "1h", "symbols": len(long_term_bot.get_symbols())},
            "arbitrage": {"interval": "30s", "exchanges": len(exchange_registry.get_connected())},
            "grid": {"interval": "60s", "symbols": len(grid_bot.get_symbols())},
            "mean_reversion": {"interval": "2m", "symbols": len(mean_reversion_bot.get_symbols())},
            "momentum": {"interval": "5m", "symbols": len(momentum_bot.get_symbols())},
            "dca": {"interval": "3m", "symbols": len(dca_bot.get_symbols())},
        },
        "exchanges": exchange_registry.status(),
    }


@app.post("/api/bots/stop")
async def stop_bots(_auth=Depends(require_auth)):
    scalper_bot.stop()
    swing_bot.stop()
    long_term_bot.stop()
    arb_bot.stop()
    grid_bot.stop()
    mean_reversion_bot.stop()
    momentum_bot.stop()
    dca_bot.stop()
    return {"status": "stopped"}


@app.get("/api/bots/running")
async def bots_running(account: str = "default"):
    if account != "default":
        from app.core.accounts import account_manager
        try:
            acct = account_manager.get(account)
            result = {}
            for bt_name, bot in acct.bots.items():
                result[bt_name] = {"running": bot.running, "active_trades": len(bot.active_trades)}
            if "arbitrage" not in result:
                result["arbitrage"] = {"running": False, "active_trades": 0, "trades_executed": 0}
            return result
        except Exception:
            pass
    return {
        "scalper": {"running": scalper_bot.running, "active_trades": len(scalper_bot.active_trades)},
        "swing": {"running": swing_bot.running, "active_trades": len(swing_bot.active_trades)},
        "long_term": {"running": long_term_bot.running, "active_trades": len(long_term_bot.active_trades)},
        "arbitrage": arb_bot.status(),
        "grid": {"running": grid_bot.running, "active_trades": len(grid_bot.active_trades)},
        "mean_reversion": {"running": mean_reversion_bot.running, "active_trades": len(mean_reversion_bot.active_trades)},
        "momentum": {"running": momentum_bot.running, "active_trades": len(momentum_bot.active_trades)},
        "dca": {"running": dca_bot.running, "active_trades": len(dca_bot.active_trades)},
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
async def portfolio_chart(limit: int = 200, account: str = "default"):
    from app.core.accounts import account_manager
    try:
        acct = account_manager.get(account)
    except ValueError:
        acct = account_manager.get("default")
    _ts = acct.trade_store
    _pe = acct.paper_exchange
    data = _ts.get_portfolio_chart(limit)
    now_balance = _fast_live_balance(_pe, _ts)
    data.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "balance": now_balance,
    })

    trades = []
    for t in _ts.trades:
        trade_id = t.get("id", 0)
        ts = t.get("opened_at", "")
        if ts:
            trades.append({
                "timestamp": ts,
                "side": t.get("side", "buy"),
                "symbol": t.get("symbol", ""),
                "price": t.get("entry_price", 0),
                "quantity": t.get("quantity", 0),
                "bot_type": t.get("bot_type", ""),
                "type": "entry",
                "trade_id": trade_id,
                "stop_loss": t.get("stop_loss_price", 0),
                "take_profit": t.get("take_profit_price", 0),
                "entry_fee": t.get("entry_fee_usd", 0),
                "strategy": t.get("strategy", ""),
                "signal_score": t.get("signal_score", 0),
                "status": t.get("status", "open"),
            })
        if t.get("status") in ("closed", "stopped_out") and t.get("closed_at"):
            trades.append({
                "timestamp": t["closed_at"],
                "side": "sell" if t.get("side") == "buy" else "buy",
                "symbol": t.get("symbol", ""),
                "price": t.get("exit_price", 0),
                "quantity": t.get("quantity", 0),
                "bot_type": t.get("bot_type", ""),
                "type": "exit",
                "trade_id": trade_id,
                "pnl_usd": t.get("pnl_usd", 0),
                "pnl_pct": t.get("pnl_pct", 0),
                "exit_fee": t.get("exit_fee_usd", 0),
                "exit_reason": t.get("exit_reason", ""),
                "entry_price": t.get("entry_price", 0),
                "strategy": t.get("strategy", ""),
                "status": t.get("status", "closed"),
            })

    events = []
    for d in _ts.deposits:
        events.append({
            "timestamp": d.get("timestamp", ""),
            "type": "deposit",
            "amount_usd": d.get("amount_usd", 0),
        })
    for w in _ts.withdrawals:
        events.append({
            "timestamp": w.get("timestamp", ""),
            "type": "withdrawal",
            "amount_usd": w.get("amount_usd", 0),
        })

    return {"chart": data, "trades": trades, "events": events}


@app.post("/api/toggle-paper-mode")
async def toggle_paper_mode(body: dict, _auth=Depends(require_auth)):
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
        "hummingbot_connected": hbot_manager.is_connected,
        "gateway_connected": hbot_manager.is_gateway_connected,
        "auth_enabled": bool(_os.environ.get("API_SECRET_KEY", "")),
    }
