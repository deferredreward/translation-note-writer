"""
Item Processor - Unified processing for all modes

This module provides a single ItemProcessor class that handles ALL item processing
logic for complete, once, and continuous modes. It consolidates the duplicate
processing code paths that existed across main.py, batch_processor.py, and
continuous_batch_manager.py.

The ItemProcessor handles:
1. J1 language conversion trigger detection and processing
2. Pending work detection
3. Processing mode separation (L/LA/AI)
4. Language-only processing (Go? = 'L')
5. Language+AI processing (Go? = 'LA')
6. AI-only processing (default)
7. Cache clearing for L/LA/J1 triggers

This ensures:
- J1='YES' is detected in ALL modes (not just continuous)
- Processing logic is consistent across all modes
- New features only need to be added once
"""

import logging
import os
from typing import Dict, List, Any, Optional

from .config_manager import ConfigManager
from .ai_service import AIService
from .sheet_manager import SheetManager
from .cache_manager import CacheManager
from .processing_pipeline import ItemProcessingPipeline, PreparedItems
from .processing_utils import (
    prepare_update_data, separate_items_by_processing_type,
    generate_programmatic_note, update_conversion_data_immediately
)


class ItemProcessor:
    """Unified processor for all processing modes.

    This class provides a single entry point for processing items across
    all modes (complete, once, continuous). It handles:

    1. J1 language conversion trigger (sheet-level bulk conversion)
    2. Pending work detection and processing
    3. Processing mode separation (L/LA/AI)
    4. Language-only processing
    5. Language+AI processing
    6. AI-only processing

    Usage:
        processor = ItemProcessor(config, ai_service, sheet_manager, cache_manager, logger)
        processed_count = processor.check_and_process_sheet(sheet_id, user)
    """

    def __init__(self, config: ConfigManager, ai_service: AIService,
                 sheet_manager: SheetManager, cache_manager: CacheManager,
                 logger: Optional[logging.Logger] = None,
                 completion_callback=None):
        """Initialize the ItemProcessor.

        Args:
            config: Configuration manager
            ai_service: AI service for processing
            sheet_manager: Sheet manager for updates
            cache_manager: Cache manager for biblical text
            logger: Optional logger instance
            completion_callback: Optional callback for when results are written
        """
        self.config = config
        self.ai_service = ai_service
        self.sheet_manager = sheet_manager
        self.cache_manager = cache_manager
        self.logger = logger or logging.getLogger(__name__)
        self.completion_callback = completion_callback

        # Create the pre-processing pipeline
        self.pipeline = ItemProcessingPipeline(
            cache_manager=self.cache_manager,
            sheet_manager=self.sheet_manager,
            config=self.config,
            logger=self.logger
        )

    def check_and_process_sheet(self, sheet_id: str, user: str,
                                 immediate_mode: bool = False) -> int:
        """Check for work and process it - single entry point for all modes.

        This method:
        1. Checks J1 trigger (sheet-level language conversion)
        2. Gets and processes pending work (row-level)

        Args:
            sheet_id: Google Sheets ID
            user: User key (e.g., 'editor3')
            immediate_mode: If True, use synchronous AI calls (for complete/once modes)

        Returns:
            Number of items processed
        """
        total_processed = 0

        # Step 1: Check J1 trigger (sheet-level language conversion)
        total_processed += self._check_and_process_language_trigger(sheet_id, user)

        # Step 2: Get and process pending work (row-level)
        total_processed += self._process_pending_items(sheet_id, user, immediate_mode)

        return total_processed

    def _check_and_process_language_trigger(self, sheet_id: str, user: str) -> int:
        """Check J1 trigger and run bulk language conversion if needed.

        The J1 trigger is when 'output for converter' sheet, J1 cell = 'YES'.
        When triggered, this runs language conversion on ALL rows (not just pending),
        similar to the --convert-language CLI command.

        Args:
            sheet_id: Google Sheets ID
            user: User key (e.g., 'editor3')

        Returns:
            Number of items processed (0 if no trigger, count if triggered)
        """
        try:
            if not self.sheet_manager.check_language_conversion_trigger(sheet_id):
                return 0

            friendly_name = self.config.get_friendly_name_with_id(user)
            self.logger.info(f"Language conversion trigger (J1) detected for {friendly_name}")

            return self._process_language_conversion_trigger(sheet_id, user)

        except Exception as e:
            friendly_name = self.config.get_friendly_name_with_id(user)
            self.logger.error(f"Error checking language trigger for {friendly_name}: {e}")
            return 0

    def _process_language_conversion_trigger(self, sheet_id: str, user: str) -> int:
        """Process sheet-level language conversion trigger.

        This runs language conversion on ALL rows (regardless of Go? value),
        similar to the --convert-language CLI command. Go? values are NOT changed.

        Args:
            sheet_id: Google Sheets ID
            user: User key (e.g., 'editor3')

        Returns:
            Number of items processed
        """
        friendly_name = self.config.get_friendly_name_with_id(user)

        try:
            # Get ALL rows for conversion (regardless of Go? value)
            all_items = self.sheet_manager.get_all_rows_for_language_conversion(sheet_id)

            if not all_items:
                self.logger.info(f"No items found for language conversion trigger in {friendly_name}")
                self.sheet_manager.reset_language_conversion_trigger(sheet_id)
                return 0

            # Detect book
            _, book = self.cache_manager.detect_user_book_from_items(all_items)

            if not book:
                self.logger.warning(f"Could not detect book for {friendly_name}, skipping language conversion")
                self.sheet_manager.reset_language_conversion_trigger(sheet_id)
                return 0

            self.logger.info(f"Running bulk language conversion for {friendly_name}: {len(all_items)} items, book={book}")

            # Clear ULT/UST cache for fresh data (J1 trigger should get fresh data)
            self._clear_biblical_text_cache(user, book)

            # Run language conversion using LanguageConverter directly
            from .language_converter import LanguageConverter

            converter = LanguageConverter(cache_manager=self.cache_manager)
            enriched_items = converter.enrich_items_with_conversion(
                items=all_items,
                book_code=book,
                sheet_manager=self.sheet_manager,
                sheet_id=sheet_id,
                verbose=False
            )

            # Update sheet with conversion data (Go? values are NOT changed)
            count = 0
            if not self.config.get('debug.dry_run', False):
                count = update_conversion_data_immediately(
                    items=enriched_items,
                    sheet_id=sheet_id,
                    sheet_manager=self.sheet_manager,
                    config=self.config,
                    logger=self.logger
                )
                self.logger.info(f"Bulk language conversion complete for {friendly_name}: {count} rows updated")

            # Reset the trigger
            self.sheet_manager.reset_language_conversion_trigger(sheet_id)

            return count

        except Exception as e:
            self.logger.error(f"Error processing language conversion trigger for {friendly_name}: {e}")
            # Still try to reset trigger to prevent infinite loop
            try:
                self.sheet_manager.reset_language_conversion_trigger(sheet_id)
            except:
                pass
            return 0

    def _process_pending_items(self, sheet_id: str, user: str, immediate_mode: bool) -> int:
        """Get pending items and process by mode.

        Args:
            sheet_id: Google Sheets ID
            user: User key (e.g., 'editor3')
            immediate_mode: If True, use synchronous AI calls

        Returns:
            Number of items processed
        """
        # Get pending items with optional limit
        processing_config = self.config.get_processing_config()
        max_items = processing_config.get('max_items_per_work_cycle', 0)
        max_items = max_items if max_items > 0 else None

        pending_items = self.sheet_manager.get_pending_work(sheet_id, max_items=max_items)

        if not pending_items:
            return 0

        friendly_name = self.config.get_friendly_name_with_id(user)
        self.logger.info(f"Found {len(pending_items)} pending items for {friendly_name}")

        # Separate items by processing mode
        language_only_items = [i for i in pending_items if i.get('processing_mode') == 'language_only']
        language_and_ai_items = [i for i in pending_items if i.get('processing_mode') == 'language_and_ai']
        ai_only_items = [i for i in pending_items if i.get('processing_mode') == 'ai_only']

        self.logger.info(f"Processing modes for {friendly_name}: L={len(language_only_items)}, "
                        f"LA={len(language_and_ai_items)}, AI={len(ai_only_items)}")

        total_processed = 0

        # Process language-only items (Go? = 'L') - no AI, just language conversion
        if language_only_items:
            total_processed += self._process_language_only(
                language_only_items, sheet_id, user
            )

        # Process language+AI items (Go? = 'LA') - language conversion then AI
        if language_and_ai_items:
            total_processed += self._process_language_and_ai(
                language_and_ai_items, sheet_id, user, immediate_mode
            )

        # Process AI-only items (default) - no language conversion, just AI
        if ai_only_items:
            total_processed += self._process_ai_only(
                ai_only_items, sheet_id, user, immediate_mode
            )

        return total_processed

    def _process_language_only(self, items: List[Dict[str, Any]], sheet_id: str, user: str) -> int:
        """Process items with Go? = 'L' (language conversion only, no AI).

        Args:
            items: List of items to process
            sheet_id: Google Sheets ID
            user: User key (e.g., 'editor3')

        Returns:
            Number of items processed
        """
        if not items:
            return 0

        friendly_name = self.config.get_friendly_name_with_id(user)
        self.logger.info(f"Processing {len(items)} language-only items for {friendly_name}")

        # Clear ULT/UST cache for fresh data
        self._clear_biblical_text_cache_for_items(items, user)

        # Use pipeline with language conversion
        prepared = self.pipeline.prepare_items(
            items, sheet_id, user=user, run_language_conversion=True
        )

        # Get completion marker from config
        processing_config = self.config.get_processing_config()
        completion_marker = processing_config.get('language_only_completion_marker', 'L-done')

        # Update Go? column to completion marker (conversion data already written by pipeline)
        updates = []
        for item in prepared.items:
            row_number = item.get('row') or item.get('row_number')
            if row_number:
                updates.append({
                    'row_number': row_number,
                    'updates': {'Go?': completion_marker}
                })

        if updates and not self.config.get('debug.dry_run', False):
            self.sheet_manager.batch_update_rows(sheet_id, updates, self.completion_callback)
            self.logger.info(f"Marked {len(updates)} rows as '{completion_marker}' for {friendly_name}")

        return len(updates)

    def _process_language_and_ai(self, items: List[Dict[str, Any]], sheet_id: str,
                                   user: str, immediate_mode: bool) -> int:
        """Process items with Go? = 'LA' (language conversion + AI).

        Args:
            items: List of items to process
            sheet_id: Google Sheets ID
            user: User key (e.g., 'editor3')
            immediate_mode: If True, use synchronous AI calls

        Returns:
            Number of items processed
        """
        if not items:
            return 0

        friendly_name = self.config.get_friendly_name_with_id(user)
        self.logger.info(f"Processing {len(items)} language+AI items for {friendly_name}")

        # Clear ULT/UST cache for fresh data
        self._clear_biblical_text_cache_for_items(items, user)

        # Use pipeline with language conversion
        prepared = self.pipeline.prepare_items(
            items, sheet_id, user=user, run_language_conversion=True
        )

        # Now process with AI
        return self._process_ai_items(prepared, sheet_id, user, immediate_mode)

    def _process_ai_only(self, items: List[Dict[str, Any]], sheet_id: str,
                          user: str, immediate_mode: bool) -> int:
        """Process items with default Go? values (AI only, no language conversion).

        Args:
            items: List of items to process
            sheet_id: Google Sheets ID
            user: User key (e.g., 'editor3')
            immediate_mode: If True, use synchronous AI calls

        Returns:
            Number of items processed
        """
        if not items:
            return 0

        friendly_name = self.config.get_friendly_name_with_id(user)
        self.logger.info(f"Processing {len(items)} AI-only items for {friendly_name}")

        # Use pipeline WITHOUT language conversion
        prepared = self.pipeline.prepare_items(
            items, sheet_id, user=user, run_language_conversion=False
        )

        return self._process_ai_items(prepared, sheet_id, user, immediate_mode)

    def _process_ai_items(self, prepared: PreparedItems, sheet_id: str,
                           user: str, immediate_mode: bool) -> int:
        """Process prepared items through AI.

        Args:
            prepared: PreparedItems from the pipeline
            sheet_id: Google Sheets ID
            user: User key (e.g., 'editor3')
            immediate_mode: If True, use synchronous AI calls

        Returns:
            Number of items successfully processed
        """
        items = prepared.items

        if not items:
            return 0

        self.logger.info(f"ITEM_PROCESSOR: Processing {len(items)} items through AI "
                        f"(user='{user}', book='{prepared.book}', immediate={immediate_mode})")

        # Separate items that can be handled programmatically vs need AI
        programmatic_items, ai_items = separate_items_by_processing_type(
            items, self.ai_service, self.cache_manager, self.logger
        )

        total_processed = 0

        # Handle programmatic items immediately (no AI needed)
        if programmatic_items:
            self.logger.info(f"Processing {len(programmatic_items)} items programmatically (no AI needed)")
            programmatic_processed = self._process_programmatic_items(programmatic_items, sheet_id)
            total_processed += programmatic_processed

        # Process AI items
        if ai_items:
            if immediate_mode:
                # Synchronous processing (for complete/once modes)
                ai_processed = self._process_ai_items_immediately(
                    ai_items, sheet_id, user, prepared.book
                )
            else:
                # Batch processing (for continuous mode or when not immediate)
                ai_processed = self._process_ai_items_batch(
                    ai_items, sheet_id, user, prepared.book
                )
            total_processed += ai_processed

        return total_processed

    def _process_programmatic_items(self, items: List[Dict[str, Any]], sheet_id: str) -> int:
        """Process items that can be handled programmatically without AI.

        Args:
            items: List of programmatic items
            sheet_id: Google Sheets ID

        Returns:
            Number of items successfully processed
        """
        if self.config.get('debug.dry_run', False):
            self.logger.info("DRY RUN: Would process programmatic items")
            return len(items)

        updates = []
        success_count = 0

        for item in items:
            try:
                # Generate the programmatic note
                note = generate_programmatic_note(item, self.logger)

                if note:
                    update_data = prepare_update_data(item, note, self.logger)
                    if update_data:
                        updates.append(update_data)
                        success_count += 1

            except Exception as e:
                self.logger.error(f"Error generating programmatic note for item {item.get('Ref', 'unknown')}: {e}")

        # Batch update the sheet
        if updates:
            try:
                self.sheet_manager.batch_update_rows(sheet_id, updates, self.completion_callback)
                self.logger.info(f"Successfully updated {len(updates)} programmatic items in sheet")
            except Exception as e:
                self.logger.error(f"Error updating sheet with programmatic items: {e}")
                success_count = 0

        return success_count

    def _process_ai_items_immediately(self, items: List[Dict[str, Any]], sheet_id: str,
                                        user: str, book: str) -> int:
        """Process AI items using synchronous calls (for complete/once modes).

        Args:
            items: List of items that need AI processing
            sheet_id: Google Sheets ID
            user: User key (e.g., 'editor3')
            book: Book code

        Returns:
            Number of items successfully processed
        """
        if not items:
            return 0

        friendly_name = self.config.get_friendly_name_with_id(user)

        try:
            # Process items using immediate AI service
            results = self.ai_service.process_items_immediately(
                items, user=user, book=book
            )

            # Prepare updates for successful results
            updates = []
            success_count = 0

            for result in results:
                if result['success']:
                    update_data = prepare_update_data(
                        result['original_item'], result['output'], self.logger
                    )
                    if update_data:
                        updates.append(update_data)
                        success_count += 1
                    else:
                        self.logger.error(f"Failed to prepare update data for item: "
                                        f"{result['original_item'].get('Ref', 'unknown')}")
                else:
                    self.logger.error(f"AI processing failed for item "
                                    f"{result['original_item'].get('Ref', 'unknown')}: "
                                    f"{result.get('error', 'Unknown error')}")

            # Update the sheet with results
            if updates:
                if not self.config.get('debug.dry_run', False):
                    self.sheet_manager.batch_update_rows(sheet_id, updates, self.completion_callback)
                    self.logger.info(f"Successfully updated {len(updates)} rows in {friendly_name}")
                else:
                    self.logger.info(f"DRY RUN: Would update {len(updates)} rows in {friendly_name}")

            return success_count

        except Exception as e:
            self.logger.error(f"Error during immediate AI processing for {friendly_name}: {e}")
            return 0

    def _process_ai_items_batch(self, items: List[Dict[str, Any]], sheet_id: str,
                                  user: str, book: str) -> int:
        """Process AI items using batch API (for better throughput).

        Args:
            items: List of items that need AI processing
            sheet_id: Google Sheets ID
            user: User key (e.g., 'editor3')
            book: Book code

        Returns:
            Number of items successfully processed
        """
        if not items:
            return 0

        # For batch processing, we use the BatchProcessor directly
        # This is typically used in continuous mode where batch efficiency matters
        from .batch_processor import BatchProcessor

        batch_processor = BatchProcessor(
            config=self.config,
            ai_service=self.ai_service,
            sheet_manager=self.sheet_manager,
            cache_manager=self.cache_manager,
            completion_callback=self.completion_callback
        )

        # Use the batch processor's AI-only processing path
        # (language conversion already done, so we pass items directly)
        return batch_processor._process_ai_items_from_prepared(
            PreparedItems(user=user, book=book, items=items, conversion_count=0),
            sheet_id
        )

    def _clear_biblical_text_cache(self, user: str, book: str):
        """Clear ULT/UST cache for the user and book.

        This is called for L/LA/J1 modes to ensure fresh data is fetched from Door43.

        Args:
            user: User key (e.g., 'editor3')
            book: Book code
        """
        if user and book:
            self.logger.info(f"Clearing ULT/UST cache for user={user}, book={book} (language conversion triggered)")
            self.cache_manager.clear_user_cache(user, book)
        elif book:
            self.logger.info(f"Clearing ULT/UST cache for book={book} (language conversion triggered)")
            try:
                cache_files = os.listdir(self.cache_manager.cache_dir)
                for cache_file in cache_files:
                    if (cache_file.startswith('ult_chapters') or cache_file.startswith('ust_chapters')) and book in cache_file:
                        cache_path = os.path.join(self.cache_manager.cache_dir, cache_file)
                        os.remove(cache_path)
                        self.logger.info(f"Cleared cache: {cache_file}")
            except Exception as e:
                self.logger.warning(f"Error clearing cache for book {book}: {e}")

    def _clear_biblical_text_cache_for_items(self, items: List[Dict[str, Any]], user: str):
        """Clear ULT/UST cache for the book in these items.

        Args:
            items: List of items to get book from
            user: User key (e.g., 'editor3')
        """
        if not items:
            return

        # Detect book from items
        _, book = self.cache_manager.detect_user_book_from_items(items)

        if book:
            self._clear_biblical_text_cache(user, book)
