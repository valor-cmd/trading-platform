import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, field_validator

from app.core.security import require_auth

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.core.store import store, trade_store
from app.exchange.simulator import paper_exchange
from app.exchange.live_prices import live_prices
from app.risk.engine import RiskEngine
from app.backtesting.engine import BacktestEngine
from app.core.accounts import account_manager


def _resolve_account(account: str = "default"):
    try:
        return account_manager.get(account)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Account '{account}' not found")


def _entry_price_map(ts=None) -> dict[str, float]:
    ts = ts or trade_store
    m: dict[str, float] = {}
    for t in ts.trades:
        sym = t.get("symbol", "")
        ep = t.get("entry_price", 0)
        if sym and ep > 0:
            m[sym] = ep
    return m


async def _fetch_prices_batch(symbols: list[str], timeout_sec: float = 8.0, max_live: int = 30) -> dict[str, float]:
    if not symbols:
        return {}

    prices: dict[str, float] = {}
    entry_prices = _entry_price_map()

    for sym in symbols:
        prices[sym] = entry_prices.get(sym, 0)

    for cache_key, cached in live_prices._ticker_cache.items():
        if cached and cached.get("last", 0) > 0:
            sym = cache_key.split(":", 1)[-1] if ":" in cache_key else cache_key
            if sym in prices:
                prices[sym] = cached["last"]

    missing = [s for s in symbols if prices.get(s, 0) <= 0]
    if not missing:
        return prices

    to_fetch = missing[:max_live]
    by_exchange: dict[str, list[str]] = {}
    for sym in to_fetch:
        ex = paper_exchange._resolve_exchange(sym)
        by_exchange.setdefault(ex, []).append(sym)

    async def _fetch_one_exchange(ex: str, syms: list[str]):
        try:
            batch = await asyncio.wait_for(
                live_prices.fetch_tickers_batch(ex, syms[:20]),
                timeout=timeout_sec,
            )
            for sym, ticker in batch.items():
                if ticker.get("last", 0) > 0:
                    prices[sym] = ticker["last"]
        except asyncio.TimeoutError:
            logger.warning(f"Price fetch timeout for {ex} ({len(syms)} symbols)")
        except Exception as e:
            logger.debug(f"Price fetch failed for {ex}: {e}")

    tasks = [_fetch_one_exchange(ex, syms) for ex, syms in by_exchange.items()]
    await asyncio.gather(*tasks, return_exceptions=True)

    return prices


def _get_cached_prices() -> dict[str, float]:
    cached_prices: dict[str, float] = {}
    for cache_key, cached in live_prices._ticker_cache.items():
        if cached and cached.get("last", 0) > 0:
            sym = cache_key.split(":", 1)[-1] if ":" in cache_key else cache_key
            cached_prices[sym] = cached["last"]
    return cached_prices


def _resolve_token_price(token: str, cached_prices: dict[str, float], entry_prices: dict[str, float]) -> float:
    for quote in ("USDT", "USD"):
        sym = f"{token}/{quote}"
        p = cached_prices.get(sym) or entry_prices.get(sym)
        if p and p > 0:
            return p
    return 0.0


def _fast_live_balance(pe=None, ts=None) -> float:
    pe = pe or paper_exchange
    ts = ts or trade_store
    cached_prices = _get_cached_prices()
    entry_prices = _entry_price_map(ts)
    total = 0.0
    for asset, balance in pe.balances.items():
        if abs(balance) < 1e-10:
            continue
        if asset in ("USDT", "USD"):
            total += balance
        else:
            price = _resolve_token_price(asset, cached_prices, entry_prices)
            total += balance * price
    return round(total, 5)

router = APIRouter()

risk_engine = RiskEngine()
risk_engine.set_paper_exchange(paper_exchange)


class ConnectExchangeRequest(BaseModel):
    exchange_id: str
    api_key: str = ""
    api_secret: str = ""


