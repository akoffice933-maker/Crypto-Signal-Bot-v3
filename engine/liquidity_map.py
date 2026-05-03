"""
Liquidity Map Engine — 1D + 4H

Rules:
  • Equal highs / lows: ≥ 3 wick touches within 0.2% of each other
  • Lookback: 90 days (≈90 daily candles, ≈540 4h candles)
  • Mitigation: if price crossed level and returned → mitigated=True
    (but level stays active — can be swept again)
  • Target: nearest non-proxied pool (distance ≥ 1.5%)
  • TF weights: 1d=3, 4h=1  (used for strength scoring)
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from config.settings import settings

logger = logging.getLogger(__name__)

TF_WEIGHT = {"1d": 3.0, "4h": 1.0}


@dataclass
class LiquidityLevel:
    timeframe:   str       # 1d | 4h
    pool_type:   str       # equal_highs | equal_lows
    price:       float
    touch_count: int
    strength:    float     # touch_count × tf_weight
    mitigated:   bool
    distance_pct: float    # from current price, positive
    level_score: int = 0   # NEW: 0-9 composite score
    freshness_score: int = 0  # NEW: 0-10 freshness bonus

    def __post_init__(self):
        """Calculate level_score and freshness_score after initialization."""
        # Freshness score: fewer touches = fresher = more reliable
        # touches=3 → +7, touches=10 → 0, touches=20 → -10
        self.freshness_score = max(0, 10 - self.touch_count)

        # Level score: combines strength, touches, freshness, and timeframe weight
        # 1D levels are 3× more significant than 4H levels (TF_WEIGHT)
        tf_weight = TF_WEIGHT.get(self.timeframe, 1.0)

        # Touches bonus (diminishing returns after 10)
        touches_bonus = min(self.touch_count, 10)

        # Stale penalty (too many touches = overused level)
        stale_penalty = max(0, self.touch_count - 15)

        self.level_score = int(
            self.strength * tf_weight +  # Base strength scaled by timeframe weight
            self.freshness_score +       # Freshness bonus
            touches_bonus -              # Touches bonus (capped)
            stale_penalty                # Stale penalty
        )

    @property
    def is_above(self) -> bool:
        return self.pool_type == "equal_highs"

    def __str__(self) -> str:
        m = " [mitigated]" if self.mitigated else ""
        return (f"{self.timeframe} {self.pool_type} @ {self.price:.2f} "
                f"(touches={self.touch_count}, str={self.strength:.1f}, "
                f"score={self.level_score}, fresh={self.freshness_score}{m}, "
                f"dist={self.distance_pct*100:.2f}%)")


def _find_equal_levels(
    prices: pd.Series,
    tolerance_pct: float = 0.002,
    min_touches: int = 3,
) -> List[Tuple[float, int]]:
    """
    Cluster price extremes within tolerance_pct.
    Returns [(representative_price, touch_count), ...] sorted by price.
    Only clusters with touch_count >= min_touches are returned.
    """
    vals = sorted(prices.dropna().tolist())
    if not vals:
        return []

    clusters: List[Tuple[float, List[float]]] = []
    for v in vals:
        merged = False
        for i, (rep, members) in enumerate(clusters):
            if abs(v - rep) / rep <= tolerance_pct:
                members.append(v)
                clusters[i] = (np.mean(members), members)
                merged = True
                break
        if not merged:
            clusters.append((v, [v]))

    return [
        (round(rep, 2), len(members))
        for rep, members in clusters
        if len(members) >= min_touches
    ]


def detect_levels(
    df: pd.DataFrame,
    timeframe: str,
    current_price: float,
    tolerance_pct: float = None,
    min_touches: int = None,
) -> List[LiquidityLevel]:
    """
    Detect equal highs and equal lows from a single-timeframe OHLC DataFrame.
    Uses wick highs/lows (not close prices).
    """
    tol   = tolerance_pct or settings.liquidity_tolerance_pct
    min_t = min_touches   or settings.liquidity_touch_min
    weight = TF_WEIGHT.get(timeframe, 1.0)

    levels: List[LiquidityLevel] = []

    # Equal highs — wick highs
    for price, touches in _find_equal_levels(df["high"], tol, min_t):
        dist = abs(price - current_price) / current_price
        levels.append(LiquidityLevel(
            timeframe=timeframe,
            pool_type="equal_highs",
            price=price,
            touch_count=touches,
            strength=round(touches * weight, 2),
            mitigated=_check_mitigated(df, price, "high"),
            distance_pct=dist,
        ))

    # Equal lows — wick lows
    for price, touches in _find_equal_levels(df["low"], tol, min_t):
        dist = abs(price - current_price) / current_price
        levels.append(LiquidityLevel(
            timeframe=timeframe,
            pool_type="equal_lows",
            price=price,
            touch_count=touches,
            strength=round(touches * weight, 2),
            mitigated=_check_mitigated(df, price, "low"),
            distance_pct=dist,
        ))

    return levels


def _check_mitigated(df: pd.DataFrame, level: float, side: str) -> bool:
    """
    A level is mitigated if price crossed it at some point after the
    first recorded touch, then returned to the same side.
    Simple heuristic: close crossed the level at least once.
    """
    closes = df["close"].tolist()
    if side == "high":
        return any(c > level for c in closes)
    return any(c < level for c in closes)


def select_target_level(
    levels: List[LiquidityLevel],
    current_price: float,
    direction: str,               # LONG or SHORT
    min_distance_pct: float = None,
) -> Optional[LiquidityLevel]:
    """
    Select the nearest valid target liquidity level in the signal direction.

    LONG  → target is equal_highs above current price (we're aiming up)
    SHORT → target is equal_lows  below current price (we're aiming down)

    Must be:
      • Not proxied (distance ≥ min_distance_pct)
      • On the correct side
      • Strongest first if multiple at similar distance
    """
    min_dist = min_distance_pct or settings.liquidity_min_distance_pct

    if direction == "LONG":
        candidates = [
            lv for lv in levels
            if lv.pool_type == "equal_highs"
            and lv.price > current_price
            and lv.distance_pct >= min_dist
        ]
    else:
        candidates = [
            lv for lv in levels
            if lv.pool_type == "equal_lows"
            and lv.price < current_price
            and lv.distance_pct >= min_dist
        ]

    if not candidates:
        return None

    # Prefer 1D over 4H, then nearest, then strongest
    candidates.sort(key=lambda lv: (
        0 if lv.timeframe == "1d" else 1,
        lv.distance_pct,
        -lv.strength,
    ))
    return candidates[0]


def build_liquidity_map(
    df_1d: pd.DataFrame,
    df_4h: pd.DataFrame,
    current_price: float,
) -> List[LiquidityLevel]:
    """
    Combine levels from 1D and 4H into a single sorted list.
    """
    levels_1d = detect_levels(df_1d, "1d", current_price)
    levels_4h = detect_levels(df_4h, "4h", current_price)

    all_levels = levels_1d + levels_4h
    # Sort by distance
    all_levels.sort(key=lambda lv: lv.distance_pct)
    logger.debug(f"Liquidity map: {len(levels_1d)} 1D + {len(levels_4h)} 4H levels")
    return all_levels
