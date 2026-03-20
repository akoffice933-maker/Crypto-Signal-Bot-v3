"""
Analysis Pipeline — runs every 15 minutes after candle close.

Order of operations:
  1. Load candles (15m, 4H, 1D)
  2. Market State (ADX, ATR%) → bail if dead_zone / low-vol / no session
  3. Build Liquidity Map (1D + 4H)
  4. Squeeze Detector (4H)
  5. Order Flow (funding, OI cascade, CVD)
  6. Strategy A: Sweep Reversal
  7. Strategy B: Volatility Breakout (only if squeeze)
  8. Confidence filter (≥ 65)
  9. Cooldown check
 10. Save to DB + send Telegram
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List

from data.binance_client import BinanceFuturesClient
from data.orderflow_ws import OrderFlowWebSocket
from database.db import Database
from engine.candle_loader import load_candles
from engine.liquidity_map import build_liquidity_map
from engine.market_state import get_market_context
from engine.orderflow import evaluate_oi_cascade
from engine.squeeze import is_squeeze
from strategies.breakout import check_breakout
from strategies.breakout import signal_to_dict as breakout_to_dict
from strategies.sweep_reversal import check_sweep_reversal
from strategies.sweep_reversal import signal_to_dict as sweep_to_dict
from config.settings import settings
from engine.logger import log_analysis_summary, log_liquidity_levels

logger = logging.getLogger(__name__)


async def run_pipeline(
    client: BinanceFuturesClient,
    db: Database,
    ws: OrderFlowWebSocket,
    notifier,                          # TelegramNotifier | None
) -> Optional[dict]:
    """
    Full analysis cycle.
    Returns the signal dict if one was sent, else None.
    """
    
    cycle_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    logger.info(f"\n{'='*60}")
    logger.info(f"ANALYSIS CYCLE START — {cycle_time}")
    logger.info(f"{'='*60}")

    # ── 1. Load candles ───────────────────────────────────────
    try:
        candles = await load_candles(
            client, settings.symbol, ["15m", "4h", "1d"]
        )
    except Exception as e:
        logger.error(f"Candle load failed: {e}")
        return None

    df_15m = candles["15m"]
    df_4h  = candles["4h"]
    df_1d  = candles["1d"]
    current_price = float(df_15m["close"].iloc[-1])
    
    logger.info(f"📊 Loaded candles: 15m={len(df_15m)}, 4h={len(df_4h)}, 1d={len(df_1d)}")
    logger.info(f"💰 Current price: ${current_price:,.2f}")

    # ── 2. Market State ───────────────────────────────────────
    ctx = get_market_context(df_15m)
    logger.info(f"\n📈 Market State:")
    logger.info(f"  • ADX: {ctx.adx_value:.1f} ({ctx.market_state})")
    logger.info(f"  • ATR%: {ctx.atr_pct*100:.2f}% ({ctx.volatility_regime})")
    logger.info(f"  • Session: {ctx.session if ctx.session else 'None (off-hours)'}")
    logger.info(f"  • Tradeable: {ctx.tradeable}")

    if not ctx.tradeable:
        blockers = []
        if ctx.market_state == "dead_zone":
            blockers.append("ADX dead zone (20-25) [-25]")
        if ctx.volatility_regime == "low":
            blockers.append("Low volatility (<0.7%) [-30]")
        if not ctx.session:
            blockers.append("Off-hours (no session) [-30]")
        
        logger.info(f"\n❌ SKIP: Market not tradeable")
        logger.info(f"  Blockers: {', '.join(blockers)}")
        return None

    # ── 3. Liquidity Map ──────────────────────────────────────
    levels = build_liquidity_map(df_1d, df_4h, current_price)
    logger.info(f"\n🎯 Liquidity Levels: {len(levels)} found")
    log_liquidity_levels(levels)

    # ── 4. Squeeze ────────────────────────────────────────────
    squeeze_active = is_squeeze(df_4h)
    logger.info(f"\n📊 Squeeze Detector (4H): {'ACTIVE ✅' if squeeze_active else 'inactive ❌'}")

    # ── 5. Order Flow ─────────────────────────────────────────
    # Funding rate
    try:
        fi = await client.get_premium_index(settings.symbol)
        funding_rate = float(fi.get("lastFundingRate", 0))
    except Exception:
        funding_rate = 0.0

    # OI cascade
    try:
        oi_data  = await client.get_open_interest(settings.symbol)
        oi_now   = float(oi_data["openInterest"])
        await db.save_oi(oi_now, current_price)
        oi_snap  = await db.get_oi_ago(settings.oi_lookback_minutes)
        oi_60m, price_60m = (oi_snap[0], oi_snap[1]) if oi_snap else (None, None)
        cascade, oi_chg_pct = evaluate_oi_cascade(
            oi_now, oi_60m, current_price, price_60m
        )
        logger.info(f"\n📊 Order Flow:")
        logger.info(f"  • Funding rate: {funding_rate*100:.3f}%")
        logger.info(f"  • OI change (60m): {oi_chg_pct:.2f}% if oi_chg_pct else 'N/A'}")
        logger.info(f"  • OI Cascade: {'Yes ✅' if cascade else 'No ❌'}")
    except Exception as e:
        logger.warning(f"OI fetch failed: {e}")
        cascade, oi_chg_pct = False, None

    # CVD from WebSocket
    cvd_div = ws.cvd_divergence() if ws.is_connected else None
    logger.info(f"  • CVD divergence: {cvd_div if cvd_div else 'None'}")

    # ── 6. Sweep Reversal ─────────────────────────────────────
    signal_dict = None

    sweep_sig = check_sweep_reversal(
        df_15m=df_15m,
        levels=levels,
        squeeze_active=squeeze_active,
        cvd_divergence=cvd_div,
        funding_rate=funding_rate,
        liquidation_cascade=cascade,
        market_state=ctx.market_state,
        adx_value=ctx.adx_value,
        trend_direction=ctx.trend_direction,
        session=ctx.session,
    )

    if sweep_sig and sweep_sig.confidence.score >= settings.confidence_threshold:
        signal_dict = sweep_to_dict(
            sweep_sig,
            session=ctx.session,
            market_state=ctx.market_state,
            volatility_regime=ctx.volatility_regime,
            adx_value=ctx.adx_value,
            atr_pct=ctx.atr_pct,
            oi_change_pct=oi_chg_pct,
            cvd_divergence=cvd_div,
            funding_rate=funding_rate,
            liquidation_cascade=cascade,
            squeeze_active=squeeze_active,
        )
        logger.info(
            f"Sweep signal: {sweep_sig.direction} "
            f"entry={sweep_sig.entry_market} conf={sweep_sig.confidence.score}"
        )

    # ── 7. Breakout (only if sweep found nothing) ─────────────
    if signal_dict is None and squeeze_active:
        bo_sig = check_breakout(
            df_15m=df_15m,
            squeeze_active=squeeze_active,
            session=ctx.session,
            cvd_divergence=cvd_div,
            funding_rate=funding_rate,
            liquidation_cascade=cascade,
            adx_value=ctx.adx_value,
        )
        if bo_sig and bo_sig.confidence.score >= settings.confidence_threshold:
            signal_dict = breakout_to_dict(
                bo_sig,
                session=ctx.session,
                volatility_regime=ctx.volatility_regime,
                adx_value=ctx.adx_value,
                atr_pct=ctx.atr_pct,
                oi_change_pct=oi_chg_pct,
                cvd_divergence=cvd_div,
                funding_rate=funding_rate,
                liquidation_cascade=cascade,
            )
            logger.info(
                f"\n📈 Breakout signal: {bo_sig.direction} "
                f"entry={bo_sig.entry_market} conf={bo_sig.confidence.score}"
            )

    # ── No signal found ───────────────────────────────────────
    if signal_dict is None:
        logger.info(f"\n❌ No signal this cycle")
        logger.info(f"  Reasons:")
        logger.info(f"    • No sweep reversal pattern detected")
        if not squeeze_active:
            logger.info(f"    • No squeeze active (4H)")
        logger.info(f"{'='*60}\n")
        return None

    # ── 8. Cooldown check ─────────────────────────────────────
    sig_id = signal_dict["signal_id"]
    if await db.is_on_cooldown(sig_id):
        logger.info(f"\n⏰ Signal {sig_id[:8]}... on cooldown (60 min) — skipping")
        return None

    # ── 9. Persist + notify ───────────────────────────────────
    await db.save_signal(signal_dict)
    await db.set_cooldown(sig_id, minutes=60)

    logger.info(f"\n✅ SIGNAL FOUND!")
    logger.info(f"  Strategy: {signal_dict['strategy']}")
    logger.info(f"  Direction: {signal_dict['direction']}")
    logger.info(f"  Entry: ${signal_dict['entry_market']:.2f}")
    logger.info(f"  SL: ${signal_dict['stop_loss']:.2f}")
    logger.info(f"  TP: ${signal_dict['take_profit']:.2f}")
    logger.info(f"  RR: {signal_dict['rr_ratio']:.2f}")
    logger.info(f"  Confidence: {signal_dict['confidence_score']}%")
    
    if notifier:
        await notifier.send_signal(signal_dict)
        logger.info(f"  📱 Sent to Telegram")

    logger.info(f"{'='*60}\n")
    
    return signal_dict
