#!/usr/bin/env python3
"""
Process TSV files through tnwriter-dev pipeline without Google Sheets.

This script provides a TSV-to-TSV processing mode that runs the same
AI note generation and language conversion pipeline used for Google Sheets,
but reads from and writes to TSV files instead.

Usage:
    python tsv_processor.py input.tsv output.tsv [--book PSA] [--mode LA]
    python tsv_processor.py input.tsv output.tsv --dry-run
    python tsv_processor.py input.tsv output.tsv --language-only

Examples:
    # Full processing (language conversion + AI note generation)
    python tsv_processor.py ../cSkillBP/output/issues/PSA-065.tsv output/PSA-065-notes.tsv

    # Language conversion only (get Hebrew quotes and IDs)
    python tsv_processor.py ../cSkillBP/output/issues/PSA-065.tsv output/PSA-065-converted.tsv --language-only

    # Preview without processing
    python tsv_processor.py ../cSkillBP/output/issues/PSA-065.tsv output/test.tsv --dry-run
"""

import argparse
import logging
import os
import sys

# Add modules to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.tsv_work_provider import TSVWorkProvider
from modules.tsv_result_writer import TSVResultWriter
from modules.config_manager import ConfigManager
from modules.cache_manager import CacheManager
from modules.language_converter import LanguageConverter
from modules.ai_service import AIService
from modules.tsv_notes_cache import TSVNotesCache


def setup_logging(verbose: bool = False):
    """Set up logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )


def detect_book_from_filename(filepath: str) -> str:
    """Detect book code from filename like PSA-065.tsv.

    Args:
        filepath: Path to TSV file

    Returns:
        3-letter book code or 'UNK' if not detected
    """
    filename = os.path.basename(filepath)
    # Try to extract book code from patterns like PSA-065.tsv or psa_065.tsv
    parts = filename.replace('_', '-').split('-')
    if parts:
        potential_book = parts[0].upper()
        # Basic validation - 3 letter code
        if len(potential_book) == 3 and potential_book.isalpha():
            return potential_book
    return 'UNK'


def process_language_conversion(items, book_code, cache_manager, logger):
    """Run language conversion on items to get Hebrew quotes and IDs.

    Args:
        items: List of item dictionaries
        book_code: 3-letter book code
        cache_manager: Cache manager instance
        logger: Logger instance

    Returns:
        List of enriched items with conversion_data
    """
    logger.info(f"Running language conversion for {len(items)} items in {book_code}")

    converter = LanguageConverter(cache_manager=cache_manager)
    enriched_items = converter.enrich_items_with_conversion(
        items=items,
        book_code=book_code,
        sheet_manager=None,  # No sheet manager in TSV mode
        sheet_id=None,
        verbose=False
    )

    # Count successful conversions
    converted_count = sum(1 for item in enriched_items if item.get('conversion_data'))
    logger.info(f"Language conversion complete: {converted_count}/{len(items)} items enriched")

    return enriched_items


def process_ai_notes(items, book_code, config, cache_manager, logger):
    """Run AI note generation on items.

    Args:
        items: List of item dictionaries (should have conversion_data)
        book_code: 3-letter book code
        config: ConfigManager instance
        cache_manager: CacheManager instance
        logger: Logger instance

    Returns:
        List of items with AI TN field populated
    """
    logger.info(f"Running AI note generation for {len(items)} items")

    ai_service = AIService(config, cache_manager)

    # Process items immediately (synchronous mode)
    results = ai_service.process_items_immediately(
        items,
        user='tsv_mode',  # Placeholder user for TSV mode
        book=book_code
    )

    # Merge AI results back into items
    for result in results:
        if result['success']:
            original_item = result['original_item']
            original_item['AI TN'] = result['output']
        else:
            logger.warning(
                f"AI processing failed for {result['original_item'].get('Ref', 'unknown')}: "
                f"{result.get('error', 'Unknown error')}"
            )

    # Count successful AI generations
    ai_count = sum(1 for item in items if item.get('AI TN'))
    logger.info(f"AI note generation complete: {ai_count}/{len(items)} items have notes")

    return items


def main():
    parser = argparse.ArgumentParser(
        description='Process TSV through TN pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('input_tsv', help='Input TSV file path')
    parser.add_argument('output_tsv', help='Output TSV file path')
    parser.add_argument('--book', default=None, help='Book code (e.g., PSA). Auto-detected from filename if not provided.')
    parser.add_argument('--mode', default='LA', choices=['L', 'LA', 'AI'],
                        help='Processing mode: L=language only, LA=language+AI (default), AI=AI only')
    parser.add_argument('--dry-run', action='store_true', help='Preview without processing')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--language-only', action='store_true', help='Shortcut for --mode L')
    parser.add_argument('--max-items', type=int, default=None, help='Limit number of items to process')
    args = parser.parse_args()

    # Set up logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # Handle --language-only shortcut
    if args.language_only:
        args.mode = 'L'

    # Detect book from filename if not provided
    book_code = args.book
    if not book_code:
        book_code = detect_book_from_filename(args.input_tsv)
        logger.info(f"Auto-detected book code: {book_code}")

    logger.info(f"Processing {args.input_tsv} as book {book_code} in mode {args.mode}")

    # Load work items from TSV
    provider = TSVWorkProvider(args.input_tsv, book_code)
    items = provider.get_pending_work(max_items=args.max_items)

    if not items:
        logger.warning("No items found in input TSV")
        return

    logger.info(f"Loaded {len(items)} items from {args.input_tsv}")

    if args.dry_run:
        print(f"\nDry run - would process {len(items)} items:")
        print(f"  Book: {book_code}")
        print(f"  Mode: {args.mode}")
        print(f"  Output: {args.output_tsv}")
        print("\nSample items:")
        for item in items[:5]:
            print(f"  - {item['Ref']}: {item['SRef']} - {item['GLQuote'][:50]}...")
        return

    # Initialize config and cache manager
    # Note: CacheManager normally requires sheet_manager, but for TSV mode
    # we pass None since we don't need sheet-related caching
    config = ConfigManager()
    cache_manager = CacheManager(config, sheet_manager=None)

    # Process based on mode
    if args.mode in ['L', 'LA']:
        # Run language conversion
        items = process_language_conversion(items, book_code, cache_manager, logger)

    if args.mode in ['LA', 'AI']:
        # Run AI note generation
        items = process_ai_notes(items, book_code, config, cache_manager, logger)

    # Ensure output directory exists
    output_dir = os.path.dirname(args.output_tsv)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Write results to output TSV
    writer = TSVResultWriter(args.output_tsv)
    written = writer.write_results(items)

    print(f"\nProcessing complete!")
    print(f"  Input: {len(provider)} items")
    print(f"  Output: {written} rows written to {args.output_tsv}")


if __name__ == '__main__':
    main()