class DepositRequest(BaseModel):
    exchange: str
    amount_usd: float
    asset: str
    asset_amount: float
    wallet_address: Optional[str] = None
    tx_hash: Optional[str] = None

    @field_validator("amount_usd")
    @classmethod
    def validate_amount_usd(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("amount_usd must be positive")
        if v > 10_000_000:
            raise ValueError("amount_usd exceeds maximum")
        return round(v, 5)

    @field_validator("asset_amount")
    @classmethod
    def validate_asset_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("asset_amount must be positive")
        return v


class WithdrawalRequest(BaseModel):
    exchange: str
    amount_usd: float
    asset: str
    asset_amount: float
    wallet_address: Optional[str] = None
    tx_hash: Optional[str] = None

    @field_validator("amount_usd")
    @classmethod
    def validate_amount_usd(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("amount_usd must be positive")
        if v > 10_000_000:
            raise ValueError("amount_usd exceeds maximum")
        return round(v, 5)

    @field_validator("asset_amount")
    @classmethod
    def validate_asset_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("asset_amount must be positive")
        return v


class TrackWalletRequest(BaseModel):
    label: str
    address: str
    chain: str


class BacktestRequest(BaseModel):
    exchange_id: str
    symbol: str
    timeframe: str = "1h"
    initial_capital: float = 1000.0
    risk_per_trade_pct: float = 2.0
    limit: int = 500
    sl_atr_multiplier: float = 1.5
    tp_rr_ratio: float = 2.0
    min_confidence: float = 0.15
    min_confirmations: int = 3


class RebalanceRequest(BaseModel):
    total_capital: Optional[float] = None


@router.post("/exchange/connect")
async def connect_exchange(req: ConnectExchangeRequest, _auth=Depends(require_auth)):
    paper_exchange.connect(req.exchange_id)
    return {"status": "connected", "exchange": req.exchange_id}


@router.get("/exchange/{exchange_id}/balance")
async def get_balance(exchange_id: str):
    if not paper_exchange.is_connected(exchange_id):
        paper_exchange.connect(exchange_id)
    balance = await paper_exchange.fetch_balance(exchange_id)
    return balance


@router.get("/market/{exchange_id}/{symbol}/ticker")
async def get_ticker(exchange_id: str, symbol: str):
    sym = symbol.replace("-", "/")
    ticker = await paper_exchange.fetch_ticker(exchange_id, sym)
    return ticker


@router.get("/market/{exchange_id}/{symbol}/ohlcv")
async def get_ohlcv(exchange_id: str, symbol: str, timeframe: str = "1h", limit: int = 100):
    sym = symbol.replace("-", "/")
    df = await paper_exchange.fetch_ohlcv(exchange_id, sym, timeframe, limit=limit)
    if df is None or len(df) == 0:
        return []
    records = []
    for _, row in df.iterrows():
        records.append({
            "timestamp": int(row["timestamp"]) if "timestamp" in row else 0,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row.get("volume", 0)),
        })
    return records


@router.get("/market/{exchange_id}/{symbol}/analysis")
async def get_analysis(exchange_id: str, symbol: str, timeframe: str = "1h"):
    from app.indicators.technical import TechnicalAnalyzer
    sym = symbol.replace("-", "/")
    df = await paper_exchange.fetch_ohlcv(exchange_id, sym, timeframe)
    if len(df) < 50:
        raise HTTPException(status_code=400, detail="Not enough data")
    analyzer = TechnicalAnalyzer(df)
    signal = analyzer.analyze()
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "rsi": signal.rsi,
        "rsi_signal": signal.rsi_signal,
        "macd_signal": signal.macd_signal,
        "bollinger_signal": signal.bollinger_signal,
        "ema_trend": signal.ema_trend,
        "volume_trend": signal.volume_trend,
        "atr": signal.atr,
        "support": signal.support,
        "resistance": signal.resistance,
        "overall_signal": signal.overall_signal,
        "confidence": signal.confidence,
    }


