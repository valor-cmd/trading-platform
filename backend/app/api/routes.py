from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import json

from datetime import datetime, timezone

from app.core.config import settings
from app.core.store import store, trade_store
from app.exchange.simulator import paper_exchange
from app.risk.engine import RiskEngine
from app.backtesting.engine import BacktestEngine


async def _record_live_snapshot():
    usdt = paper_exchange.balances.get("USDT", 0)
    open_pos_value = 0.0
    for t in trade_store.get_open_trades():
        sym = t.get("symbol", "")
        qty = t.get("quantity", 0)
        try:
            ticker = await paper_exchange.fetch_ticker("paper", sym)
            open_pos_value += ticker["last"] * qty
        except Exception:
            open_pos_value += t.get("entry_price", 0) * qty
    live_balance = usdt + open_pos_value
    trade_store.snapshots.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "balance": round(live_balance, 5),
        "open_trades": len(trade_store.get_open_trades()),
        "total_trades": len(trade_store.trades),
    })

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


class WithdrawalRequest(BaseModel):
    exchange: str
    amount_usd: float
    asset: str
    asset_amount: float
    wallet_address: Optional[str] = None
    tx_hash: Optional[str] = None


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


class RebalanceRequest(BaseModel):
    total_capital: Optional[float] = None


@router.post("/exchange/connect")
async def connect_exchange(req: ConnectExchangeRequest):
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
async def record_deposit(req: DepositRequest):
    dep = trade_store.add_deposit({
        "exchange": req.exchange,
        "amount_usd": req.amount_usd,
        "asset": req.asset,
        "asset_amount": req.asset_amount,
        "wallet_address": req.wallet_address,
        "tx_hash": req.tx_hash,
    })
    paper_exchange.balances["USDT"] = paper_exchange.balances.get("USDT", 0) + req.amount_usd
    allocation = await risk_engine.get_bucket_allocation()
    allocation.total_capital_usd += req.amount_usd
    await risk_engine.save_bucket_allocation(allocation)
    await _record_live_snapshot()
    return {"id": dep["id"], "amount_usd": req.amount_usd}


@router.post("/accounting/withdrawal")
async def record_withdrawal(req: WithdrawalRequest):
    wd = trade_store.add_withdrawal({
        "exchange": req.exchange,
        "amount_usd": req.amount_usd,
        "asset": req.asset,
        "asset_amount": req.asset_amount,
        "wallet_address": req.wallet_address,
        "tx_hash": req.tx_hash,
    })
    paper_exchange.balances["USDT"] = max(0, paper_exchange.balances.get("USDT", 0) - req.amount_usd)
    allocation = await risk_engine.get_bucket_allocation()
    allocation.total_capital_usd = max(0, allocation.total_capital_usd - req.amount_usd)
    await risk_engine.save_bucket_allocation(allocation)
    await _record_live_snapshot()
    return {"id": wd["id"], "amount_usd": req.amount_usd}


@router.get("/accounting/summary")
async def get_accounting_summary():
    data = trade_store.full_accounting()
    usdt = paper_exchange.balances.get("USDT", 0)
    open_pos_value = 0.0
    for t in trade_store.get_open_trades():
        sym = t.get("symbol", "")
        qty = t.get("quantity", 0)
        try:
            ticker = await paper_exchange.fetch_ticker("paper", sym)
            open_pos_value += ticker["last"] * qty
        except Exception:
            open_pos_value += t.get("entry_price", 0) * qty
    live_total = usdt + open_pos_value
    deps = data["summary"]["total_deposits_usd"]
    wds = data["summary"]["total_withdrawals_usd"]
    net_deps = deps - wds
    live_pnl = live_total - net_deps if net_deps > 0 else 0
    data["summary"]["account_value_usd"] = round(live_total, 5)
    data["summary"]["net_pnl_usd"] = round(live_pnl, 5)
    data["summary"]["cash_balance_usd"] = round(usdt, 5)
    data["summary"]["open_position_value_usd"] = round(open_pos_value, 5)
    return data


