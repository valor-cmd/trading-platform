import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

BACKTESTED_OPTIMAL = {
    "scalper": {
        "sl_atr_multiplier": 1.2,
        "tp_rr_ratio": 2.5,
        "min_confidence": 0.12,
        "min_confirmations": 2,
        "risk_per_trade_pct": 1.5,
        "preferred_timeframe": "1h",
        "backtest_return_pct": 4.44,
        "backtest_win_rate": 52.2,
        "backtest_sharpe": 3.07,
    },
    "mean_reversion": {
        "sl_atr_multiplier": 1.0,
        "tp_rr_ratio": 1.5,
        "min_confidence": 0.08,
        "min_confirmations": 1,
        "risk_per_trade_pct": 1.5,
        "preferred_timeframe": "1h",
        "backtest_return_pct": 9.18,
        "backtest_win_rate": 51.5,
        "backtest_sharpe": 3.78,
    },
    "grid": {
        "sl_atr_multiplier": 1.0,
        "tp_rr_ratio": 1.5,
        "min_confidence": 0.10,
        "min_confirmations": 2,
        "risk_per_trade_pct": 1.0,
        "preferred_timeframe": "1h",
        "backtest_return_pct": 8.45,
        "backtest_win_rate": 51.5,
        "backtest_sharpe": 3.96,
    },
    "swing": {
        "sl_atr_multiplier": 2.0,
        "tp_rr_ratio": 2.0,
        "min_confidence": 0.12,
        "min_confirmations": 2,
        "risk_per_trade_pct": 2.5,
        "preferred_timeframe": "1h",
        "backtest_return_pct": 1.76,
        "backtest_win_rate": 45.5,
        "backtest_sharpe": 1.73,
    },
    "momentum": {
        "sl_atr_multiplier": 1.2,
        "tp_rr_ratio": 3.0,
        "min_confidence": 0.10,
        "min_confirmations": 2,
        "risk_per_trade_pct": 2.5,
        "preferred_timeframe": "1h",
        "backtest_return_pct": 2.37,
        "backtest_win_rate": 40.7,
        "backtest_sharpe": 0.94,
    },
    "long_term": {
        "sl_atr_multiplier": 2.5,
        "tp_rr_ratio": 4.0,
        "min_confidence": 0.08,
        "min_confirmations": 1,
        "risk_per_trade_pct": 1.0,
        "preferred_timeframe": "1d",
        "backtest_return_pct": 2.66,
        "backtest_win_rate": 40.0,
        "backtest_sharpe": 3.1,
    },
    "dca": {
        "sl_atr_multiplier": 2.0,
        "tp_rr_ratio": 3.0,
        "min_confidence": 0.08,
        "min_confirmations": 1,
        "risk_per_trade_pct": 1.0,
        "preferred_timeframe": "1d",
        "backtest_return_pct": 2.66,
        "backtest_win_rate": 40.0,
        "backtest_sharpe": 3.1,
    },
}

COINSKID_ZONE_MAP = {
    "extreme_fear": {"bias": "strong_buy", "boost": 0.15, "description": "Extreme fear - contrarian buy"},
    "fearful": {"bias": "lean_buy", "boost": 0.08, "description": "Fear zone - accumulation"},
    "worry": {"bias": "lean_buy", "boost": 0.04, "description": "Worry zone - cautious buy"},
    "neutral": {"bias": "neutral", "boost": 0.0, "description": "Neutral - no directional bias"},
    "optimism": {"bias": "lean_sell", "boost": -0.03, "description": "Optimism - reduce position size"},
    "greed": {"bias": "lean_sell", "boost": -0.08, "description": "Greed zone - take profits"},
    "extreme_greed": {"bias": "strong_sell", "boost": -0.15, "description": "Extreme greed - contrarian sell"},
}

GRID_STRATEGY_RULES = {
    "min_adx_for_grid": 20,
    "grid_levels": 10,
    "grid_spacing_type": "arithmetic",
    "use_bb_as_bounds": True,
    "trailing_up_enabled": True,
    "trailing_down_enabled": True,
    "pause_on_trend": True,
    "min_range_width_pct": 2.0,
    "max_range_width_pct": 15.0,
    "profit_per_grid_pct": 0.3,
}

