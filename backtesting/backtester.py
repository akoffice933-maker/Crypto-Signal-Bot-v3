"""
Event-driven backtester for bot_final.

Plugs directly into the same strategy functions used in production:
    engine/liquidity_map.py   → build_liquidity_map()
    strategies/sweep_reversal → check_sweep_reversal() logic (sync version)
    engine/confidence.py      → compute_confidence()

Look-ahead prevention:
    Levels rebuilt from candles[:idx] every N bars.
    Signal uses only candles visible at bar idx.
    confirmation_delay=0 (sweep detected on the closed rejection candle — no future data needed).
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from config.settings import settings
from engine.indicators import candle_parts, volume_ma
from engine.liquidity_map import (
    LiquidityLevel,
    build_liquidity_map,
    select_target_level,
    detect_levels,
)
from engine.confidence import compute_confidence

logger = logging.getLogger(__name__)


@dataclass
class BTConfig:
    initial_balance:   float = 10_000.0
    fee_pct:           float = 0.0004    # 0.04% Binance Futures taker
    slippage_pct:      float = 0.0008    # 0.08% conservative slippage
    max_position_pct:  float = 0.10      # 10% of balance per trade
    min_rr:            float = 2.0
    confidence_min:    int   = 65
    max_candles_hold:  int   = 20        # ~5h on 15m → timeout
    level_rebuild_every: int = 15        # rebuild levels every N bars


@dataclass
class BTTrade:
    entry_date:   str
    exit_date:    str
    direction:    str
    entry_price:  float
    exit_price:   float
    pnl_pct:      float
    pnl_net:      float
    rr_achieved:  float
    confidence:   int
    exit_reason:  str   # tp | sl | timeout


class Backtester:
    """
    Single-timeframe backtester (uses 15m df as primary).
    Levels are built from the same 15m df (simulating 1D/4H lookback
    by using a longer lookback window on the same data).
    For production validation, pass real 1D/4H frames separately.
    """

    def __init__(self, cfg: BTConfig = None):
        self.cfg    = cfg or BTConfig()
        self.trades: List[BTTrade] = []
        self.equity_curve: List[Dict] = []
        self._pending: Dict[int, dict] = {}   # {confirm_idx: signal_dict}

    # ── Public ────────────────────────────────────────────────

    def run(self, df: pd.DataFrame) -> Dict:
        """
        df: OHLCV DataFrame with open_time column.
        Returns metrics dict.
        """
        cfg = self.cfg
        equity = cfg.initial_balance
        in_pos = False
        trade  = None

        self.trades       = []
        self.equity_curve = []
        self._pending     = {}
        level_cache: List[LiquidityLevel] = []
        level_cache_at    = -999

        for i in range(100, len(df) - 5):
            row   = df.iloc[i]
            price = float(row["close"])

            # ── Rebuild levels (no look-ahead: only df[:i+1]) ──
            if i - level_cache_at >= cfg.level_rebuild_every:
                window = df.iloc[max(0, i - 400): i + 1]
                level_cache = detect_levels(window, "15m", price,
                                            min_touches=3)
                level_cache_at = i

            # ── Check pending signals ──────────────────────────
            if i in self._pending and not in_pos:
                sig = self._pending.pop(i)
                if self._passes_filters(sig, df, i):
                    trade  = self._enter(sig, price, equity, i)
                    in_pos = bool(trade)

            # ── Generate signal ────────────────────────────────
            if not in_pos:
                sig = self._generate(df, i, price, level_cache)
                if sig:
                    delay = sig.get("confirmation_delay", 0)
                    ci    = i + delay
                    if delay > 0 and ci < len(df) - 5:
                        self._pending[ci] = sig
                    elif delay == 0 and self._passes_filters(sig, df, i):
                        trade  = self._enter(sig, price, equity, i)
                        in_pos = bool(trade)

            # ── Manage position ────────────────────────────────
            elif in_pos and trade:
                result = self._manage(trade, df, i, row)
                if result:
                    equity += result["pnl_net"]
                    self.trades.append(BTTrade(
                        entry_date  = str(df.iloc[trade["entry_idx"]]["open_time"]),
                        exit_date   = str(row["open_time"]),
                        direction   = trade["direction"],
                        entry_price = trade["entry_price"],
                        exit_price  = result["exit_price"],
                        pnl_pct     = result["pnl_pct"],
                        pnl_net     = result["pnl_net"],
                        rr_achieved = result["rr"],
                        confidence  = trade["confidence"],
                        exit_reason = result["reason"],
                    ))
                    in_pos = False
                    trade  = None

            self.equity_curve.append({
                "date":       str(row["open_time"]),
                "equity":     round(equity, 2),
                "in_pos":     in_pos,
            })

        return self._metrics()

    # ── Signal generation ─────────────────────────────────────

    def _generate(
        self,
        df: pd.DataFrame,
        idx: int,
        price: float,
        levels: List[LiquidityLevel],
    ) -> Optional[dict]:
        """
        Sweep + rejection detection using only df[:idx+1].
        Mirrors strategies/sweep_reversal.py logic exactly.
        """
        if idx < 2 or not levels:
            return None

        sweep_c = df.iloc[idx - 1]
        rej_c   = df.iloc[idx]
        vol_ma20 = float(volume_ma(df.iloc[:idx + 1], 20).iloc[-1])
        parts   = candle_parts(rej_c)

        for level in levels:
            lp   = level.price
            tol  = settings.sweep_tolerance_pct

            # LONG: sweep equal_lows
            if level.pool_type == "equal_lows":
                swept    = float(sweep_c["low"])   < lp * (1 - tol)
                returned = float(sweep_c["close"])  > lp
                if not (swept and returned):
                    continue
                if not self._is_rejection(parts, "LONG"):
                    continue
                direction = "LONG"
                body = abs(float(sweep_c["close"]) - float(sweep_c["open"]))
                entry  = float(rej_c["close"])
                sl     = float(sweep_c["low"]) * 0.999
                target = select_target_level(levels, price, "LONG")
                tp     = target.price if target else entry + (entry - sl) * self.cfg.min_rr

            # SHORT: sweep equal_highs
            elif level.pool_type == "equal_highs":
                swept    = float(sweep_c["high"])  > lp * (1 + tol)
                returned = float(sweep_c["close"]) < lp
                if not (swept and returned):
                    continue
                if not self._is_rejection(parts, "SHORT"):
                    continue
                direction = "SHORT"
                body = abs(float(sweep_c["close"]) - float(sweep_c["open"]))
                entry  = float(rej_c["close"])
                sl     = float(sweep_c["high"]) * 1.001
                target = select_target_level(levels, price, "SHORT")
                tp     = target.price if target else entry - (sl - entry) * self.cfg.min_rr

            else:
                continue

            rr = abs(tp - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0
            if rr < self.cfg.min_rr:
                continue

            vol_spike = (float(sweep_c["volume"]) >= vol_ma20 * settings.volume_spike_multiplier or
                         float(rej_c["volume"])   >= vol_ma20 * settings.volume_spike_multiplier)

            conf = compute_confidence(
                strategy="sweep_reversal",
                direction=direction,
                session="london",        # assume active session in backtest
                market_state="ranging",  # neutral assumption
                adx_value=20.0,
                volume_spike=vol_spike,
                squeeze_active=False,
                cvd_divergence=None,
                funding_rate=0.0,
                liquidation_cascade=False,
            )

            return {
                "direction":          direction,
                "entry":              entry,
                "stop_loss":          sl,
                "take_profit":        tp,
                "rr":                 round(rr, 2),
                "confidence":         conf.score,
                "volume_spike":       vol_spike,
                "confirmation_delay": 0,
            }

        return None

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _is_rejection(parts: dict, direction: str) -> bool:
        body = parts["body"]
        rng  = parts["range"]
        if rng == 0:
            return False
        wick = parts["lower_wick"] if direction == "LONG" else parts["upper_wick"]
        if body == 0:
            return True   # doji
        return (wick >= settings.rejection_wick_ratio * body and
                body <= settings.rejection_body_range_max * rng)

    def _passes_filters(self, sig: dict, df: pd.DataFrame, idx: int) -> bool:
        if sig["confidence"] < self.cfg.confidence_min:
            return False
        if sig["rr"] < self.cfg.min_rr:
            return False
        # Minimum recent range (not completely flat market)
        rng = (df["high"].iloc[idx - 10:idx].max() -
               df["low"].iloc[idx - 10:idx].min())
        if rng / sig["entry"] < 0.003:
            return False
        return True

    def _enter(self, sig: dict, price: float, equity: float, idx: int) -> Optional[dict]:
        if sig["direction"] == "LONG":
            ep = price * (1 + self.cfg.slippage_pct)
        else:
            ep = price * (1 - self.cfg.slippage_pct)

        pos_val = equity * self.cfg.max_position_pct
        fee     = pos_val * self.cfg.fee_pct
        return {
            "direction":   sig["direction"],
            "entry_price": ep,
            "stop_loss":   sig["stop_loss"],
            "take_profit": sig["take_profit"],
            "pos_val":     pos_val,
            "fee":         fee,
            "confidence":  sig["confidence"],
            "entry_idx":   idx,
        }

    def _manage(self, trade: dict, df: pd.DataFrame,
                idx: int, row: pd.Series) -> Optional[dict]:
        # Timeout
        if idx - trade["entry_idx"] >= self.cfg.max_candles_hold:
            ep, reason = float(row["close"]), "timeout"
        elif trade["direction"] == "LONG":
            if float(row["low"])  <= trade["stop_loss"]:
                ep, reason = trade["stop_loss"],  "sl"
            elif float(row["high"]) >= trade["take_profit"]:
                ep, reason = trade["take_profit"], "tp"
            else:
                return None
        else:
            if float(row["high"]) >= trade["stop_loss"]:
                ep, reason = trade["stop_loss"],  "sl"
            elif float(row["low"]) <= trade["take_profit"]:
                ep, reason = trade["take_profit"], "tp"
            else:
                return None

        if trade["direction"] == "LONG":
            pnl_pct = (ep - trade["entry_price"]) / trade["entry_price"]
        else:
            pnl_pct = (trade["entry_price"] - ep) / trade["entry_price"]

        fee_exit = trade["pos_val"] * self.cfg.fee_pct
        pnl_net  = trade["pos_val"] * pnl_pct - trade["fee"] - fee_exit
        rr       = abs(ep - trade["entry_price"]) / abs(trade["entry_price"] - trade["stop_loss"])
        return {"exit_price": ep, "pnl_pct": pnl_pct * 100,
                "pnl_net": pnl_net, "rr": rr, "reason": reason}

    def _metrics(self) -> Dict:
        if not self.trades:
            return {"error": "No trades", "total_trades": 0}
        df  = pd.DataFrame([asdict(t) for t in self.trades])
        win = df[df["pnl_pct"] > 0]
        los = df[df["pnl_pct"] <= 0]
        eq  = [e["equity"] for e in self.equity_curve]
        pk  = np.maximum.accumulate(eq)
        dd  = (pk - eq) / pk * 100
        return {
            "initial_balance":   self.cfg.initial_balance,
            "final_balance":     self.equity_curve[-1]["equity"],
            "total_return_pct":  round((self.equity_curve[-1]["equity"] - self.cfg.initial_balance)
                                       / self.cfg.initial_balance * 100, 2),
            "profit_factor":     round(abs(win["pnl_net"].sum() / los["pnl_net"].sum()), 2)
                                       if len(los) > 0 else float("inf"),
            "winrate_pct":       round(len(win) / len(df) * 100, 1),
            "max_drawdown_pct":  round(float(np.max(dd)), 2),
            "total_trades":      len(df),
            "winning_trades":    len(win),
            "losing_trades":     len(los),
            "avg_rr":            round(float(df["rr_achieved"].mean()), 2),
            "exits":             df["exit_reason"].value_counts().to_dict(),
            "trades":            [asdict(t) for t in self.trades],
            "equity_curve":      self.equity_curve,
        }
