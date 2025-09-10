#!/usr/bin/env python3
"""
Test 1: Check Book Detection
Verifies what book is being detected from the spreadsheet items.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

def main():
    print("=== TEST 1: BOOK DETECTION CHECK ===")
    print()
    
    try:
        from modules.config_manager import ConfigManager
        from modules.sheet_manager import SheetManager

        config = ConfigManager()
        sheet_manager = SheetManager(config)

        # Get sheet ID for editor3 (Benjamin)
        sheet_ids = config.get('google_sheets.sheet_ids', {})
        sheet_id = sheet_ids.get('editor3')
        print(f"Editor3 sheet ID: {sheet_id}")
        
        if not sheet_id:
            print("❌ ERROR: No sheet ID found for editor3")
            return
        
        # Get the pending items to see what book it detected
        print("Fetching pending items...")
        items = sheet_manager.get_pending_work(sheet_id, max_items=5)
        print(f"Found {len(items)} items:")
        print()
        
        if not items:
            print("⚠️  No pending items found")
            return
            
        for i, item in enumerate(items):
            book_value = item.get("Book", "MISSING")
            ref_value = item.get("Ref", "MISSING")
            go_value = item.get("Go?", "MISSING")
            print(f"  Item {i+1}:")
            print(f"    Book: \"{book_value}\"")
            print(f"    Ref: \"{ref_value}\"") 
            print(f"    Go?: \"{go_value}\"")
            print()
        
        print("Available columns in first item:")
        for key, value in items[0].items():
            print(f"  {key}: \"{value}\"")
        
        print()
        print("✅ Book detection check completed")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()