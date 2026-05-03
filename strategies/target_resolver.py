import logging
from typing import Optional

from config.settings import settings


def _price_at_rr(direction: str, entry: float, stop_loss: float, rr_multiple: float) -> float:
    risk = abs(entry - stop_loss)
    if direction == "LONG":
        return entry + risk * rr_multiple
    return entry - risk * rr_multiple


def resolve_take_profit(
    *,
    direction: str,
    entry_price: float,
    stop_loss: float,
    current_price: float,
    operating_mode: str,
    target_price: Optional[float] = None,
    fallback_rr: Optional[float] = None,
    fallback_pct: Optional[float] = None,
    logger: Optional[logging.Logger] = None,
) -> tuple[float, float]:
    """
    Resolve TP from either:
      - explicit structural/liquidity target
      - fallback RR multiple
      - fallback percent move

    Applies the same mode-aware caps for all strategies.
    Returns:
      take_profit
      distance_to_target_pct (vs current_price)
    """
    if target_price is not None:
        take_profit = target_price
    elif fallback_rr is not None:
        take_profit = _price_at_rr(direction, entry_price, stop_loss, fallback_rr)
    elif fallback_pct is not None:
        if direction == "LONG":
            take_profit = entry_price * (1 + fallback_pct)
        else:
            take_profit = entry_price * (1 - fallback_pct)
    else:
        raise ValueError("resolve_take_profit requires target_price, fallback_rr, or fallback_pct")

    dist_to_target = abs(take_profit - current_price) / current_price

    if operating_mode == "quiet":
        if direction == "LONG":
            max_tp = entry_price * (1 + settings.quiet_tp_max_pct)
            if take_profit > max_tp:
                if logger:
                    logger.info(
                        f"  ⚠️  TP capped for Quiet: {take_profit:.2f} → {max_tp:.2f} "
                        f"(max +{settings.quiet_tp_max_pct * 100:.1f}%)"
                    )
                take_profit = max_tp
                dist_to_target = abs(take_profit - entry_price) / entry_price
        else:
            max_tp = entry_price * (1 - settings.quiet_tp_max_pct)
            if take_profit < max_tp:
                if logger:
                    logger.info(
                        f"  ⚠️  TP capped for Quiet: {take_profit:.2f} → {max_tp:.2f} "
                        f"(max -{settings.quiet_tp_max_pct * 100:.1f}%)"
                    )
                take_profit = max_tp
                dist_to_target = abs(take_profit - entry_price) / entry_price

    max_tp_pct = 0.10
    max_take_profit = (
        entry_price * (1 + max_tp_pct)
        if direction == "LONG"
        else entry_price * (1 - max_tp_pct)
    )

    if direction == "LONG" and take_profit > max_take_profit:
        if logger:
            logger.info(f"  ⚠️  TP capped: {take_profit:.2f} → {max_take_profit:.2f} (max +10%)")
        take_profit = max_take_profit
        dist_to_target = abs(take_profit - entry_price) / entry_price
    elif direction == "SHORT" and take_profit < max_take_profit:
        if logger:
            logger.info(f"  ⚠️  TP capped: {take_profit:.2f} → {max_take_profit:.2f} (max -10%)")
        take_profit = max_take_profit
        dist_to_target = abs(take_profit - entry_price) / entry_price

    return take_profit, dist_to_target
