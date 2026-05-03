"""
Tests for replay_sweep.py success criteria evaluation.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.replay_sweep import evaluate_success_criteria


def test_evaluate_success_criteria_pass():
    """Test configuration that passes all criteria."""
    summary = {
        "expectancy": 0.72,
        "profit_factor": 1.82,
        "sl_rate": 0.32,
        "mfe_mae_ratio": 2.1,
    }
    verdict, issues = evaluate_success_criteria(summary)
    assert verdict == "PASS"
    assert len(issues) == 0


def test_evaluate_success_criteria_low_expectancy():
    """Test configuration with low expectancy (single P0 issue -> PARTIAL)."""
    summary = {
        "expectancy": 0.3,
        "profit_factor": 1.8,
        "sl_rate": 0.35,
        "mfe_mae_ratio": 1.8,
    }
    verdict, issues = evaluate_success_criteria(summary)
    assert verdict == "PARTIAL"
    assert len(issues) == 1
    assert any("Expectancy" in issue for issue in issues)


def test_evaluate_success_criteria_low_pf():
    """Test configuration with low profit factor (single P0 issue -> PARTIAL)."""
    summary = {
        "expectancy": 0.6,
        "profit_factor": 1.2,
        "sl_rate": 0.35,
        "mfe_mae_ratio": 1.8,
    }
    verdict, issues = evaluate_success_criteria(summary)
    assert verdict == "PARTIAL"
    assert len(issues) == 1
    assert any("Profit Factor" in issue for issue in issues)


def test_evaluate_success_criteria_high_sl_rate():
    """Test configuration with high SL rate."""
    summary = {
        "expectancy": 0.6,
        "profit_factor": 1.6,
        "sl_rate": 0.45,
        "mfe_mae_ratio": 1.8,
    }
    verdict, issues = evaluate_success_criteria(summary)
    assert verdict == "FAIL"
    assert any("SL rate" in issue for issue in issues)


def test_evaluate_success_criteria_low_mfe_mae():
    """Test configuration with low MFE/MAE ratio."""
    summary = {
        "expectancy": 0.6,
        "profit_factor": 1.6,
        "sl_rate": 0.35,
        "mfe_mae_ratio": 1.2,
    }
    verdict, issues = evaluate_success_criteria(summary)
    assert verdict == "FAIL"
    assert any("MFE/MAE" in issue for issue in issues)


def test_evaluate_success_criteria_partial():
    """Test configuration that partially passes (only expectancy issue)."""
    summary = {
        "expectancy": 0.3,
        "profit_factor": 1.8,
        "sl_rate": 0.35,
        "mfe_mae_ratio": 1.8,
    }
    verdict, issues = evaluate_success_criteria(summary)
    assert verdict == "PARTIAL"
    assert len(issues) == 1


def test_evaluate_success_criteria_multiple_issues():
    """Test configuration with multiple issues."""
    summary = {
        "expectancy": 0.2,
        "profit_factor": 1.1,
        "sl_rate": 0.50,
        "mfe_mae_ratio": 1.0,
    }
    verdict, issues = evaluate_success_criteria(summary)
    assert verdict == "FAIL"
    assert len(issues) == 4


if __name__ == "__main__":
    test_evaluate_success_criteria_pass()
    test_evaluate_success_criteria_low_expectancy()
    test_evaluate_success_criteria_low_pf()
    test_evaluate_success_criteria_high_sl_rate()
    test_evaluate_success_criteria_low_mfe_mae()
    test_evaluate_success_criteria_partial()
    test_evaluate_success_criteria_multiple_issues()
    print("[OK] replay_sweep success criteria tests passed")
