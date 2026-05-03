#!/usr/bin/env python3
"""
Fix CVD/OI Recording Script
Adds CVD and OI recording code to pipeline.py
"""

import sys
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Add project path
sys.path.insert(0, '/opt/crypto-bot')


def fix_pipeline():
    """Add CVD/OI recording to pipeline.py"""
    
    logger.info("=" * 70)
    logger.info("  🔧 FIXING CVD/OI RECORDING IN PIPELINE")
    logger.info("=" * 70)
    
    pipeline_path = '/opt/crypto-bot/engine/pipeline.py'
    
    try:
        with open(pipeline_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        logger.error(f"❌ File not found: {pipeline_path}")
        return False
    
    # Check if already fixed
    if 'db.save_oi' in content and 'db.add_cvd_delta' in content:
        logger.info("\n✅ Code already has CVD/OI recording!")
        return True
    
    # Add datetime import if missing
    if 'from datetime import' not in content:
        logger.info("\n📝 Adding datetime import...")
        content = content.replace(
            'import logging',
            'import logging\nfrom datetime import datetime, timezone'
        )
    
    # Find the Order Flow section and add recording
    logger.info("\n📝 Adding CVD/OI recording code...")
    
    # Find where to insert OI recording
    oi_marker = 'await db.save_oi(oi_now, current_price)'
    if oi_marker in content:
        logger.info("  • OI recording already exists")
    else:
        # Add after OI cascade calculation
        oi_cascade_marker = 'cascade, oi_chg_pct = evaluate_oi_cascade('
        if oi_cascade_marker in content:
            # Find the end of this block
            insert_pos = content.find(oi_cascade_marker)
            # Find the closing parenthesis
            paren_count = 0
            for i, char in enumerate(content[insert_pos:], insert_pos):
                if char == '(':
                    paren_count += 1
                elif char == ')':
                    paren_count -= 1
                    if paren_count == 0:
                        # Found end of function call
                        insert_pos = i + 1
                        break
            
            # Add newline and recording code
            recording_code = '''
    # Save OI to database
    await db.save_oi(oi_now, current_price)'''
            
            content = content[:insert_pos] + recording_code + content[insert_pos:]
            logger.info("  • Added OI recording")
    
    # Find where to insert CVD recording
    cvd_marker = 'cvd_div = ws.cvd_divergence()'
    if cvd_marker in content:
        logger.info("  • CVD recording already exists")
    else:
        # Add after CVD divergence check
        cvd_check_marker = 'cvd_div = ws.cvd_divergence() if ws.is_connected else None'
        if cvd_check_marker in content:
            insert_pos = content.find(cvd_check_marker)
            # Find end of line
            end_of_line = content.find('\n', insert_pos)
            
            recording_code = '''
    
    # Save CVD to database
    cvd_now = ws.current_cvd() if ws.is_connected else None
    if cvd_now is not None and ctx.session:
        try:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            await db.add_cvd_delta(ctx.session, date_str, cvd_now)
        except Exception as e:
            logger.warning(f"Failed to save CVD: {e}")'''
            
            content = content[:end_of_line] + recording_code + content[end_of_line:]
            logger.info("  • Added CVD recording")
    
    # Write back
    with open(pipeline_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logger.info("\n✅ Code updated successfully!")
    logger.info("\n" + "=" * 70)
    logger.info("  📋 NEXT STEPS:")
    logger.info("=" * 70)
    logger.info("  1. Restart the bot:")
    logger.info("     systemctl restart crypto-bot")
    logger.info("  2. Check logs:")
    logger.info("     journalctl -u crypto-bot -f")
    logger.info("  3. Verify CVD/OI recording:")
    logger.info("     python3 /opt/crypto-bot/scripts/check_cvd_oi.py")
    logger.info("=" * 70)
    
    return True


if __name__ == "__main__":
    success = fix_pipeline()
    sys.exit(0 if success else 1)
