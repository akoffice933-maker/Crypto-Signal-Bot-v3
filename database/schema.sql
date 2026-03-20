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
    take_profit      REAL NOT NULL,
    rr_ratio         REAL NOT NULL,
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

-- ── Indexes ───────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_signals_created   ON signals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_strategy  ON signals(strategy, direction);
CREATE INDEX IF NOT EXISTS idx_pools_active      ON liquidity_pools(is_active, timeframe, price);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pools_bucket_unique
    ON liquidity_pools(timeframe, pool_type, ROUND(price, 0));
CREATE INDEX IF NOT EXISTS idx_oi_recorded       ON oi_snapshots(recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_logs_level        ON system_logs(level, created_at DESC);