@router.post("/accounting/deposit")
def record_deposit(req: DepositRequest, bg: BackgroundTasks, account: str = "default", _auth=Depends(require_auth)):
    acct = _resolve_account(account)
    dep = acct.trade_store.add_deposit({
        "exchange": req.exchange,
        "amount_usd": req.amount_usd,
        "asset": req.asset,
        "asset_amount": req.asset_amount,
        "wallet_address": req.wallet_address,
        "tx_hash": req.tx_hash,
    })
    acct.paper_exchange.balances["USDT"] = acct.paper_exchange.balances.get("USDT", 0) + req.amount_usd
    acct.paper_exchange._save()
    new_total = acct.paper_exchange.balances.get("USDT", 0)
    bg.add_task(acct.risk_engine.rebalance_buckets, new_total, {})
    acct.trade_store.snapshots.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "balance": round(new_total, 5),
        "open_trades": len(acct.trade_store.get_open_trades()),
        "total_trades": len(acct.trade_store.trades),
    })
    acct.trade_store._save()
    return {
        "id": dep["id"],
        "amount_usd": req.amount_usd,
        "new_balance": round(new_total, 5),
    }


@router.post("/accounting/withdrawal")
def record_withdrawal(req: WithdrawalRequest, bg: BackgroundTasks, account: str = "default", _auth=Depends(require_auth)):
    acct = _resolve_account(account)
    wd = acct.trade_store.add_withdrawal({
        "exchange": req.exchange,
        "amount_usd": req.amount_usd,
        "asset": req.asset,
        "asset_amount": req.asset_amount,
        "wallet_address": req.wallet_address,
        "tx_hash": req.tx_hash,
    })
    acct.paper_exchange.balances["USDT"] = max(0, acct.paper_exchange.balances.get("USDT", 0) - req.amount_usd)
    acct.paper_exchange._save()
    new_total = acct.paper_exchange.balances.get("USDT", 0)
    bg.add_task(acct.risk_engine.rebalance_buckets, new_total, {})
    acct.trade_store.snapshots.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "balance": round(new_total, 5),
        "open_trades": len(acct.trade_store.get_open_trades()),
        "total_trades": len(acct.trade_store.trades),
    })
    acct.trade_store._save()
    return {
        "id": wd["id"],
        "amount_usd": req.amount_usd,
        "new_balance": round(new_total, 5),
    }


@router.post("/accounting/reset")
def reset_account(bg: BackgroundTasks, account: str = "default", _auth=Depends(require_auth)):
    acct = _resolve_account(account)
    acct.paper_exchange.balances = {"USDT": 0.0}
    acct.paper_exchange._save()
    acct.trade_store.trades.clear()
    acct.trade_store.deposits.clear()
    acct.trade_store.withdrawals.clear()
    acct.trade_store.snapshots.clear()
    acct.trade_store._running_balance = 0.0
    acct.trade_store._next_id = 1
    acct.trade_store.snapshots.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "balance": 0.0,
        "open_trades": 0,
        "total_trades": 0,
    })
    acct.trade_store._save()

    async def _reset_buckets():
        from app.risk.engine import BucketAllocation
        allocation = BucketAllocation(total_capital_usd=0.0)
        await acct.risk_engine.save_bucket_allocation(allocation)
        await store.set("daily_pnl", "0")

    bg.add_task(_reset_buckets)
    return {"status": "reset", "balance": 0.0}


@router.get("/accounting/summary")
def get_accounting_summary(account: str = "default"):
    acct = _resolve_account(account)
    data = acct.trade_store.full_accounting()
    live_total = _fast_live_balance(acct.paper_exchange, acct.trade_store)
    cash = sum(v for k, v in acct.paper_exchange.balances.items() if k in ("USDT", "USD"))
    open_pos_value = live_total - cash
    deps = data["summary"]["total_deposits_usd"]
    wds = data["summary"]["total_withdrawals_usd"]
    net_deps = deps - wds
    live_pnl = live_total - net_deps if net_deps > 0 else 0
    data["summary"]["account_value_usd"] = round(live_total, 5)
    data["summary"]["net_pnl_usd"] = round(live_pnl, 5)
    data["summary"]["cash_balance_usd"] = round(cash, 5)
    data["summary"]["open_position_value_usd"] = round(open_pos_value, 5)
    data["summary"]["daily_target_pct"] = acct.config.daily_target_pct
    data["summary"]["target_hit"] = acct._target_hit
    data["summary"]["auto_stop_on_target"] = acct.config.auto_stop_on_target
    return data


