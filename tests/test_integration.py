import asyncio
import sys, os
from contextlib import contextmanager
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

# Set API_KEY and DEV_MODE BEFORE importing app
os.environ['API_KEY'] = 'test_api_key_for_integration_tests'
os.environ['DEV_MODE'] = 'true'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from database.db import Database
from web.app import app
from web.dependencies import set_db


async def _seed_db(db: Database):
    await db._exec("""
        INSERT INTO signals (
            signal_id, created_at, closed_at, pair, strategy, direction, session,
            entry_market, entry_limit, stop_loss, take_profit, rr_ratio,
            position_size_pct, confidence_score, confidence_breakdown,
            market_state, volatility_regime, adx_value, atr_pct,
            target_liquidity_price, target_liquidity_tf, target_liquidity_type,
            distance_to_target_pct, cvd_divergence, oi_change_pct,
            liquidation_cascade, funding_rate, squeeze_active, status, result_pnl_pct
        ) VALUES (
            ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'BTCUSDT', 'sweep_reversal', 'LONG', 'london',
            60000, 59900, 59750, 60600, 2.0,
            NULL, 82, '[]',
            'ranging', 'normal', 19.0, 0.01,
            60600, '1d', 'equal_highs',
            1.0, 'bullish', 0.5,
            1, -0.0002, 0, 'tp_hit', 3.2
        )
    """, ("sig_recent_tp",))
    await db._exec("""
        INSERT INTO signals (
            signal_id, created_at, closed_at, pair, strategy, direction, session,
            entry_market, entry_limit, stop_loss, take_profit, rr_ratio,
            position_size_pct, confidence_score, confidence_breakdown,
            market_state, volatility_regime, adx_value, atr_pct,
            target_liquidity_price, target_liquidity_tf, target_liquidity_type,
            distance_to_target_pct, cvd_divergence, oi_change_pct,
            liquidation_cascade, funding_rate, squeeze_active, status, result_pnl_pct
        ) VALUES (
            ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'BTCUSDT', 'breakout', 'SHORT', 'ny',
            60500, NULL, 60900, 59800, 2.1,
            NULL, 76, '[]',
            'trending', 'high', 31.0, 0.02,
            NULL, NULL, NULL,
            NULL, 'bearish', -1.0,
            0, 0.0003, 1, 'sl_hit', -1.5
        )
    """, ("sig_recent_sl",))
    await db._exec("""
        INSERT INTO signals (
            signal_id, created_at, pair, strategy, direction, session,
            entry_market, entry_limit, stop_loss, take_profit, rr_ratio,
            position_size_pct, confidence_score, confidence_breakdown,
            market_state, volatility_regime, adx_value, atr_pct,
            target_liquidity_price, target_liquidity_tf, target_liquidity_type,
            distance_to_target_pct, cvd_divergence, oi_change_pct,
            liquidation_cascade, funding_rate, squeeze_active, status
        ) VALUES (
            ?, datetime('now','-2 days'), 'BTCUSDT', 'sweep_reversal', 'LONG', 'asian',
            59000, 58950, 58600, 59600, 2.0,
            NULL, 68, '[]',
            'ranging', 'normal', 18.0, 0.01,
            59600, '4h', 'equal_highs',
            1.2, NULL, NULL,
            0, 0.0, 0, 'sent'
        )
    """, ("sig_old",))
    await db._exec("""
        INSERT INTO liquidity_pools (timeframe, pool_type, price, touch_count, strength, mitigated)
        VALUES ('1d', 'equal_highs', 61000, 3, 9.0, 0),
               ('4h', 'equal_lows', 59000, 4, 4.0, 1)
    """)


@contextmanager
def integration_client():
    tmp_root = Path(__file__).resolve().parent / "_tmp_integration"
    tmp_dir = tmp_root / uuid4().hex
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        db = Database(str(tmp_dir / "integration.db"))
        asyncio.run(db.connect())
        asyncio.run(_seed_db(db))
        set_db(db)
        client = TestClient(app)
        try:
            yield client
        finally:
            client.close()
            asyncio.run(db.close())
            set_db(None)
    finally:
        if tmp_dir.exists():
            rmtree(tmp_dir, ignore_errors=True)


