#!/usr/bin/env python3
"""
Test 2: Test Book Detection Logic
Tests the actual book detection logic that should trigger biblical text caching.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

def main():
    print("=== TEST 2: BOOK DETECTION LOGIC ===")
    print()
    
    try:
        from modules.cache_manager import CacheManager
        from modules.sheet_manager import SheetManager  
        from modules.config_manager import ConfigManager

        config = ConfigManager()
        sheet_manager = SheetManager(config)
        cache_manager = CacheManager(config, sheet_manager)

        # Get items like the system does
        sheet_id = config.get('google_sheets.sheet_ids', {}).get('editor3')
        print(f"Getting items from sheet: {sheet_id}")
        
        items = sheet_manager.get_pending_work(sheet_id, max_items=5)
        print(f"Retrieved {len(items)} items")
        print()

        if items:
            print("Testing book detection logic...")
            user, book = cache_manager.detect_user_book_from_items(items)
            print(f"Detected: user=\"{user}\", book=\"{book}\"")
            print()
            
            if book:
                print(f"✅ Book \"{book}\" was detected - should trigger biblical text fetch")
            else:
                print("❌ No book detected - this is the problem!")
                print()
                print("DEBUG: Available columns in first item:")
                for key, value in items[0].items():
                    print(f"  {key}: \"{value}\"")
                print()
                print("The system expects a 'Book' column with a valid book abbreviation.")
        else:
            print("⚠️  No pending items found")
            
        print()
        print("✅ Book detection logic test completed")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()