@router.get("/accounting/pnl")
async def get_pnl(days: int = 30):
    return trade_store.pnl_by_date(days)


@router.get("/accounting/win-rate")
async def get_win_rate():
    return trade_store.win_rate()


@router.get("/accounting/by-bot")
async def get_pnl_by_bot():
    return trade_store.pnl_by_bot()


@router.get("/accounting/trades")
async def get_trades(status: str = "all"):
    if status == "open":
        return trade_store.get_open_trades()
    elif status == "closed":
        return trade_store.get_closed_trades()
    return trade_store.trades


@router.get("/accounting/trades/with-balance")
async def get_trades_with_balance():
    return trade_store.trades_with_running_balance()


@router.get("/accounting/active-trades-live")
async def get_active_trades_live():
    open_trades = trade_store.get_open_trades()
    result = []
    for t in open_trades:
        symbol = t.get("symbol", "")
        try:
            ticker = await paper_exchange.fetch_ticker("paper", symbol)
            current_price = ticker["last"]
        except Exception:
            current_price = t.get("entry_price", 0)
        entry_price = t.get("entry_price", 0)
        quantity = t.get("quantity", 0)
        side = t.get("side", "buy")
        position_value = current_price * quantity
        entry_value = entry_price * quantity
        if side == "buy":
            unrealized_pnl = (current_price - entry_price) * quantity
        else:
            unrealized_pnl = (entry_price - current_price) * quantity
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


@router.get("/accounting/fees")
async def get_total_fees():
    return {
        "total_fees_usd": trade_store.total_fees(),
        "fee_breakdown": {
            "entry_fees": round(sum(t.get("entry_fee_usd", 0) for t in trade_store.trades), 4),
            "exit_fees": round(sum(t.get("exit_fee_usd", 0) for t in trade_store.trades), 4),
        },
    }


@router.get("/accounting/live-balance")
async def get_live_balance():
    balance = await paper_exchange.fetch_balance("paper")
    usdt = balance["total"].get("USDT", 0)
    open_trades = trade_store.get_open_trades()
    open_position_value = 0.0
    for t in open_trades:
        try:
            ticker = await paper_exchange.fetch_ticker("paper", t.get("symbol", ""))
            open_position_value += ticker["last"] * t.get("quantity", 0)
        except Exception:
            open_position_value += t.get("entry_price", 0) * t.get("quantity", 0)
    return {
        "cash_balance_usd": round(usdt, 5),
        "open_position_value_usd": round(open_position_value, 5),
        "total_live_balance_usd": round(usdt + open_position_value, 4),
        "open_trade_count": len(open_trades),
    }


@router.post("/backtest")
async def run_backtest(req: BacktestRequest):
    df = await paper_exchange.fetch_ohlcv(req.exchange_id, req.symbol, req.timeframe, limit=req.limit)
    if len(df) < 201:
        raise HTTPException(status_code=400, detail="Not enough candle data for backtest")
    engine = BacktestEngine()
    result = engine.run(
        df, req.symbol, req.timeframe,
        initial_capital=req.initial_capital,
        risk_per_trade_pct=req.risk_per_trade_pct,
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
async def rebalance(req: RebalanceRequest):
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
async def get_bot_status():
    bots = {}
    for bot_type in ["scalper", "swing", "long_term"]:
        trades = await store.hgetall(f"active_trades:{bot_type}")
        bots[bot_type] = {
            "active_trades": len(trades),
            "trades": [json.loads(v) for v in trades.values()],
        }
    return bots


@router.get("/accounting/ledger")
async def get_ledger():
    return trade_store.get_ledger()


@router.get("/config")
async def get_config():
    return {
        "max_position_size_usd": settings.max_position_size_usd,
        "max_daily_loss_usd": settings.max_daily_loss_usd,
        "default_stop_loss_pct": settings.default_stop_loss_pct,
        "max_leverage": settings.max_leverage,
        "paper_trading": settings.paper_trading,
    }
