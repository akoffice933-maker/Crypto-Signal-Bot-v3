#!/usr/bin/env python3
"""
Rebuild Liquidity Pools Script
Forces rebuild of liquidity levels from Binance data
Run manually or schedule daily
"""

import asyncio
import sys
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Add project path
sys.path.insert(0, '/opt/crypto-bot')

from data.binance_client import BinanceFuturesClient
from engine.candle_loader import load_candles
from engine.liquidity_map import build_liquidity_map, detect_levels
from database.db import Database


async def rebuild_liquidity(
    symbol: str = 'BTCUSDT',
    min_touches: int = 2,
    clear_existing: bool = True
):
    """
    Rebuild liquidity pools from scratch.
    
    Args:
        symbol: Trading pair
        min_touches: Minimum touches for level to be valid
        clear_existing: Clear existing levels before rebuild
    """
    
    logger.info("=" * 70)
    logger.info("  🔄 REBUILDING LIQUIDITY POOLS")
    logger.info("=" * 70)
    logger.info(f"  Symbol: {symbol}")
    logger.info(f"  Min touches: {min_touches}")
    logger.info(f"  Clear existing: {clear_existing}")
    logger.info("=" * 70)
    
    # Connect to DB
    db = Database('data/signals.db')
    await db.connect()
    
    # Clear existing levels if requested
    if clear_existing:
        logger.info("\n🗑️  Clearing existing levels...")
        await db._exec("DELETE FROM liquidity_pools")
        logger.info("✅ Existing levels cleared")
    
    # Load candles from Binance
    logger.info("\n📊 Loading candles from Binance...")
    client = BinanceFuturesClient('https://fapi.binance.com')
    
    try:
        candles = await load_candles(client, symbol, ['1d', '4h'])
    except Exception as e:
        logger.error(f"❌ Failed to load candles: {e}")
        await db.close()
        return False
    
    logger.info(f"✅ Loaded {len(candles['1d'])} daily candles")
    logger.info(f"✅ Loaded {len(candles['4h'])} 4h candles")
    
    # Get current price
    current_price = float(candles['1d']['close'].iloc[-1])
    logger.info(f"\n💰 Current price: ${current_price:,.2f}")
    
    # Detect 1D levels
    logger.info("\n📊 Detecting 1D levels...")
    levels_1d = detect_levels(candles['1d'], '1d', current_price, min_touches=min_touches)
    logger.info(f"✅ Found {len(levels_1d)} levels on 1D")
    
    # Detect 4H levels
    logger.info("\n📊 Detecting 4H levels...")
    levels_4h = detect_levels(candles['4h'], '4h', current_price, min_touches=min_touches)
    logger.info(f"✅ Found {len(levels_4h)} levels on 4H")
    
    # Save to DB
    logger.info("\n💾 Saving to database...")
    all_levels = levels_1d + levels_4h
    
    saved_count = 0
    for level in all_levels:
        try:
            await db.upsert_pool(
                timeframe=level.timeframe,
                pool_type=level.pool_type,
                price=level.price,
                touch_count=level.touch_count,
                strength=level.strength
            )
            saved_count += 1
        except Exception as e:
            logger.warning(f"Failed to save level {level}: {e}")
    
    logger.info(f"✅ Saved {saved_count}/{len(all_levels)} levels")
    
    # Show summary
    logger.info("\n" + "=" * 70)
    logger.info("  📊 SUMMARY")
    logger.info("=" * 70)
    
    # Count by timeframe
    for tf in ['1d', '4h']:
        tf_levels = [l for l in all_levels if l.timeframe == tf]
        logger.info(f"  • {tf.upper()}: {len(tf_levels)} levels")
    
    # Count by type
    for ptype in ['equal_highs', 'equal_lows']:
        type_levels = [l for l in all_levels if l.pool_type == ptype]
        emoji = "🔴" if ptype == "equal_highs" else "🟢"
        logger.info(f"  • {emoji} {ptype}: {len(type_levels)} levels")
    
    # Show top 5 by strength
    logger.info("\n🎯 TOP 5 LEVELS BY STRENGTH:")
    for i, level in enumerate(sorted(all_levels, key=lambda x: x.strength, reverse=True)[:5], 1):
        emoji = "🔴" if level.pool_type == "equal_highs" else "🟢"
        logger.info(f"  {i}. {emoji} {level.timeframe} {level.pool_type}: ${level.price:,.2f} (strength: {level.strength:.2f})")
    
    # Verify in DB
    await db._exec("SELECT COUNT(*) FROM liquidity_pools WHERE is_active=1")
    
    logger.info("\n" + "=" * 70)
    logger.info("  ✅ REBUILD COMPLETE!")
    logger.info("=" * 70)
    
    await db.close()
    return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Rebuild liquidity pools')
    parser.add_argument('--symbol', default='BTCUSDT', help='Trading pair')
    parser.add_argument('--min-touches', type=int, default=2, help='Minimum touches')
    parser.add_argument('--clear', action='store_true', help='Clear existing levels')
    
    args = parser.parse_args()
    
    success = asyncio.run(rebuild_liquidity(
        symbol=args.symbol,
        min_touches=args.min_touches,
        clear_existing=args.clear
    ))
    
    sys.exit(0 if success else 1)
