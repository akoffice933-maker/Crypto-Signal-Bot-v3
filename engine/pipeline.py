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

import asyncio
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
from engine.sweep_trigger_5m import SweepTrigger5m
from config.settings import settings
from engine.confidence import ConfidenceResult
from engine.logger import log_analysis_summary, log_liquidity_levels

logger = logging.getLogger(__name__)
_STRATEGY_VERSION = "v4-hybrid"


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _log_confidence_fail(strategy_label: str, confidence: ConfidenceResult, threshold: int):
    """Emit explicit diagnostics when a candidate pattern fails confidence filtering."""
    logger.info(
        f"❌ CONFIDENCE FAIL ({strategy_label}): {confidence.score} < {threshold}"
    )
    if confidence.factors:
        logger.info("  Breakdown:")
        for factor in confidence.factors:
            sign = "+" if factor.delta >= 0 else ""
            logger.info(f"    {sign}{factor.delta} {factor.label}")
    else:
        logger.info("  Breakdown: no confidence factors recorded")


def _quiet_breakout_blocker_reason(adx_value: float) -> str:
    return (
        f"Quiet breakout blocked (ADX {adx_value:.1f} < {settings.quiet_breakout_min_adx:.0f})"
    )


def _make_cycle_id(now_utc: datetime) -> str:
    return f"{settings.symbol}-{now_utc.strftime('%Y%m%d%H%M%S')}"


def _init_cycle_summary(now_utc: datetime) -> Dict:
    return {
        "cycle_id": _make_cycle_id(now_utc),
        "created_at": now_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "pair": settings.symbol,
        "analysis_time_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "session": None,
        "hour_utc": now_utc.hour,
        "market_state": None,
        "volatility_regime": None,
        "operating_mode": None,
        "tradeable": False,
        "adx_value": None,
        "atr_pct": None,
        "current_price": None,
        "candles_15m": None,
        "candles_4h": None,
        "candles_1d": None,
        "liquidity_levels_found": None,
        "liquidity_levels_eligible": None,
        "liquidity_levels_filtered": None,
        "squeeze_active": None,
        "funding_rate": None,
        "oi_change_pct": None,
        "liquidation_cascade": None,
        "cvd_divergence": None,
        "sweep_candidate": False,
        "breakout_candidate": False,
        "confidence_score": None,
        "confidence_threshold": None,
        "confidence_stage": None,
        "confidence_breakdown": None,
        "final_status": "error",
        "final_reason": None,
        "blocker_reason": None,
        "signal_id": None,
        "signal_strategy": None,
        "signal_direction": None,
        "tp1_price": None,
        "tp1_rr": None,
        "tp1_size_pct": None,
        "final_tp_size_pct": None,
        "rr_ratio": None,
        "rr_market": None,
        "rr_limit": None,
        "execution_basis": None,
        "cooldown_hit": False,
        "strategy_version": _STRATEGY_VERSION,
    }


async def _save_cycle_summary_safe(db: Database, cycle_data: Dict):
    try:
        await db.save_cycle_summary(cycle_data)
    except Exception as e:
        logger.warning(f"Failed to save cycle_summary {cycle_data.get('cycle_id')}: {e}")


async def run_pipeline(
    client: BinanceFuturesClient,
    db: Database,
    ws: OrderFlowWebSocket,
    notifier,                          # TelegramNotifier | None
    sweep_trigger=None,                # SweepTrigger5m | None
) -> Optional[dict]:
    """
    Full analysis cycle for all configured pairs.
    Returns the last signal dict if one was sent, else None.
    """
    all_signals = []
    symbols = list(settings.symbols)  # snapshot to avoid mutation issues

    # DIAG: check connectivity
    logger.info(f"  🔍 [DIAG] Pipeline start — pairs={symbols}, ws_connected={ws.is_connected if ws else 'N/A'}")

    for symbol in symbols:
        logger.info(f"\n{'='*60}")
        logger.info(f"ANALYZING PAIR: {symbol}")
        logger.info(f"{'='*60}")

        try:
            signal = await _analyze_single_pair(
                client=client,
                db=db,
                ws=ws,
                notifier=notifier,
                symbol=symbol,
                sweep_trigger=sweep_trigger,
            )
            if signal:
                all_signals.append(signal)
        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}", exc_info=True)

        # Rate limit: small delay between pairs
        if symbol != symbols[-1]:
            await asyncio.sleep(2)

    # Return last signal or None
    return all_signals[-1] if all_signals else None


