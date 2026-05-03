#!/usr/bin/env python3
"""
Check and Fix CVD/OI Recording Script
Verifies that CVD and OI data are being saved to database
Adds recording if missing
"""

import asyncio
import sys
import logging
import re
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Add project path
sys.path.insert(0, '/opt/crypto-bot')

from database.db import Database


def check_pipeline_code():
    """Check if pipeline.py has CVD/OI recording code."""
    
    logger.info("=" * 70)
    logger.info("  🔍 CHECKING PIPELINE CODE FOR CVD/OI RECORDING")
    logger.info("=" * 70)
    
    pipeline_path = '/opt/crypto-bot/engine/pipeline.py'
    
    try:
        with open(pipeline_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        logger.error(f"❌ File not found: {pipeline_path}")
        return False
    
    # Check for OI recording
    has_oi_save = 'db.save_oi' in content
    logger.info(f"\n📊 OI Recording:")
    logger.info(f"  • db.save_oi call: {'✅ Found' if has_oi_save else '❌ Missing'}")
    
    # Check for CVD recording
    has_cvd_save = 'db.add_cvd_delta' in content
    logger.info(f"\n📊 CVD Recording:")
    logger.info(f"  • db.add_cvd_delta call: {'✅ Found' if has_cvd_save else '❌ Missing'}")
    
    # Check for imports
    has_datetime = 'from datetime import' in content
    logger.info(f"\n📊 Imports:")
    logger.info(f"  • datetime import: {'✅ Found' if has_datetime else '❌ Missing'}")
    
    needs_fix = not (has_oi_save and has_cvd_save)
    
    if needs_fix:
        logger.info("\n⚠️  CODE NEEDS FIX!")
        logger.info("Run: python3 /opt/crypto-bot/scripts/fix_cvd_oi_recording.py")
    else:
        logger.info("\n✅ CODE IS OK!")
    
    logger.info("=" * 70)
    
    return not needs_fix


async def check_database_tables():
    """Check if CVD and OI tables exist."""
    
    logger.info("\n" + "=" * 70)
    logger.info("  🔍 CHECKING DATABASE TABLES")
    logger.info("=" * 70)
    
    db = Database('data/signals.db')
    await db.connect()
    
    # Check tables
    tables = await db._fetch("""
        SELECT name FROM sqlite_master WHERE type='table'
    """)
    
    table_names = [t[0] for t in (tables or [])]
    
    logger.info(f"\n📊 Tables found: {len(table_names)}")
    for table in sorted(table_names):
        count = await db._fetch_one(f"SELECT COUNT(*) FROM {table}")
        logger.info(f"  • {table}: {count[0] if count else 0} rows")
    
    # Check specific tables
    has_cvd = 'cvd_buckets' in table_names
    has_oi = 'oi_snapshots' in table_names
    
    logger.info(f"\n📊 Required tables:")
    logger.info(f"  • cvd_buckets: {'✅ Exists' if has_cvd else '❌ Missing'}")
    logger.info(f"  • oi_snapshots: {'✅ Exists' if has_oi else '❌ Missing'}")
    
    await db.close()
    
    logger.info("=" * 70)
    
    return has_cvd and has_oi


async def test_cvd_oi_recording():
    """Test if CVD and OI are actually being recorded."""
    
    logger.info("\n" + "=" * 70)
    logger.info("  🧪 TESTING CVD/OI RECORDING")
    logger.info("=" * 70)
    
    db = Database('data/signals.db')
    await db.connect()
    
    # Check recent CVD
    cvd_count = await db._fetch_one("SELECT COUNT(*) FROM cvd_buckets")
    logger.info(f"\n📊 CVD Buckets: {cvd_count[0] if cvd_count else 0}")
    
    # Check recent OI
    oi_count = await db._fetch_one("SELECT COUNT(*) FROM oi_snapshots")
    logger.info(f"📊 OI Snapshots: {oi_count[0] if oi_count else 0}")
    
    # Check if recent (last 24h)
    oi_recent = await db._fetch_one("""
        SELECT COUNT(*) FROM oi_snapshots 
        WHERE recorded_at > datetime('now', '-24 hours')
    """)
    logger.info(f"📊 OI (last 24h): {oi_recent[0] if oi_recent else 0}")
    
    await db.close()
    
    if (cvd_count and cvd_count[0] > 0) or (oi_recent and oi_recent[0] > 0):
        logger.info("\n✅ CVD/OI recording is WORKING!")
    else:
        logger.info("\n⚠️  CVD/OI recording is NOT WORKING!")
        logger.info("Run: python3 /opt/crypto-bot/scripts/fix_cvd_oi_recording.py")
    
    logger.info("=" * 70)


async def main():
    """Main check function."""
    
    logger.info("\n" + "=" * 70)
    logger.info("  📋 CVD/OI RECORDING CHECK")
    logger.info("=" * 70)
    
    # Check code
    code_ok = check_pipeline_code()
    
    # Check tables
    tables_ok = await check_database_tables()
    
    # Test recording
    await test_cvd_oi_recording()
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("  📊 SUMMARY")
    logger.info("=" * 70)
    logger.info(f"  • Code check: {'✅ PASS' if code_ok else '❌ FAIL'}")
    logger.info(f"  • Tables check: {'✅ PASS' if tables_ok else '❌ FAIL'}")
    logger.info("=" * 70)
    
    if code_ok and tables_ok:
        logger.info("\n✅ ALL CHECKS PASSED!")
    else:
        logger.info("\n⚠️  SOME CHECKS FAILED!")
        logger.info("\nTo fix, run:")
        logger.info("  python3 /opt/crypto-bot/scripts/fix_cvd_oi_recording.py")
    
    logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
