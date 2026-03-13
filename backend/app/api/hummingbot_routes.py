import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.core.security import require_auth, sanitize_key_for_log

from app.hummingbot.manager import hbot_manager
from app.hummingbot.strategies import (
    StrategyType,
    create_strategy_config,
    PMMStrategyConfig,
    GridStrategyConfig,
    DCAStrategyConfig,
    ArbStrategyConfig,
    DirectionalStrategyConfig,
)
from app.hummingbot.fee_tracker import fee_tracker

logger = logging.getLogger(__name__)

hbot_router = APIRouter(prefix="/hummingbot", tags=["hummingbot"])


class ConnectRequest(BaseModel):
    hbot_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    gateway_url: Optional[str] = None


class AddExchangeRequest(BaseModel):
    exchange: str
    api_key: str
    api_secret: str
    account_name: Optional[str] = None
    passphrase: Optional[str] = None
    subaccount: Optional[str] = None


class ModeRequest(BaseModel):
    paper: bool = True


class StrategyRequest(BaseModel):
    strategy_type: str
    bot_name: Optional[str] = None
    params: dict = {}


class OrderRequest(BaseModel):
    connector: str
    trading_pair: str
    order_type: str = "limit"
    side: str = "buy"
    amount: float = 0.001
    price: Optional[float] = None


class RPCConfigRequest(BaseModel):
    chain: str
    network: str = "mainnet"
    provider: str = "flashbots"
    api_key: Optional[str] = None


class SwapRequest(BaseModel):
    chain: str
    network: str = "mainnet"
    connector: str
    base_token: str
    quote_token: str
    amount: str
    side: str = "buy"
    slippage: float = 1.0
    address: Optional[str] = None


@hbot_router.post("/connect")
async def connect_hummingbot(req: ConnectRequest, _auth=Depends(require_auth)):
    result = await hbot_manager.connect(
        hbot_url=req.hbot_url,
        username=req.username,
        password=req.password,
        gateway_url=req.gateway_url,
    )
    if not result.get("connected"):
        return {"status": "unavailable", "message": "Hummingbot API not reachable", **result}
    await hbot_manager.start_health_monitor()
    return {"status": "connected", **result}


@hbot_router.post("/disconnect")
async def disconnect_hummingbot(_auth=Depends(require_auth)):
    await hbot_manager.disconnect()
    return {"status": "disconnected"}


@hbot_router.get("/status")
async def hummingbot_status():
    return await hbot_manager.status()


@hbot_router.post("/mode")
async def set_mode(req: ModeRequest, _auth=Depends(require_auth)):
    hbot_manager.set_mode(req.paper)
    return {"paper_mode": hbot_manager.is_paper_mode}


