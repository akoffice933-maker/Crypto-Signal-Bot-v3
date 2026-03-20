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
from typing import Optional

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

    # ── 2. Market State ───────────────────────────────────────
    ctx = get_market_context(df_15m)
    logger.info(str(ctx))

    if not ctx.tradeable:
        logger.info(f"Not tradeable: {ctx.market_state}, vol={ctx.volatility_regime}, "
                    f"session={ctx.session}")
        return None

    # ── 3. Liquidity Map ──────────────────────────────────────
    levels = build_liquidity_map(df_1d, df_4h, current_price)
    logger.info(f"Liquidity map: {len(levels)} levels")

    # ── 4. Squeeze ────────────────────────────────────────────
    squeeze_active = is_squeeze(df_4h)

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
    except Exception as e:
        logger.warning(f"OI fetch failed: {e}")
        cascade, oi_chg_pct = False, None

    # CVD from WebSocket
    cvd_div = ws.cvd_divergence() if ws.is_connected else None

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
                f"Breakout signal: {bo_sig.direction} "
                f"entry={bo_sig.entry_market} conf={bo_sig.confidence.score}"
            )

    if signal_dict is None:
        logger.debug("No signal this cycle")
        return None

    # ── 8. Cooldown check ─────────────────────────────────────
    sig_id = signal_dict["signal_id"]
    if await db.is_on_cooldown(sig_id):
        logger.info(f"Signal {sig_id} on cooldown — skipping")
        return None

    # ── 9. Persist + notify ───────────────────────────────────
    await db.save_signal(signal_dict)
    await db.set_cooldown(sig_id, minutes=60)

    if notifier:
        await notifier.send_signal(signal_dict)

    return signal_dict