@router.get("/accounting/pnl")
def get_pnl(days: int = 30, account: str = "default"):
    acct = _resolve_account(account)
    return acct.trade_store.pnl_by_date(days)


@router.get("/accounting/win-rate")
def get_win_rate(account: str = "default"):
    acct = _resolve_account(account)
    return acct.trade_store.win_rate()


@router.get("/accounting/by-bot")
def get_pnl_by_bot(account: str = "default"):
    acct = _resolve_account(account)
    return acct.trade_store.pnl_by_bot()


@router.get("/accounting/trades")
def get_trades(status: str = "all", account: str = "default"):
    acct = _resolve_account(account)
    if status == "open":
        return acct.trade_store.get_open_trades()
    elif status == "closed":
        return acct.trade_store.get_closed_trades()
    return acct.trade_store.trades


@router.get("/accounting/trades/with-balance")
def get_trades_with_balance(account: str = "default"):
    acct = _resolve_account(account)
    return acct.trade_store.trades_with_running_balance()


@router.get("/accounting/active-trades-live")
def get_active_trades_live(account: str = "default"):
    acct = _resolve_account(account)
    open_trades = acct.trade_store.get_open_trades()
    entry_prices = _entry_price_map(acct.trade_store)
    cached_prices: dict[str, float] = {}
    for cache_key, cached in live_prices._ticker_cache.items():
        if cached and cached.get("last", 0) > 0:
            sym = cache_key.split(":", 1)[-1] if ":" in cache_key else cache_key
            cached_prices[sym] = cached["last"]
    result = []
    for t in open_trades:
        symbol = t.get("symbol", "")
        current_price = cached_prices.get(symbol) or entry_prices.get(symbol) or t.get("entry_price", 0)
        entry_price = t.get("entry_price", 0)
        quantity = t.get("quantity", 0)
        side = t.get("side", "buy")
        entry_value = entry_price * quantity
        if side == "buy":
            position_value = current_price * quantity
            unrealized_pnl = (current_price - entry_price) * quantity
        else:
            unrealized_pnl = (entry_price - current_price) * quantity
            position_value = entry_value + unrealized_pnl
        fees = t.get("entry_fee_usd", 0)
        unrealized_pnl -= fees
        pnl_pct = (unrealized_pnl / entry_value * 100) if entry_value > 0 else 0
        result.append({
            **t,
            "current_price": round(current_price, 8),
            "current_value_usd": round(position_value, 2),
            "unrealized_pnl_usd": round(unrealized_pnl, 2),
            "unrealized_pnl_pct": round(pnl_pct, 2),
            "stop_loss_price": t.get("stop_loss_price", 0),
            "take_profit_price": t.get("take_profit_price", 0),
        })
    return result


@router.post("/accounting/trades/{trade_ref}/close")
async def close_trade_manually(trade_ref: str, account: str = "default", _auth=Depends(require_auth)):
    acct = _resolve_account(account)
    ts = acct.trade_store
    pe = acct.paper_exchange

    trade = None
    for t in ts.get_open_trades():
        if str(t.get("id")) == trade_ref or t.get("order_id", "") == trade_ref:
            trade = t
            break
    if not trade:
        raise HTTPException(status_code=404, detail="Open trade not found")
    trade_id = trade["id"]

    symbol = trade["symbol"]
    entry_price = trade.get("entry_price", 0)
    quantity = trade.get("quantity", 0)
    side = trade.get("side", "buy")

    try:
        close_side = "sell" if side == "buy" else "buy"
        order = await pe.create_order("paper", symbol, close_side, quantity)
        exit_price = order["price"]
        exit_fee = order.get("fee", 0)
        exit_slippage = order.get("slippage_usd", 0)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to close: {str(e)}")

    if side == "buy":
        gross_pnl = (exit_price - entry_price) * quantity
    else:
        gross_pnl = (entry_price - exit_price) * quantity

    entry_fee = trade.get("entry_fee_usd", 0)
    net_pnl = round(gross_pnl - entry_fee - exit_fee, 5)

    ts.close_trade(trade_id, exit_price, net_pnl, round(exit_fee, 5), "closed", exit_slippage_usd=round(exit_slippage, 8))
    ts.record_snapshot()

    _all_bots = _get_all_bots(account)
    for bot in _all_bots:
        bot.active_trades = [t for t in bot.active_trades if t.get("symbol") != symbol or t.get("order_id") != trade.get("order_id", "")]

    return {
        "status": "closed",
        "trade_id": trade_id,
        "symbol": symbol,
        "exit_price": exit_price,
        "pnl_usd": net_pnl,
        "exit_fee": round(exit_fee, 5),
    }


