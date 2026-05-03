from pathlib import Path

from fastapi import APIRouter, Query

router = APIRouter(tags=["logs"])

_LOG_PATH = Path("logs") / "bot.log"
_IMPORTANT_PATTERNS = (
    "Signal:",
    "Not tradeable",
    "Sweep signal",
    "Breakout signal",
    "❌ SKIP:",
    "✅ SIGNAL FOUND",
)
_CYCLE_MARKER = "ANALYSIS CYCLE START"


def _tail_lines(path: Path, limit: int) -> list[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        lines = handle.readlines()
    return [line.rstrip("\n") for line in lines[-limit:]]


def _last_cycle(lines: list[str]) -> list[str]:
    last_idx = None
    for idx, line in enumerate(lines):
        if _CYCLE_MARKER in line:
            last_idx = idx
    if last_idx is None:
        return lines
    return lines[last_idx:]


def _cycle_summary(lines: list[str]) -> dict[str, str | None]:
    cycle_lines = _last_cycle(lines)
    tradeable = "unknown"
    blocking_reason = None
    signal_state = "none"

    for i, line in enumerate(cycle_lines):
        # New format: "• Tradeable: False" or old format
        if "Tradeable: True" in line or "tradeable=True" in line:
            tradeable = "tradeable"
        elif "Tradeable: False" in line or "tradeable=False" in line:
            tradeable = "not tradeable"

        # New format: "❌ SKIP: Market not tradeable"
        if "❌ SKIP:" in line or "Not tradeable:" in line:
            tradeable = "not tradeable"
            # Extract blockers from next line (new format has "  Blockers:" on next line)
            if i + 1 < len(cycle_lines) and "Blockers:" in cycle_lines[i + 1]:
                blocking_reason = cycle_lines[i + 1].split("Blockers:", 1)[1].strip()
            elif "❌ SKIP:" in line:
                # Fallback: try to extract from same line
                blocking_reason = line.split("❌ SKIP:", 1)[1].strip()
            elif "Not tradeable:" in line:
                blocking_reason = line.split("Not tradeable:", 1)[1].strip()

        # Signal detection (new and old format)
        if "✅ SIGNAL FOUND" in line or "Signal:" in line:
            signal_state = "final signal"
        elif signal_state != "final signal" and (
            "Sweep signal" in line or "Breakout signal" in line
        ):
            signal_state = "candidate"

    if tradeable == "tradeable":
        blocking_reason = None

    return {
        "tradeable": tradeable,
        "blocking_reason": blocking_reason,
        "signal_state": signal_state,
    }


@router.get("/logs")
async def recent_logs(
    limit: int = Query(default=80, ge=1, le=500),
    important_only: bool = Query(default=False),
    last_cycle_only: bool = Query(default=False),
):
    lines = _tail_lines(_LOG_PATH, limit)
    if last_cycle_only:
        lines = _last_cycle(lines)
    if important_only:
        lines = [line for line in lines if any(pattern in line for pattern in _IMPORTANT_PATTERNS)]
    return {
        "path": str(_LOG_PATH),
        "lines": lines,
        "count": len(lines),
    }


@router.get("/logs/summary")
async def current_cycle_summary():
    lines = _tail_lines(_LOG_PATH, 500)
    summary = _cycle_summary(lines)
    return {
        "path": str(_LOG_PATH),
        **summary,
    }
