#!/usr/bin/env python3
"""
Test 4: Test Chrome/Selenium Setup
Verifies that Chrome/Selenium is working properly for web scraping.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

def main():
    print("=== TEST 4: CHROME/SELENIUM SETUP ===")
    print()
    
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service

        print("Testing Chrome/Selenium setup...")
        print()
        
        # Configure Chrome options
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--remote-debugging-port=9222')
        
        print("Chrome options configured:")
        for arg in options.arguments:
            print(f"  {arg}")
        print()
        
        # Try to create driver
        print("Creating Chrome driver...")
        driver = webdriver.Chrome(options=options)
        print("✅ Chrome driver created successfully")
        
        # Test basic web access
        print("Testing basic web access...")
        driver.get('https://www.google.com')
        title = driver.title
        print(f"✅ Can access Google.com - Title: {title[:50]}...")
        
        # Test the actual site we need for biblical text
        print("Testing Door43 access...")
        driver.get('https://git.door43.org')
        title = driver.title
        print(f"✅ Can access Door43 - Title: {title[:50]}...")
        
        # Test a specific ULT page
        print("Testing specific ULT page access...")
        test_url = "https://git.door43.org/unfoldingWord/en_ult/raw/branch/master/01-GEN/01.usfm"
        driver.get(test_url)
        page_text = driver.page_source[:200]
        print(f"✅ Can access ULT page - Content preview: {page_text[:100]}...")
        
        driver.quit()
        print()
        print("✅ Chrome/Selenium fully working")
        
    except ImportError as e:
        print(f"❌ Import error - Selenium not installed: {e}")
        print("Install with: pip install selenium")
        
    except Exception as e:
        print(f"❌ Chrome/Selenium failed: {e}")
        print()
        print("Common fixes:")
        print("- Install Chrome: sudo apt install google-chrome-stable")
        print("- Install ChromeDriver: sudo apt install chromium-chromedriver")  
        print("- Or install Chromium: sudo apt install chromium-browser")
        print()
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()