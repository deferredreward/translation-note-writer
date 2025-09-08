#!/usr/bin/env python3
"""
SRef Conversion Demo
Demonstrates the SRef conversion functionality that converts short forms to full support reference names.
"""

import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.config_manager import ConfigManager
from modules.logger import setup_logging
from modules.sheet_manager import SheetManager
from modules.cache_manager import CacheManager


def demo_sref_conversion():
    """Demonstrate SRef conversion functionality."""
    
    # Initialize components
    config = ConfigManager()
    logger = setup_logging(config)
    sheet_manager = SheetManager(config)
    cache_manager = CacheManager(config, sheet_manager)
    
    logger.info("=== SRef Conversion Demo ===")
    
    # Sample data to demonstrate conversion
    sample_items = [
        {'SRef': 'you', 'row': 1},
        {'SRef': 'metaphor', 'row': 2},
        {'SRef': 'pronouns', 'row': 3},
        {'SRef': 'quotations', 'row': 4},
        {'SRef': 'connecting', 'row': 5},
        {'SRef': 'background', 'row': 6},
        {'SRef': 'figs-metaphor', 'row': 7},  # Already correct
        {'SRef': 'writing-poetry', 'row': 8},  # Already correct
        {'SRef': 'explicit', 'row': 9},
        {'SRef': 'hyperbole', 'row': 10},
        {'SRef': '', 'row': 11},  # Empty SRef
        {'SRef': 'unknown-term', 'row': 12},  # Unknown term
    ]
    
    logger.info("Sample SRef values to convert:")
    for item in sample_items:
        sref = item['SRef'] if item['SRef'] else '(empty)'
        logger.info(f"  Row {item['row']}: '{sref}'")
    
    # Get support references (use cached if available)
    support_references = cache_manager.get_cached_data('support_references')
    if not support_references:
        logger.info("Fetching support references...")
        support_references = sheet_manager.fetch_support_references()
        if support_references:
            cache_manager.set_cached_data('support_references', support_references)
        else:
            logger.error("Failed to fetch support references")
            return
    
    logger.info(f"Loaded {len(support_references)} support references")
    
    # Perform conversion
    logger.info("\n=== Conversion Results ===")
    updates_needed = sheet_manager.convert_sref_values(sample_items, support_references)
    
    if updates_needed:
        logger.info(f"Found {len(updates_needed)} conversions:")
        for update in updates_needed:
            logger.info(f"  Row {update['row_number']}: '{update['original_sref']}' → '{update['updated_sref']}'")
    else:
        logger.info("No conversions needed")
    
    # Show mapping examples
    logger.info("\n=== Short Form Mappings ===")
    mappings = {
        'you': 'figs-you',
        'metaphor': 'figs-metaphor',
        'pronouns': 'writing-pronouns',
        'quotations': 'figs-quotations',
        'connecting': 'grammar-connect-words-phrases',
        'background': 'writing-background',
        'explicit': 'figs-explicit',
        'hyperbole': 'figs-hyperbole',
        'idiom': 'figs-idiom',
        'simile': 'figs-simile',
        'irony': 'figs-irony',
        'parallelism': 'figs-parallelism',
        'poetry': 'writing-poetry',
        'participants': 'writing-participants',
    }
    
    for short, full in mappings.items():
        logger.info(f"  '{short}' → '{full}'")
    
    logger.info("\n=== Demo Complete ===")
    logger.info("To run SRef conversion on your sheets:")
    logger.info("  python main.py --convert-sref")
    logger.info("  python main.py --convert-sref --dry-run  # Preview only")


if __name__ == '__main__':
    demo_sref_conversion() 