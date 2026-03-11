from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/trading_platform"
    redis_url: str = "redis://localhost:6379/0"

    coinbase_api_key: str = ""
    coinbase_api_secret: str = ""

    metamask_rpc_url: str = ""

    xaman_api_key: str = ""
    xaman_api_secret: str = ""

    fear_greed_api_url: str = "https://api.alternative.me/fng/"

    max_position_size_usd: float = 10000.0
    max_daily_loss_usd: float = 50.0
    default_stop_loss_pct: float = 2.0
    max_leverage: float = 3.0

    paper_trading: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
