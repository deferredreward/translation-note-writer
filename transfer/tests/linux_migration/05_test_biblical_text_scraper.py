#!/usr/bin/env python3
"""
Test 5: Test Biblical Text Scraper
Directly tests the biblical text scraping using the actual system API.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.getcwd())

def main():
    print("=== TEST 5: BIBLICAL TEXT SCRAPER ===")
    print()
    
    # Get book from command line or default to 'oba'
    test_book = sys.argv[1] if len(sys.argv) > 1 else 'oba'
    test_chapter = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    
    print(f"Testing biblical text scraper for book: '{test_book}', chapter: {test_chapter}")
    print()
    
    try:
        # Import the actual biblical text scraper class
        from modules.biblical_text_scraper import BiblicalTextScraper
        print("✅ BiblicalTextScraper imported successfully")
        print()
        
        # Create scraper instance
        scraper = BiblicalTextScraper()
        
        # Test ULT fetching
        print(f"Fetching ULT for {test_book}...")
        try:
            ult_result = scraper.scrape_biblical_text(test_book.upper(), 'ULT')
            if ult_result:
                chapters = ult_result.get('chapters', [])
                if chapters:
                    total_verses = sum(len(ch.get('verses', [])) for ch in chapters)
                    print(f"✅ ULT fetched: {len(chapters)} chapters, {total_verses} verses")
                    
                    # Show sample content
                    first_chapter = chapters[0]
                    first_verses = first_chapter.get('verses', [])[:3]  # First 3 verses
                    for verse in first_verses:
                        content = verse.get('content', '')[:100]
                        print(f"  Sample verse {verse.get('number', '?')}: {content}...")
                else:
                    print("❌ ULT data has no chapters")
            else:
                print("❌ ULT fetch returned empty/None")
        except Exception as e:
            print(f"❌ ULT fetch failed: {e}")
        
        print()
        
        # Test UST fetching  
        print(f"Fetching UST for {test_book}...")
        try:
            ust_result = scraper.scrape_biblical_text(test_book.upper(), 'UST')
            if ust_result:
                chapters = ust_result.get('chapters', [])
                if chapters:
                    total_verses = sum(len(ch.get('verses', [])) for ch in chapters)
                    print(f"✅ UST fetched: {len(chapters)} chapters, {total_verses} verses")
                    
                    # Show sample content
                    first_chapter = chapters[0]
                    first_verses = first_chapter.get('verses', [])[:3]  # First 3 verses
                    for verse in first_verses:
                        content = verse.get('content', '')[:100]
                        print(f"  Sample verse {verse.get('number', '?')}: {content}...")
                else:
                    print("❌ UST data has no chapters")
            else:
                print("❌ UST fetch returned empty/None")
        except Exception as e:
            print(f"❌ UST fetch failed: {e}")
            
        print()
        print("✅ Biblical text scraper test completed")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure you're running from the project root directory")
        print(f"Current working directory: {os.getcwd()}")
        print(f"Python path: {sys.path[:3]}...")
        
    except Exception as e:
        print(f"❌ Biblical text scraper test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Usage: python 05_test_biblical_text_scraper.py [book] [chapter]")
    print("Example: python 05_test_biblical_text_scraper.py oba 1")
    print("Example: python 05_test_biblical_text_scraper.py mat 1")
    print()
    main()