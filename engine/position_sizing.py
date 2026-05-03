"""
Position Sizing Calculator with Leverage

Calculates optimal position size and leverage based on:
- Account balance
- Risk per trade (%)
- Stop Loss distance (%)
- Maximum position size (%)
- Maximum leverage (x)
- Liquidation price safety check

Formula:
    risk_amount = balance * (risk_pct / 100)
    position_size = risk_amount / sl_distance
    position_value = position_size * entry_price
    
    leverage = min(position_value / balance, max_leverage)
    margin_required = position_value / leverage
    
    liquidation_price = calculate_liquidation(entry, leverage, direction)
    
    Safety check:
    - LONG: liquidation < stop_loss
    - SHORT: liquidation > stop_loss
"""

from dataclasses import dataclass
from typing import Optional

from config.settings import settings


@dataclass
class PositionSizeResult:
    """Result of position size calculation with leverage."""
    
    # Input parameters
    balance: float
    risk_pct: float
    sl_pct: float
    max_position_pct: float
    max_leverage: float
    
    # Calculated values
    risk_amount: float      # $ amount at risk
    position_size: float    # BTC amount
    position_size_pct: float  # % of balance (margin)
    position_value: float   # $ value of position (with leverage)
    leverage: float         # Applied leverage (x)
    margin_required: float  # $ margin used
    
    # Leverage diagnostics
    liquidation_price: float  # Liquidation price
    liquidation_distance_pct: float  # Distance to liquidation (%)
    is_liquidation_safe: bool  # True if liquidation is beyond SL
    leverage_capped: bool  # True if capped by max_leverage
    
    # Position sizing diagnostics
    is_position_capped: bool  # True if capped by max_position_pct
    sl_distance: float      # SL distance in $


def calculate_liquidation_price(
    entry_price: float,
    leverage: float,
    direction: str,
    maintenance_margin_rate: float = 0.005,  # 0.5% typical for BTC
) -> float:
    """
    Calculate liquidation price for a leveraged position.
    
    Args:
        entry_price: Entry price in USD
        leverage: Leverage (x)
        direction: 'LONG' or 'SHORT'
        maintenance_margin_rate: Maintenance margin rate (default 0.5%)
    
    Returns:
        Liquidation price in USD
    """
    # Simplified liquidation formula
    # Long: liquidation = entry * (1 - 1/leverage + mmr)
    # Short: liquidation = entry * (1 + 1/leverage - mmr)
    
    if direction == "LONG":
        liquidation = entry_price * (1 - 1/leverage + maintenance_margin_rate)
    else:  # SHORT
        liquidation = entry_price * (1 + 1/leverage - maintenance_margin_rate)
    
    return round(liquidation, 2)