def _get_all_bots(account: str = "default"):
    if account == "default":
        from app.main import scalper_bot, swing_bot, long_term_bot, grid_bot, mean_reversion_bot, momentum_bot, dca_bot
        return [scalper_bot, swing_bot, long_term_bot, grid_bot, mean_reversion_bot, momentum_bot, dca_bot]
    try:
        acct = account_manager.get(account)
        return list(acct.bots.values())
    except Exception:
        return []


@router.get("/accounting/fees")
def get_total_fees(account: str = "default"):
    acct = _resolve_account(account)
    return {
        "total_fees_usd": acct.trade_store.total_fees(),
        "fee_breakdown": {
            "entry_fees": round(sum(t.get("entry_fee_usd", 0) for t in acct.trade_store.trades), 4),
            "exit_fees": round(sum(t.get("exit_fee_usd", 0) for t in acct.trade_store.trades), 4),
        },
    }


@router.get("/accounting/live-balance")
def get_live_balance(account: str = "default"):
    acct = _resolve_account(account)
    cash = sum(v for k, v in acct.paper_exchange.balances.items() if k in ("USDT", "USD"))
    live_total = _fast_live_balance(acct.paper_exchange, acct.trade_store)
    open_pos = live_total - cash
    return {
        "cash_balance_usd": round(cash, 5),
        "open_position_value_usd": round(open_pos, 5),
        "total_live_balance_usd": round(live_total, 5),
        "open_trade_count": len(acct.trade_store.get_open_trades()),
    }


@router.post("/backtest")
async def run_backtest(req: BacktestRequest, _auth=Depends(require_auth)):
    try:
        df = await paper_exchange.fetch_ohlcv(req.exchange_id, req.symbol, req.timeframe, limit=req.limit)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch data for {req.symbol} on {req.exchange_id}: {str(e)}")
    if len(df) < 50:
        raise HTTPException(status_code=400, detail=f"Not enough candle data ({len(df)} candles). Need at least 50.")
    engine = BacktestEngine()
    result = engine.run(
        df, req.symbol, req.timeframe,
        initial_capital=req.initial_capital,
        risk_per_trade_pct=req.risk_per_trade_pct,
        sl_atr_multiplier=req.sl_atr_multiplier,
        tp_rr_ratio=req.tp_rr_ratio,
        min_confidence=req.min_confidence,
        min_confirmations=req.min_confirmations,
    )
    return {
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "start_date": result.start_date,
        "end_date": result.end_date,
        "initial_capital": result.initial_capital,
        "final_capital": result.final_capital,
        "total_trades": result.total_trades,
        "winning_trades": result.winning_trades,
        "losing_trades": result.losing_trades,
        "win_rate": result.win_rate,
        "total_pnl_usd": result.total_pnl_usd,
        "total_fees_usd": result.total_fees_usd,
        "max_drawdown_pct": result.max_drawdown_pct,
        "sharpe_ratio": result.sharpe_ratio,
        "trades": [t.__dict__ for t in result.trades],
    }


@router.get("/risk/status")
async def get_risk_status():
    daily_pnl = await risk_engine.get_daily_pnl()
    circuit_breaker = await risk_engine.check_circuit_breaker()
    allocation = await risk_engine.get_bucket_allocation()
    return {
        "daily_pnl_usd": daily_pnl,
        "circuit_breaker_active": circuit_breaker,
        "max_daily_loss_usd": settings.max_daily_loss_usd,
        "bucket_allocation": allocation.__dict__,
        "paper_trading": settings.paper_trading,
    }


