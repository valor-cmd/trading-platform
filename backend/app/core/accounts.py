import json
import os
import logging
from datetime import datetime, timezone
from typing import Optional

from app.core.store import TradeStore, InMemoryStore
from app.exchange.simulator import PaperExchangeManager
from app.risk.engine import RiskEngine

logger = logging.getLogger(__name__)

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")


class AccountConfig:
    def __init__(
        self,
        name: str,
        label: str = "",
        daily_target_pct: Optional[float] = None,
        max_daily_loss_usd: float = 50.0,
        auto_stop_on_target: bool = False,
        created_at: str = "",
    ):
        self.name = name
        self.label = label or name
        self.daily_target_pct = daily_target_pct
        self.max_daily_loss_usd = max_daily_loss_usd
        self.auto_stop_on_target = auto_stop_on_target
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "daily_target_pct": self.daily_target_pct,
            "max_daily_loss_usd": self.max_daily_loss_usd,
            "auto_stop_on_target": self.auto_stop_on_target,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AccountConfig":
        return cls(
            name=d["name"],
            label=d.get("label", d["name"]),
            daily_target_pct=d.get("daily_target_pct"),
            max_daily_loss_usd=d.get("max_daily_loss_usd", 50.0),
            auto_stop_on_target=d.get("auto_stop_on_target", False),
            created_at=d.get("created_at", ""),
        )


class Account:
    def __init__(self, config: AccountConfig, trade_store: TradeStore, paper_exchange: PaperExchangeManager, risk_engine: RiskEngine):
        self.config = config
        self.trade_store = trade_store
        self.paper_exchange = paper_exchange
        self.risk_engine = risk_engine
        self.bot_tasks: dict = {}
        self.bots: dict = {}
        self._target_hit = False
        self._target_hit_at: Optional[str] = None

    def check_daily_target(self) -> bool:
        if not self.config.daily_target_pct or not self.config.auto_stop_on_target:
            return False
        if self._target_hit:
            return True
        deps = self.trade_store.total_deposits() - self.trade_store.total_withdrawals()
        if deps <= 0:
            return False
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_pnl = 0.0
        for t in self.trade_store.get_closed_trades():
            closed_at = t.get("closed_at", "")
            if closed_at and closed_at[:10] == today:
                today_pnl += t.get("pnl_usd", 0)
        target_usd = deps * (self.config.daily_target_pct / 100.0)
        if today_pnl >= target_usd:
            self._target_hit = True
            self._target_hit_at = datetime.now(timezone.utc).isoformat()
            logger.info(f"Account '{self.config.name}' hit daily target: ${today_pnl:.2f} >= ${target_usd:.2f} ({self.config.daily_target_pct}%)")
            return True
        return False

    def reset_daily_target(self):
        self._target_hit = False
        self._target_hit_at = None


class AccountManager:
    def __init__(self):
        self._accounts: dict[str, Account] = {}
        self._configs: dict[str, AccountConfig] = {}
        self._load_configs()

    def _load_configs(self):
        try:
            if os.path.exists(ACCOUNTS_FILE):
                with open(ACCOUNTS_FILE, "r") as f:
                    data = json.load(f)
                for d in data.get("accounts", []):
                    cfg = AccountConfig.from_dict(d)
                    self._configs[cfg.name] = cfg
        except Exception as e:
            logger.error(f"Failed to load accounts config: {e}")

        if "default" not in self._configs:
            self._configs["default"] = AccountConfig(
                name="default",
                label="Main Account",
                max_daily_loss_usd=50.0,
            )

    def _save_configs(self):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            data = {"accounts": [c.to_dict() for c in self._configs.values()]}
            tmp = ACCOUNTS_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f)
            os.replace(tmp, ACCOUNTS_FILE)
        except Exception as e:
            logger.error(f"Failed to save accounts config: {e}")

    def _make_account(self, config: AccountConfig) -> Account:
        if config.name == "default":
            from app.core.store import trade_store as default_trade_store
            from app.exchange.simulator import paper_exchange as default_paper_exchange
            from app.api.routes import risk_engine as default_risk_engine
            return Account(config, default_trade_store, default_paper_exchange, default_risk_engine)

        acct_dir = os.path.join(DATA_DIR, f"account_{config.name}")
        os.makedirs(acct_dir, exist_ok=True)
        ts = TradeStore(persist_path=os.path.join(acct_dir, "trade_store.json"))
        pe = PaperExchangeManager(persist_path=os.path.join(acct_dir, "paper_exchange.json"))
        acct_store = InMemoryStore()
        re = RiskEngine(own_store=acct_store, trade_store_ref=ts)
        re.set_paper_exchange(pe)
        re.max_daily_loss = config.max_daily_loss_usd
        return Account(config, ts, pe, re)

    def get(self, name: str = "default") -> Account:
        if name not in self._accounts:
            config = self._configs.get(name)
            if not config:
                raise ValueError(f"Account '{name}' not found")
            self._accounts[name] = self._make_account(config)
        return self._accounts[name]

    def create(self, name: str, label: str = "", daily_target_pct: Optional[float] = None, max_daily_loss_usd: float = 50.0, auto_stop_on_target: bool = False) -> AccountConfig:
        if name in self._configs:
            raise ValueError(f"Account '{name}' already exists")
        if not name.isalnum() or len(name) > 30:
            raise ValueError("Account name must be alphanumeric, max 30 chars")
        config = AccountConfig(
            name=name,
            label=label or name,
            daily_target_pct=daily_target_pct,
            max_daily_loss_usd=max_daily_loss_usd,
            auto_stop_on_target=auto_stop_on_target,
        )
        self._configs[name] = config
        self._save_configs()
        return config

    def update(self, name: str, **kwargs) -> AccountConfig:
        config = self._configs.get(name)
        if not config:
            raise ValueError(f"Account '{name}' not found")
        for k, v in kwargs.items():
            if v is not None and hasattr(config, k):
                setattr(config, k, v)
        self._save_configs()
        if name in self._accounts:
            self._accounts[name].config = config
            if "max_daily_loss_usd" in kwargs and kwargs["max_daily_loss_usd"] is not None:
                self._accounts[name].risk_engine.max_daily_loss = kwargs["max_daily_loss_usd"]
        return config

    def delete(self, name: str):
        if name == "default":
            raise ValueError("Cannot delete default account")
        if name in self._accounts:
            acct = self._accounts[name]
            for task in acct.bot_tasks.values():
                task.cancel()
            for bot in acct.bots.values():
                bot.stop()
            del self._accounts[name]
        self._configs.pop(name, None)
        self._save_configs()

    def list_accounts(self) -> list[dict]:
        result = []
        for name, config in self._configs.items():
            acct = self._accounts.get(name)
            balance = 0.0
            if acct:
                balance = acct.paper_exchange.balances.get("USDT", 0)
            info = config.to_dict()
            info["balance_usd"] = round(balance, 5)
            info["active"] = name in self._accounts
            info["target_hit"] = acct._target_hit if acct else False
            result.append(info)
        return result


account_manager = AccountManager()
