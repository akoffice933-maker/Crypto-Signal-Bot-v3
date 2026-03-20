import sys, os, traceback
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_confidence    import (test_minimum_sweep_score, test_all_bonuses,
    test_funding_block_long, test_funding_block_short, test_no_session_penalty,
    test_adx_counter_trend_penalty, test_session_no_double_count,
    test_cvd_wrong_direction_no_bonus)
from tests.test_liquidity_map import (test_basic_cluster, test_min_touches_filter,
    test_tolerance_separation, test_detect_equal_highs, test_detect_equal_lows,
    test_strength_tf_weight, test_select_target_long, test_select_target_short,
    test_no_target_all_too_close, test_1d_preferred_over_4h)
from tests.test_market_state  import (test_session_priority_overlap, test_session_asian,
    test_session_ny, test_between_sessions, test_low_volatility_not_tradeable,
    test_dead_zone_not_tradeable, test_tradeable_conditions)
from tests.test_sweep_pattern import (test_long_rejection_valid, test_short_rejection_valid,
    test_rejection_fails_large_body, test_rejection_fails_small_wick,
    test_doji_is_rejection, test_wrong_wick_direction,
    test_counter_trend_requires_opposite_bias,
    test_candle_parts_bull, test_candle_parts_bear)
from tests.test_no_lookahead  import test_no_lookahead_bias
from tests.test_runtime_and_routes import (
    test_apply_cli_overrides_enables_testnet,
    test_validate_runtime_config_requires_telegram_token,
    test_liquidity_route_uses_current_price,
    test_liquidity_route_without_current_price,
)
from tests.test_integration import (
    test_health_endpoint_exposes_metrics,
    test_signals_endpoints_return_seeded_data,
    test_metrics_endpoint_returns_prometheus_text,
    test_logs_endpoint_and_dashboard_log_panel,
    test_dashboard_and_csv_export_routes,
    test_root_redirect_and_browser_assets,
    test_google_sheets_export_route_uses_sync_service,
)
from tests.test_exports_and_notifier import (
    test_render_signals_csv_contains_headers_and_rows,
    test_telegram_rate_limit_guard_waits_between_messages,
    test_telegram_start_text_contains_mode_and_chat_id,
)

SUITES = {
    "Confidence Score":        [test_minimum_sweep_score, test_all_bonuses,
                                 test_funding_block_long, test_funding_block_short,
                                 test_no_session_penalty, test_adx_counter_trend_penalty,
                                 test_session_no_double_count, test_cvd_wrong_direction_no_bonus],
    "Liquidity Map":           [test_basic_cluster, test_min_touches_filter,
                                 test_tolerance_separation, test_detect_equal_highs,
                                 test_detect_equal_lows, test_strength_tf_weight,
                                 test_select_target_long, test_select_target_short,
                                 test_no_target_all_too_close, test_1d_preferred_over_4h],
    "Market State & Sessions": [test_session_priority_overlap, test_session_asian,
                                 test_session_ny, test_between_sessions,
                                 test_low_volatility_not_tradeable, test_dead_zone_not_tradeable,
                                 test_tradeable_conditions],
    "Sweep Pattern (Pin-bar)": [test_long_rejection_valid, test_short_rejection_valid,
                                 test_rejection_fails_large_body, test_rejection_fails_small_wick,
                                 test_doji_is_rejection, test_wrong_wick_direction,
                                 test_counter_trend_requires_opposite_bias,
                                 test_candle_parts_bull, test_candle_parts_bear],
    "Backtester (Look-ahead)": [test_no_lookahead_bias],
    "Runtime & API":           [test_apply_cli_overrides_enables_testnet,
                                 test_validate_runtime_config_requires_telegram_token,
                                 test_liquidity_route_uses_current_price,
                                 test_liquidity_route_without_current_price],
    "Integration":             [test_health_endpoint_exposes_metrics,
                                 test_signals_endpoints_return_seeded_data,
                                 test_metrics_endpoint_returns_prometheus_text,
                                 test_logs_endpoint_and_dashboard_log_panel,
                                 test_dashboard_and_csv_export_routes,
                                 test_root_redirect_and_browser_assets,
                                 test_google_sheets_export_route_uses_sync_service],
    "Exports & Notifier":      [test_render_signals_csv_contains_headers_and_rows,
                                 test_telegram_rate_limit_guard_waits_between_messages,
                                 test_telegram_start_text_contains_mode_and_chat_id],
}

def _configure_output_encoding():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")

def main():
    _configure_output_encoding()
    print("=" * 60)
    print("  Crypto Signal Bot — Final — Test Suite")
    print("=" * 60)
    total = passed = failed = 0
    errors = []
    for suite, tests in SUITES.items():
        print(f"\n── {suite} ({'─'*(54-len(suite))})")
        for fn in tests:
            total += 1
            label = fn.__name__.replace("test_","").replace("_"," ")
            try:
                fn()
                print(f"  ✅  {label}")
                passed += 1
            except AssertionError as e:
                print(f"  ❌  {label}\n       {e}")
                errors.append((fn.__name__, str(e))); failed += 1
            except Exception as e:
                print(f"  💥  {label}  [{type(e).__name__}]")
                errors.append((fn.__name__, traceback.format_exc())); failed += 1
    print(f"\n{'='*60}")
    print(f"  {passed} passed  |  {failed} failed  |  {total} total")
    print("=" * 60)
    if errors:
        for name, msg in errors:
            print(f"\n── {name}\n{msg}")
        sys.exit(1)
    else:
        print("\n✅  All tests passed — bot_final ready")
        sys.exit(0)

if __name__ == "__main__":
    main()
