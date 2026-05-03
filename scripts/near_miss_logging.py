#!/usr/bin/env python3
"""
Near-Miss Logging Script for v4
Logs cycles where confidence was close to threshold (50-67 points)
Helps understand why signals are not generated
"""

import asyncio
import sys
import logging
from datetime import datetime, timezone

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Add project path
sys.path.insert(0, '/opt/crypto-bot')

from database.db import Database


async def log_near_miss(
    cycle_time: str,
    confidence_score: int,
    blockers: list,
    market_state: str,
    volatility_regime: str,
    session: str
):
    """
    Log a near-miss cycle (confidence 50-67).
    
    Args:
        cycle_time: UTC timestamp
        confidence_score: Calculated confidence (50-67)
        blockers: List of reasons why signal was not generated
        market_state: ADX state (ranging/trending/dead_zone)
        volatility_regime: low/normal/high
        session: asian/london/ny/None
    """
    
    db = Database('data/signals.db')
    await db.connect()
    
    # Create near_miss table if not exists
    await db._exec("""
        CREATE TABLE IF NOT EXISTS near_miss (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_time DATETIME,
            confidence_score INTEGER,
            market_state TEXT,
            volatility_regime TEXT,
            session TEXT,
            blockers TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Insert near-miss
    blockers_str = ', '.join(blockers)
    await db._exec("""
        INSERT INTO near_miss (
            cycle_time, confidence_score, market_state, 
            volatility_regime, session, blockers
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (cycle_time, confidence_score, market_state, 
          volatility_regime, session, blockers_str))
    
    await db.close()
    
    # Also log to console
    logger.info(f"\n⚠️  NEAR-MISS DETECTED")
    logger.info(f"  Time: {cycle_time}")
    logger.info(f"  Confidence: {confidence_score}/100 (needed {68-confidence_score} more)")
    logger.info(f"  Market State: {market_state}, {volatility_regime}, {session or 'off-hours'}")
    logger.info(f"  Blockers: {blockers_str}")
    logger.info("")


async def get_near_miss_stats(hours: int = 24):
    """Get near-miss statistics for last N hours."""
    
    db = Database('data/signals.db')
    await db.connect()
    
    # Total near-misses
    total = await db._fetch_one(f"""
        SELECT COUNT(*) FROM near_miss 
        WHERE created_at > datetime('now', '-{hours} hours')
    """)
    
    # Average confidence
    avg_conf = await db._fetch_one(f"""
        SELECT AVG(confidence_score) FROM near_miss 
        WHERE created_at > datetime('now', '-{hours} hours')
    """)
    
    # Top blockers
    blockers = await db._fetch(f"""
        SELECT blockers, COUNT(*) as count FROM near_miss 
        WHERE created_at > datetime('now', '-{hours} hours')
        GROUP BY blockers
        ORDER BY count DESC
        LIMIT 5
    """)
    
    await db.close()
    
    return {
        'total': total[0] if total else 0,
        'avg_conf': avg_conf[0] if avg_conf else 0,
        'top_blockers': blockers or []
    }


async def send_daily_near_miss_report():
    """Generate daily near-miss report (for 00:00 UTC schedule)."""
    
    logger.info("=" * 70)
    logger.info("  📊 DAILY NEAR-MISS REPORT")
    logger.info("=" * 70)
    
    stats = await get_near_miss_stats(hours=24)
    
    logger.info(f"\n📈 Last 24 hours:")
    logger.info(f"  • Near-misses: {stats['total']}")
    logger.info(f"  • Avg confidence: {stats['avg_conf']:.1f}/100")
    
    if stats['top_blockers']:
        logger.info(f"\n🚫 Top blockers:")
        for blocker, count in stats['top_blockers'][:5]:
            logger.info(f"    • {blocker}: {count} times")
    
    logger.info("\n" + "=" * 70)
    
    return stats


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Near-miss logging utility')
    parser.add_argument('--report', action='store_true', help='Generate daily report')
    parser.add_argument('--hours', type=int, default=24, help='Hours for report')
    
    args = parser.parse_args()
    
    if args.report:
        asyncio.run(send_daily_near_miss_report())
    else:
        print("Usage: python3 near_miss_logging.py --report")
        print("       This script is called automatically from pipeline.py")
