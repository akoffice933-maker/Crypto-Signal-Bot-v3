#!/usr/bin/env python3
"""
Batch parameter sweep for signal replay.

Runs multiple replay configurations and compares results.

Usage:
    python scripts/replay_sweep.py
    python scripts/replay_sweep.py --db data/signals.db --limit 100
    python scripts/replay_sweep.py --experiment A
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.signal_replay import (
    ReplayConfig,
    run_signal_replay,
    summarize_results,
    DEFAULT_DB_PATH,
)

DEFAULT_OUTPUT_DIR = Path("results")

# ── Configuration Grid ─────────────────────────────────────────

CONFIG_GRID = [
    # ── Experiment A: Timeout sweep ────────────────────────────
    {
        "experiment": "A",
        "config_label": "A1",
        "timeout_candles": 20,
        "tp_model": "liquidity",
        "tp_max_pct": None,
        "sl_mult": 0.5,
        "tp1_mult": 2.0,
        "reduced_rr_mult": 3.0,
    },
    {
        "experiment": "A",
        "config_label": "A2",
        "timeout_candles": 30,
        "tp_model": "liquidity",
        "tp_max_pct": None,
        "sl_mult": 0.5,
        "tp1_mult": 2.0,
        "reduced_rr_mult": 3.0,
    },
    {
        "experiment": "A",
        "config_label": "A3",
        "timeout_candles": 40,
        "tp_model": "liquidity",
        "tp_max_pct": None,
        "sl_mult": 0.5,
        "tp1_mult": 2.0,
        "reduced_rr_mult": 3.0,
    },
    {
        "experiment": "A",
        "config_label": "A4",
        "timeout_candles": 60,
        "tp_model": "liquidity",
        "tp_max_pct": None,
        "sl_mult": 0.5,
        "tp1_mult": 2.0,
        "reduced_rr_mult": 3.0,
    },
    # ── Experiment B: TP cap (capped model) ───────────────────
    {
        "experiment": "B",
        "config_label": "B1",
        "timeout_candles": 20,
        "tp_model": "capped",
        "tp_max_pct": 0.8,
        "sl_mult": 0.5,
        "tp1_mult": 2.0,
        "reduced_rr_mult": 3.0,
    },
    {
        "experiment": "B",
        "config_label": "B2",
        "timeout_candles": 20,
        "tp_model": "capped",
        "tp_max_pct": 1.0,
        "sl_mult": 0.5,
        "tp1_mult": 2.0,
        "reduced_rr_mult": 3.0,
    },
    {
        "experiment": "B",
        "config_label": "B3",
        "timeout_candles": 20,
        "tp_model": "capped",
        "tp_max_pct": 1.2,
        "sl_mult": 0.5,
        "tp1_mult": 2.0,
        "reduced_rr_mult": 3.0,
    },
    {
        "experiment": "B",
        "config_label": "B4",
        "timeout_candles": 20,
        "tp_model": "capped",
        "tp_max_pct": 1.5,
        "sl_mult": 0.5,
        "tp1_mult": 2.0,
        "reduced_rr_mult": 3.0,
    },
    # ── Experiment C: SL expansion ────────────────────────────
    {
        "experiment": "C",
        "config_label": "C1",
        "timeout_candles": 20,
        "tp_model": "liquidity",
        "tp_max_pct": None,
        "sl_mult": 0.7,
        "tp1_mult": 2.0,
        "reduced_rr_mult": 3.0,
    },
    {
        "experiment": "C",
        "config_label": "C2",
        "timeout_candles": 20,
        "tp_model": "liquidity",
        "tp_max_pct": None,
        "sl_mult": 0.8,
        "tp1_mult": 2.0,
        "reduced_rr_mult": 3.0,
    },
    {
        "experiment": "C",
        "config_label": "C3",
        "timeout_candles": 20,
        "tp_model": "liquidity",
        "tp_max_pct": None,
        "sl_mult": 1.0,
        "tp1_mult": 2.0,
        "reduced_rr_mult": 3.0,
    },
    # ── Experiment D: Combined ────────────────────────────────
    {
        "experiment": "D",
        "config_label": "D1",
        "timeout_candles": 40,
        "tp_model": "capped",
        "tp_max_pct": 1.0,
        "sl_mult": 0.8,
        "tp1_mult": 2.0,
        "reduced_rr_mult": 3.0,
    },
    {
        "experiment": "D",
        "config_label": "D2",
        "timeout_candles": 60,
        "tp_model": "capped",
        "tp_max_pct": 1.0,
        "sl_mult": 0.8,
        "tp1_mult": 2.0,
        "reduced_rr_mult": 3.0,
    },
    {
        "experiment": "D",
        "config_label": "D3",
        "timeout_candles": 40,
        "tp_model": "reduced_multiple",
        "tp_max_pct": None,
        "sl_mult": 0.8,
        "tp1_mult": 2.0,
        "reduced_rr_mult": 3.0,
    },
]

COMPARISON_COLUMNS = [
    "config_id",
    "experiment",
    "timeout_candles",
    "tp_model",
    "tp_max_pct",
    "sl_mult",
    "tp1_mult",
    "signals_processed",
    "validated",
    "expectancy",
    "profit_factor",
    "sl_rate",
    "timeout_rate",
    "full_tp_rate",
    "tp1_hit_rate",
    "avg_mfe_pct",
    "avg_mae_pct",
    "mfe_mae_ratio",
    "timeout_pnl_median",
    "no_fill_rate",
    "verdict",
]


@dataclass
class SweepResult:
    config: dict[str, Any]
    summary: dict[str, Any]
    results: list[dict[str, Any]] = field(default_factory=list)
    verdict: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch parameter sweep for signal replay")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to SQLite DB")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of signals")
    parser.add_argument("--pair", default=None, help="Filter by pair")
    parser.add_argument("--experiment", default=None, help="Run only specific experiment (A, B, C, D)")
    parser.add_argument("--out", default=None, help="Output directory")
    parser.add_argument("--initial-balance", type=float, default=10_000.0)
    parser.add_argument("--position-pct", type=float, default=0.10)
    return parser.parse_args()


def _config_id(cfg: dict[str, Any]) -> str:
    """Generate unique config ID from parameters."""
    return cfg.get("config_label", f"{cfg['timeout_candles']}_{cfg['tp_model']}_{cfg['sl_mult']}")


def _verdict_icon(verdict_code: str) -> str:
    """Convert verdict code to icon."""
    icons = {
        "PASS": "✅",
        "PARTIAL": "⚠️",
        "FAIL": "❌",
    }
    return icons.get(verdict_code, verdict_code)


def evaluate_success_criteria(summary: dict[str, Any]) -> tuple[str, list[str]]:
    """
    Evaluate configuration against success criteria.
    
    Returns:
        tuple: (verdict_code, list_of_issues)
    """
    issues = []
    
    # P0: Expectancy > 0.5% И Profit Factor > 1.5
    if summary["expectancy"] < 0.5:
        issues.append(f"Expectancy {summary['expectancy']:.2f}% < 0.5%")
    if summary["profit_factor"] < 1.5:
        issues.append(f"Profit Factor {summary['profit_factor']:.2f} < 1.5")
    
    # P1: SL rate < 40%
    if summary["sl_rate"] > 0.40:
        issues.append(f"SL rate {summary['sl_rate']*100:.1f}% > 40%")
    
    # P2: MFE/MAE > 1.5
    if summary["mfe_mae_ratio"] < 1.5:
        issues.append(f"MFE/MAE {summary['mfe_mae_ratio']:.2f} < 1.5")
    
    # Determine verdict
    if not issues:
        return "PASS", []
    elif len(issues) == 1 and ("Expectancy" in issues[0] or "Profit Factor" in issues[0]):
        return "PARTIAL", issues
    else:
        return "FAIL", issues


def run_single_config(
    config: dict[str, Any],
    db_path: str,
    limit: int | None,
    pair: str | None,
    initial_balance: float,
    position_pct: float,
) -> SweepResult:
    """Run replay for a single configuration."""
    config_id = _config_id(config)
    print(f"\n{'='*60}")
    print(f"Running config: {config_id}")
    print(f"  timeout={config['timeout_candles']}, tp_model={config['tp_model']}, "
          f"tp_max={config['tp_max_pct']}, sl_mult={config['sl_mult']}")
    print(f"{'='*60}")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        replay_result = loop.run_until_complete(
            run_signal_replay(
                db_path=db_path,
                limit=limit,
                pair=pair,
                initial_balance=initial_balance,
                position_pct=position_pct,
                max_candles_hold=config["timeout_candles"],
                limit_expiry=2,
                default_basis="limit",
                tp_model=config["tp_model"],
                tp_max_pct=config["tp_max_pct"],
                sl_mult=config["sl_mult"],
                tp1_mult=config["tp1_mult"],
                reduced_rr_mult=config["reduced_rr_mult"],
                config_id=config_id,
                store_db=True,
            )
        )
    finally:
        loop.close()
    
    summary = replay_result["summary"]
    verdict_code, issues = evaluate_success_criteria(summary)
    
    return SweepResult(
        config=config,
        summary=summary,
        results=replay_result["results"],
        verdict=verdict_code,
    )


def write_comparison_csv(
    results: list[SweepResult],
    output_path: Path,
) -> None:
    """Write comparison summary CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    rows = []
    for r in results:
        cfg = r.config
        s = r.summary
        rows.append({
            "config_id": _config_id(cfg),
            "experiment": cfg.get("experiment", ""),
            "timeout_candles": cfg["timeout_candles"],
            "tp_model": cfg["tp_model"],
            "tp_max_pct": cfg["tp_max_pct"] if cfg["tp_max_pct"] is not None else "",
            "sl_mult": cfg["sl_mult"],
            "tp1_mult": cfg["tp1_mult"],
            "signals_processed": s["signals_processed"],
            "validated": s["validated"],
            "expectancy": f"{s['expectancy']:.4f}",
            "profit_factor": f"{s['profit_factor']:.4f}" if s["profit_factor"] not in (0.0, float("inf")) else "inf",
            "sl_rate": f"{s['sl_rate']:.4f}",
            "timeout_rate": f"{s['timeout_rate']:.4f}",
            "full_tp_rate": f"{s['full_tp_rate']:.4f}",
            "tp1_hit_rate": f"{s['tp1_hit_rate']:.4f}",
            "avg_mfe_pct": f"{s['avg_mfe_pct']:.4f}",
            "avg_mae_pct": f"{s['avg_mae_pct']:.4f}",
            "mfe_mae_ratio": f"{s['mfe_mae_ratio']:.4f}",
            "timeout_pnl_median": f"{s['timeout_pnl_median']:.4f}" if s["timeout_pnl_median"] is not None else "",
            "no_fill_rate": f"{s['no_fill'] / s['signals_processed']:.4f}" if s["signals_processed"] else "",
            "verdict": _verdict_icon(r.verdict),
        })
    
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COMPARISON_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_summary_json(
    results: list[SweepResult],
    output_path: Path,
) -> None:
    """Write full summary JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "configs": []
    }
    
    for r in results:
        cfg = r.config
        s = r.summary
        data["configs"].append({
            "config_id": _config_id(cfg),
            "experiment": cfg.get("experiment", ""),
            "parameters": {
                "timeout_candles": cfg["timeout_candles"],
                "tp_model": cfg["tp_model"],
                "tp_max_pct": cfg["tp_max_pct"],
                "sl_mult": cfg["sl_mult"],
                "tp1_mult": cfg["tp1_mult"],
                "reduced_rr_mult": cfg["reduced_rr_mult"],
            },
            "metrics": {
                "signals_processed": s["signals_processed"],
                "validated": s["validated"],
                "no_fill": s["no_fill"],
                "no_data": s["no_data"],
                "insufficient_future_data": s["insufficient_future_data"],
                "full_tp_hits": s["full_tp_hits"],
                "tp1_hits": s["tp1_hits"],
                "sl_hits": s["sl_hits"],
                "timeout_hits": s["timeout_hits"],
                "expectancy": s["expectancy"],
                "profit_factor": s["profit_factor"] if s["profit_factor"] not in (float("inf"),) else None,
                "sl_rate": s["sl_rate"],
                "timeout_rate": s["timeout_rate"],
                "full_tp_rate": s["full_tp_rate"],
                "tp1_hit_rate": s["tp1_hit_rate"],
                "avg_mfe_pct": s["avg_mfe_pct"],
                "avg_mae_pct": s["avg_mae_pct"],
                "mfe_mae_ratio": s["mfe_mae_ratio"],
                "timeout_pnl_median": s["timeout_pnl_median"],
            },
            "verdict": r.verdict,
        })
    
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def print_comparison_table(results: list[SweepResult]) -> None:
    """Print comparison table to console."""
    print("\n" + "=" * 100)
    print("SWEEP RESULTS COMPARISON")
    print("=" * 100)
    
    header = (
        f"{'Config':<8} {'Exp':<4} {'Timeout':>7} {'TP Model':<12} {'TP Max':>6} {'SL':>4} "
        f"{'Exp%':>7} {'PF':>6} {'SL%':>5} {'TO%':>5} {'TP1%':>5} {'MFE/MAE':>7} {'Verdict':>7}"
    )
    print(header)
    print("-" * 100)
    
    for r in results:
        cfg = r.config
        s = r.summary
        pf_str = f"{s['profit_factor']:.2f}" if s["profit_factor"] not in (0.0, float("inf")) else "inf"
        tp_max_str = f"{cfg['tp_max_pct']:.1f}" if cfg["tp_max_pct"] is not None else "—"
        
        print(
            f"{_config_id(cfg):<8} {cfg.get('experiment', ''):<4} {cfg['timeout_candles']:>7} "
            f"{cfg['tp_model']:<12} {tp_max_str:>6} {cfg['sl_mult']:>4.2f} "
            f"{s['expectancy']:>7.2f} {pf_str:>6} {s['sl_rate']*100:>5.1f} {s['timeout_rate']*100:>5.1f} "
            f"{s['tp1_hit_rate']*100:>5.1f} {s['mfe_mae_ratio']:>7.2f} {_verdict_icon(r.verdict):>7}"
        )
    
    print("=" * 100)
    
    # Print best config
    passing = [r for r in results if r.verdict == "PASS"]
    if passing:
        best = max(passing, key=lambda r: r.summary["expectancy"])
        print(f"\n✅ BEST CONFIG: {_config_id(best.config)} (Expectancy: {best.summary['expectancy']:.2f}%)")
    else:
        partial = [r for r in results if r.verdict == "PARTIAL"]
        if partial:
            best = max(partial, key=lambda r: r.summary["expectancy"])
            print(f"\n⚠️ NO PASSING CONFIGS. BEST PARTIAL: {_config_id(best.config)} (Expectancy: {best.summary['expectancy']:.2f}%)")
        else:
            print(f"\n❌ NO PASSING OR PARTIAL CONFIGS FOUND")


async def run_sweep_async(
    configs: list[dict[str, Any]],
    db_path: str,
    limit: int | None,
    pair: str | None,
    initial_balance: float,
    position_pct: float,
) -> list[SweepResult]:
    """Run sweep asynchronously (for future async optimization)."""
    results = []
    for cfg in configs:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            run_single_config,
            cfg,
            db_path,
            limit,
            pair,
            initial_balance,
            position_pct,
        )
        results.append(result)
    return results


def run_sweep(
    db_path: str,
    limit: int | None,
    pair: str | None,
    experiment_filter: str | None,
    out_dir: Path,
    initial_balance: float,
    position_pct: float,
) -> list[SweepResult]:
    """Run full parameter sweep."""
    # Filter configs if experiment specified
    configs = CONFIG_GRID
    if experiment_filter:
        configs = [c for c in configs if c.get("experiment") == experiment_filter]
    
    if not configs:
        raise ValueError(f"No configs found for experiment '{experiment_filter}'")
    
    print(f"\n{'='*60}")
    print(f"SWEEP PARAMETERS")
    print(f"{'='*60}")
    print(f"DB: {db_path}")
    print(f"Signal limit: {limit if limit else 'all'}")
    print(f"Pair filter: {pair if pair else 'all'}")
    print(f"Experiment filter: {experiment_filter if experiment_filter else 'all'}")
    print(f"Configs to run: {len(configs)}")
    print(f"{'='*60}")
    
    results = []
    for cfg in configs:
        result = run_single_config(
            config=cfg,
            db_path=db_path,
            limit=limit,
            pair=pair,
            initial_balance=initial_balance,
            position_pct=position_pct,
        )
        results.append(result)
    
    return results


def main() -> int:
    args = parse_args()
    
    out_dir = Path(args.out) if args.out else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    
    results = run_sweep(
        db_path=args.db,
        limit=args.limit,
        pair=args.pair,
        experiment_filter=args.experiment,
        out_dir=out_dir,
        initial_balance=args.initial_balance,
        position_pct=args.position_pct,
    )
    
    # Write outputs
    comparison_path = out_dir / f"replay_comparison_{timestamp}.csv"
    summary_path = out_dir / f"replay_summary_{timestamp}.json"
    
    write_comparison_csv(results, comparison_path)
    write_summary_json(results, summary_path)
    
    print_comparison_table(results)
    
    print(f"\n📁 Comparison CSV: {comparison_path}")
    print(f"📁 Summary JSON: {summary_path}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
