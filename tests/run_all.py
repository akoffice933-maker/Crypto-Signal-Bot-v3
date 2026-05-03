import sys, os
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
from tests.test_dual_mode import (test_operating_mode_selection,
    test_blocked_mode_not_tradeable, test_quiet_mode_blocks_disallowed_session,
    test_quiet_mode_allows_configured_session, test_quiet_mode_uses_configured_allowlist,
    test_normal_mode_tradeable, test_dead_zone_remains_not_tradeable)

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
    "Dual-Mode (NEW)":         [test_operating_mode_selection, test_blocked_mode_not_tradeable,
                                 test_quiet_mode_blocks_disallowed_session,
                                 test_quiet_mode_allows_configured_session,
                                 test_quiet_mode_uses_configured_allowlist,
                                 test_normal_mode_tradeable, test_dead_zone_remains_not_tradeable],
}

def main():
    print("=" * 60)
    print("  Crypto Signal Bot — Test Suite")
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
                errors.append((fn.__name__, str(e))); failed += 1
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