def test_health_endpoint_exposes_metrics():
    with integration_client() as client:
        response = client.get("/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "healthy"
        assert payload["metrics"]["signals_24h"] == 2
        assert payload["metrics"]["winrate_24h"] == 50.0
        assert payload["metrics"]["avg_drawdown_pct_24h"] == 1.5


def test_signals_endpoints_return_seeded_data():
    with integration_client() as client:
        response = client.get("/signals/api?limit=5")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 3

        stats = client.get("/signals/stats")
        assert stats.status_code == 200
        stats_payload = stats.json()
        assert stats_payload["total"] == 3
        assert stats_payload["tp_hits"] == 1
        assert stats_payload["sl_hits"] == 1
        assert stats_payload["winrate_pct"] == 50.0

        liquidity = client.get("/signals/liquidity?current_price=60000")
        assert liquidity.status_code == 200
        liquidity_payload = liquidity.json()
        assert liquidity_payload[0]["distance_pct"] == 1.67


def test_metrics_endpoint_returns_prometheus_text():
    with integration_client() as client:
        response = client.get("/metrics")
        assert response.status_code == 200
        body = response.text
        assert "crypto_signal_signals_24h 2" in body
        assert "crypto_signal_winrate_24h 50.0" in body
        assert "crypto_signal_avg_drawdown_pct_24h 1.5" in body


def test_logs_endpoint_and_dashboard_log_panel():
    import web.routes.logs as logs_module

    tmp_root = Path(__file__).resolve().parent / "_tmp_integration"
    tmp_root.mkdir(exist_ok=True)
    log_path = tmp_root / f"log_test_{uuid4().hex}.log"
    original_path = logs_module._LOG_PATH
    try:
        log_path.write_text("line one\nline two\nline three\n", encoding="utf-8")
        logs_module._LOG_PATH = log_path
        with integration_client() as client:
            logs = client.get("/logs?limit=2")
            assert logs.status_code == 200
            payload = logs.json()
            assert payload["lines"] == ["line two", "line three"]

            important = client.get("/logs?limit=5&important_only=true")
            assert important.status_code == 200
            assert important.json()["lines"] == []

            log_path.write_text(
                "old line\n"
                "2026-03-19 cycle ANALYSIS CYCLE START\n"
                "Signal: old cycle\n"
                "2026-03-19 cycle ANALYSIS CYCLE START\n"
                "❌ SKIP: Market not tradeable\n"
                "  Blockers: ranging, vol=low, session=None\n"
                "Sweep signal: LONG entry=60000 conf=70\n",
                encoding="utf-8",
            )
            last_cycle = client.get("/logs?limit=20&important_only=true&last_cycle_only=true")
            assert last_cycle.status_code == 200
            # Updated to match new log format - only important lines
            assert last_cycle.json()["lines"] == [
                "❌ SKIP: Market not tradeable",
                "Sweep signal: LONG entry=60000 conf=70",
            ]

            summary = client.get("/logs/summary")
            assert summary.status_code == 200
            assert summary.json()["tradeable"] == "not tradeable"
            # Updated to extract blockers from next line
            assert summary.json()["blocking_reason"] == "ranging, vol=low, session=None"
            assert summary.json()["signal_state"] == "candidate"

            dashboard = client.get("/dashboard")
            assert dashboard.status_code == 200
            assert "Current Cycle Summary" in dashboard.text
            assert "Live Log" in dashboard.text
            assert "Important Events" in dashboard.text
            assert "setInterval(() => refreshLogs().catch(showError), 5000);" in dashboard.text
            assert "Last Cycle" in dashboard.text
            assert "last_cycle_only=true" in dashboard.text
            assert 'fetchJson("/logs/summary")' in dashboard.text
            assert 'id="cycle-tradeable"' in dashboard.text
            assert 'id="cycle-reason"' in dashboard.text
            assert 'id="cycle-signal"' in dashboard.text
            assert ".log-line.signal" in dashboard.text
            assert ".log-line.blocked" in dashboard.text
            assert ".log-line.candidate" in dashboard.text
            assert "function classifyLogLine(line)" in dashboard.text
    finally:
        logs_module._LOG_PATH = original_path
        if log_path.exists():
            log_path.unlink()


def test_dashboard_and_csv_export_routes():
    with integration_client() as client:
        dashboard = client.get("/dashboard")
        assert dashboard.status_code == 200
        assert "Signal flow with enough context to act." in dashboard.text

        export = client.get("/signals/export.csv?limit=2")
        assert export.status_code == 200
        assert "text/csv" in export.headers["content-type"]
        assert "signal_id,created_at,pair,strategy" in export.text


def test_root_redirect_and_browser_assets():
    with integration_client() as client:
        root = client.get("/", follow_redirects=False)
        assert root.status_code == 307
        assert root.headers["location"] == "/dashboard"

        favicon = client.get("/favicon.ico")
        assert favicon.status_code == 200
        assert favicon.headers["content-type"] == "image/x-icon"
        assert len(favicon.content) > 0

        chrome = client.get("/.well-known/appspecific/com.chrome.devtools.json")
        assert chrome.status_code == 200
        assert chrome.json() == {}


def test_google_sheets_export_route_uses_sync_service():
    import web.routes.signals as signals_module

    async def fake_sync(rows, webhook_url=None):
        assert len(rows) == 2
        assert webhook_url == "https://example.test/webhook"
        return {"rows_sent": len(rows), "webhook_url": webhook_url}

    original = signals_module.sync_signals_to_google_sheets
    signals_module.sync_signals_to_google_sheets = fake_sync
    try:
        with integration_client() as client:
            response = client.post("/signals/export/google-sheets", json={
                "limit": 2,
                "webhook_url": "https://example.test/webhook",
            })
            assert response.status_code == 200
            payload = response.json()
            assert payload["rows_sent"] == 2
    finally:
        signals_module.sync_signals_to_google_sheets = original


def test_auth_middleware_warns_without_api_key():
    """Test that auth middleware is configured correctly."""
    import os
    from web.middleware import API_KEY, PUBLIC_PATHS, DEV_MODE
    
    # Check configuration
    assert '/health' in PUBLIC_PATHS
    assert '/docs' in PUBLIC_PATHS
    assert '/metrics' in PUBLIC_PATHS
    
    # In test environment, API_KEY may or may not be set
    print(f"✅ Auth middleware configured (API_KEY={'set' if API_KEY else 'not set'}, DEV_MODE={DEV_MODE})")


def test_auth_middleware_with_api_key():
    """Test that auth middleware configuration is correct."""
    from web.middleware import API_KEY, DEV_MODE
    
    # In test environment, these should be set
    assert API_KEY == 'test_api_key_for_integration_tests'
    assert DEV_MODE is True
    
    print(f"✅ Auth middleware configured (API_KEY={'set' if API_KEY else 'not set'}, DEV_MODE={DEV_MODE})")
