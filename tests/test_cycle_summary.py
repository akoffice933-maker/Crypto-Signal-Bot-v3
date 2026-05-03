import asyncio
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from shutil import rmtree
from types import SimpleNamespace
from uuid import uuid4

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import Database
import engine.pipeline as pipeline


class _FakeClient:
    async def get_premium_index(self, _symbol):
        return {"lastFundingRate": "0.0001"}

    async def get_open_interest(self, _symbol):
        return {"openInterest": "12345"}


class _FakeWS:
    is_connected = False

    def cvd_divergence(self):
        return None


def _candles():
    def _df(periods, freq, start):
        return pd.DataFrame(
            {
                "open": [70000.0] * periods,
                "high": [70100.0] * periods,
                "low": [69900.0] * periods,
                "close": [70050.0] * periods,
                "volume": [1000.0] * periods,
            },
            index=pd.date_range(start, periods=periods, freq=freq),
        )

    df_15m = _df(30, "15min", "2026-03-25")
    df_4h = _df(540, "4h", "2025-12-25")
    df_1d = _df(90, "1D", "2025-12-26")
    return {"15m": df_15m, "4h": df_4h, "1d": df_1d}


def _ctx(**overrides):
    defaults = dict(
        market_state="ranging",
        volatility_regime="quiet",
        adx_value=19.0,
        atr_pct=0.003,
        session="ny",
        hour_utc=13,
        tradeable=True,
        operating_mode="quiet",
        trend_direction=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _confidence(score, label="Liquidity sweep confirmed"):
    return SimpleNamespace(
        score=score,
        breakdown_json=[{"factor": label, "delta": 30}],
        factors=[SimpleNamespace(label=label, delta=30)],
    )


def _sweep_signal(score=75):
    return SimpleNamespace(
        direction="SHORT",
        entry_market=71692.90,
        entry_limit=71645.30,
        stop_loss=72003.83,
        tp1_price=70928.24,
        tp1_rr=2.0,
        tp1_size_pct=0.5,
        final_tp_size_pct=0.5,
        take_profit=70357.42,
        rr_ratio=4.3,
        rr_market=4.3,
        rr_limit=4.87,
        execution_basis="limit",
        volume_spike=True,
        confidence=_confidence(score),
    )


def _signal_dict():
    return {
        "signal_id": "sig12345abcd",
        "pair": "BTCUSDT",
        "strategy": "sweep_reversal",
        "direction": "SHORT",
        "session": "ny",
        "entry_market": 71692.90,
        "entry_limit": 71645.30,
        "stop_loss": 72003.83,
        "tp1_price": 70928.24,
        "tp1_rr": 2.0,
        "tp1_size_pct": 0.5,
        "final_tp_size_pct": 0.5,
        "take_profit": 70357.42,
        "rr_ratio": 4.3,
        "rr_market": 4.3,
        "rr_limit": 4.87,
        "execution_basis": "limit",
        "position_size_pct": None,
        "confidence_score": 75,
        "confidence_breakdown": '[{"factor":"Liquidity sweep confirmed","delta":30}]',
        "market_state": "ranging",
        "volatility_regime": "quiet",
        "adx_value": 19.0,
        "atr_pct": 0.003,
        "target_liquidity_price": 70357.42,
        "target_liquidity_tf": "1d",
        "target_liquidity_type": "equal_lows",
        "distance_to_target_pct": 0.018,
        "cvd_divergence": None,
        "oi_change_pct": 0.2,
        "liquidation_cascade": False,
        "funding_rate": 0.0001,
        "squeeze_active": False,
    }


def _breakout_signal(score=70):
    return SimpleNamespace(
        direction="LONG",
        entry_market=70125.50,
        stop_loss=69740.00,
        tp1_price=70896.50,
        tp1_rr=2.0,
        tp1_size_pct=0.5,
        final_tp_size_pct=0.5,
        take_profit=72229.27,
        rr_ratio=2.4,
        rr_market=2.4,
        rr_limit=None,
        execution_basis="market",
        sl_pct_used=0.0055,
        sl_pct_raw=0.0049,
        sl_mode="adaptive_raw",
        breakout_type="bb_upper",
        confidence=_confidence(score, label="Squeeze breakout confirmed"),
    )


def _breakout_signal_dict():
    return {
        "signal_id": "break12345abcd",
        "pair": "BTCUSDT",
        "strategy": "breakout",
        "direction": "LONG",
        "session": "london",
        "entry_market": 70125.50,
        "entry_limit": None,
        "stop_loss": 69740.00,
        "tp1_price": 70896.50,
        "tp1_rr": 2.0,
        "tp1_size_pct": 0.5,
        "final_tp_size_pct": 0.5,
        "take_profit": 72229.27,
        "rr_ratio": 2.4,
        "rr_market": 2.4,
        "rr_limit": None,
        "execution_basis": "market",
        "position_size_pct": None,
        "confidence_score": 70,
        "confidence_breakdown": '[{"factor":"Squeeze breakout confirmed","delta":30}]',
        "market_state": "trending",
        "volatility_regime": "quiet",
        "adx_value": 35.0,
        "atr_pct": 0.003,
        "target_liquidity_price": None,
        "target_liquidity_tf": None,
        "target_liquidity_type": None,
        "distance_to_target_pct": None,
        "cvd_divergence": None,
        "oi_change_pct": 0.2,
        "liquidation_cascade": False,
        "funding_rate": 0.0001,
        "squeeze_active": True,
    }


def _fetch_summary(db: Database):
    row = asyncio.run(
        db._fetch_one(
            """
            SELECT final_status, blocker_reason, final_reason, confidence_stage,
                   cooldown_hit, signal_id, signal_strategy, signal_direction
            FROM cycle_summary
            ORDER BY id DESC
            LIMIT 1
            """
        )
    )
    return row


@contextmanager
def _test_db():
    tmp_root = Path(__file__).resolve().parent / "_tmp_cycle_summary"
    tmp_dir = tmp_root / uuid4().hex
    tmp_dir.mkdir(parents=True, exist_ok=True)
    db = Database(str(tmp_dir / "test.db"))
    try:
        asyncio.run(db.connect())
        yield db
    finally:
        asyncio.run(db.close())
        if tmp_dir.exists():
            rmtree(tmp_dir, ignore_errors=True)


def test_save_cycle_summary_smoke():
    with _test_db() as db:
            asyncio.run(
                db.save_cycle_summary(
                    {
                        "cycle_id": "BTCUSDT-20260325130000",
                        "created_at": "2026-03-25 13:00:00",
                        "pair": "BTCUSDT",
                        "analysis_time_utc": "2026-03-25 13:00:00 UTC",
                        "session": "ny",
                        "hour_utc": 13,
                        "market_state": "ranging",
                        "volatility_regime": "quiet",
                        "operating_mode": "quiet",
                        "tradeable": 1,
                        "adx_value": 19.0,
                        "atr_pct": 0.003,
                        "current_price": 70000.0,
                        "candles_15m": 200,
                        "candles_4h": 540,
                        "candles_1d": 90,
                        "liquidity_levels_found": 10,
                        "liquidity_levels_eligible": 4,
                        "liquidity_levels_filtered": 6,
                        "squeeze_active": 0,
                        "funding_rate": 0.0,
                        "oi_change_pct": None,
                        "liquidation_cascade": 0,
                        "cvd_divergence": None,
                        "sweep_candidate": 0,
                        "breakout_candidate": 0,
                        "confidence_score": None,
                        "confidence_threshold": 60,
                        "confidence_stage": None,
                        "confidence_breakdown": [],
                        "final_status": "no_signal",
                        "final_reason": "No sweep reversal pattern detected",
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
                        "cooldown_hit": 0,
                        "strategy_version": "v4-hybrid",
                    }
                )
            )
            row = asyncio.run(
                db._fetch_one("SELECT final_status FROM cycle_summary WHERE cycle_id=?", ("BTCUSDT-20260325130000",))
            )
            assert row[0] == "no_signal"


def test_cycle_summary_skip(monkeypatch):
    with _test_db() as db:
            monkeypatch.setattr(pipeline, "load_candles", lambda *args, **kwargs: asyncio.sleep(0, result=_candles()))
            monkeypatch.setattr(pipeline, "get_market_context", lambda _df: _ctx(tradeable=False, session=None, market_state="dead_zone", adx_value=22.0))

            asyncio.run(pipeline.run_pipeline(_FakeClient(), db, _FakeWS(), None))
            row = _fetch_summary(db)
            assert row[0] == "skip"
            assert "ADX dead zone" in row[1]


def test_cycle_summary_no_signal(monkeypatch):
    with _test_db() as db:
            monkeypatch.setattr(pipeline, "load_candles", lambda *args, **kwargs: asyncio.sleep(0, result=_candles()))
            monkeypatch.setattr(pipeline, "get_market_context", lambda _df: _ctx())
            monkeypatch.setattr(pipeline, "build_liquidity_map", lambda *_args, **_kwargs: [])
            monkeypatch.setattr(pipeline, "is_squeeze", lambda _df: False)
            monkeypatch.setattr(pipeline, "check_sweep_reversal", lambda **_kwargs: None)

            asyncio.run(pipeline.run_pipeline(_FakeClient(), db, _FakeWS(), None))
            row = _fetch_summary(db)
            assert row[0] == "no_signal"
            assert "No sweep reversal pattern detected" in row[2]
            assert "No squeeze active (4H)" in row[2]


def test_cycle_summary_confidence_fail(monkeypatch):
    with _test_db() as db:
            monkeypatch.setattr(pipeline, "load_candles", lambda *args, **kwargs: asyncio.sleep(0, result=_candles()))
            monkeypatch.setattr(pipeline, "get_market_context", lambda _df: _ctx())
            monkeypatch.setattr(pipeline, "build_liquidity_map", lambda *_args, **_kwargs: [])
            monkeypatch.setattr(pipeline, "is_squeeze", lambda _df: False)
            monkeypatch.setattr(pipeline, "check_sweep_reversal", lambda **_kwargs: _sweep_signal(score=55))

            asyncio.run(pipeline.run_pipeline(_FakeClient(), db, _FakeWS(), None))
            row = _fetch_summary(db)
            assert row[0] == "confidence_fail"
            assert row[3] == "sweep"


def test_cycle_summary_cooldown(monkeypatch):
    with _test_db() as db:
            monkeypatch.setattr(pipeline, "load_candles", lambda *args, **kwargs: asyncio.sleep(0, result=_candles()))
            monkeypatch.setattr(pipeline, "get_market_context", lambda _df: _ctx())
            monkeypatch.setattr(pipeline, "build_liquidity_map", lambda *_args, **_kwargs: [])
            monkeypatch.setattr(pipeline, "is_squeeze", lambda _df: False)
            monkeypatch.setattr(pipeline, "check_sweep_reversal", lambda **_kwargs: _sweep_signal(score=75))
            monkeypatch.setattr(pipeline, "sweep_to_dict", lambda *_args, **_kwargs: _signal_dict())

            async def _cooldown(_sig_id):
                return True

            monkeypatch.setattr(db, "is_on_cooldown", _cooldown)

            asyncio.run(pipeline.run_pipeline(_FakeClient(), db, _FakeWS(), None))
            row = _fetch_summary(db)
            assert row[0] == "cooldown"
            assert row[4] == 1
            assert row[5] == "sig12345abcd"


def test_cycle_summary_signal(monkeypatch):
    with _test_db() as db:
            monkeypatch.setattr(pipeline, "load_candles", lambda *args, **kwargs: asyncio.sleep(0, result=_candles()))
            monkeypatch.setattr(pipeline, "get_market_context", lambda _df: _ctx())
            monkeypatch.setattr(pipeline, "build_liquidity_map", lambda *_args, **_kwargs: [])
            monkeypatch.setattr(pipeline, "is_squeeze", lambda _df: False)
            monkeypatch.setattr(pipeline, "check_sweep_reversal", lambda **_kwargs: _sweep_signal(score=75))
            monkeypatch.setattr(pipeline, "sweep_to_dict", lambda *_args, **_kwargs: _signal_dict())

            async def _no_cooldown(_sig_id):
                return False

            monkeypatch.setattr(db, "is_on_cooldown", _no_cooldown)

            signal = asyncio.run(pipeline.run_pipeline(_FakeClient(), db, _FakeWS(), None))
            row = _fetch_summary(db)
            count = asyncio.run(db._fetch_one("SELECT COUNT(*) FROM signals"))
            assert signal is not None
            assert row[0] == "signal"
            assert row[5] == "sig12345abcd"
            assert count[0] == 1


def test_cycle_summary_quiet_breakout_signal(monkeypatch):
    with _test_db() as db:
            monkeypatch.setattr(pipeline, "load_candles", lambda *args, **kwargs: asyncio.sleep(0, result=_candles()))
            monkeypatch.setattr(
                pipeline,
                "get_market_context",
                lambda _df: _ctx(market_state="trending", adx_value=35.0, session="london", operating_mode="quiet"),
            )
            monkeypatch.setattr(pipeline, "build_liquidity_map", lambda *_args, **_kwargs: [])
            monkeypatch.setattr(pipeline, "is_squeeze", lambda _df: True)
            monkeypatch.setattr(pipeline, "check_sweep_reversal", lambda **_kwargs: None)
            monkeypatch.setattr(pipeline, "check_breakout", lambda **_kwargs: _breakout_signal(score=70))
            monkeypatch.setattr(pipeline, "breakout_to_dict", lambda *_args, **_kwargs: _breakout_signal_dict())

            async def _no_cooldown(_sig_id):
                return False

            monkeypatch.setattr(db, "is_on_cooldown", _no_cooldown)

            signal = asyncio.run(pipeline.run_pipeline(_FakeClient(), db, _FakeWS(), None))
            row = _fetch_summary(db)
            count = asyncio.run(db._fetch_one("SELECT COUNT(*) FROM signals"))
            assert signal is not None
            assert row[0] == "signal"
            assert row[6] == "breakout"
            assert count[0] == 1


def test_cycle_summary_error(monkeypatch):
    with _test_db() as db:
            async def _boom(*_args, **_kwargs):
                raise RuntimeError("candle failure")

            monkeypatch.setattr(pipeline, "load_candles", _boom)

            asyncio.run(pipeline.run_pipeline(_FakeClient(), db, _FakeWS(), None))
            row = _fetch_summary(db)
            assert row[0] == "error"
            assert "candle failure" in row[2]
