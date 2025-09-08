#!/usr/bin/env python3
"""
Run Single Linux Migration Test
Runs a single diagnostic test with detailed logging.
"""

import sys
import os
import subprocess
import datetime

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

def main():
    if len(sys.argv) < 2:
        print("Usage: python run_single_test.py <test_number>")
        print()
        print("Available tests:")
        print("  1 - Book Detection Check")
        print("  2 - Book Detection Logic Test")
        print("  3 - Biblical Text Caching Test")
        print("  4 - Chrome/Selenium Test") 
        print("  5 - Biblical Text Scraper Test")
        print()
        print("Example: python run_single_test.py 4")
        return
    
    test_num = sys.argv[1]
    
    # Map test numbers to scripts
    test_map = {
        '1': '01_check_book_detection.py',
        '2': '02_test_book_detection_logic.py',
        '3': '03_test_biblical_text_caching.py',
        '4': '04_test_chrome_selenium.py',
        '5': '05_test_biblical_text_scraper.py'
    }
    
    if test_num not in test_map:
        print(f"❌ Invalid test number: {test_num}")
        return
    
    test_script = test_map[test_num]
    test_path = os.path.join(os.path.dirname(__file__), test_script)
    
    if not os.path.exists(test_path):
        print(f"❌ Test script not found: {test_script}")
        return
    
    # Create logs directory
    logs_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    
    # Create log file
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    log_filename = f"linux_test_{test_num}_{timestamp}.log"
    log_path = os.path.join(logs_dir, log_filename)
    
    print(f"=== RUNNING SINGLE TEST: {test_script} ===")
    print(f"📝 Logging to: {log_path}")
    print()
    
    try:
        # Run the test
        result = subprocess.run([sys.executable, test_path], 
                              capture_output=True, text=True, timeout=300)  # 5 minutes for Linux
        
        # Combine output
        full_output = ""
        if result.stdout:
            full_output += result.stdout
        if result.stderr:
            full_output += "\n--- STDERR ---\n" + result.stderr
        
        # Print to console
        if full_output:
            print(full_output)
        
        # Write to log file
        with open(log_path, 'w', encoding='utf-8') as log_file:
            log_file.write(f"LINUX MIGRATION TEST: {test_script}\n")
            log_file.write("=" * 50 + "\n")
            log_file.write(f"Time: {datetime.datetime.now()}\n")
            log_file.write(f"Python version: {sys.version}\n")
            log_file.write(f"Working directory: {os.getcwd()}\n")
            log_file.write("=" * 50 + "\n\n")
            log_file.write(full_output)
            
            success = result.returncode == 0
            status_msg = f"\n✅ Test completed successfully" if success else f"\n❌ Test failed with return code: {result.returncode}"
            log_file.write(status_msg + "\n")
            log_file.write(f"\nEnd time: {datetime.datetime.now()}\n")
        
        # Print status
        if result.returncode == 0:
            print("\n✅ Test completed successfully")
        else:
            print(f"\n❌ Test failed with return code: {result.returncode}")
        
        print(f"\n📄 Log saved to: {log_path}")
        
    except subprocess.TimeoutExpired:
        print("❌ Test timed out (300 seconds / 5 minutes)")
    except Exception as e:
        print(f"❌ Error running test: {e}")

if __name__ == "__main__":
    main()