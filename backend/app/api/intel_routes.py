from fastapi import APIRouter, Depends, Query
from typing import Optional

from app.core.security import require_auth
from app.services.apify_intel import apify_intel
from app.services.strategy_intel import strategy_intel

intel_router = APIRouter(prefix="/intel", tags=["intelligence"])


@intel_router.get("/signals")
async def get_signals(max_age: int = 600, _auth=Depends(require_auth)):
    return apify_intel.get_unified_signals(max_age_seconds=max_age)


@intel_router.get("/summary")
async def get_signal_summary(_auth=Depends(require_auth)):
    return apify_intel.get_signal_summary()


@intel_router.get("/bot-boost")
async def get_bot_boost(symbol: str, bot_type: str = "momentum", _auth=Depends(require_auth)):
    return apify_intel.get_bot_signal_boost(symbol, bot_type)


@intel_router.post("/refresh")
async def refresh_all_sources(_auth=Depends(require_auth)):
    return await apify_intel.refresh_all()


@intel_router.get("/news/cryptopanic")
async def get_cryptopanic(force: bool = False, _auth=Depends(require_auth)):
    return await apify_intel.get_cryptopanic_news(force=force)


@intel_router.get("/news/pro")
async def get_crypto_news_pro(force: bool = False, _auth=Depends(require_auth)):
    return await apify_intel.get_crypto_news_pro(force=force)


@intel_router.get("/pump-detector")
async def get_pump_detector(symbol: Optional[str] = None, force: bool = False, _auth=Depends(require_auth)):
    return await apify_intel.get_crypto_signals(symbol=symbol, force=force)


@intel_router.get("/whale-tracker")
async def get_whale_tracker(force: bool = False, _auth=Depends(require_auth)):
    return await apify_intel.get_whale_tracker(force=force)


@intel_router.get("/coinmarketcap")
async def get_coinmarketcap(force: bool = False, _auth=Depends(require_auth)):
    return await apify_intel.get_coinmarketcap(force=force)


@intel_router.get("/yahoo-finance")
async def get_yahoo_finance(
    symbols: str = "BTC-USD,ETH-USD,SOL-USD",
    days: str = "7",
    interval: str = "1d",
    force: bool = False,
    _auth=Depends(require_auth),
):
    sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
    return await apify_intel.get_yahoo_finance(sym_list, days=days, interval=interval, force=force)


@intel_router.get("/twitter/sentiment")
async def get_twitter_sentiment(query: str = "$BTC", force: bool = False, _auth=Depends(require_auth)):
    return await apify_intel.get_twitter_sentiment(query=query, force=force)


@intel_router.get("/twitter/stream")
async def get_twitter_stream(users: str = "", force: bool = False, _auth=Depends(require_auth)):
    return await apify_intel.get_twitter_stream_snapshot(users=users, force=force)


@intel_router.get("/finance-agent")
async def get_finance_agent(ticker: str = "BTC-USD", force: bool = False, _auth=Depends(require_auth)):
    from app.core.config import settings
    return await apify_intel.get_finance_agent(ticker=ticker, openai_key=settings.openai_api_key, force=force)


@intel_router.get("/kepler")
async def get_kepler_insights(force: bool = False, _auth=Depends(require_auth)):
    return await apify_intel.get_kepler_insights(force=force)


@intel_router.get("/token-scanner")
async def get_token_scanner(symbol: str = "BTC", force: bool = False, _auth=Depends(require_auth)):
    return await apify_intel.get_token_scanner(symbol=symbol, force=force)


@intel_router.get("/coinskid/{page}")
async def get_coinskid(page: str = "ckr_index", force: bool = False, _auth=Depends(require_auth)):
    return await apify_intel.scrape_coinskid(page=page, force=force)


@intel_router.get("/strategy/advice")
async def get_strategy_advice(symbol: str, bot_type: str = "scalper", _auth=Depends(require_auth)):
    advice = strategy_intel.get_advice(bot_type, symbol)
    return {
        "bot_type": advice.bot_type,
        "symbol": advice.symbol,
        "confidence_boost": advice.confidence_boost,
        "direction_bias": advice.direction_bias,
        "coinskid_zone": advice.coinskid_zone,
        "grid_bounds": advice.grid_bounds,
        "strategy_notes": advice.strategy_notes,
        "should_trade": advice.should_trade,
        "optimal_params": advice.optimal_params,
    }


@intel_router.get("/strategy/params")
async def get_strategy_params(_auth=Depends(require_auth)):
    return strategy_intel.get_all_optimal_params()


@intel_router.get("/strategy/bot-report")
async def get_strategy_bot_report(_auth=Depends(require_auth)):
    return strategy_intel.get_bot_report()
