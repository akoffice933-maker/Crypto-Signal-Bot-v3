#!/usr/bin/env python3
"""
Daily Auto-Report Script
Runs at 00:00 UTC and sends summary to Telegram
Shows signals, winrate, blockers, and near-misses
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
from telegram.bot import TelegramNotifier
from config.settings import settings


async def generate_daily_report():
    """
    Generate and send daily report at 00:00 UTC.
    
    Includes:
    - Signals count (24h)
    - Winrate (if any closed trades)
    - Avg confidence
    - Top blockers
    - Near-misses
    - Market conditions summary
    """
    
    logger.info("=" * 70)
    logger.info("  📊 GENERATING DAILY REPORT")
    logger.info("=" * 70)
    
    db = Database('data/signals.db')
    await db.connect()
    
    # Signals (24h)
    signals_24h = await db._fetch_one("""
        SELECT COUNT(*) FROM signals 
        WHERE created_at > datetime('now', '-24 hours')
    """)
    
    # Winrate (24h, closed trades only)
    winrate = await db._fetch_one("""
        SELECT 
            SUM(CASE WHEN status='tp_hit' THEN 1 ELSE 0 END) * 100.0 / 
            NULLIF(SUM(CASE WHEN status IN ('tp_hit', 'sl_hit') THEN 1 ELSE 0 END), 0)
        FROM signals 
        WHERE created_at > datetime('now', '-24 hours')
    """)
    
    # Avg confidence (24h)
    avg_conf = await db._fetch_one("""
        SELECT AVG(confidence_score) FROM signals 
        WHERE created_at > datetime('now', '-24 hours')
    """)
    
    # Avg RR (24h)
    avg_rr = await db._fetch_one("""
        SELECT AVG(rr_ratio) FROM signals 
        WHERE created_at > datetime('now', '-24 hours')
    """)
    
    # Near-misses (24h)
    near_misses = await db._fetch_one("""
        SELECT COUNT(*) FROM near_miss 
        WHERE created_at > datetime('now', '-24 hours')
    """)
    
    # Top blockers (24h)
    blockers = await db._fetch("""
        SELECT blockers, COUNT(*) as count FROM near_miss 
        WHERE created_at > datetime('now', '-24 hours')
        GROUP BY blockers
        ORDER BY count DESC
        LIMIT 3
    """)
    
    # Active liquidity pools
    active_pools = await db._fetch_one("""
        SELECT COUNT(*) FROM liquidity_pools WHERE is_active=1
    """)
    
    await db.close()
    
    # Format report
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    report = f"""
📊 **Daily Recap — {today}**

**Signals (24h):** {signals_24h[0] if signals_24h else 0}

"""
    
    if signals_24h and signals_24h[0] > 0:
        report += f"""**Winrate:** {winrate[0]:.1f}% (if closed)
**Avg Confidence:** {avg_conf[0]:.1f}%
**Avg RR:** {avg_rr[0]:.2f}

"""
    else:
        report += """**No signals today** (market conditions not met)

"""
    
    if near_misses and near_misses[0] > 0:
        report += f"""**Near-misses:** {near_misses[0]}
"""
        
        if blockers:
            report += f"""**Top Blockers:**
"""
            for blocker, count in blockers[:3]:
                report += f"• {blocker}: {count}x\n"
        report += "\n"
    
    report += f"""**Active Liquidity Pools:** {active_pools[0] if active_pools else 0}

─────────────────────────────
🤖 Bot: @Akoffice_bot
📊 Dashboard: http://{settings.base_url.replace('https://', '').split('/')[0]}:8001/dashboard
"""
    
    logger.info(report)
    
    # Send to Telegram
    notifier = TelegramNotifier()
    await notifier.start()
    await notifier.send_text(report)
    await notifier.stop()
    
    logger.info("✅ Daily report sent to Telegram!")
    logger.info("=" * 70)
    
    return {
        'signals_24h': signals_24h[0] if signals_24h else 0,
        'winrate': winrate[0] if winrate else 0,
        'avg_conf': avg_conf[0] if avg_conf else 0,
        'near_misses': near_misses[0] if near_misses else 0,
    }


async def main():
    """Main function."""
    try:
        await generate_daily_report()
    except Exception as e:
        logger.error(f"Failed to generate daily report: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
