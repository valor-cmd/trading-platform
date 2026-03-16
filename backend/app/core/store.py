import json
import os
import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")


class InMemoryStore:
    def __init__(self):
        self.data: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = defaultdict(dict)
        self.subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    async def get(self, key: str) -> Optional[str]:
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None):
        self.data[key] = value

    async def hset(self, name: str, key: str, value: str):
        self.hashes[name][key] = value

    async def hgetall(self, name: str) -> dict[str, str]:
        return dict(self.hashes.get(name, {}))

    async def hdel(self, name: str, key: str):
        self.hashes.get(name, {}).pop(key, None)

    async def publish(self, channel: str, message: str):
        for queue in self.subscribers.get(channel, []):
            await queue.put({"type": "message", "data": message})

    def pubsub(self):
        return InMemoryPubSub(self)


class InMemoryPubSub:
    def __init__(self, store: InMemoryStore):
        self.store = store
        self.queue: asyncio.Queue = asyncio.Queue()
        self.channels: list[str] = []

    async def subscribe(self, channel: str):
        self.channels.append(channel)
        self.store.subscribers[channel].append(self.queue)

    async def listen(self):
        while True:
            msg = await self.queue.get()
            yield msg


store = InMemoryStore()


class TradeStore:
    def __init__(self, persist_path: Optional[str] = None):
        self.trades: list[dict] = []
        self.deposits: list[dict] = []
        self.withdrawals: list[dict] = []
        self.snapshots: list[dict] = []
        self._next_id = 1
        self._running_balance = 0.0
        self._persist_path = persist_path or os.path.join(DATA_DIR, "trade_store.json")
        self._save_lock = threading.Lock()
        self._load()

    def _load(self):
        try:
            if os.path.exists(self._persist_path):
                with open(self._persist_path, "r") as f:
                    data = json.load(f)
                self.trades = data.get("trades", [])
                self.deposits = data.get("deposits", [])
                self.withdrawals = data.get("withdrawals", [])
                self.snapshots = data.get("snapshots", [])[-500:]
                self._next_id = data.get("next_id", 1)
                self._running_balance = data.get("running_balance", 0.0)
                logger.info(f"Loaded trade store: {len(self.trades)} trades, {len(self.deposits)} deposits, balance=${self._running_balance:.2f}")
        except Exception as e:
            logger.error(f"Failed to load trade store: {e}")

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
            data = {
                "trades": self.trades,
                "deposits": self.deposits,
                "withdrawals": self.withdrawals,
                "snapshots": self.snapshots[-500:],
                "next_id": self._next_id,
                "running_balance": self._running_balance,
            }
            with self._save_lock:
                tmp = self._persist_path + ".tmp"
                with open(tmp, "w") as f:
                    json.dump(data, f)
                os.replace(tmp, self._persist_path)
        except Exception as e:
            logger.error(f"Failed to save trade store: {e}")

    def next_id(self) -> int:
        i = self._next_id
        self._next_id += 1
        return i

    def add_trade(self, trade: dict) -> dict:
        trade["id"] = self.next_id()
        if "opened_at" not in trade:
            trade["opened_at"] = datetime.now(timezone.utc).isoformat()
        if "status" not in trade:
            trade["status"] = "open"
        trade["balance_at_entry"] = round(self._running_balance, 2)
        self.trades.append(trade)
        self._save()
        return trade

    def close_trade(self, trade_id: int, exit_price: float, pnl_usd: float, exit_fee: float, status: str = "closed") -> Optional[dict]:
        for t in self.trades:
            if t["id"] == trade_id:
                t["exit_price"] = exit_price
                t["pnl_usd"] = pnl_usd
                t["pnl_pct"] = (pnl_usd / (t["entry_price"] * t["quantity"])) * 100 if t.get("quantity") and t.get("entry_price") else 0
                t["exit_fee_usd"] = exit_fee
                t["status"] = status
                t["closed_at"] = datetime.now(timezone.utc).isoformat()
                self._running_balance += pnl_usd
                t["balance_at_exit"] = round(self._running_balance, 2)
                self._save()
                return t
        return None

    def get_open_trades(self) -> list[dict]:
        return [t for t in self.trades if t.get("status") == "open"]

    def get_closed_trades(self) -> list[dict]:
        return [t for t in self.trades if t.get("status") in ("closed", "stopped_out")]

    def add_deposit(self, dep: dict) -> dict:
        dep["id"] = self.next_id()
        dep["timestamp"] = datetime.now(timezone.utc).isoformat()
        self.deposits.append(dep)
        self._running_balance += dep.get("amount_usd", 0)
        self._save()
        return dep

    def add_withdrawal(self, wd: dict) -> dict:
        wd["id"] = self.next_id()
        wd["timestamp"] = datetime.now(timezone.utc).isoformat()
        self.withdrawals.append(wd)
        self._running_balance -= wd.get("amount_usd", 0)
        self._save()
        return wd

    def total_deposits(self) -> float:
        return sum(d.get("amount_usd", 0) for d in self.deposits)

    def total_withdrawals(self) -> float:
        return sum(w.get("amount_usd", 0) for w in self.withdrawals)

    def total_pnl(self) -> dict:
        closed = self.get_closed_trades()
        total_pnl = sum(t.get("pnl_usd", 0) for t in closed)
        total_fees = sum(t.get("entry_fee_usd", 0) + t.get("exit_fee_usd", 0) for t in closed)
        return {
            "total_pnl_usd": round(total_pnl, 2),
            "total_fees_usd": round(total_fees, 2),
            "net_pnl_usd": round(total_pnl, 2),
            "total_trades": len(closed),
        }

    def win_rate(self) -> dict:
        closed = self.get_closed_trades()
        winners = [t for t in closed if t.get("pnl_usd", 0) > 0]
        total = len(closed)
        return {
            "total_trades": total,
            "winning_trades": len(winners),
            "losing_trades": total - len(winners),
            "win_rate": round(len(winners) / total * 100, 1) if total > 0 else 0.0,
        }

    def pnl_by_bot(self) -> dict:
        result = {}
        for t in self.get_closed_trades():
            bot = t.get("bot_type", "unknown")
            if bot not in result:
                result[bot] = {"pnl_usd": 0, "trades": 0}
            result[bot]["pnl_usd"] = round(result[bot]["pnl_usd"] + t.get("pnl_usd", 0), 2)
            result[bot]["trades"] += 1
        return result

    def pnl_by_date(self, days: int = 30) -> list[dict]:
        from collections import defaultdict
        daily = defaultdict(lambda: {"pnl_usd": 0, "trades": 0})
        for t in self.get_closed_trades():
            date = t.get("closed_at", "")[:10]
            if date:
                daily[date]["pnl_usd"] = round(daily[date]["pnl_usd"] + t.get("pnl_usd", 0), 2)
                daily[date]["trades"] += 1
        return [{"date": k, **v} for k, v in sorted(daily.items())[-days:]]

    def total_fees(self) -> float:
        total = 0.0
        for t in self.trades:
            total += t.get("entry_fee_usd", 0)
            total += t.get("exit_fee_usd", 0)
        return round(total, 5)

    def trades_with_running_balance(self) -> list[dict]:
        result = []
        for t in self.trades:
            entry = dict(t)
            entry["balance_at_entry"] = t.get("balance_at_entry", 0)
            entry["balance_at_exit"] = t.get("balance_at_exit", None)
            result.append(entry)
        return result

    def record_snapshot(self):
        self.snapshots.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "balance": round(self._running_balance, 2),
            "open_trades": len(self.get_open_trades()),
            "total_trades": len(self.trades),
        })
        if len(self.snapshots) % 20 == 0:
            self._save()

    def get_portfolio_chart(self, limit: int = 200) -> list[dict]:
        if not self.snapshots:
            return [{"timestamp": datetime.now(timezone.utc).isoformat(), "balance": round(self._running_balance, 2)}]
        return self.snapshots[-limit:]

    def get_ledger(self) -> list[dict]:
        ledger = []
        for d in self.deposits:
            ledger.append({
                "type": "deposit",
                "timestamp": d.get("timestamp", ""),
                "description": f"Deposit {d.get('asset', 'USDT')}",
                "asset": d.get("asset", "USDT"),
                "amount_usd": d.get("amount_usd", 0),
                "pnl_usd": None,
                "fee_usd": 0,
                "running_balance": None,
                "side": "credit",
                "symbol": None,
                "bot_type": None,
            })
        for w in self.withdrawals:
            ledger.append({
                "type": "withdrawal",
                "timestamp": w.get("timestamp", ""),
                "description": f"Withdrawal {w.get('asset', 'USDT')}",
                "asset": w.get("asset", "USDT"),
                "amount_usd": -w.get("amount_usd", 0),
                "pnl_usd": None,
                "fee_usd": 0,
                "running_balance": None,
                "side": "debit",
                "symbol": None,
                "bot_type": None,
            })
        for t in self.trades:
            entry_fee = t.get("entry_fee_usd", 0)
            ledger.append({
                "type": "trade_entry",
                "timestamp": t.get("opened_at", ""),
                "description": f"{t.get('side', 'buy').upper()} {t.get('symbol', '?')} @ ${t.get('entry_price', 0):.8g}",
                "asset": t.get("symbol", ""),
                "amount_usd": -(t.get("entry_price", 0) * t.get("quantity", 0)),
                "pnl_usd": None,
                "fee_usd": entry_fee,
                "running_balance": t.get("balance_at_entry"),
                "side": t.get("side", "buy"),
                "symbol": t.get("symbol"),
                "bot_type": t.get("bot_type"),
                "trade_id": t.get("id"),
                "status": t.get("status"),
                "quantity": t.get("quantity", 0),
                "price": t.get("entry_price", 0),
            })
            if t.get("status") in ("closed", "stopped_out"):
                exit_fee = t.get("exit_fee_usd", 0)
                pnl = t.get("pnl_usd", 0)
                ledger.append({
                    "type": "trade_exit",
                    "timestamp": t.get("closed_at", ""),
                    "description": f"CLOSE {t.get('symbol', '?')} @ ${t.get('exit_price', 0):.8g}",
                    "asset": t.get("symbol", ""),
                    "amount_usd": t.get("exit_price", 0) * t.get("quantity", 0),
                    "pnl_usd": pnl,
                    "fee_usd": exit_fee,
                    "running_balance": t.get("balance_at_exit"),
                    "side": "sell" if t.get("side") == "buy" else "buy",
                    "symbol": t.get("symbol"),
                    "bot_type": t.get("bot_type"),
                    "trade_id": t.get("id"),
                    "status": t.get("status"),
                    "quantity": t.get("quantity", 0),
                    "price": t.get("exit_price", 0),
                })
        ledger.sort(key=lambda x: x.get("timestamp") or "")
        running = 0.0
        for entry in ledger:
            if entry["type"] == "deposit":
                running += entry["amount_usd"]
                entry["running_balance"] = round(running, 5)
            elif entry["type"] == "withdrawal":
                running += entry["amount_usd"]
                entry["running_balance"] = round(running, 5)
            elif entry["type"] == "trade_exit" and entry["pnl_usd"] is not None:
                running += entry["pnl_usd"]
                entry["running_balance"] = round(running, 5)
            else:
                entry["running_balance"] = round(running, 5)
        return ledger

    def full_accounting(self) -> dict:
        pnl = self.total_pnl()
        deps = self.total_deposits()
        wds = self.total_withdrawals()
        open_trades = self.get_open_trades()
        closed_trades = self.get_closed_trades()
        return {
            "summary": {
                "total_deposits_usd": round(deps, 5),
                "total_withdrawals_usd": round(wds, 5),
                "net_deposits_usd": round(deps - wds, 5),
                "total_pnl_usd": pnl["total_pnl_usd"],
                "total_fees_usd": pnl["total_fees_usd"],
                "net_pnl_usd": pnl["net_pnl_usd"],
                "total_trades": len(self.trades),
                "open_trades": len(open_trades),
                "closed_trades": len(closed_trades),
                "account_value_usd": round((deps - wds) + pnl["net_pnl_usd"], 5),
                "total_fees_all_time": self.total_fees(),
                "running_balance": round(self._running_balance, 5),
            },
            "win_rate": self.win_rate(),
            "pnl_by_bot": self.pnl_by_bot(),
            "pnl_by_date": self.pnl_by_date(),
        }


trade_store = TradeStore()