@router.post("/risk/rebalance")
async def rebalance(req: RebalanceRequest, _auth=Depends(require_auth)):
    try:
        total = req.total_capital
        if total is None or total <= 0:
            balance = await paper_exchange.fetch_balance("paper")
            total = balance["total"].get("USDT", 0)
        if total <= 0:
            total = trade_store.total_deposits() - trade_store.total_withdrawals()
        allocation = await risk_engine.rebalance_buckets(total, {})
        return {
            "status": "rebalanced",
            "total_capital_usd": round(total, 2),
            "allocation": allocation.__dict__,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bots/status")
async def get_bot_status(account: str = "default"):
    acct = _resolve_account(account)
    kv = acct.risk_engine._store
    all_bots = _get_all_bots(account)
    bot_map = {getattr(b, 'bot_type', None): b for b in all_bots if hasattr(b, 'bot_type')}
    bots = {}
    for bot_type in ["scalper", "swing", "long_term", "grid", "mean_reversion", "momentum", "dca"]:
        trades = await kv.hgetall(f"active_trades:{bot_type}")
        bot_inst = bot_map.get(None)
        for b in all_bots:
            if hasattr(b, 'bot_type') and b.bot_type.value == bot_type:
                bot_inst = b
                break
        bots[bot_type] = {
            "active_trades": len(trades),
            "trades": [json.loads(v) for v in trades.values()],
            "running": bot_inst.running if bot_inst else False,
        }
    return bots


@router.get("/accounting/ledger")
def get_ledger(account: str = "default"):
    acct = _resolve_account(account)
    return acct.trade_store.get_ledger()


class UpdateConfigRequest(BaseModel):
    max_daily_loss_usd: Optional[float] = None
    max_position_size_usd: Optional[float] = None
    default_stop_loss_pct: Optional[float] = None
    max_leverage: Optional[float] = None


@router.get("/config")
async def get_config():
    return {
        "max_position_size_usd": settings.max_position_size_usd,
        "max_daily_loss_usd": settings.max_daily_loss_usd,
        "default_stop_loss_pct": settings.default_stop_loss_pct,
        "max_leverage": settings.max_leverage,
        "paper_trading": settings.paper_trading,
    }


@router.post("/config")
async def update_config(req: UpdateConfigRequest, _auth=Depends(require_auth)):
    if req.max_daily_loss_usd is not None:
        settings.max_daily_loss_usd = req.max_daily_loss_usd
        risk_engine.max_daily_loss = req.max_daily_loss_usd
    if req.max_position_size_usd is not None:
        settings.max_position_size_usd = req.max_position_size_usd
    if req.default_stop_loss_pct is not None:
        settings.default_stop_loss_pct = req.default_stop_loss_pct
        risk_engine.default_sl_pct = req.default_stop_loss_pct
    if req.max_leverage is not None:
        settings.max_leverage = req.max_leverage
        risk_engine.max_leverage = req.max_leverage
    return {
        "max_position_size_usd": settings.max_position_size_usd,
        "max_daily_loss_usd": settings.max_daily_loss_usd,
        "default_stop_loss_pct": settings.default_stop_loss_pct,
        "max_leverage": settings.max_leverage,
        "paper_trading": settings.paper_trading,
    }


class CreateAccountRequest(BaseModel):
    name: str
    label: str = ""
    daily_target_pct: Optional[float] = None
    max_daily_loss_usd: float = 50.0
    auto_stop_on_target: bool = False
    initial_deposit_usd: float = 0.0


class UpdateAccountRequest(BaseModel):
    label: Optional[str] = None
    daily_target_pct: Optional[float] = None
    max_daily_loss_usd: Optional[float] = None
    auto_stop_on_target: Optional[bool] = None


@router.get("/accounts")
def list_accounts():
    return account_manager.list_accounts()


@router.post("/accounts")
def create_account(req: CreateAccountRequest, _auth=Depends(require_auth)):
    try:
        config = account_manager.create(
            name=req.name,
            label=req.label,
            daily_target_pct=req.daily_target_pct,
            max_daily_loss_usd=req.max_daily_loss_usd,
            auto_stop_on_target=req.auto_stop_on_target,
        )
        if req.initial_deposit_usd > 0:
            acct = account_manager.get(req.name)
            acct.trade_store.add_deposit({
                "exchange": "paper",
                "amount_usd": req.initial_deposit_usd,
                "asset": "USDT",
                "asset_amount": req.initial_deposit_usd,
            })
            acct.paper_exchange.balances["USDT"] = req.initial_deposit_usd
            acct.paper_exchange._save()
            acct.paper_exchange.connect("paper")
        return config.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/accounts/{name}")
def update_account_config(name: str, req: UpdateAccountRequest, _auth=Depends(require_auth)):
    try:
        config = account_manager.update(
            name,
            label=req.label,
            daily_target_pct=req.daily_target_pct,
            max_daily_loss_usd=req.max_daily_loss_usd,
            auto_stop_on_target=req.auto_stop_on_target,
        )
        return config.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/accounts/{name}")
def delete_account(name: str, _auth=Depends(require_auth)):
    try:
        account_manager.delete(name)
        return {"status": "deleted", "name": name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/accounts/{name}/start-bots")
async def start_account_bots(name: str, _auth=Depends(require_auth)):
    acct = _resolve_account(name)
    if not acct.paper_exchange.is_connected("paper"):
        acct.paper_exchange.connect("paper")

    balance = await acct.paper_exchange.fetch_balance("paper")
    total = balance.get("total", {}).get("USDT", 0) or 0
    if total > 0:
        await acct.risk_engine.rebalance_buckets(total, {})
    else:
        raise HTTPException(status_code=400, detail="No USDT balance -- deposit funds first")

    from app.bots.scalper import ScalperBot
    from app.bots.swing import SwingBot
    from app.bots.long_term import LongTermBot
    from app.bots.grid import GridBot
    from app.bots.mean_reversion import MeanReversionBot
    from app.bots.momentum import MomentumBot
    from app.bots.dca import DCABot
    from app.indicators.sentiment import SentimentAnalyzer

    sentiment = SentimentAnalyzer()
    pe = acct.paper_exchange
    re = acct.risk_engine

    bots_map = {
        "scalper": (ScalperBot(pe, re, sentiment), 30),
        "swing": (SwingBot(pe, re, sentiment), 300),
        "long_term": (LongTermBot(pe, re, sentiment), 3600),
        "grid": (GridBot(pe, re, sentiment), 60),
        "mean_reversion": (MeanReversionBot(pe, re, sentiment), 120),
        "momentum": (MomentumBot(pe, re, sentiment), 300),
        "dca": (DCABot(pe, re, sentiment), 180),
    }

    acct.bots = {k: v[0] for k, v in bots_map.items()}

    for bot in acct.bots.values():
        bot._account = acct
        bot._trade_store = acct.trade_store
        bot._kv_store = acct.risk_engine._store

    import asyncio
    for bot_name, (bot, interval) in bots_map.items():
        if bot_name not in acct.bot_tasks or acct.bot_tasks[bot_name].done():
            acct.bot_tasks[bot_name] = asyncio.create_task(
                bot.start("paper", interval_seconds=interval),
                name=f"bot_{name}_{bot_name}",
            )

    return {"status": "started", "account": name, "bots": list(bots_map.keys())}


@router.get("/learning/stats")
async def learning_stats(_auth=Depends(require_auth)):
    from app.learning.autopsy import adaptive_memory
    stats = adaptive_memory.get_stats()
    return stats


@router.get("/learning/autopsies")
async def learning_autopsies(limit: int = 20, _auth=Depends(require_auth)):
    from app.learning.autopsy import adaptive_memory
    autopsies = adaptive_memory.autopsies[-limit:]
    autopsies.reverse()
    return {"autopsies": autopsies, "total": len(adaptive_memory.autopsies)}


@router.get("/learning/adjustments")
async def learning_adjustments(_auth=Depends(require_auth)):
    from app.learning.autopsy import adaptive_memory
    return {"adjustments": adaptive_memory.adjustments}


@router.post("/accounts/{name}/stop-bots")
async def stop_account_bots(name: str, _auth=Depends(require_auth)):
    acct = _resolve_account(name)
    for bot in acct.bots.values():
        bot.stop()
    for task in acct.bot_tasks.values():
        task.cancel()
    acct.bot_tasks.clear()
    return {"status": "stopped", "account": name}
