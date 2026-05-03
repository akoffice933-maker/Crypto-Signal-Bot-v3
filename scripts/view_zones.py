#!/usr/bin/env python3
"""
Crypto Signal Bot v3 - Quick Liquidity Zones View
Usage: python3 scripts/view_zones.py
"""

import sqlite3
import sys

DB_PATH = "data/signals.db"

def view_zones(min_strength=3.0, limit=20):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get active liquidity pools (Gravity Zones)
    cursor.execute("""
        SELECT timeframe, pool_type, price, touch_count, strength, mitigated
        FROM liquidity_pools
        WHERE is_active = 1 AND strength >= ?
        ORDER BY strength DESC, timeframe DESC
        LIMIT ?
    """, (min_strength, limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print(f"\n❌ No active zones with strength >= {min_strength}\n")
        return
    
    print("\n" + "=" * 80)
    print("  🎯 CRYPTO SIGNAL BOT - ACTIVE GRAVITY ZONES")
    print("=" * 80)
    print(f"  Min Strength: {min_strength} | Limit: {limit} | DB: {DB_PATH}")
    print("=" * 80)
    print()
    print(f"{'TF':<6} {'Type':<14} {'Price':<14} {'Touches':<10} {'Strength':<10} {'Mitigated':<10}")
    print("-" * 80)
    
    for row in rows:
        tf, ptype, price, touches, strength, mitigated = row
        mitigated_str = "✅" if mitigated else "⭕"
        emoji = "🔴" if ptype == "equal_highs" else "🟢"
        print(f"{tf:<6} {emoji} {ptype:<12} ${price:<12,.2f} {touches:<10} {strength:<10.2f} {mitigated_str:<10}")
    
    print("-" * 80)
    print(f"Total zones: {len(rows)}")
    print("=" * 80)
    
    # Summary by timeframe
    print("\n📊 SUMMARY BY TIMEFRAME:")
    print("-" * 40)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT timeframe, COUNT(*), AVG(strength), MAX(price), MIN(price)
        FROM liquidity_pools
        WHERE is_active = 1
        GROUP BY timeframe
        ORDER BY timeframe DESC
    """)
    
    for row in cursor.fetchall():
        tf, count, avg_str, max_p, min_p = row
        print(f"  {tf:<6} | Zones: {count:<3} | Avg Strength: {avg_str:.2f} | Range: ${min_p:,.0f} - ${max_p:,.0f}")
    
    conn.close()
    print("=" * 80)
    print()

if __name__ == "__main__":
    min_str = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    view_zones(min_str, limit)