async def _analyze_single_pair(
    client: BinanceFuturesClient,
    db: Database,
    ws: OrderFlowWebSocket,
    notifier,
    symbol: str,
    sweep_trigger=None,                # SweepTrigger5m | None
) -> Optional[dict]:
    """
    Analyze a single trading pair.
    Returns the signal dict if one was sent, else None.
    """
    now_utc = datetime.now(timezone.utc)
    cycle_data = _init_cycle_summary(now_utc)
    cycle_data["pair"] = symbol  # Override pair
    cycle_time = cycle_data["analysis_time_utc"]
    logger.info(f"  🕐 Cycle time: {cycle_time}")
    try:
        # ── 1. Load candles ───────────────────────────────────────
        logger.info(f"  🔍 [DIAG] Attempting to load candles for {symbol}...")
        try:
            candles = await load_candles(
                client, symbol, ["15m", "4h", "1d"]
            )
            logger.info(f"  ✅ [DIAG] Candles loaded successfully for {symbol}")
        except Exception as e:
            logger.error(f"  ❌ [DIAG] Candle load FAILED for {symbol}: {e}")
            raise  # re-raise to be caught by outer handler

        df_15m = candles["15m"]
        df_4h  = candles["4h"]
        df_1d  = candles["1d"]
        current_price = float(df_15m["close"].iloc[-1])
        cycle_data.update({
            "current_price": current_price,
            "candles_15m": len(df_15m),
            "candles_4h": len(df_4h),
            "candles_1d": len(df_1d),
        })

        logger.info(f"📊 Loaded candles: 15m={len(df_15m)}, 4h={len(df_4h)}, 1d={len(df_1d)}")
        logger.info(f"💰 Current price: ${current_price:,.2f}")

        # ── 2. Market State ───────────────────────────────────────
        ctx = get_market_context(df_15m)
        cycle_data.update({
            "session": ctx.session,
            "hour_utc": ctx.hour_utc,
            "market_state": ctx.market_state,
            "volatility_regime": ctx.volatility_regime,
            "operating_mode": ctx.operating_mode,
            "tradeable": ctx.tradeable,
            "adx_value": ctx.adx_value,
            "atr_pct": ctx.atr_pct,
        })
        logger.info(f"\n📈 Market State:")
        logger.info(f"  • ADX: {ctx.adx_value:.1f} ({ctx.market_state})")
        logger.info(f"  • ATR%: {ctx.atr_pct*100:.2f}% ({ctx.volatility_regime})")
        logger.info(f"  • Mode: {ctx.operating_mode.upper()}")
        logger.info(f"  • Session: {ctx.session if ctx.session else 'None (off-hours)'}")
        logger.info(f"  • Tradeable: {ctx.tradeable}")

        if not ctx.tradeable:
            blockers = []
            if ctx.operating_mode == 'blocked':
                blockers.append(
                    f"ATR below minimum ({_fmt_pct(ctx.atr_pct)} < {_fmt_pct(settings.quiet_atr_min)})"
                )
            if ctx.market_state == "dead_zone":
                blockers.append(
                    f"ADX dead zone ({settings.adx_dead_zone_min:.0f}-{settings.adx_dead_zone_max:.0f})"
                )
            if not ctx.session:
                blockers.append("Off-hours (no session)")
            if ctx.operating_mode == 'quiet' and ctx.session is not None and ctx.session not in settings.quiet_allowed_sessions:
                allowed = ", ".join(settings.quiet_allowed_sessions)
                blockers.append(f"Session '{ctx.session}' not allowed in QUIET mode (allowed: {allowed})")

            # DIAG: detailed market state dump
            logger.info(f"  🔍 DIAG MarketState: ADX={ctx.adx_value:.1f} ATR={ctx.atr_pct*100:.3f}% "
                        f"mode={ctx.operating_mode} session={ctx.session} "
                        f"tradeable={ctx.tradeable}")

            blocker_text = ", ".join(blockers)
            logger.info(f"\n❌ SKIP: Market not tradeable")
            logger.info(f"  Blockers: {blocker_text}")
            cycle_data["final_status"] = "skip"
            cycle_data["blocker_reason"] = blocker_text
            cycle_data["final_reason"] = blocker_text
            await _save_cycle_summary_safe(db, cycle_data)
            return None

        # ── 3. Liquidity Map ──────────────────────────────────────
        levels = build_liquidity_map(df_1d, df_4h, current_price)
        logger.info(f"\n🎯 Liquidity Levels: {len(levels)} found")
        log_liquidity_levels(levels)

        min_level_score = (
            settings.quiet_level_score_min
            if ctx.operating_mode == "quiet"
            else settings.normal_level_score_min
        )
        eligible_levels = [lvl for lvl in levels if lvl.level_score >= min_level_score]
        cycle_data.update({
            "liquidity_levels_found": len(levels),
            "liquidity_levels_eligible": len(eligible_levels),
            "liquidity_levels_filtered": len(levels) - len(eligible_levels),
        })

        # ── 4. Real-time Sweep Detection (5M) ─────────────────────
        sweep_detected = False
        if sweep_trigger:
            try:
                sweep_detected = await sweep_trigger.check_sweep(
                    symbol=symbol,
                    current_price=current_price,
                    levels=levels,
                    market_state=ctx.market_state,
                    operating_mode=ctx.operating_mode,
                )
                if sweep_detected:
                    logger.info(f"  ⚡ [SWEEP] Real-time 5M sweep detected for {symbol}")
                else:
                    logger.info(f"  ⚡ [SWEEP] No real-time sweep detected")
            except Exception as e:
                logger.warning(f"  ⚡ [SWEEP] Error checking sweep: {e}")
        else:
            logger.info(f"  ⚡ [SWEEP] No sweep_trigger provided")
        
        cycle_data["sweep_5m_detected"] = sweep_detected

        # ── 5. Squeeze ────────────────────────────────────────────
        squeeze_active = is_squeeze(df_4h)
        cycle_data["squeeze_active"] = squeeze_active
        logger.info(f"\n📊 Squeeze Detector (4H): {'ACTIVE ✅' if squeeze_active else 'inactive ❌'}")

        # ── 6. Order Flow ─────────────────────────────────────────
        # Funding rate
        try:
            fi = await client.get_premium_index(symbol)
            funding_rate = float(fi.get("lastFundingRate", 0))
        except Exception:
            funding_rate = 0.0
        cycle_data["funding_rate"] = funding_rate

        # OI cascade
        try:
            oi_data  = await client.get_open_interest(symbol)
            oi_now   = float(oi_data["openInterest"])
            await db.save_oi(symbol, oi_now, current_price)
            oi_snap  = await db.get_oi_ago(symbol, settings.oi_lookback_minutes)
            oi_60m, price_60m = (oi_snap[0], oi_snap[1]) if oi_snap else (None, None)
            cascade, oi_chg_pct = evaluate_oi_cascade(
                oi_now, oi_60m, current_price, price_60m
            )
            logger.info(f"\n📊 Order Flow:")
            logger.info(f"  • Funding rate: {funding_rate*100:.3f}%")
            oi_text = f"{oi_chg_pct:.2f}%" if oi_chg_pct is not None else "N/A"
            logger.info(f"  • OI change (60m): {oi_text}")
            logger.info(f"  • OI Cascade: {'Yes ✅' if cascade else 'No ❌'}")
        except Exception as e:
            logger.warning(f"OI fetch failed: {e}")
            cascade, oi_chg_pct = False, None
        cycle_data["oi_change_pct"] = oi_chg_pct
        cycle_data["liquidation_cascade"] = cascade

        # CVD from WebSocket
        cvd_div = ws.cvd_divergence() if ws.is_connected else None
        cycle_data["cvd_divergence"] = cvd_div
        logger.info(f"  • CVD divergence: {cvd_div if cvd_div else 'None'}")

        # ── 7. Sweep Reversal ─────────────────────────────────────
        signal_dict = None
        bo_sig = None
        no_signal_reasons: List[str] = []

        # Get mode-specific thresholds
        if ctx.operating_mode == 'quiet':
            confidence_threshold = settings.quiet_confidence_threshold
            volume_spike_multiplier = settings.quiet_volume_spike_multiplier
            min_rr = settings.quiet_min_rr
        else:  # normal
            confidence_threshold = settings.normal_confidence_threshold
            volume_spike_multiplier = settings.normal_volume_spike_multiplier
            min_rr = settings.normal_min_rr
        cycle_data["confidence_threshold"] = confidence_threshold

        # DIAG: log before sweep check
        logger.info(f"  🔍 [DIAG] SweepReversal check: levels={len(eligible_levels)} squeeze={squeeze_active} cvd_div={cvd_div}")
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
            atr_pct=ctx.atr_pct,
            operating_mode=ctx.operating_mode,  # NEW: pass operating mode
            min_rr=min_rr,
            volume_spike_multiplier=volume_spike_multiplier,
        )

        if sweep_sig:
            logger.info(f"  ✅ [DIAG] Sweep reversal pattern DETECTED for {symbol}")
            cycle_data["sweep_candidate"] = True
            # Check mandatory factors for quality control
            has_volume_spike = sweep_sig.volume_spike
            confidence_score = sweep_sig.confidence.score

            # Mandatory volume confirmation for signals below 75% confidence
            if not has_volume_spike and confidence_score < 75:
                logger.info(f"❌ MANDATORY FAIL (Sweep): No volume spike with confidence {confidence_score} < 75")
                no_signal_reasons.append(
                    f"Sweep missing volume spike (confidence {confidence_score} < 75)"
                )
            elif confidence_score >= confidence_threshold:
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
            else:
                _log_confidence_fail("Sweep", sweep_sig.confidence, confidence_threshold)
                cycle_data.update({
                    "confidence_score": sweep_sig.confidence.score,
                    "confidence_threshold": confidence_threshold,
                    "confidence_stage": "sweep",
                    "confidence_breakdown": sweep_sig.confidence.breakdown_json,
                    "rr_ratio": sweep_sig.rr_ratio,
                    "rr_market": sweep_sig.rr_market,
                    "rr_limit": sweep_sig.rr_limit,
                    "execution_basis": sweep_sig.execution_basis,
                    "final_status": "confidence_fail",
                })
                no_signal_reasons.append(
                    f"Sweep confidence {sweep_sig.confidence.score} < {confidence_threshold}"
                )
        else:
            logger.info(f"  ❌ [DIAG] Sweep reversal pattern NOT detected for {symbol}")
            no_signal_reasons.append("No sweep reversal pattern detected")

        # ── 8. Breakout ──────────────────────────────────────────
        quiet_breakout_allowed = (
            ctx.operating_mode == 'quiet'
            and squeeze_active
            and ctx.adx_value >= settings.quiet_breakout_min_adx
        )
        breakout_allowed = signal_dict is None and squeeze_active and (
            ctx.operating_mode == 'normal' or quiet_breakout_allowed
        )

        if breakout_allowed:
            breakout_confidence_threshold = (
                settings.quiet_breakout_confidence_threshold
                if ctx.operating_mode == 'quiet'
                else confidence_threshold
            )
            breakout_min_rr = (
                settings.quiet_breakout_min_rr
                if ctx.operating_mode == 'quiet'
                else min_rr
            )
            bo_sig = check_breakout(
                df_15m=df_15m,
                squeeze_active=squeeze_active,
                session=ctx.session,
                cvd_divergence=cvd_div,
                funding_rate=funding_rate,
                liquidation_cascade=cascade,
                adx_value=ctx.adx_value,
                atr_pct=ctx.atr_pct,
                operating_mode=ctx.operating_mode,
                min_rr=breakout_min_rr,
                volume_spike_multiplier=volume_spike_multiplier,
            )
            if bo_sig:
                cycle_data["breakout_candidate"] = True
                raw_sl_text = (
                    f"{bo_sig.sl_pct_raw * 100:.2f}%"
                    if bo_sig.sl_pct_raw is not None
                    else "N/A"
                )
                logger.info(
                    f"Breakout candidate: {bo_sig.direction} "
                    f"entry={bo_sig.entry_market} "
                    f"sl_pct={bo_sig.sl_pct_used * 100:.2f}% "
                    f"raw_sl={raw_sl_text} "
                    f"mode={bo_sig.sl_mode} "
                    f"rr={bo_sig.rr_ratio:.2f} "
                    f"conf={bo_sig.confidence.score}"
                )
                if bo_sig.confidence.score >= breakout_confidence_threshold:
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
                else:
                    _log_confidence_fail("Breakout", bo_sig.confidence, breakout_confidence_threshold)
                    cycle_data.update({
                        "confidence_score": bo_sig.confidence.score,
                        "confidence_threshold": breakout_confidence_threshold,
                        "confidence_stage": (
                            "multiple"
                            if cycle_data.get("confidence_stage") and cycle_data["confidence_stage"] != "breakout"
                            else "breakout"
                        ),
                        "confidence_breakdown": bo_sig.confidence.breakdown_json,
                        "rr_ratio": bo_sig.rr_ratio,
                        "rr_market": bo_sig.rr_market,
                        "rr_limit": bo_sig.rr_limit,
                        "execution_basis": bo_sig.execution_basis,
                        "final_status": "confidence_fail",
                    })
                    no_signal_reasons.append(
                        f"Breakout confidence {bo_sig.confidence.score} < {breakout_confidence_threshold}"
                    )
            else:
                no_signal_reasons.append("No breakout pattern detected")
        elif signal_dict is None and ctx.operating_mode == 'quiet' and squeeze_active:
            no_signal_reasons.append(_quiet_breakout_blocker_reason(ctx.adx_value))
        elif signal_dict is None and ctx.operating_mode not in {'normal', 'quiet'}:
            no_signal_reasons.append("Breakout disabled in BLOCKED mode")
        elif signal_dict is None and not squeeze_active:
            no_signal_reasons.append("No squeeze active (4H)")

        # ── No signal found ───────────────────────────────────────
        if signal_dict is None:
            logger.info(f"\n❌ No signal this cycle")
            logger.info(f"  Reasons:")
            for reason in no_signal_reasons:
                logger.info(f"    • {reason}")
            logger.info(f"{'='*60}\n")
            if cycle_data["final_status"] == "confidence_fail":
                cycle_data["final_reason"] = "; ".join(no_signal_reasons)
            else:
                cycle_data["final_status"] = "no_signal"
                cycle_data["final_reason"] = "; ".join(no_signal_reasons)
            await _save_cycle_summary_safe(db, cycle_data)
            return None

        cycle_data.update({
            "signal_id": signal_dict["signal_id"],
            "signal_strategy": signal_dict["strategy"],
            "signal_direction": signal_dict["direction"],
            "tp1_price": signal_dict.get("tp1_price"),
            "tp1_rr": signal_dict.get("tp1_rr"),
            "tp1_size_pct": signal_dict.get("tp1_size_pct"),
            "final_tp_size_pct": signal_dict.get("final_tp_size_pct"),
            "rr_ratio": signal_dict["rr_ratio"],
            "rr_market": signal_dict.get("rr_market"),
            "rr_limit": signal_dict.get("rr_limit"),
            "execution_basis": signal_dict.get("execution_basis"),
            "confidence_score": signal_dict["confidence_score"],
            "confidence_breakdown": signal_dict.get("confidence_breakdown"),
        })

        # ── 8. Cooldown check ─────────────────────────────────────
        sig_id = signal_dict["signal_id"]
        if await db.is_on_cooldown(sig_id):
            logger.info(f"\n⏰ Signal {sig_id[:8]}... on cooldown (60 min) — skipping")
            cycle_data["final_status"] = "cooldown"
            cycle_data["final_reason"] = f"Signal {sig_id[:8]} on cooldown"
            cycle_data["cooldown_hit"] = True
            await _save_cycle_summary_safe(db, cycle_data)
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
        cycle_data["final_status"] = "signal"
        cycle_data["final_reason"] = "Signal emitted"
        await _save_cycle_summary_safe(db, cycle_data)

        return signal_dict
    except asyncio.CancelledError:
        logger.error(f"  ❌ [DIAG] Pipeline CANCELLED for {symbol} — likely network timeout")
        cycle_data["final_status"] = "error"
        cycle_data["final_reason"] = "CancelledError (network timeout)"
        await _save_cycle_summary_safe(db, cycle_data)
        return None
    except Exception as e:
        cycle_data["final_status"] = "error"
        cycle_data["final_reason"] = str(e)
        await _save_cycle_summary_safe(db, cycle_data)
        logger.error(f"  ❌ [DIAG] Pipeline error for {symbol}: {e}", exc_info=True)
        return None
