#!/usr/bin/env python3
"""
Test script for the suggestion functionality
"""

import os
import sys
import json

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.config_manager import ConfigManager
from modules.logger import setup_logging
from modules.sheet_manager import SheetManager
from modules.cache_manager import CacheManager


def test_translation_issue_descriptions():
    """Test loading translation issue descriptions."""
    try:
        cache_dir = os.path.join(os.path.dirname(__file__), 'cache')
        cache_file = os.path.join(cache_dir, 'translation_issue_descriptions.json')
        
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                issues = json.load(f)
            print(f"✓ Found {len(issues)} translation issue descriptions")
            
            # Show first few
            for i, issue in enumerate(issues[:3]):
                print(f"  {i+1}. {issue.get('type', 'Unknown')}: {issue.get('description', 'No description')[:80]}...")
            
            return True
        else:
            print(f"✗ Translation issue descriptions file not found at: {cache_file}")
            return False
            
    except Exception as e:
        print(f"✗ Error loading translation issue descriptions: {e}")
        return False


def test_sheet_manager_initialization():
    """Test sheet manager initialization."""
    try:
        config = ConfigManager()
        logger = setup_logging(config)
        sheet_manager = SheetManager(config)
        print("✓ Sheet manager initialized successfully")
        return True
        
    except Exception as e:
        print(f"✗ Error initializing sheet manager: {e}")
        return False


def test_cache_manager_initialization():
    """Test cache manager initialization."""
    try:
        config = ConfigManager()
        logger = setup_logging(config)
        sheet_manager = SheetManager(config)
        cache_manager = CacheManager(config, sheet_manager)
        print("✓ Cache manager initialized successfully")
        return True
        
    except Exception as e:
        print(f"✗ Error initializing cache manager: {e}")
        return False


def main():
    """Run all tests."""
    print("Testing suggestion functionality components...\n")
    
    tests = [
        ("Translation Issue Descriptions", test_translation_issue_descriptions),
        ("Sheet Manager Initialization", test_sheet_manager_initialization),
        ("Cache Manager Initialization", test_cache_manager_initialization),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"Testing {test_name}:")
        if test_func():
            passed += 1
        print()
    
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✓ All tests passed! Suggestion functionality should work correctly.")
        return True
    else:
        print("✗ Some tests failed. Please check the configuration and setup.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 