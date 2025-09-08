#!/usr/bin/env python3
"""
Test 3: Test Biblical Text Caching
Force tests the biblical text caching for a specific book (default: 'oba').
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

def main():
    print("=== TEST 3: BIBLICAL TEXT CACHING ===")
    print()
    
    # Get book from command line or default to 'oba'
    test_book = sys.argv[1] if len(sys.argv) > 1 else 'oba'
    test_user = 'editor3'
    
    print(f"Testing biblical text caching for book: '{test_book}'")
    print(f"Testing for user: '{test_user}'")
    print()
    
    try:
        from modules.processing_utils import ensure_biblical_text_cached
        from modules.cache_manager import CacheManager
        from modules.sheet_manager import SheetManager
        from modules.config_manager import ConfigManager
        from modules.logger import setup_logging

        config = ConfigManager()
        sheet_manager = SheetManager(config)
        cache_manager = CacheManager(config, sheet_manager)
        logger = setup_logging(config)

        print("Calling ensure_biblical_text_cached...")
        ensure_biblical_text_cached(test_user, test_book, cache_manager, sheet_manager, config, logger)
        print()
        print("✅ Biblical text caching completed")
        
        # Check if data was actually cached
        print()
        print("Checking cached data...")
        ult_cache_key = f"ult_chapters_{test_user}_{test_book}"
        ust_cache_key = f"ust_chapters_{test_user}_{test_book}"
        
        ult_data = cache_manager.get_cached_data(ult_cache_key)
        ust_data = cache_manager.get_cached_data(ust_cache_key)
        
        if ult_data:
            print(f"✅ ULT data cached: {len(str(ult_data))} characters")
        else:
            print("❌ No ULT data in cache")
            
        if ust_data:
            print(f"✅ UST data cached: {len(str(ust_data))} characters")
        else:
            print("❌ No UST data in cache")
        
    except Exception as e:
        print(f"❌ Biblical text caching failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()