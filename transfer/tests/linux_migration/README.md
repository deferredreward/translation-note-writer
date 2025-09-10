# Linux Migration Diagnostic Tests

This directory contains diagnostic tests to identify and fix biblical text fetching issues when migrating the Translation Notes AI system to Linux.

## 📋 Overview

These tests help diagnose why biblical text (ULT/UST) is not being fetched on Linux systems. Common issues include:
- Chrome/Selenium setup problems
- Book detection logic failures
- Network/scraping issues
- Cache management problems

## 🧪 Individual Tests

### 1. Book Detection Check
**File:** `01_check_book_detection.py`
**Purpose:** Verify what book data is in the spreadsheet
```bash
python tests/linux_migration/01_check_book_detection.py
```

### 2. Book Detection Logic Test
**File:** `02_test_book_detection_logic.py`  
**Purpose:** Test the actual book detection logic
```bash
python tests/linux_migration/02_test_book_detection_logic.py
```

### 3. Biblical Text Caching Test
**File:** `03_test_biblical_text_caching.py`
**Purpose:** Force test the biblical text caching pipeline
```bash
python tests/linux_migration/03_test_biblical_text_caching.py
# Or test specific book:
python tests/linux_migration/03_test_biblical_text_caching.py mat
```

### 4. Chrome/Selenium Test
**File:** `04_test_chrome_selenium.py`
**Purpose:** Verify Chrome/Selenium is working
```bash
python tests/linux_migration/04_test_chrome_selenium.py
```

### 5. Biblical Text Scraper Test
**File:** `05_test_biblical_text_scraper.py`
**Purpose:** Directly test the scraping functions
```bash
python tests/linux_migration/05_test_biblical_text_scraper.py
# Or test specific book/chapter:
python tests/linux_migration/05_test_biblical_text_scraper.py oba 1
python tests/linux_migration/05_test_biblical_text_scraper.py mat 1
```

## 🚀 Run All Tests

**File:** `run_all_tests.py`
**Purpose:** Run all tests in sequence with summary and detailed logging
```bash
python tests/linux_migration/run_all_tests.py
```
This creates a timestamped log file in `logs/linux_migration_tests_YYYYMMDD_HHMMSS.log`

## 🎯 Run Single Test

**File:** `run_single_test.py`
**Purpose:** Run individual test with logging
```bash
python tests/linux_migration/run_single_test.py 4  # Run Chrome/Selenium test
python tests/linux_migration/run_single_test.py 1  # Run Book Detection test
```
This creates individual log files like `logs/linux_test_4_YYYYMMDD_HHMMSS.log`

## 🔧 Common Fixes

### Chrome/Selenium Issues
```bash
# Install Chrome
sudo apt install google-chrome-stable

# Or install Chromium
sudo apt install chromium-browser chromium-chromedriver

# Test if chromedriver is available
which chromedriver
chromedriver --version
```

### Missing Dependencies
```bash
# Install missing Python packages
pip install selenium

# Install system packages
sudo apt install python3-dev
```

### Book Detection Issues
- Check the "Book" column in your spreadsheet
- Ensure book abbreviations are correct (e.g., "oba" for Obadiah)
- Verify the spreadsheet has data in the expected format

### Network/Scraping Issues
- Test internet connectivity
- Check if Door43 sites are accessible
- Verify firewall settings

## 📊 Interpreting Results

### ✅ All Tests Pass
The issue is likely in the application logic - the system should be calling `ensure_biblical_text_cached` but isn't.

### ❌ Chrome/Selenium Fails
Install Chrome/ChromeDriver and ensure they work together.

### ❌ Book Detection Fails  
Check your spreadsheet format and book abbreviations.

### ❌ Scraper Fails
Network or site access issue. Check connectivity to Door43.

### ❌ Caching Fails
Permissions or cache directory issues.

## 🎯 Troubleshooting Steps

1. **Run all tests:** `python tests/linux_migration/run_all_tests.py`
2. **Fix Chrome issues first** - most common problem
3. **Check book detection** - ensure correct spreadsheet format
4. **Test biblical text scraping** - verify network access
5. **Debug caching pipeline** - check permissions and disk space

## 💡 Usage in Linux Migration

After transferring your project to Linux:

1. **Fix line endings:**
   ```bash
   find . -name "*.py" -exec sed -i 's/\r$//' {} \;
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   sudo apt install chromium-browser chromium-chromedriver
   ```

3. **Run diagnostic tests:**
   ```bash
   python tests/linux_migration/run_all_tests.py
   ```

4. **Fix any failing tests before running the main application**

These tests will help you identify and fix biblical text fetching issues quickly on your new Linux system!