QUANTIFIED_STRATEGIES_RULES = {
    "trend_following": {
        "entry_rule": "Buy when price > 200-day MA AND 50-day MA crosses above 200-day MA",
        "exit_rule": "Sell when price < 200-day MA OR 50-day MA crosses below 200-day MA",
        "backtest_win_rate": 42,
        "avg_winner_pct": 21,
        "avg_loser_pct": 4,
        "annual_return_pct": 87,
        "best_for": ["long_term", "swing", "momentum"],
    },
    "mean_reversion_bb": {
        "entry_rule": "Buy when price touches lower BB AND RSI < 30 AND z-score < -2",
        "exit_rule": "Sell when price reaches BB midline OR RSI > 50",
        "backtest_win_rate": 55,
        "avg_winner_pct": 5,
        "avg_loser_pct": 3,
        "best_for": ["mean_reversion", "grid", "scalper"],
    },
}


@dataclass
class StrategyAdvice:
    bot_type: str
    symbol: str
    confidence_boost: float = 0.0
    direction_bias: str = "neutral"
    coinskid_zone: str = "unknown"
    grid_bounds: Optional[dict] = None
    strategy_notes: list[str] = field(default_factory=list)
    should_trade: bool = True
    optimal_params: dict = field(default_factory=dict)


class StrategyIntelService:
    def __init__(self):
        self._coinskid_zones: dict[str, dict] = {}
        self._coinskid_ckr: dict = {}
        self._coinskid_bottom_checklist: dict = {}
        self._last_coinskid_update: float = 0
        self._coinskid_ttl: int = 600

    def update_coinskid_zones(self, data: dict):
        if isinstance(data, dict):
            self._coinskid_zones = data
            self._last_coinskid_update = time.time()

    def update_coinskid_ckr(self, data: dict):
        if isinstance(data, dict):
            self._coinskid_ckr = data

    def update_coinskid_bottom_checklist(self, data: dict):
        if isinstance(data, dict):
            self._coinskid_bottom_checklist = data

    def _get_coin_zone(self, symbol: str) -> str:
        base = symbol.split("/")[0].upper() if "/" in symbol else symbol.upper()
        name_map = {
            "BTC": "bitcoin", "ETH": "ethereum", "BNB": "bnb", "XRP": "xrp",
            "SOL": "solana", "DOGE": "dogecoin", "ADA": "cardano", "AVAX": "avalanche",
            "DOT": "polkadot", "LINK": "chainlink", "SHIB": "shiba inu", "LTC": "litecoin",
            "SUI": "sui", "TON": "toncoin", "TRX": "tron", "XLM": "stellar",
            "MATIC": "polygon", "HBAR": "hedera", "UNI": "uniswap", "NEAR": "near",
        }
        coin_name = name_map.get(base, base.lower())
        for key, val in self._coinskid_zones.items():
            if isinstance(val, str) and coin_name.lower() in key.lower():
                return val.lower().replace(" zone", "").replace(" ", "_")
        return "neutral"

    def get_advice(self, bot_type: str, symbol: str, signal_data: dict = None) -> StrategyAdvice:
        advice = StrategyAdvice(bot_type=bot_type, symbol=symbol)

        optimal = BACKTESTED_OPTIMAL.get(bot_type, {})
        advice.optimal_params = dict(optimal)

        zone = self._get_coin_zone(symbol)
        advice.coinskid_zone = zone
        zone_info = COINSKID_ZONE_MAP.get(zone, COINSKID_ZONE_MAP["neutral"])
        advice.confidence_boost = zone_info["boost"]
        advice.direction_bias = zone_info["bias"]
        advice.strategy_notes.append(f"Coinskid: {zone_info['description']}")

        if self._coinskid_ckr:
            ckr_values = self._coinskid_ckr.get("extracted_values", [])
            if ckr_values:
                ckr_val = ckr_values[0]
                if ckr_val < 5:
                    advice.confidence_boost += 0.10
                    advice.strategy_notes.append(f"CKR={ckr_val:.0f}: macro bottom zone - strong buy signal")
                elif ckr_val > 95:
                    advice.confidence_boost -= 0.10
                    advice.strategy_notes.append(f"CKR={ckr_val:.0f}: macro top zone - strong sell signal")
            buy_mentions = self._coinskid_ckr.get("buy_mentions", 0)
            sell_mentions = self._coinskid_ckr.get("sell_mentions", 0)
            if buy_mentions + sell_mentions > 10:
                ratio = buy_mentions / (buy_mentions + sell_mentions)
                if ratio > 0.7:
                    advice.confidence_boost += 0.05
                elif ratio < 0.3:
                    advice.confidence_boost -= 0.05

        bottom_data = self._coinskid_bottom_checklist
        if bottom_data:
            triggered = 0
            total_checks = 13
            raw = str(bottom_data)
            triggered = raw.lower().count("triggered")
            if triggered >= 5:
                advice.confidence_boost += 0.08
                advice.strategy_notes.append(f"Bottom checklist: {triggered}/{total_checks} triggered - accumulation phase")
            elif triggered >= 3:
                advice.confidence_boost += 0.04
                advice.strategy_notes.append(f"Bottom checklist: {triggered}/{total_checks} triggered")

        if bot_type == "grid" and signal_data:
            bb_upper = signal_data.get("bb_upper", 0)
            bb_lower = signal_data.get("bb_lower", 0)
            price = signal_data.get("price", 0)
            atr = signal_data.get("atr", 0)

            if bb_upper > 0 and bb_lower > 0 and price > 0:
                range_pct = (bb_upper - bb_lower) / price * 100
                if GRID_STRATEGY_RULES["min_range_width_pct"] <= range_pct <= GRID_STRATEGY_RULES["max_range_width_pct"]:
                    grid_levels = GRID_STRATEGY_RULES["grid_levels"]
                    step = (bb_upper - bb_lower) / grid_levels
                    advice.grid_bounds = {
                        "upper": round(bb_upper, 8),
                        "lower": round(bb_lower, 8),
                        "grid_levels": grid_levels,
                        "grid_step": round(step, 8),
                        "range_pct": round(range_pct, 2),
                        "spacing_type": GRID_STRATEGY_RULES["grid_spacing_type"],
                        "est_profit_per_grid_pct": GRID_STRATEGY_RULES["profit_per_grid_pct"],
                    }
                    advice.strategy_notes.append(
                        f"Grid: {grid_levels} levels, range={range_pct:.1f}%, "
                        f"step=${step:.4f}"
                    )
                else:
                    if range_pct < GRID_STRATEGY_RULES["min_range_width_pct"]:
                        advice.should_trade = False
                        advice.strategy_notes.append(f"Grid: range too narrow ({range_pct:.1f}%) - skip")
                    elif range_pct > GRID_STRATEGY_RULES["max_range_width_pct"]:
                        advice.strategy_notes.append(f"Grid: range wide ({range_pct:.1f}%) - increase caution")

        if zone_info["bias"] == "strong_sell" and bot_type in ("scalper", "momentum", "swing"):
            if signal_data and signal_data.get("side") == "buy":
                advice.confidence_boost -= 0.10
                advice.strategy_notes.append("Extreme greed + buy signal = reduced confidence (contrarian)")

        if zone_info["bias"] == "strong_buy" and bot_type == "long_term":
            advice.confidence_boost += 0.10
            advice.strategy_notes.append("Extreme fear + long-term = max accumulation boost")

        advice.confidence_boost = max(-0.25, min(0.25, advice.confidence_boost))

        return advice

    def get_all_optimal_params(self) -> dict:
        return {
            "backtested_params": BACKTESTED_OPTIMAL,
            "grid_rules": GRID_STRATEGY_RULES,
            "quantified_strategies": QUANTIFIED_STRATEGIES_RULES,
            "coinskid_zones": COINSKID_ZONE_MAP,
            "coinskid_data": {
                "zones": self._coinskid_zones,
                "ckr": self._coinskid_ckr,
                "bottom_checklist": self._coinskid_bottom_checklist,
                "last_update": self._last_coinskid_update,
            },
        }

    def get_bot_report(self) -> list[dict]:
        report = []
        for bot_type, params in BACKTESTED_OPTIMAL.items():
            report.append({
                "bot_type": bot_type,
                "optimal_timeframe": params["preferred_timeframe"],
                "backtest_return_pct": params["backtest_return_pct"],
                "backtest_win_rate": params["backtest_win_rate"],
                "backtest_sharpe": params["backtest_sharpe"],
                "sl_atr_multiplier": params["sl_atr_multiplier"],
                "tp_rr_ratio": params["tp_rr_ratio"],
                "risk_per_trade_pct": params["risk_per_trade_pct"],
            })
        report.sort(key=lambda x: x["backtest_return_pct"], reverse=True)
        return report


strategy_intel = StrategyIntelService()
