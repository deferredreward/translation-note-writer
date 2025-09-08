#!/usr/bin/env python3
"""
Run All Linux Migration Tests
Runs all diagnostic tests in sequence to identify biblical text fetching issues.
Creates detailed log files for easy sharing and debugging.
"""

import sys
import os
import subprocess
import datetime

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

def run_test(test_script, log_file):
    """Run a test script and capture output"""
    test_name = os.path.basename(test_script)
    
    print("=" * 60)
    print(f"RUNNING: {test_name}")
    print("=" * 60)
    
    # Write to log file
    log_file.write("=" * 60 + "\n")
    log_file.write(f"RUNNING: {test_name}\n")
    log_file.write(f"Time: {datetime.datetime.now()}\n")
    log_file.write("=" * 60 + "\n")
    
    try:
        # Run the test script
        result = subprocess.run([sys.executable, test_script], 
                              capture_output=True, text=True, timeout=300)  # 5 minutes for Linux
        
        # Combine stdout and stderr for complete output
        full_output = ""
        if result.stdout:
            full_output += result.stdout
        if result.stderr:
            full_output += "\n--- STDERR ---\n" + result.stderr
        
        # Print to console
        if full_output:
            print(full_output)
        
        # Write to log file
        log_file.write(full_output + "\n")
        
        # Handle return code
        success = result.returncode == 0
        status_msg = f"✅ Test completed successfully" if success else f"❌ Test failed with return code: {result.returncode}"
        
        print(status_msg)
        log_file.write(status_msg + "\n")
        log_file.write("\n")
        
        return success
        
    except subprocess.TimeoutExpired:
        error_msg = "❌ Test timed out (300 seconds / 5 minutes)"
        print(error_msg)
        log_file.write(error_msg + "\n\n")
        return False
    except Exception as e:
        error_msg = f"❌ Error running test: {e}"
        print(error_msg)
        log_file.write(error_msg + "\n\n")
        return False

def main():
    print("=== LINUX MIGRATION DIAGNOSTIC TESTS ===")
    print()
    print("This will run all diagnostic tests to identify biblical text fetching issues.")
    print()
    
    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    
    # Create log file with timestamp
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    log_filename = f"linux_migration_tests_{timestamp}.log"
    log_path = os.path.join(logs_dir, log_filename)
    
    print(f"📝 Logging to: {log_path}")
    print()
    
    # Get test directory
    test_dir = os.path.dirname(__file__)
    
    # List of tests to run in order
    tests = [
        "01_check_book_detection.py",
        "02_test_book_detection_logic.py", 
        "04_test_chrome_selenium.py",
        "05_test_biblical_text_scraper.py",
        "03_test_biblical_text_caching.py",
    ]
    
    results = []
    
    # Open log file
    with open(log_path, 'w', encoding='utf-8') as log_file:
        # Write header to log
        log_file.write("LINUX MIGRATION DIAGNOSTIC TESTS\n")
        log_file.write("=" * 50 + "\n")
        log_file.write(f"Start time: {datetime.datetime.now()}\n")
        log_file.write(f"Python version: {sys.version}\n")
        log_file.write(f"Working directory: {os.getcwd()}\n")
        log_file.write("=" * 50 + "\n\n")
        
        for test in tests:
            test_path = os.path.join(test_dir, test)
            if os.path.exists(test_path):
                success = run_test(test_path, log_file)
                results.append((test, success))
                print()
            else:
                error_msg = f"⚠️  Test not found: {test}"
                print(error_msg)
                log_file.write(error_msg + "\n\n")
                results.append((test, False))
    
        # Write summary to log file
        log_file.write("=" * 50 + "\n")
        log_file.write("TEST SUMMARY\n")
        log_file.write("=" * 50 + "\n")
        
        passed = 0
        failed = 0
        
        for test, success in results:
            status = "✅ PASS" if success else "❌ FAIL"
            summary_line = f"{status}: {test}"
            print(summary_line)
            log_file.write(summary_line + "\n")
            if success:
                passed += 1
            else:
                failed += 1
        
        summary_stats = [
            f"Total: {len(results)} tests",
            f"Passed: {passed}",
            f"Failed: {failed}"
        ]
        
        print()
        for stat in summary_stats:
            print(stat)
            log_file.write(stat + "\n")
        
        if failed == 0:
            conclusion = "🎉 All tests passed! The issue might be in the application logic."
        else:
            conclusion = "🔍 Some tests failed. Check the output above for specific issues."
        
        print()
        print(conclusion)
        log_file.write("\n" + conclusion + "\n")
        
        next_steps = [
            "Next steps:",
            "1. Fix any Chrome/Selenium issues first",
            "2. Check book detection logic", 
            "3. Verify biblical text scraping works",
            "4. Test the complete caching pipeline"
        ]
        
        print()
        log_file.write("\n")
        for step in next_steps:
            print(step)
            log_file.write(step + "\n")
        
        log_file.write(f"\nEnd time: {datetime.datetime.now()}\n")
    
    print()
    print(f"📄 Complete log saved to: {log_path}")
    print("You can copy this log file to share the results!")

if __name__ == "__main__":
    main()