@hbot_router.post("/exchange/add")
async def add_exchange(req: AddExchangeRequest, _auth=Depends(require_auth)):
    extra = {}
    if req.passphrase:
        extra["passphrase"] = req.passphrase
    if req.subaccount:
        extra["subaccount"] = req.subaccount
    result = await hbot_manager.add_exchange_credentials(
        exchange=req.exchange,
        api_key=req.api_key,
        api_secret=req.api_secret,
        account_name=req.account_name,
        **extra,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@hbot_router.get("/exchanges")
async def list_exchanges():
    if not hbot_manager.client or not hbot_manager.is_connected:
        return {"connected": False, "exchanges": []}
    accounts = await hbot_manager.client.get_accounts()
    connectors = await hbot_manager.client.get_connectors()
    return {"accounts": accounts, "connectors": connectors}


@hbot_router.get("/portfolio")
async def get_portfolio(account: Optional[str] = None):
    if not hbot_manager.client or not hbot_manager.is_connected:
        return {"connected": False, "portfolio": {}}
    return await hbot_manager.client.get_portfolio(account)


@hbot_router.post("/strategy/start")
async def start_strategy(req: StrategyRequest, _auth=Depends(require_auth)):
    if not hbot_manager.client or not hbot_manager.is_connected:
        raise HTTPException(status_code=503, detail="Hummingbot API not connected")

    try:
        config = create_strategy_config(req.strategy_type, req.params)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    paper = hbot_manager.is_paper_mode
    bot_name = req.bot_name or f"{req.strategy_type}_{req.params.get('trading_pair', 'BTC-USDT')}"

    if hasattr(config, "to_hbot_config"):
        hbot_config = config.to_hbot_config(paper=paper)
    elif hasattr(config, "to_executor_config"):
        hbot_config = config.to_executor_config(paper=paper)
    else:
        raise HTTPException(status_code=400, detail="Invalid strategy config")

    deploy_result = await hbot_manager.client.deploy_bot(bot_name)
    if "error" in deploy_result:
        logger.warning(f"Bot deploy note: {deploy_result}")

    script = "v2_with_controllers.py"
    if req.strategy_type in ("pure_market_making", "arbitrage"):
        script = f"{req.strategy_type}.py"

    start_result = await hbot_manager.client.start_bot(bot_name, script=script, config=hbot_config)
    return {
        "status": "started",
        "bot_name": bot_name,
        "strategy_type": req.strategy_type,
        "paper_mode": paper,
        "config": hbot_config,
        "start_result": start_result,
    }


@hbot_router.post("/strategy/stop")
async def stop_strategy(bot_name: str, _auth=Depends(require_auth)):
    if not hbot_manager.client or not hbot_manager.is_connected:
        raise HTTPException(status_code=503, detail="Hummingbot API not connected")
    result = await hbot_manager.client.stop_bot(bot_name)
    return {"status": "stopped", "bot_name": bot_name, "result": result}


@hbot_router.get("/bots")
async def list_bots():
    if not hbot_manager.client or not hbot_manager.is_connected:
        return {"connected": False, "bots": []}
    return await hbot_manager.client.list_bots()


@hbot_router.get("/bots/{bot_name}/status")
async def bot_status(bot_name: str):
    if not hbot_manager.client or not hbot_manager.is_connected:
        raise HTTPException(status_code=503, detail="Hummingbot API not connected")
    return await hbot_manager.client.get_bot_status(bot_name)


@hbot_router.get("/bots/{bot_name}/history")
async def bot_history(bot_name: str):
    if not hbot_manager.client or not hbot_manager.is_connected:
        raise HTTPException(status_code=503, detail="Hummingbot API not connected")
    return await hbot_manager.client.get_bot_history(bot_name)


@hbot_router.post("/order")
async def place_order(req: OrderRequest, _auth=Depends(require_auth)):
    if not hbot_manager.client or not hbot_manager.is_connected:
        raise HTTPException(status_code=503, detail="Hummingbot API not connected")

    connector = hbot_manager.get_connector_name(req.connector)
    result = await hbot_manager.client.create_order(
        connector=connector,
        trading_pair=req.trading_pair,
        order_type=req.order_type,
        side=req.side,
        amount=req.amount,
        price=req.price,
    )

    if "error" not in result:
        fee_rate = fee_tracker.get_exchange_fees(req.connector)
        rate = fee_rate.get("taker", 0.001)
        price = req.price or 0
        fee_usd = req.amount * price * rate if price else 0
        fee_tracker.record_trade_fee(
            exchange=req.connector,
            trading_pair=req.trading_pair,
            side=req.side,
            amount=req.amount,
            price=price,
            actual_fee_usd=fee_usd,
            fee_type="taker" if req.order_type == "market" else "maker",
        )

    return result


@hbot_router.delete("/order/{order_id}")
async def cancel_order(order_id: str, connector: str, trading_pair: str, _auth=Depends(require_auth)):
    if not hbot_manager.client or not hbot_manager.is_connected:
        raise HTTPException(status_code=503, detail="Hummingbot API not connected")
    return await hbot_manager.client.cancel_order(connector, trading_pair, order_id)


@hbot_router.get("/orders")
async def get_orders(connector: Optional[str] = None):
    if not hbot_manager.client or not hbot_manager.is_connected:
        return {"connected": False, "orders": []}
    return await hbot_manager.client.get_open_orders(connector)


@hbot_router.get("/trades")
async def get_trades(connector: Optional[str] = None, limit: int = 100):
    if not hbot_manager.client or not hbot_manager.is_connected:
        return {"connected": False, "trades": []}
    return await hbot_manager.client.get_trade_history(connector, limit)


@hbot_router.get("/market/ticker/{connector}/{pair}")
async def get_ticker(connector: str, pair: str):
    if not hbot_manager.client or not hbot_manager.is_connected:
        raise HTTPException(status_code=503, detail="Hummingbot API not connected")
    return await hbot_manager.client.get_ticker(connector, pair)


@hbot_router.get("/market/orderbook/{connector}/{pair}")
async def get_orderbook(connector: str, pair: str):
    if not hbot_manager.client or not hbot_manager.is_connected:
        raise HTTPException(status_code=503, detail="Hummingbot API not connected")
    return await hbot_manager.client.get_orderbook(connector, pair)


@hbot_router.get("/fees")
async def get_fees():
    return fee_tracker.get_fee_summary()


@hbot_router.get("/fees/recent")
async def get_recent_fees(limit: int = 50):
    return fee_tracker.get_recent_fees(limit)


@hbot_router.get("/fees/estimate")
async def estimate_fees(
    exchange: str,
    amount: float,
    price: float,
    is_maker: bool = False,
    chain: Optional[str] = None,
    dex_connector: Optional[str] = None,
):
    cex_fee = fee_tracker.estimate_cex_fee(exchange, amount, price, is_maker)
    result = {
        "exchange": exchange,
        "amount": amount,
        "price": price,
        "notional_usd": amount * price,
        "is_maker": is_maker,
        "fee_rate": fee_tracker.get_exchange_fees(exchange),
        "estimated_fee_usd": round(cex_fee, 5),
    }
    if chain and dex_connector:
        gas = fee_tracker.estimate_dex_gas(chain, dex_connector)
        result["gas_estimate_usd"] = round(gas, 5)
        result["total_estimated_cost_usd"] = round(cex_fee + gas, 5)
    return result


@hbot_router.post("/rpc/configure")
async def configure_rpc(req: RPCConfigRequest, _auth=Depends(require_auth)):
    result = await hbot_manager.configure_private_rpc(
        chain=req.chain,
        network=req.network,
        provider=req.provider,
        api_key=req.api_key,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@hbot_router.get("/rpc/configs")
async def get_rpc_configs():
    return hbot_manager.get_rpc_configs()


@hbot_router.get("/gateway/status")
async def gateway_status():
    if hbot_manager.gateway and hbot_manager.is_gateway_connected:
        return await hbot_manager.gateway.health()
    if hbot_manager.client and hbot_manager.is_connected:
        return await hbot_manager.client.gateway_status()
    return {"connected": False}


@hbot_router.get("/gateway/chains")
async def gateway_chains():
    if hbot_manager.gateway and hbot_manager.is_gateway_connected:
        return await hbot_manager.gateway.get_chain_status()
    if hbot_manager.client and hbot_manager.is_connected:
        return await hbot_manager.client.gateway_get_chains()
    return {"connected": False, "chains": []}


@hbot_router.get("/gateway/connectors")
async def gateway_connectors():
    if hbot_manager.gateway and hbot_manager.is_gateway_connected:
        return await hbot_manager.gateway.get_connectors()
    if hbot_manager.client and hbot_manager.is_connected:
        return await hbot_manager.client.gateway_get_connectors()
    return {"connected": False, "connectors": []}


@hbot_router.get("/gateway/tokens/{chain}/{network}")
async def gateway_tokens(chain: str, network: str):
    if hbot_manager.gateway and hbot_manager.is_gateway_connected:
        return await hbot_manager.gateway.get_tokens(chain, network)
    if hbot_manager.client and hbot_manager.is_connected:
        return await hbot_manager.client.gateway_get_tokens(chain, network)
    return {"connected": False, "tokens": []}


@hbot_router.post("/gateway/swap/quote")
async def gateway_swap_quote(req: SwapRequest, _auth=Depends(require_auth)):
    if hbot_manager.gateway and hbot_manager.is_gateway_connected:
        return await hbot_manager.gateway.quote_swap(
            chain=req.chain,
            connector=req.connector,
            base_token=req.base_token,
            quote_token=req.quote_token,
            amount=req.amount,
            side=req.side,
            network=req.network,
            slippage=req.slippage,
        )
    if hbot_manager.client and hbot_manager.is_connected:
        return await hbot_manager.client.gateway_quote_swap(
            chain=req.chain,
            network=req.network,
            connector=req.connector,
            base_token=req.base_token,
            quote_token=req.quote_token,
            amount=req.amount,
            side=req.side,
            slippage=req.slippage,
        )
    raise HTTPException(status_code=503, detail="Gateway not connected")


@hbot_router.post("/gateway/swap/execute")
async def gateway_swap_execute(req: SwapRequest, _auth=Depends(require_auth)):
    result = None
    if hbot_manager.gateway and hbot_manager.is_gateway_connected:
        result = await hbot_manager.gateway.execute_swap(
            chain=req.chain,
            connector=req.connector,
            base_token=req.base_token,
            quote_token=req.quote_token,
            amount=req.amount,
            side=req.side,
            network=req.network,
            slippage=req.slippage,
            address=req.address,
        )
    elif hbot_manager.client and hbot_manager.is_connected:
        result = await hbot_manager.client.gateway_execute_swap(
            chain=req.chain,
            network=req.network,
            connector=req.connector,
            base_token=req.base_token,
            quote_token=req.quote_token,
            amount=req.amount,
            side=req.side,
            slippage=req.slippage,
            address=req.address,
        )
    else:
        raise HTTPException(status_code=503, detail="Gateway not connected")

    if result and "error" not in result:
        gas = fee_tracker.estimate_dex_gas(req.chain, req.connector)
        fee_tracker.record_trade_fee(
            exchange=f"gateway:{req.connector}",
            trading_pair=f"{req.base_token}-{req.quote_token}",
            side=req.side,
            amount=float(req.amount),
            price=0,
            actual_fee_usd=0,
            fee_type="dex_swap",
            gas_cost_usd=gas,
            slippage_pct=req.slippage,
        )

    return result


@hbot_router.get("/gateway/swap/status")
async def gateway_swap_status(chain: str, network: str, tx_hash: str):
    if hbot_manager.gateway and hbot_manager.is_gateway_connected:
        return await hbot_manager.gateway.get_swap_status(chain, tx_hash, network)
    if hbot_manager.client and hbot_manager.is_connected:
        return await hbot_manager.client.gateway_swap_status(chain, network, tx_hash)
    raise HTTPException(status_code=503, detail="Gateway not connected")


@hbot_router.post("/backtest")
async def run_backtest(config: dict, _auth=Depends(require_auth)):
    if not hbot_manager.client or not hbot_manager.is_connected:
        raise HTTPException(status_code=503, detail="Hummingbot API not connected")
    return await hbot_manager.client.run_backtest(config)


@hbot_router.get("/strategy/types")
async def get_strategy_types():
    return {
        "types": [
            {
                "id": "pure_market_making",
                "name": "Pure Market Making",
                "description": "Place bid/ask orders around mid-price with configurable spreads",
                "executor": "V1 Strategy",
                "params": ["connector", "trading_pair", "bid_spread", "ask_spread", "order_amount", "order_levels"],
            },
            {
                "id": "grid",
                "name": "Grid Trading",
                "description": "Place grid of orders between price range to profit from oscillations",
                "executor": "GridExecutor",
                "params": ["connector", "trading_pair", "start_price", "end_price", "total_amount_quote", "num_levels"],
            },
            {
                "id": "dca",
                "name": "Dollar Cost Average",
                "description": "Spread investment across multiple orders to reduce volatility impact",
                "executor": "DCAExecutor",
                "params": ["connector", "trading_pair", "side", "total_amount_quote", "num_orders", "stop_loss", "take_profit"],
            },
            {
                "id": "arbitrage",
                "name": "Cross-Exchange Arbitrage",
                "description": "Exploit price differences between two exchanges",
                "executor": "V1 Strategy",
                "params": ["connector_1", "connector_2", "trading_pair", "min_profitability", "order_amount"],
            },
            {
                "id": "directional",
                "name": "Directional Trading",
                "description": "Open position with stop-loss and take-profit (triple barrier)",
                "executor": "PositionExecutor",
                "params": ["connector", "trading_pair", "side", "order_amount", "stop_loss", "take_profit", "trailing_stop"],
            },
        ]
    }
