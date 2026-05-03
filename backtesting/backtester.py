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
from engine.indicators import adx as calc_adx
from engine.indicators import atr_pct as calc_atr_pct
from engine.indicators import trend_direction as calc_trend_direction
from engine.liquidity_map import (
    LiquidityLevel,
    build_liquidity_map,
    detect_levels,
)
from engine.market_state import get_operating_mode
from engine.squeeze import is_squeeze
from strategies.breakout import check_breakout
from strategies.sweep_reversal import check_sweep_reversal

logger = logging.getLogger(__name__)


@dataclass
class BTConfig:
    initial_balance:   float = 10_000.0
    fee_pct:           float = 0.0004    # 0.04% Binance Futures taker
    slippage_pct:      float = 0.0008    # 0.08% conservative slippage
    max_position_pct:  float = 0.10      # 10% of balance per trade
    min_rr:            Optional[float] = None
    confidence_min:    Optional[int]   = None
    max_candles_hold:  int   = 20        # ~5h on 15m → timeout
    level_rebuild_every: int = 15        # rebuild levels every N bars
    execution_basis:   Optional[str] = None
    limit_order_expiry_candles: int = 2


@dataclass
class BTTrade:
    entry_date:   str
    exit_date:    str
    strategy:     str
    direction:    str
    entry_price:  float
    exit_price:   float
    pnl_pct:      float
    pnl_net:      float
    rr_achieved:  float
    confidence:   int
    exit_reason:  str   # tp | sl | timeout | tp1_tp | tp1_sl | tp1_timeout


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
        self._pending_entries: List[dict] = []

    # ── Public ────────────────────────────────────────────────

    def run(self, data) -> Dict:
        """
        data: OHLCV DataFrame with open_time column or
              {"15m": df_15m, "4h": df_4h, "1d": df_1d}
        Returns metrics dict.
        """
        cfg = self.cfg
        equity = cfg.initial_balance
        in_pos = False
        trade  = None

        if isinstance(data, dict):
            df = data["15m"]
            df_4h_full = data.get("4h")
            df_1d_full = data.get("1d")
        else:
            df = data
            df_4h_full = None
            df_1d_full = None

        self.trades       = []
        self.equity_curve = []
        self._pending     = {}
        self._pending_entries = []
        level_cache: List[LiquidityLevel] = []
        level_cache_at    = -999
        squeeze_active = False

        for i in range(100, len(df) - 5):
            row   = df.iloc[i]
            price = float(row["close"])
            ts = pd.Timestamp(row["open_time"])
            df_4h_window = self._slice_tf(df_4h_full, ts)
            df_1d_window = self._slice_tf(df_1d_full, ts)

            # ── Rebuild levels (no look-ahead: only df[:i+1]) ──
            if i - level_cache_at >= cfg.level_rebuild_every:
                if df_4h_window is not None and df_1d_window is not None:
                    level_cache = build_liquidity_map(df_1d_window, df_4h_window, price)
                    squeeze_active = is_squeeze(df_4h_window)
                else:
                    window = df.iloc[max(0, i - 400): i + 1]
                    level_cache = detect_levels(window, "15m", price, min_touches=3)
                    squeeze_active = False
                level_cache_at = i

            # ── Check pending signals ──────────────────────────
            if i in self._pending and not in_pos:
                sig = self._pending.pop(i)
                if self._passes_filters(sig, df, i):
                    trade = self._maybe_enter_or_queue(sig, row, equity, i)
                    in_pos = bool(trade)

            # ── Generate signal ────────────────────────────────
            if not in_pos:
                trade = self._fill_pending_entry(row, equity, i)
                in_pos = bool(trade)

            if not in_pos:
                sig = self._generate(df, i, price, level_cache, squeeze_active=squeeze_active)
                if sig:
                    delay = sig.get("confirmation_delay", 0)
                    ci    = i + delay
                    if delay > 0 and ci < len(df) - 5:
                        self._pending[ci] = sig
                    elif delay == 0 and self._passes_filters(sig, df, i):
                        trade = self._maybe_enter_or_queue(sig, row, equity, i)
                        in_pos = bool(trade)

            # ── Manage position ────────────────────────────────
            elif in_pos and trade:
                result = self._manage(trade, df, i, row)
                if result:
                    equity += result["pnl_net"]
                    self.trades.append(BTTrade(
                        entry_date  = str(df.iloc[trade["entry_idx"]]["open_time"]),
                        exit_date   = str(row["open_time"]),
                        strategy    = trade["strategy"],
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
        *,
        squeeze_active: bool,
    ) -> Optional[dict]:
        """
        Sweep + rejection detection using only df[:idx+1].
        Reuses the production strategy with mode/session context.
        """
        if idx < 2 or not levels:
            return None

        window = df.iloc[:idx + 1]
        ts = pd.Timestamp(df.iloc[idx]["open_time"])
        if ts.weekday() >= 5:
            return None

        session = settings.get_session(ts.hour)
        if session is None:
            return None

        adx_value = float(calc_adx(window).iloc[-1])
        atr_pct = float(calc_atr_pct(window, period=14, lookback=20))
        trend_direction = calc_trend_direction(window, period=14)
        operating_mode = get_operating_mode(atr_pct)

        if operating_mode == "blocked":
            return None
        if operating_mode == "quiet" and session not in settings.quiet_allowed_sessions:
            return None

        if settings.adx_dead_zone_min <= adx_value <= settings.adx_dead_zone_max:
            return None

        market_state = (
            "trending" if adx_value > settings.adx_trending_threshold else "ranging"
        )
        min_rr = (
            self.cfg.min_rr
            if self.cfg.min_rr is not None
            else (
                settings.quiet_min_rr
                if operating_mode == "quiet"
                else settings.normal_min_rr
            )
        )
        confidence_threshold = (
            self.cfg.confidence_min
            if self.cfg.confidence_min is not None
            else (
                settings.quiet_confidence_threshold
                if operating_mode == "quiet"
                else settings.normal_confidence_threshold
            )
        )
        volume_spike_multiplier = (
            settings.quiet_volume_spike_multiplier
            if operating_mode == "quiet"
            else settings.normal_volume_spike_multiplier
        )

        sig = check_sweep_reversal(
            df_15m=window,
            levels=levels,
            squeeze_active=False,
            cvd_divergence=None,
            funding_rate=0.0,
            liquidation_cascade=False,
            market_state=market_state,
            adx_value=adx_value,
            trend_direction=trend_direction,
            session=session,
            atr_pct=atr_pct,
            operating_mode=operating_mode,
            min_rr=min_rr,
            volume_spike_multiplier=volume_spike_multiplier,
        )
        if sig is None:
            if operating_mode == "normal" and squeeze_active:
                bo_sig = check_breakout(
                    df_15m=window,
                    squeeze_active=squeeze_active,
                    session=session,
                    cvd_divergence=None,
                    funding_rate=0.0,
                    liquidation_cascade=False,
                    adx_value=adx_value,
                    atr_pct=atr_pct,
                    operating_mode=operating_mode,
                    min_rr=min_rr,
                    volume_spike_multiplier=volume_spike_multiplier,
                )
                if bo_sig is None:
                    return None
                return {
                    "strategy": "breakout",
                    "direction": bo_sig.direction,
                    "entry_market": bo_sig.entry_market,
                    "entry_limit": None,
                    "stop_loss": bo_sig.stop_loss,
                    "take_profit": bo_sig.take_profit,
                    "tp1_price": getattr(bo_sig, "tp1_price", None),
                    "tp1_size_pct": getattr(bo_sig, "tp1_size_pct", None),
                    "final_tp_size_pct": getattr(bo_sig, "final_tp_size_pct", 1.0),
                    "execution_basis": getattr(bo_sig, "execution_basis", None) or "market",
                    "rr": bo_sig.rr_ratio,
                    "confidence": bo_sig.confidence.score,
                    "confidence_threshold": confidence_threshold,
                    "confirmation_delay": 0,
                }
            return None

        return {
            "strategy": "sweep_reversal",
            "direction": sig.direction,
            "entry_market": sig.entry_market,
            "entry_limit": sig.entry_limit,
            "stop_loss": sig.stop_loss,
            "take_profit": sig.take_profit,
            "tp1_price": getattr(sig, "tp1_price", None),
            "tp1_size_pct": getattr(sig, "tp1_size_pct", None),
            "final_tp_size_pct": getattr(sig, "final_tp_size_pct", 1.0),
            "execution_basis": getattr(sig, "execution_basis", None) or self.cfg.execution_basis or settings.execution_basis,
            "rr": sig.rr_ratio,
            "confidence": sig.confidence.score,
            "confidence_threshold": confidence_threshold,
            "confirmation_delay": 0,
        }

    def _passes_filters(self, sig: dict, df: pd.DataFrame, idx: int) -> bool:
        threshold = sig.get(
            "confidence_threshold",
            self.cfg.confidence_min if self.cfg.confidence_min is not None else settings.normal_confidence_threshold,
        )
        min_rr = self.cfg.min_rr if self.cfg.min_rr is not None else settings.normal_min_rr
        if sig["confidence"] < threshold:
            return False
        if sig["rr"] < min_rr:
            return False
        # Minimum recent range (not completely flat market)
        rng = (df["high"].iloc[idx - 10:idx].max() -
               df["low"].iloc[idx - 10:idx].min())
        entry_ref = sig.get("entry_limit") or sig.get("entry_market")
        if rng / entry_ref < 0.003:
            return False
        return True

    def _build_trade(
        self,
        sig: dict,
        entry_price: float,
        equity: float,
        idx: int,
        *,
        limit_fill: bool,
    ) -> dict:
        pos_val = equity * self.cfg.max_position_pct
        fee_multiplier = 0.5 if limit_fill else 1.0
        fee = pos_val * self.cfg.fee_pct * fee_multiplier
        return {
            "strategy":    sig.get("strategy", "sweep_reversal"),
            "direction":   sig["direction"],
            "entry_price": entry_price,
            "stop_loss":   sig["stop_loss"],
            "take_profit": sig["take_profit"],
            "tp1_price": sig.get("tp1_price"),
            "tp1_hit": False,
            "tp1_size_pct": sig.get("tp1_size_pct"),
            "final_tp_size_pct": sig.get("final_tp_size_pct", 1.0),
            "realized_pnl_net": 0.0,
            "realized_pnl_pct": 0.0,
            "realized_rr": 0.0,
            "pos_val":     pos_val,
            "fee":         fee,
            "confidence":  sig["confidence"],
            "entry_idx":   idx,
        }

    def _slice_tf(self, df: Optional[pd.DataFrame], ts: pd.Timestamp) -> Optional[pd.DataFrame]:
        if df is None:
            return None
        ts = pd.Timestamp(ts)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        open_times = pd.to_datetime(df["open_time"], utc=True)
        sliced = df[open_times <= ts]
        return sliced.reset_index(drop=True)

    def _enter_market(self, sig: dict, price: float, equity: float, idx: int) -> dict:
        if sig["direction"] == "LONG":
            ep = price * (1 + self.cfg.slippage_pct)
        else:
            ep = price * (1 - self.cfg.slippage_pct)
        return self._build_trade(sig, ep, equity, idx, limit_fill=False)

    def _queue_limit_entry(self, sig: dict, idx: int) -> None:
        entry_limit = sig.get("entry_limit")
        if entry_limit is None:
            return
        self._pending_entries.append({
            "signal": sig,
            "placed_idx": idx,
            "expires_idx": idx + max(1, self.cfg.limit_order_expiry_candles),
        })

    def _maybe_enter_or_queue(self, sig: dict, row: pd.Series, equity: float, idx: int) -> Optional[dict]:
        basis = sig.get("execution_basis") or self.cfg.execution_basis or settings.execution_basis
        if basis == "limit" and sig.get("entry_limit") is not None:
            self._queue_limit_entry(sig, idx)
            return None
        return self._enter_market(sig, float(row["close"]), equity, idx)

    def _fill_pending_entry(self, row: pd.Series, equity: float, idx: int) -> Optional[dict]:
        if not self._pending_entries:
            return None

        remaining: List[dict] = []
        for pending_idx, pending in enumerate(self._pending_entries):
            if idx <= pending["placed_idx"]:
                remaining.append(pending)
                continue

            if idx > pending["expires_idx"]:
                continue

            sig = pending["signal"]
            entry_limit = sig.get("entry_limit")
            if entry_limit is None:
                continue

            row_low = float(row["low"])
            row_high = float(row["high"])
            if row_low <= entry_limit <= row_high:
                remaining.extend(self._pending_entries[pending_idx + 1 :])
                self._pending_entries = remaining
                return self._build_trade(sig, entry_limit, equity, idx, limit_fill=True)

            remaining.append(pending)

        self._pending_entries = remaining
        return None

    def _exit_fraction(
        self,
        trade: dict,
        exit_price: float,
        fraction: float,
    ) -> tuple[float, float, float]:
        if trade["direction"] == "LONG":
            pnl_pct = (exit_price - trade["entry_price"]) / trade["entry_price"]
        else:
            pnl_pct = (trade["entry_price"] - exit_price) / trade["entry_price"]

        leg_pos_val = trade["pos_val"] * fraction
        fee_exit = leg_pos_val * self.cfg.fee_pct
        fee_entry = trade["fee"] * fraction
        pnl_net = leg_pos_val * pnl_pct - fee_entry - fee_exit
        rr = abs(exit_price - trade["entry_price"]) / abs(trade["entry_price"] - trade["stop_loss"])
        return pnl_pct * 100, pnl_net, rr

    def _manage(self, trade: dict, df: pd.DataFrame,
                idx: int, row: pd.Series) -> Optional[dict]:
        row_low = float(row["low"])
        row_high = float(row["high"])
        remainder = trade["final_tp_size_pct"] if trade["tp1_hit"] else 1.0

        # Stop always has priority over targets on ambiguous OHLC bars.
        if trade["direction"] == "LONG" and row_low <= trade["stop_loss"]:
            pnl_pct, pnl_net, rr = self._exit_fraction(trade, trade["stop_loss"], remainder)
            return {
                "exit_price": trade["stop_loss"],
                "pnl_pct": trade["realized_pnl_pct"] + pnl_pct * remainder,
                "pnl_net": trade["realized_pnl_net"] + pnl_net,
                "rr": trade["realized_rr"] + rr * remainder,
                "reason": "tp1_sl" if trade["tp1_hit"] else "sl",
            }
        if trade["direction"] == "SHORT" and row_high >= trade["stop_loss"]:
            pnl_pct, pnl_net, rr = self._exit_fraction(trade, trade["stop_loss"], remainder)
            return {
                "exit_price": trade["stop_loss"],
                "pnl_pct": trade["realized_pnl_pct"] + pnl_pct * remainder,
                "pnl_net": trade["realized_pnl_net"] + pnl_net,
                "rr": trade["realized_rr"] + rr * remainder,
                "reason": "tp1_sl" if trade["tp1_hit"] else "sl",
            }

        tp1_price = trade.get("tp1_price")
        tp1_size_pct = trade.get("tp1_size_pct")
        if not trade["tp1_hit"] and tp1_price is not None and tp1_size_pct:
            tp1_hit = (
                (trade["direction"] == "LONG" and row_high >= tp1_price) or
                (trade["direction"] == "SHORT" and row_low <= tp1_price)
            )
            if tp1_hit:
                pnl_pct, pnl_net, rr = self._exit_fraction(trade, tp1_price, tp1_size_pct)
                trade["tp1_hit"] = True
                trade["realized_pnl_net"] += pnl_net
                trade["realized_pnl_pct"] += pnl_pct * tp1_size_pct
                trade["realized_rr"] += rr * tp1_size_pct

        final_tp_hit = (
            (trade["direction"] == "LONG" and row_high >= trade["take_profit"]) or
            (trade["direction"] == "SHORT" and row_low <= trade["take_profit"])
        )
        if final_tp_hit:
            remainder = trade["final_tp_size_pct"] if trade["tp1_hit"] else 1.0
            pnl_pct, pnl_net, rr = self._exit_fraction(trade, trade["take_profit"], remainder)
            return {
                "exit_price": trade["take_profit"],
                "pnl_pct": trade["realized_pnl_pct"] + pnl_pct * remainder,
                "pnl_net": trade["realized_pnl_net"] + pnl_net,
                "rr": trade["realized_rr"] + rr * remainder,
                "reason": "tp1_tp" if trade["tp1_hit"] else "tp",
            }

        if idx - trade["entry_idx"] >= self.cfg.max_candles_hold:
            remainder = trade["final_tp_size_pct"] if trade["tp1_hit"] else 1.0
            exit_price = float(row["close"])
            pnl_pct, pnl_net, rr = self._exit_fraction(trade, exit_price, remainder)
            return {
                "exit_price": exit_price,
                "pnl_pct": trade["realized_pnl_pct"] + pnl_pct * remainder,
                "pnl_net": trade["realized_pnl_net"] + pnl_net,
                "rr": trade["realized_rr"] + rr * remainder,
                "reason": "tp1_timeout" if trade["tp1_hit"] else "timeout",
            }

        return None

    def _metrics(self) -> Dict:
        if not self.trades:
            return {"error": "No trades", "total_trades": 0}
        df  = pd.DataFrame([asdict(t) for t in self.trades])
        win = df[df["pnl_pct"] > 0]
        los = df[df["pnl_pct"] <= 0]
        eq  = [e["equity"] for e in self.equity_curve]
        pk  = np.maximum.accumulate(eq)
        dd  = (pk - eq) / pk * 100
        exit_counts = df["exit_reason"].value_counts().to_dict()
        tp1_hits = int(df["exit_reason"].isin(["tp1_tp", "tp1_sl", "tp1_timeout"]).sum())
        full_tp_hits = int(df["exit_reason"].isin(["tp", "tp1_tp"]).sum())
        sl_hits = int(df["exit_reason"].isin(["sl", "tp1_sl"]).sum())
        timeout_hits = int(df["exit_reason"].isin(["timeout", "tp1_timeout"]).sum())
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
            "exits":             exit_counts,
            "tp1_hits":          tp1_hits,
            "full_tp_hits":      full_tp_hits,
            "sl_hits":           sl_hits,
            "timeout_hits":      timeout_hits,
            "trades":            [asdict(t) for t in self.trades],
            "equity_curve":      self.equity_curve,
        }
