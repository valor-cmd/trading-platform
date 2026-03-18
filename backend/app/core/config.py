from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    database_url: str = ""
    redis_url: str = ""

    coinbase_api_key: str = ""
    coinbase_api_secret: str = ""

    metamask_rpc_url: str = ""

    xaman_api_key: str = ""
    xaman_api_secret: str = ""

    api_secret_key: str = ""

    fear_greed_api_url: str = "https://api.alternative.me/fng/"

    max_position_size_usd: float = 500.0
    max_daily_loss_usd: float = 5.0
    default_stop_loss_pct: float = 2.0
    max_leverage: float = 3.0

    paper_trading: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
