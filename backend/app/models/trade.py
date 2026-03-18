from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum

from app.core.database import Base


class TradeStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    STOPPED_OUT = "stopped_out"


class TradeSide(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class BotType(str, enum.Enum):
    SCALPER = "scalper"
    SWING = "swing"
    LONG_TERM = "long_term"
    ARBITRAGE = "arbitrage"
    GRID = "grid"
    MEAN_REVERSION = "mean_reversion"
    MOMENTUM = "momentum"
    DCA = "dca"


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    bot_type = Column(Enum(BotType), nullable=False)
    exchange = Column(String, nullable=False)
    symbol = Column(String, nullable=False)
    side = Column(Enum(TradeSide), nullable=False)
    status = Column(Enum(TradeStatus), default=TradeStatus.OPEN)

    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=False)
    leverage = Column(Float, default=1.0)

    stop_loss_price = Column(Float, nullable=False)
    take_profit_price = Column(Float, nullable=True)

    entry_fee_usd = Column(Float, default=0.0)
    exit_fee_usd = Column(Float, default=0.0)

    pnl_usd = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)

    bucket = Column(String, nullable=True)
    reasoning = Column(Text, nullable=True)

    opened_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    closed_at = Column(DateTime, nullable=True)

    is_paper = Column(Boolean, default=True)


class Deposit(Base):
    __tablename__ = "deposits"

    id = Column(Integer, primary_key=True, index=True)
    exchange = Column(String, nullable=False)
    wallet_address = Column(String, nullable=True)
    amount_usd = Column(Float, nullable=False)
    asset = Column(String, nullable=False)
    asset_amount = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    tx_hash = Column(String, nullable=True)


class Withdrawal(Base):
    __tablename__ = "withdrawals"

    id = Column(Integer, primary_key=True, index=True)
    exchange = Column(String, nullable=False)
    wallet_address = Column(String, nullable=True)
    amount_usd = Column(Float, nullable=False)
    asset = Column(String, nullable=False)
    asset_amount = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    tx_hash = Column(String, nullable=True)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    total_value_usd = Column(Float, nullable=False)
    total_deposits_usd = Column(Float, nullable=False)
    total_withdrawals_usd = Column(Float, nullable=False)
    total_pnl_usd = Column(Float, nullable=False)
    total_fees_usd = Column(Float, nullable=False)
    open_positions = Column(Integer, default=0)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
