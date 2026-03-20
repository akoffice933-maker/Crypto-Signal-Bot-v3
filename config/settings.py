import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing."""


@dataclass
class Settings:
    # ── Telegram ──────────────────────────────────────────────
    telegram_token: str   = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    telegram_channel_link: str = os.getenv("TELEGRAM_CHANNEL_LINK", "")

    # ── Binance ───────────────────────────────────────────────
    api_key:    str  = os.getenv("BINANCE_API_KEY", "")
    api_secret: str  = os.getenv("BINANCE_API_SECRET", "")
    testnet:    bool = os.getenv("TESTNET", "true").lower() == "true"
    symbol:     str  = "BTCUSDT"

    # ── Sessions (UTC hours, inclusive start, exclusive end) ──
    # Asian:   00:00–08:00
    # London:  07:00–11:00  (overlaps Asian 07–08; counts as ONE session)
    # NY:      13:00–17:00
    sessions: dict = field(default_factory=lambda: {
        "asian":  (0,  8),
        "london": (7,  11),
        "ny":     (13, 17),
    })

    # ── Analysis ──────────────────────────────────────────────
    analysis_interval_minutes: int = 15
    confidence_threshold:      int = 65
    min_rr:                  float = 2.0
    target_move_min_pct:     float = 0.02   # 2%
    target_move_max_pct:     float = 0.05   # 5%

    # ── Market State ──────────────────────────────────────────
    adx_trending_threshold: float = 25.0
    adx_dead_zone_min:      float = 20.0
    adx_dead_zone_max:      float = 25.0    # 20–25 → skip

    # ── Volatility ────────────────────────────────────────────
    atr_low_threshold:    float = 0.007   # < 0.7% → skip
    atr_normal_max:       float = 0.015   # 0.7–1.5% normal
    atr_lookback_candles: int   = 20      # for ATR% mean price

    # ── Liquidity Map ─────────────────────────────────────────
    liquidity_lookback_days:   int   = 90
    liquidity_touch_min:       int   = 3
    liquidity_tolerance_pct:   float = 0.002   # 0.2%
    liquidity_min_distance_pct:float = 0.015   # 1.5% — skip if closer
    # timeframes used for levels
    liquidity_timeframes: list = field(default_factory=lambda: ["1d", "4h"])

    # ── Squeeze Detector ──────────────────────────────────────
    squeeze_tf:            str = "4h"
    squeeze_lookback:      int = 50
    squeeze_range_max_pct: float = 0.015   # last 20 candles range < 1.5%
    squeeze_range_candles: int   = 20

    # ── Order Flow ────────────────────────────────────────────
    oi_drop_threshold_pct:    float = 0.02   # 2% OI drop
    oi_price_move_pct:        float = 0.012  # + 1.2% price move → cascade
    oi_lookback_minutes:      int   = 60
    funding_extreme_threshold: float = 0.0005  # 0.05%
    funding_block_threshold:   float = 0.001   # 0.10%

    # ── Sweep Reversal ────────────────────────────────────────
    sweep_tolerance_pct:      float = 0.001
    rejection_wick_ratio:     float = 2.5    # wick ≥ 2.5 × body
    rejection_body_range_max: float = 1/3    # body ≤ 1/3 of candle range
    volume_spike_multiplier:  float = 1.2    # vol ≥ 1.2× MA20
    limit_entry_pct:          float = 0.50   # 50% of sweep candle body

    # ── Squeeze Breakout ──────────────────────────────────────
    breakout_sl_pct:  float = 0.007   # 0.7%
    breakout_tp_min:  float = 0.02
    breakout_tp_max:  float = 0.04

    # ── Risk ──────────────────────────────────────────────────
    account_balance:         float = float(os.getenv("ACCOUNT_BALANCE", "10000"))
    max_risk_per_trade_pct:  float = 2.0
    max_position_pct:        float = 0.10

    # ── Storage ───────────────────────────────────────────────
    db_path:   str = os.getenv("DB_PATH", "data/signals.db")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    google_sheets_webhook_url: str = os.getenv("GOOGLE_SHEETS_WEBHOOK_URL", "")
    google_sheets_timeout_seconds: int = int(os.getenv("GOOGLE_SHEETS_TIMEOUT_SECONDS", "10"))
    telegram_max_messages_per_minute: int = int(os.getenv("TELEGRAM_MAX_MESSAGES_PER_MINUTE", "20"))
    telegram_min_interval_seconds: float = float(os.getenv("TELEGRAM_MIN_INTERVAL_SECONDS", "1.2"))

    @property
    def base_url(self) -> str:
        return ("https://testnet.binancefuture.com"
                if self.testnet else "https://fapi.binance.com")

    @property
    def ws_base(self) -> str:
        return ("wss://stream.binancefuture.com"
                if self.testnet else "wss://fstream.binance.com")

    def get_session(self, hour_utc: int) -> str | None:
        """
        Returns the active session name for a given UTC hour.
        Priority: london > ny > asian (overlap 07-08 → london wins).
        Returns None if outside all sessions.
        """
        # Check in priority order so overlapping hour 07-08 → 'london'
        for name in ("london", "ny", "asian"):
            start, end = self.sessions[name]
            if start <= hour_utc < end:
                return name
        return None

    def cvd_reset_hour(self, session: str) -> int:
        """UTC hour when CVD resets for a given session."""
        return self.sessions[session][0]

    def validate_runtime(self, *, dry_run: bool = False):
        """Validate the minimal runtime configuration for the selected mode."""
        if dry_run:
            return
        if not self.telegram_token:
            raise ConfigurationError("TELEGRAM_BOT_TOKEN required")
        if not self.telegram_chat_id:
            raise ConfigurationError("TELEGRAM_CHAT_ID required")


settings = Settings()
