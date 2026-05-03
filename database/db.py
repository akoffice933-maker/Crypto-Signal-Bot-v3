import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Database:
    def __init__(self, db_path: str = "data/signals.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[aiosqlite.Connection] = None

    # ── Lifecycle ─────────────────────────────────────────────

    async def connect(self):
        self._conn = await aiosqlite.connect(
            self.db_path, timeout=30.0, isolation_level=None
        )
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.execute("PRAGMA cache_size=-64000")
        await self._conn.execute("PRAGMA temp_store=MEMORY")
        await self._conn.execute("PRAGMA busy_timeout=30000")
        await self._apply_schema()
        logger.info(f"DB connected (WAL): {self.db_path}")

    async def _apply_schema(self):
        sql = _SCHEMA_PATH.read_text()
        await self._conn.executescript(sql)
        await self._ensure_column("signals", "rr_market", "REAL")
        await self._ensure_column("signals", "rr_limit", "REAL")
        await self._ensure_column("signals", "execution_basis", "TEXT")
        await self._ensure_column("signals", "tp1_price", "REAL")
        await self._ensure_column("signals", "tp1_rr", "REAL")
        await self._ensure_column("signals", "tp1_size_pct", "REAL")
        await self._ensure_column("signals", "final_tp_size_pct", "REAL")
        await self._ensure_column("cycle_summary", "rr_market", "REAL")
        await self._ensure_column("cycle_summary", "rr_limit", "REAL")
        await self._ensure_column("cycle_summary", "execution_basis", "TEXT")
        await self._ensure_column("cycle_summary", "tp1_price", "REAL")
        await self._ensure_column("cycle_summary", "tp1_rr", "REAL")
        await self._ensure_column("cycle_summary", "tp1_size_pct", "REAL")
        await self._ensure_column("cycle_summary", "final_tp_size_pct", "REAL")
        await self._ensure_column("oi_snapshots", "pair", "TEXT NOT NULL DEFAULT ''")
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_oi_pair_recorded ON oi_snapshots(pair, recorded_at DESC)"
        )
        await self._conn.execute(
            "UPDATE signals SET liquidation_cascade = 0 WHERE liquidation_cascade IS NULL"
        )
        await self._conn.execute(
            "UPDATE signals SET squeeze_active = 0 WHERE squeeze_active IS NULL"
        )
        await self._conn.commit()

    async def _ensure_column(self, table: str, column: str, definition: str):
        rows = await self._fetch(f"PRAGMA table_info({table})")
        existing = {row[1] for row in rows}
        if column not in existing:
            await self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    # ── Core helpers ──────────────────────────────────────────

    async def _fetch(self, query: str, params: tuple = ()) -> List[Tuple]:
        for attempt in range(3):
            try:
                async with self._conn.execute(query, params) as cur:
                    return await cur.fetchall()
            except aiosqlite.OperationalError as e:
                if "locked" in str(e) and attempt < 2:
                    await asyncio.sleep(0.1 * 2 ** attempt)
                else:
                    raise
        return []

    async def _fetch_one(self, query: str, params: tuple = ()) -> Optional[Tuple]:
        rows = await self._fetch(query, params)
        return rows[0] if rows else None

    async def _exec(self, query: str, params: tuple = ()) -> int:
        async with self._conn.execute(query, params) as cur:
            await self._conn.commit()
            return cur.lastrowid

    # ── Signals ───────────────────────────────────────────────

    async def save_signal(self, s: Dict) -> int:
        payload = dict(s)
        payload.setdefault("tp1_price", None)
        payload.setdefault("tp1_rr", None)
        payload.setdefault("tp1_size_pct", None)
        payload.setdefault("final_tp_size_pct", None)
        payload.setdefault("rr_market", None)
        payload.setdefault("rr_limit", None)
        payload.setdefault("execution_basis", None)
        payload.setdefault("liquidation_cascade", 0)
        payload.setdefault("squeeze_active", 0)

        for key in ("liquidation_cascade", "squeeze_active"):
            if key in payload and payload[key] is not None:
                payload[key] = int(bool(payload[key]))

        breakdown = payload.get("confidence_breakdown")
        if breakdown is not None and not isinstance(breakdown, str):
            payload["confidence_breakdown"] = json.dumps(breakdown)

        return await self._exec("""
            INSERT OR IGNORE INTO signals (
                signal_id, pair, strategy, direction, session,
                entry_market, entry_limit, stop_loss,
                tp1_price, tp1_rr, tp1_size_pct, final_tp_size_pct,
                take_profit, rr_ratio,
                rr_market, rr_limit, execution_basis,
                position_size_pct, confidence_score, confidence_breakdown,
                market_state, volatility_regime, adx_value, atr_pct,
                target_liquidity_price, target_liquidity_tf, target_liquidity_type,
                distance_to_target_pct, cvd_divergence, oi_change_pct,
                liquidation_cascade, funding_rate, squeeze_active
            ) VALUES (
                :signal_id, :pair, :strategy, :direction, :session,
                :entry_market, :entry_limit, :stop_loss,
                :tp1_price, :tp1_rr, :tp1_size_pct, :final_tp_size_pct,
                :take_profit, :rr_ratio,
                :rr_market, :rr_limit, :execution_basis,
                :position_size_pct, :confidence_score, :confidence_breakdown,
                :market_state, :volatility_regime, :adx_value, :atr_pct,
                :target_liquidity_price, :target_liquidity_tf, :target_liquidity_type,
                :distance_to_target_pct, :cvd_divergence, :oi_change_pct,
                :liquidation_cascade, :funding_rate, :squeeze_active
            )
        """, payload)

    async def save_cycle_summary(self, summary: Dict[str, Any]) -> int:
        payload = dict(summary)
        payload.setdefault("rr_market", None)
        payload.setdefault("rr_limit", None)
        payload.setdefault("execution_basis", None)
        payload.setdefault("tp1_price", None)
        payload.setdefault("tp1_rr", None)
        payload.setdefault("tp1_size_pct", None)
        payload.setdefault("final_tp_size_pct", None)

        for key in (
            "tradeable",
            "squeeze_active",
            "liquidation_cascade",
            "sweep_candidate",
            "breakout_candidate",
            "cooldown_hit",
        ):
            if key in payload and payload[key] is not None:
                payload[key] = int(bool(payload[key]))

        breakdown = payload.get("confidence_breakdown")
        if breakdown is not None and not isinstance(breakdown, str):
            payload["confidence_breakdown"] = json.dumps(breakdown)

        return await self._exec("""
            INSERT OR REPLACE INTO cycle_summary (
                cycle_id, created_at, pair, analysis_time_utc,
                session, hour_utc, market_state, volatility_regime, operating_mode,
                tradeable, adx_value, atr_pct, current_price,
                candles_15m, candles_4h, candles_1d,
                liquidity_levels_found, liquidity_levels_eligible, liquidity_levels_filtered,
                squeeze_active, funding_rate, oi_change_pct, liquidation_cascade, cvd_divergence,
                sweep_candidate, breakout_candidate,
                confidence_score, confidence_threshold, confidence_stage, confidence_breakdown,
                final_status, final_reason, blocker_reason,
                signal_id, signal_strategy, signal_direction,
                tp1_price, tp1_rr, tp1_size_pct, final_tp_size_pct,
                rr_ratio,
                rr_market, rr_limit, execution_basis,
                cooldown_hit, strategy_version
            ) VALUES (
                :cycle_id, :created_at, :pair, :analysis_time_utc,
                :session, :hour_utc, :market_state, :volatility_regime, :operating_mode,
                :tradeable, :adx_value, :atr_pct, :current_price,
                :candles_15m, :candles_4h, :candles_1d,
                :liquidity_levels_found, :liquidity_levels_eligible, :liquidity_levels_filtered,
                :squeeze_active, :funding_rate, :oi_change_pct, :liquidation_cascade, :cvd_divergence,
                :sweep_candidate, :breakout_candidate,
                :confidence_score, :confidence_threshold, :confidence_stage, :confidence_breakdown,
                :final_status, :final_reason, :blocker_reason,
                :signal_id, :signal_strategy, :signal_direction,
                :tp1_price, :tp1_rr, :tp1_size_pct, :final_tp_size_pct,
                :rr_ratio,
                :rr_market, :rr_limit, :execution_basis,
                :cooldown_hit, :strategy_version
            )
        """, payload)

    async def get_signals_for_export(
        self,
        limit: int = 500,
        direction: Optional[str] = None,
        strategy: Optional[str] = None,
        pair: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT signal_id, created_at, pair, strategy, direction, session,
                   entry_market, entry_limit, stop_loss,
                   tp1_price, tp1_rr, tp1_size_pct, final_tp_size_pct,
                   take_profit, rr_ratio, rr_market, rr_limit, execution_basis,
                   confidence_score, market_state, volatility_regime,
                   target_liquidity_price, target_liquidity_tf, target_liquidity_type,
                   cvd_divergence, oi_change_pct, liquidation_cascade, funding_rate,
                   squeeze_active, status, result_pnl_pct, closed_at
            FROM signals
            WHERE 1=1
        """
        params: list[Any] = []
        if direction:
            query += " AND direction=?"
            params.append(direction.upper())
        if strategy:
            query += " AND strategy=?"
            params.append(strategy)
        if pair:
            query += " AND pair=?"
            params.append(pair.upper())
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = await self._fetch(query, tuple(params))
        cols = [
            "signal_id", "created_at", "pair", "strategy", "direction", "session",
            "entry_market", "entry_limit", "stop_loss",
            "tp1_price", "tp1_rr", "tp1_size_pct", "final_tp_size_pct",
            "take_profit", "rr_ratio", "rr_market", "rr_limit", "execution_basis",
            "confidence_score", "market_state", "volatility_regime",
            "target_liquidity_price", "target_liquidity_tf", "target_liquidity_type",
            "cvd_divergence", "oi_change_pct", "liquidation_cascade", "funding_rate",
            "squeeze_active", "status", "result_pnl_pct", "closed_at",
        ]
        return [dict(zip(cols, row)) for row in rows or []]

    async def get_active_signals(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return active signals (status IN ('sent', 'partial_tp1'))."""
        rows = await self._fetch("""
            SELECT pair, direction, strategy, entry_market, stop_loss, take_profit, created_at
            FROM signals
            WHERE status IN ('sent', 'partial_tp1')
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        cols = ["pair", "direction", "strategy", "entry_market", "stop_loss", "take_profit", "created_at"]
        return [dict(zip(cols, row)) for row in rows or []]

    async def get_pair_stats(self) -> List[Dict[str, Any]]:
        """Return aggregated statistics per trading pair."""
        rows = await self._fetch("""
            SELECT pair, COUNT(*),
                   AVG(confidence_score),
                   SUM(CASE WHEN status='tp_hit' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN status='sl_hit' THEN 1 ELSE 0 END)
            FROM signals
            GROUP BY pair
            ORDER BY COUNT(*) DESC
        """)
        cols = ["pair", "total", "avg_confidence", "tp_hits", "sl_hits"]
        return [dict(zip(cols, row)) for row in rows or []]

    async def get_signals_for_telegram_export(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return signals for Telegram CSV export."""
        rows = await self._fetch("""
            SELECT signal_id, created_at, pair, strategy, direction,
                   entry_market, stop_loss, take_profit, rr_ratio,
                   confidence_score, status
            FROM signals
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        cols = ["signal_id", "created_at", "pair", "strategy", "direction",
                "entry_market", "stop_loss", "take_profit", "rr_ratio",
                "confidence_score", "status"]
        return [dict(zip(cols, row)) for row in rows or []]

    async def get_recent_signals(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Return recent signals for Telegram /signals command."""
        rows = await self._fetch("""
            SELECT created_at, strategy, direction, entry_market,
                   take_profit, rr_ratio, confidence_score, status
            FROM signals
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        cols = ["created_at", "strategy", "direction", "entry_market",
                "take_profit", "rr_ratio", "confidence_score", "status"]
        return [dict(zip(cols, row)) for row in rows or []]

    async def count_signals_24h(self) -> int:
        row = await self._fetch_one(
            "SELECT COUNT(*) FROM signals WHERE created_at > datetime('now','-24 hours')"
        )
        return row[0] if row else 0

    async def get_avg_confidence_24h(self) -> float:
        row = await self._fetch_one(
            "SELECT AVG(confidence_score) FROM signals "
            "WHERE created_at > datetime('now','-24 hours')"
        )
        return round(row[0] or 0.0, 1)

    async def get_winrate_24h(self) -> float:
        row = await self._fetch_one("""
            SELECT
                SUM(CASE WHEN status='tp_hit' THEN 1 ELSE 0 END),
                SUM(CASE WHEN status IN ('tp_hit','sl_hit') THEN 1 ELSE 0 END)
            FROM signals
            WHERE COALESCE(closed_at, created_at) > datetime('now','-24 hours')
        """)
        if not row or not row[1]:
            return 0.0
        return round((row[0] or 0) / row[1] * 100, 2)

    async def get_avg_drawdown_24h(self) -> float:
        row = await self._fetch_one("""
            SELECT AVG(ABS(result_pnl_pct))
            FROM signals
            WHERE COALESCE(closed_at, created_at) > datetime('now','-24 hours')
              AND result_pnl_pct < 0
        """)
        return round(row[0] or 0.0, 2)

    async def get_metrics_24h(self) -> Dict[str, float]:
        return {
            "signals_24h": await self.count_signals_24h(),
            "avg_confidence_24h": await self.get_avg_confidence_24h(),
            "winrate_24h": await self.get_winrate_24h(),
            "avg_drawdown_pct_24h": await self.get_avg_drawdown_24h(),
        }

    # ── Liquidity pools ───────────────────────────────────────

    async def upsert_pool(self, timeframe: str, pool_type: str,
                          price: float, touch_count: int, strength: float):
        existing = await self._fetch_one(
            "SELECT id, touch_count FROM liquidity_pools "
            "WHERE timeframe=? AND pool_type=? AND ABS(price-?)/? < 0.002",
            (timeframe, pool_type, price, price)
        )
        if existing:
            await self._exec(
                "UPDATE liquidity_pools SET touch_count=?, strength=?, "
                "last_updated=CURRENT_TIMESTAMP WHERE id=?",
                (max(existing[1], touch_count), strength, existing[0])
            )
        else:
            await self._exec(
                "INSERT INTO liquidity_pools (timeframe,pool_type,price,touch_count,strength) "
                "VALUES (?,?,?,?,?)",
                (timeframe, pool_type, price, touch_count, strength)
            )

    async def get_active_pools(
        self,
        current_price: float,
        min_distance_pct: float = 0.015,
        max_distance_pct: float = 0.08,
        timeframes: List[str] = None
    ) -> List[Dict]:
        tf_filter = ""
        params: list = []
        if timeframes:
            placeholders = ",".join("?" * len(timeframes))
            tf_filter = f"AND timeframe IN ({placeholders})"
            params.extend(timeframes)
        params.extend([current_price, min_distance_pct,
                        current_price, max_distance_pct])

        rows = await self._fetch(f"""
            SELECT timeframe, pool_type, price, touch_count, strength, mitigated
            FROM liquidity_pools
            WHERE is_active=1
            {tf_filter}
              AND ABS(price - ?) / ? >= ?
              AND ABS(price - ?) / ? <= ?
            ORDER BY strength DESC, ABS(price - {current_price})
        """, tuple(params))

        return [
            {
                "timeframe": r[0], "pool_type": r[1], "price": r[2],
                "touch_count": r[3], "strength": r[4], "mitigated": bool(r[5]),
                "distance_pct": abs(r[2] - current_price) / current_price
            }
            for r in rows
        ]

    async def mark_pool_mitigated(self, pool_id: int):
        await self._exec(
            "UPDATE liquidity_pools SET mitigated=1, last_updated=CURRENT_TIMESTAMP "
            "WHERE id=?", (pool_id,)
        )

    # ── CVD ───────────────────────────────────────────────────

    async def add_cvd_delta(self, session: str, date_str: str, delta: float):
        await self._exec("""
            INSERT INTO cvd_buckets (session, bucket_date, delta_sum)
            VALUES (?, ?, ?)
            ON CONFLICT(session, bucket_date)
            DO UPDATE SET delta_sum = delta_sum + ?, updated_at = CURRENT_TIMESTAMP
        """, (session, date_str, delta, delta))

    async def get_cvd_session(self, session: str, date_str: str) -> float:
        row = await self._fetch_one(
            "SELECT delta_sum FROM cvd_buckets WHERE session=? AND bucket_date=?",
            (session, date_str)
        )
        return row[0] if row else 0.0

    # ── OI snapshots ──────────────────────────────────────────

    async def save_oi(self, pair: str, oi: float, price: float):
        await self._exec(
            "INSERT INTO oi_snapshots (pair, open_interest, price) VALUES (?,?,?)",
            (pair, oi, price)
        )
        # Prune older than 14 days
        await self._exec(
            "DELETE FROM oi_snapshots WHERE recorded_at < datetime('now','-14 days')"
        )

    async def get_oi_ago(self, pair: str, minutes: int) -> Optional[Tuple[float, float]]:
        """Returns (open_interest, price) from N minutes ago."""
        return await self._fetch_one(
            "SELECT open_interest, price FROM oi_snapshots "
            "WHERE pair = ? AND recorded_at <= datetime('now', ? || ' minutes') "
            "ORDER BY recorded_at DESC LIMIT 1",
            (pair, f"-{minutes}")
        )

    # ── Cooldowns ─────────────────────────────────────────────

    async def is_on_cooldown(self, signal_hash: str) -> bool:
        row = await self._fetch_one(
            "SELECT cooldown_until FROM signal_cooldowns WHERE signal_hash=?",
            (signal_hash,)
        )
        if not row:
            return False
        from datetime import datetime, timezone
        return datetime.fromisoformat(row[0]) > datetime.now(timezone.utc).replace(tzinfo=None)

    async def set_cooldown(self, signal_hash: str, minutes: int = 60):
        from datetime import datetime, timedelta, timezone
        until = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=minutes)).isoformat()
        await self._exec("""
            INSERT INTO signal_cooldowns (signal_hash, last_sent, cooldown_until)
            VALUES (?, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(signal_hash) DO UPDATE SET
                last_sent=CURRENT_TIMESTAMP, cooldown_until=?, count=count+1
        """, (signal_hash, until, until))
