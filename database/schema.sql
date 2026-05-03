-- ══════════════════════════════════════════════
--  Crypto Signal Bot v3  —  Database Schema
-- ══════════════════════════════════════════════

-- Signals sent to Telegram
CREATE TABLE IF NOT EXISTS signals (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id        TEXT UNIQUE NOT NULL,          -- SHA256[:16] for dedup
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Identity
    pair             TEXT NOT NULL DEFAULT 'BTCUSDT',
    strategy         TEXT NOT NULL,                 -- sweep_reversal | breakout
    direction        TEXT CHECK(direction IN ('LONG','SHORT')) NOT NULL,
    session          TEXT NOT NULL,                 -- asian | london | ny

    -- Prices
    entry_market     REAL NOT NULL,
    entry_limit      REAL,                          -- 50% sweep body
    stop_loss        REAL NOT NULL,
    tp1_price        REAL,
    tp1_rr           REAL,
    tp1_size_pct     REAL,
    final_tp_size_pct REAL,
    take_profit      REAL NOT NULL,
    rr_ratio         REAL NOT NULL,
    rr_market        REAL,
    rr_limit         REAL,
    execution_basis  TEXT,
    position_size_pct REAL,

    -- Confidence
    confidence_score      INTEGER NOT NULL,
    confidence_breakdown  TEXT,                     -- JSON [{factor, delta}]

    -- Market context
    market_state     TEXT,                          -- trending | ranging | dead_zone
    volatility_regime TEXT,                         -- low | normal | high
    adx_value        REAL,
    atr_pct          REAL,

    -- Liquidity
    target_liquidity_price REAL,
    target_liquidity_tf    TEXT,                    -- 1d | 4h
    target_liquidity_type  TEXT,                    -- equal_highs | equal_lows
    distance_to_target_pct REAL,

    -- Order flow
    cvd_divergence    TEXT,                         -- bullish | bearish | none
    oi_change_pct     REAL,
    liquidation_cascade BOOLEAN DEFAULT FALSE,
    funding_rate      REAL,
    squeeze_active    BOOLEAN DEFAULT FALSE,

    -- Result (filled later)
    status            TEXT DEFAULT 'sent',          -- sent | tp_hit | sl_hit | expired
    result_pnl_pct    REAL,
    closed_at         DATETIME
);

-- Liquidity pools — 1D and 4H
CREATE TABLE IF NOT EXISTS liquidity_pools (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    timeframe    TEXT NOT NULL,                     -- 1d | 4h
    pool_type    TEXT NOT NULL,                     -- equal_highs | equal_lows
    price        REAL NOT NULL,
    touch_count  INTEGER NOT NULL DEFAULT 3,
    strength     REAL NOT NULL DEFAULT 1.0,         -- touch_count × tf_weight
    is_active    BOOLEAN DEFAULT TRUE,
    mitigated    BOOLEAN DEFAULT FALSE,             -- price crossed but returned
    first_seen   DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- CVD per-session buckets (in-memory primary, DB for persistence)
CREATE TABLE IF NOT EXISTS cvd_buckets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session     TEXT NOT NULL,                      -- asian | london | ny
    bucket_date TEXT NOT NULL,                      -- YYYY-MM-DD
    delta_sum   REAL NOT NULL DEFAULT 0,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session, bucket_date)
);

-- Open Interest snapshots (15-min intervals, keep 14 days)
CREATE TABLE IF NOT EXISTS oi_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    pair          TEXT NOT NULL DEFAULT '',
    open_interest REAL NOT NULL,
    price         REAL NOT NULL
);

-- System logs
CREATE TABLE IF NOT EXISTS system_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    level      TEXT CHECK(level IN ('DEBUG','INFO','WARNING','ERROR','CRITICAL')),
    component  TEXT NOT NULL,
    message    TEXT NOT NULL,
    context    TEXT                                 -- JSON
);

-- Signal dedup cooldowns
CREATE TABLE IF NOT EXISTS signal_cooldowns (
    signal_hash   TEXT PRIMARY KEY,
    last_sent     DATETIME NOT NULL,
    cooldown_until DATETIME NOT NULL,
    count         INTEGER DEFAULT 1
);

-- Analysis cycle summaries (including no-signal / skipped cycles)
CREATE TABLE IF NOT EXISTS cycle_summary (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id                  TEXT UNIQUE NOT NULL,
    created_at                DATETIME DEFAULT CURRENT_TIMESTAMP,
    pair                      TEXT NOT NULL DEFAULT 'BTCUSDT',
    analysis_time_utc         TEXT NOT NULL,
    session                   TEXT,
    hour_utc                  INTEGER,
    market_state              TEXT,
    volatility_regime         TEXT,
    operating_mode            TEXT,
    tradeable                 INTEGER NOT NULL DEFAULT 0,
    adx_value                 REAL,
    atr_pct                   REAL,
    current_price             REAL,
    candles_15m               INTEGER,
    candles_4h                INTEGER,
    candles_1d                INTEGER,
    liquidity_levels_found    INTEGER,
    liquidity_levels_eligible INTEGER,
    liquidity_levels_filtered INTEGER,
    squeeze_active            INTEGER,
    funding_rate              REAL,
    oi_change_pct             REAL,
    liquidation_cascade       INTEGER,
    cvd_divergence            TEXT,
    sweep_candidate           INTEGER NOT NULL DEFAULT 0,
    breakout_candidate        INTEGER NOT NULL DEFAULT 0,
    confidence_score          INTEGER,
    confidence_threshold      INTEGER,
    confidence_stage          TEXT,
    confidence_breakdown      TEXT,
    final_status              TEXT NOT NULL,
    final_reason              TEXT,
    blocker_reason            TEXT,
    signal_id                 TEXT,
    signal_strategy           TEXT,
    signal_direction          TEXT,
    tp1_price                 REAL,
    tp1_rr                    REAL,
    tp1_size_pct              REAL,
    final_tp_size_pct         REAL,
    rr_ratio                  REAL,
    rr_market                 REAL,
    rr_limit                  REAL,
    execution_basis           TEXT,
    cooldown_hit              INTEGER NOT NULL DEFAULT 0,
    strategy_version          TEXT
);

-- ── Indexes ───────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_signals_created   ON signals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_strategy  ON signals(strategy, direction);
CREATE INDEX IF NOT EXISTS idx_signals_pair      ON signals(pair, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pools_active      ON liquidity_pools(is_active, timeframe, price);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pools_bucket_unique
    ON liquidity_pools(timeframe, pool_type, ROUND(price, 0));
CREATE INDEX IF NOT EXISTS idx_oi_recorded       ON oi_snapshots(recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_logs_level        ON system_logs(level, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cycle_created     ON cycle_summary(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cycle_status      ON cycle_summary(final_status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cycle_mode        ON cycle_summary(operating_mode, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cycle_session     ON cycle_summary(session, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cycle_signal      ON cycle_summary(signal_id);
CREATE INDEX IF NOT EXISTS idx_cycle_pair        ON cycle_summary(pair, created_at DESC);
