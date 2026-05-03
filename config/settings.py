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
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    download_token: str = os.getenv("DOWNLOAD_TOKEN", os.getenv("API_KEY", ""))

    # ── Binance ───────────────────────────────────────────────
    api_key:    str  = os.getenv("BINANCE_API_KEY", "")
    api_secret: str  = os.getenv("BINANCE_API_SECRET", "")
    testnet:    bool = os.getenv("TESTNET", "true").lower() == "true"
    symbols:    list = field(default_factory=lambda: os.getenv("SYMBOLS", "BTCUSDT").split(","))
    
    # Legacy support (single symbol)
    @property
    def symbol(self) -> str:
        return self.symbols[0] if self.symbols else "BTCUSDT"

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
    confidence_threshold:      int = 70  # Повышено с 65 для качества
    min_rr:                  float = 2.0
    target_move_min_pct:     float = 0.02   # 2%
    target_move_max_pct:     float = 0.05   # 5%
    execution_basis:         str  = os.getenv("EXECUTION_BASIS", "limit").lower()
    tp1_rr_multiple:        float = 2.0
    tp1_size_pct:           float = 0.50

    # ── Dual-Mode Settings (NORMAL / QUIET / BLOCKED) ─────────
    # ATR thresholds for mode selection
    quiet_atr_min:           float = 0.0012  # 0.12% (below = BLOCKED), снижено с 0.18% для текущих условий
    quiet_atr_max:           float = 0.0060  # 0.60% (below = QUIET, above = NORMAL)

    # Mode-specific confidence thresholds
    normal_confidence_threshold: int = 70  # Повышено с 65 для качества
    quiet_confidence_threshold:  int = 60  # Снижено с 65 для чувствительности
    quiet_breakout_confidence_threshold: int = 65
    quiet_breakout_min_adx: float = 30.0

    # Mode-specific volume spike
    normal_volume_spike_multiplier: float = 1.2
    quiet_volume_spike_multiplier:  float = 1.03  # Более мягкий порог только для QUIET

    # Mode-specific min RR
    normal_min_rr: float = 2.0
    quiet_min_rr:  float = 1.3  # Снижено с 1.5 для чувствительности
    quiet_breakout_min_rr: float = 1.5

    # Mode-specific allowed sessions
    quiet_allowed_sessions: list = field(default_factory=lambda: ['asian', 'london', 'ny'])

    # Mode-specific level score thresholds
    normal_level_score_min: int = 5
    quiet_level_score_min:  int = 6
    max_level_touches:      int = 15

    # ── Market State ──────────────────────────────────────────
    adx_trending_threshold: float = 25.0
    adx_dead_zone_min:      float = 22.0
    adx_dead_zone_max:      float = 23.0

    # ── Volatility ────────────────────────────────────────────
    atr_low_threshold:    float = 0.0045  # Снижено с 0.007 (0.45% vs 0.7%)
    atr_normal_max:       float = 0.015   # 0.7-1.5% normal
    atr_lookback_candles: int   = 20      # for ATR% mean price

    # ── Liquidity Map ─────────────────────────────────────────
    liquidity_lookback_days:   int   = 90
    liquidity_touch_min:       int   = 2   # Снижено с 3 для чувствительности
    liquidity_tolerance_pct:   float = 0.003   # 0.3% — увеличено с 0.2% для чувствительности
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

    # ── Risk Management (на основе бэктеста) ──────────────────
    min_stop_loss_pct:       float = 0.0045  # 0.45% минимум (MAE 0.46% + буфер)
    quiet_sl_atr_mult:       float = 1.0     # 1.0×ATR для Quiet режима
    normal_sl_atr_mult:      float = 0.8     # 0.8×ATR для NORMAL
    quiet_tp_max_pct:        float = 0.011   # 1.1% макс. TP в Quiet (MFE из бэктеста)

    # ── Sweep Reversal ────────────────────────────────────────
    sweep_tolerance_pct:      float = 0.001
    rejection_wick_ratio:     float = 2.5    # wick ≥ 2.5 × body (NORMAL)
    quiet_rejection_wick_ratio: float = 1.8  # wick ≥ 1.8 × body (QUIET)
    rejection_body_range_max: float = 1/3    # body ≤ 1/3 of candle range
    volume_spike_multiplier:  float = 1.1    # Снижено с 1.2 (vol ≥ 1.1× MA20)
    limit_entry_pct:          float = 0.50   # 50% of sweep candle body

    # ── Squeeze Breakout ──────────────────────────────────────
    breakout_sl_pct:  float = 0.007   # 0.7% (устарело, используется adaptive)
    breakout_tp_min:  float = 0.02
    breakout_tp_max:  float = 0.04
    
    # Breakout SL: Adaptive ATR-based
    breakout_sl_atr_mult:      float = 1.5   # 1.5× ATR
    breakout_sl_min_pct:       float = 0.005 # Минимум 0.5%
    breakout_sl_max_pct:       float = 0.012 # Максимум 1.2%
    
    # Mode-specific ATR multipliers (опционально)
    breakout_sl_quiet_atr_mult:   float = 1.5
    breakout_sl_normal_atr_mult:  float = 1.5

    # ── Risk ──────────────────────────────────────────────────
    account_balance:         float = float(os.getenv("ACCOUNT_BALANCE", "10000"))
    max_risk_per_trade_pct:  float = 2.0    # Риск 2% от депозита на сделку
    max_position_pct:        float = 0.10   # Максимум 10% от депозита в позицию
    
    # Position sizing
    use_position_sizing:     bool = True    # Включить расчёт позиции
    position_size_rounding:  int = 3        # Округление BTC (3 знака = 0.001)
    
    # Leverage
    use_leverage:            bool = True    # Включить плечо
    max_leverage:            float = 10.0   # Максимум 10x
    maintenance_margin_rate: float = 0.005  # 0.5% maintenance margin

    # ── Storage ───────────────────────────────────────────────
    db_path:   str = os.getenv("DB_PATH", "data/signals.db")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    google_sheets_webhook_url: str = os.getenv("GOOGLE_SHEETS_WEBHOOK_URL", "")
    google_sheets_timeout_seconds: int = int(os.getenv("GOOGLE_SHEETS_TIMEOUT_SECONDS", "10"))
    telegram_max_messages_per_minute: int = int(os.getenv("TELEGRAM_MAX_MESSAGES_PER_MINUTE", "20"))
    telegram_min_interval_seconds: float = float(os.getenv("TELEGRAM_MIN_INTERVAL_SECONDS", "1.2"))
    telegram_request_timeout_seconds: float = float(os.getenv("TELEGRAM_REQUEST_TIMEOUT_SECONDS", "90"))
    telegram_polling_timeout_seconds: int = int(os.getenv("TELEGRAM_POLLING_TIMEOUT_SECONDS", "30"))

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
        if self.execution_basis not in {"market", "limit"}:
            raise ConfigurationError("EXECUTION_BASIS must be 'market' or 'limit'")
        if dry_run:
            return
        if not self.telegram_token:
            raise ConfigurationError("TELEGRAM_BOT_TOKEN required")
        if not self.telegram_chat_id:
            raise ConfigurationError("TELEGRAM_CHAT_ID required")


settings = Settings()
