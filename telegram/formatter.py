"""
Telegram signal formatter.

Produces messages matching the spec format exactly:

BTCUSDT LONG 🟢

Strategy: Liquidity Sweep Reversal
Entry (Market): 64200
Entry (Limit): 64080
Stop Loss: 63900
Take Profit: 64800
RR: 2.2
Confidence: 86%

Market State: Range
Volatility: Normal
Target Liquidity: Daily High

Order Flow:
• CVD bullish divergence
• Long liquidation detected
• Funding negative (-0.07%)

Analysis factors:
+30 Liquidity sweep
+20 Volume spike
...
"""

from typing import Optional

from engine.confidence import ConfidenceResult


_STRATEGY_LABEL = {
    "sweep_reversal": "Liquidity Sweep Reversal",
    "breakout":       "Volatility Breakout",
}

_TF_LABEL = {
    "1d": "Daily",
    "4h": "4H",
}

_POOL_LABEL = {
    "equal_highs": "High",
    "equal_lows":  "Low",
}

_MARKET_LABEL = {
    "trending":  "Trending",
    "ranging":   "Range",
    "dead_zone": "Dead Zone",
}

_VOL_LABEL = {
    "blocked": "Blocked",
    "quiet":   "Quiet",
    "low":     "Low",
    "normal":  "Normal",
    "high":    "High",
}


def format_signal(signal: dict) -> str:
    d   = signal["direction"]
    emoji = "🟢" if d == "LONG" else "🔴"
    pair  = signal.get("pair", "BTCUSDT")

    strategy_label = _STRATEGY_LABEL.get(signal["strategy"], signal["strategy"])

    entry_m = signal["entry_market"]
    entry_l = signal.get("entry_limit")
    sl      = signal["stop_loss"]
    tp1     = signal.get("tp1_price")
    tp1_rr  = signal.get("tp1_rr")
    tp1_size_pct = signal.get("tp1_size_pct")
    final_tp_size_pct = signal.get("final_tp_size_pct")
    tp      = signal["take_profit"]
    rr      = signal["rr_ratio"]
    rr_basis = signal.get("execution_basis")
    conf    = signal["confidence_score"]

    ms  = _MARKET_LABEL.get(signal.get("market_state", ""), signal.get("market_state", ""))
    vol_raw = signal.get("volatility_regime", "")
    vol = _VOL_LABEL.get(vol_raw, vol_raw)

    # Target liquidity label
    tf_raw   = signal.get("target_liquidity_tf", "")
    pool_raw = signal.get("target_liquidity_type", "")
    if tf_raw and pool_raw:
        target_label = f"{_TF_LABEL.get(tf_raw, tf_raw)} {_POOL_LABEL.get(pool_raw, pool_raw)}"
    else:
        target_label = "—"

    # Order flow bullets
    of_lines = []
    cvd = signal.get("cvd_divergence")
    if cvd:
        of_lines.append(f"• CVD {cvd} divergence")
    if signal.get("liquidation_cascade"):
        cascade_dir = "Long" if d == "LONG" else "Short"
        of_lines.append(f"• {cascade_dir} liquidation detected")
    fr = signal.get("funding_rate", 0) or 0
    if abs(fr) >= 0.0001:
        fr_label = "positive" if fr > 0 else "negative"
        of_lines.append(f"• Funding {fr_label} ({fr*100:+.3f}%)")
    if signal.get("squeeze_active"):
        of_lines.append("• Volatility squeeze active (4H)")

    of_section = ""
    if of_lines:
        of_section = "\nOrder Flow:\n" + "\n".join(of_lines)

    # Confidence breakdown
    import json as _json
    factors = []
    try:
        factors = _json.loads(signal.get("confidence_breakdown") or "[]")
    except Exception:
        pass

    factor_lines = [f"{'+' if f['delta']>=0 else ''}{f['delta']} {f['factor']}"
                    for f in factors]
    factor_section = ""
    if factor_lines:
        factor_section = "\nAnalysis factors:\n" + "\n".join(factor_lines)

    # Entry limit line
    limit_line = f"Entry (Limit):  {entry_l:.2f}\n" if entry_l else ""
    tp1_line = ""
    if tp1 is not None:
        tp1_pct_display = int(round((tp1_size_pct or 0) * 100))
        tp1_rr_display = f"{tp1_rr:.1f}" if tp1_rr is not None else "2.0"
        tp1_line = f"TP1:           {tp1:.2f} ({tp1_pct_display}% @ {tp1_rr_display}R)\n"
    final_tp_line = f"Take Profit:   {tp:.2f}"
    if final_tp_size_pct is not None and final_tp_size_pct < 1.0:
        final_tp_line += f" ({int(round(final_tp_size_pct * 100))}%)"
    final_tp_line += "\n"

    # Position size
    pos_pct = signal.get("position_size_pct")
    pos_line = f"Position Size:  {pos_pct:.1f}%\n" if pos_pct else ""
    rr_suffix = f" ({rr_basis})" if rr_basis else ""

    msg = (
        f"{pair} {d} {emoji}\n"
        f"\n"
        f"Strategy: {strategy_label}\n"
        f"Entry (Market): {entry_m:.2f}\n"
        f"{limit_line}"
        f"Stop Loss:     {sl:.2f}\n"
        f"{tp1_line}"
        f"{final_tp_line}"
        f"RR:            {rr:.1f}{rr_suffix}\n"
        f"{pos_line}"
        f"Confidence:    {conf}%\n"
        f"\n"
        f"Market State: {ms}\n"
        f"Volatility:   {vol}\n"
        f"Target Liquidity: {target_label}\n"
        f"{of_section}"
        f"{factor_section}\n"
        f"\n"
        f"🔑 `{signal.get('signal_id','')[:8]}`"
    )
    return msg.strip()