def calculate_position_size(
    entry_price: float,
    stop_loss: float,
    direction: str,
    balance: float = None,
    risk_pct: float = None,
    max_position_pct: float = None,
    max_leverage: float = 10.0,  # Default max 10x
    use_leverage: bool = True,
) -> PositionSizeResult:
    """
    Calculate position size with optional leverage.
    
    Args:
        entry_price: Entry price in USD
        stop_loss: Stop loss price in USD
        direction: 'LONG' or 'SHORT'
        balance: Account balance (default: from settings)
        risk_pct: Risk per trade % (default: from settings)
        max_position_pct: Max position % (default: from settings)
        max_leverage: Maximum allowed leverage (default: 10x)
        use_leverage: Enable leverage calculation (default: True)
    
    Returns:
        PositionSizeResult with calculated values
    """
    # Use defaults from settings
    if balance is None:
        balance = settings.account_balance
    if risk_pct is None:
        risk_pct = settings.max_risk_per_trade_pct
    if max_position_pct is None:
        max_position_pct = settings.max_position_pct
    
    # Calculate SL distance ($)
    if direction == "LONG":
        sl_distance = entry_price - stop_loss
    else:  # SHORT
        sl_distance = stop_loss - entry_price
    
    # Prevent division by zero
    if sl_distance <= 0:
        sl_distance = entry_price * 0.0001  # Minimum 0.01%
    
    sl_pct = sl_distance / entry_price
    
    # Calculate risk amount ($)
    risk_amount = balance * (risk_pct / 100)
    
    # Calculate position size (BTC)
    # Formula: position_size = risk_amount / sl_distance
    position_size = risk_amount / sl_distance
    
    # Round position size
    position_size = round(position_size, settings.position_size_rounding)
    
    # Calculate position value ($)
    position_value = position_size * entry_price
    
    # Calculate leverage
    leverage = 1.0
    if use_leverage and position_value > balance * max_position_pct:
        # Calculate optimal leverage
        optimal_leverage = position_value / (balance * max_position_pct)
        leverage = min(optimal_leverage, max_leverage)
        leverage = round(leverage, 1)
    
    # Calculate margin required
    margin_required = position_value / leverage
    
    # Calculate position size (%)
    position_size_pct = (margin_required / balance) * 100
    
    # Cap by maximum position size
    is_position_capped = False
    if position_size_pct > max_position_pct * 100:
        is_position_capped = True
        position_size_pct = max_position_pct * 100
        margin_required = balance * (max_position_pct)
        position_value = margin_required * leverage
        position_size = round(position_value / entry_price, settings.position_size_rounding)
    
    # Calculate liquidation price
    liquidation_price = calculate_liquidation_price(entry_price, leverage, direction)
    
    # Calculate liquidation distance (%)
    if direction == "LONG":
        liquidation_distance_pct = (entry_price - liquidation_price) / entry_price * 100
    else:  # SHORT
        liquidation_distance_pct = (liquidation_price - entry_price) / entry_price * 100
    
    # Check if liquidation is safe (beyond SL)
    if direction == "LONG":
        is_liquidation_safe = liquidation_price < stop_loss
    else:  # SHORT
        is_liquidation_safe = liquidation_price > stop_loss
    
    # Check if leverage is capped
    leverage_capped = leverage >= max_leverage
    
    return PositionSizeResult(
        balance=balance,
        risk_pct=risk_pct,
        sl_pct=sl_pct * 100,  # Convert to %
        max_position_pct=max_position_pct,
        max_leverage=max_leverage,
        risk_amount=risk_amount,
        position_size=position_size,
        position_size_pct=position_size_pct,
        position_value=position_value,
        leverage=leverage,
        margin_required=margin_required,
        liquidation_price=liquidation_price,
        liquidation_distance_pct=liquidation_distance_pct,
        is_liquidation_safe=is_liquidation_safe,
        leverage_capped=leverage_capped,
        is_position_capped=is_position_capped,
        sl_distance=sl_distance,
    )


def format_position_info(result: PositionSizeResult) -> str:
    """Format position size info for logging/Telegram."""
    lines = [
        f"Leverage: {result.leverage}x{' (max)' if result.leverage_capped else ''}",
        f"Margin: ${result.margin_required:,.2f} ({result.position_size_pct:.1f}% of balance)",
        f"Position Value: ${result.position_value:,.2f}",
        f"Position Size: {result.position_size:.3f} BTC",
        f"Risk Amount: ${result.risk_amount:,.2f} ({result.risk_pct}%)",
        f"SL Distance: ${result.sl_distance:.2f} ({result.sl_pct:.2f}%)",
        f"Liquidation: ${result.liquidation_price:,.2f} ({result.liquidation_distance_pct:.1f}% from entry)",
    ]
    
    if result.is_liquidation_safe:
        lines.append(f"✅ Liquidation safe (beyond SL)")
    else:
        lines.append(f"⚠️  WARNING: Liquidation within SL range!")
    
    if result.is_position_capped:
        lines.append(f"⚠️  Capped at max position ({result.max_position_pct*100:.0f}%)")
    
    return "\n".join(lines)
