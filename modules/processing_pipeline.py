"""
Processing Pipeline

This module provides a unified processing pipeline for all item processing modes
(immediate, batch, continuous). It consolidates the pre-processing logic that was
previously duplicated across main.py, batch_processor.py, and continuous_batch_manager.py.

The pipeline handles:
1. User detection from sheet_id
2. Book detection from items
3. Biblical text caching (ULT/UST)
4. Language conversion (GL to OL roundtrip)
5. Immediate update of conversion data to sheet

This ensures consistent behavior across all processing modes and eliminates
bugs caused by forgetting to add new features to all code paths.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class PreparedItems:
    """Result of preparing items for processing.

    Attributes:
        user: The detected user/editor key
        book: The detected book code
        items: The enriched items ready for processing
        conversion_count: Number of items with conversion data
    """
    user: Optional[str]
    book: Optional[str]
    items: List[Dict[str, Any]]
    conversion_count: int = 0


class ItemProcessingPipeline:
    """Unified pipeline for pre-processing items before AI processing.

    This class consolidates all the pre-processing steps that need to happen
    before items are sent to AI processing:

    1. Detect user from sheet_id
    2. Detect book from items
    3. Ensure biblical text (ULT/UST) is cached
    4. Perform language conversion (GL to OL roundtrip)
    5. Update sheet with conversion data immediately

    Usage:
        pipeline = ItemProcessingPipeline(cache_manager, sheet_manager, config, logger)
        prepared = pipeline.prepare_items(items, sheet_id)
        # Now use prepared.items for AI processing
        # prepared.user and prepared.book are available for context
    """

    def __init__(self, cache_manager, sheet_manager, config, logger: Optional[logging.Logger] = None):
        """Initialize the processing pipeline.

        Args:
            cache_manager: Cache manager for biblical text and language data
            sheet_manager: Sheet manager for fetching and updating sheets
            config: Configuration manager
            logger: Optional logger instance
        """
        self.cache_manager = cache_manager
        self.sheet_manager = sheet_manager
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

    def prepare_items(self, items: List[Dict[str, Any]], sheet_id: str,
                      user: Optional[str] = None) -> PreparedItems:
        """Prepare items for AI processing.

        This is the single entry point for all processing modes. It performs
        all necessary pre-processing steps in the correct order.

        Args:
            items: List of items to prepare
            sheet_id: Google Sheets ID
            user: Optional pre-determined user (if not provided, will be detected)

        Returns:
            PreparedItems with user, book, and enriched items
        """
        if not items:
            return PreparedItems(user=user, book=None, items=[], conversion_count=0)

        # Step 1: Detect user from sheet_id if not provided
        if not user:
            user = self._detect_user_from_sheet_id(sheet_id)

        # Step 2: Detect book from items
        _, book = self.cache_manager.detect_user_book_from_items(items)

        if not user:
            self.logger.warning(f"Could not determine user from sheet_id '{sheet_id}'")

        if not book:
            self.logger.warning("Could not determine book from items (missing Book column?)")

        # Step 3: Ensure biblical text is cached (if we have user and book)
        if user and book:
            self._ensure_biblical_text_cached(user, book)

        # Step 4: Perform language conversion (if we have book)
        enriched_items = items
        conversion_count = 0

        if book:
            enriched_items, conversion_count = self._perform_language_conversion(
                items, book, sheet_id
            )

        # Step 5: Update sheet with conversion data immediately
        if conversion_count > 0:
            self._update_conversion_data(enriched_items, sheet_id)

        return PreparedItems(
            user=user,
            book=book,
            items=enriched_items,
            conversion_count=conversion_count
        )

    def _detect_user_from_sheet_id(self, sheet_id: str) -> Optional[str]:
        """Detect user/editor key from sheet_id.

        Args:
            sheet_id: Google Sheets ID

        Returns:
            User key or None if not found
        """
        sheet_ids = self.config.get('google_sheets.sheet_ids', {})
        for key, sid in sheet_ids.items():
            if sid == sheet_id:
                return key
        return None

    def _ensure_biblical_text_cached(self, user: str, book: str):
        """Ensure biblical text is cached for the user and book.

        This uses the shared ensure_biblical_text_cached function from
        processing_utils which handles concurrent fetching of ULT and UST.

        Args:
            user: Username/editor key
            book: Book code
        """
        from .processing_utils import ensure_biblical_text_cached

        self.logger.info(f"PIPELINE: Ensuring biblical text cached for {user}/{book}")
        ensure_biblical_text_cached(
            user=user,
            book=book,
            cache_manager=self.cache_manager,
            sheet_manager=self.sheet_manager,
            config=self.config,
            logger=self.logger
        )

    def _perform_language_conversion(self, items: List[Dict[str, Any]],
                                      book: str, sheet_id: str) -> tuple:
        """Perform round-trip language conversion for items.

        This enriches items with GLQuote, OrigL, and ID fields by performing
        GL to OL conversion using the language converter.

        Args:
            items: List of items to enrich
            book: Book code for conversion context
            sheet_id: Sheet ID for logging

        Returns:
            Tuple of (enriched_items, count_of_items_with_conversion_data)
        """
        try:
            from .language_converter import LanguageConverter

            converter = LanguageConverter(cache_manager=self.cache_manager)
            enriched_items = converter.enrich_items_with_conversion(
                items=items,
                book_code=book,
                sheet_manager=self.sheet_manager,
                sheet_id=sheet_id,
                verbose=False
            )

            # Count items with conversion data
            conversion_count = sum(1 for item in enriched_items if 'conversion_data' in item)

            self.logger.info(f"PIPELINE: Language conversion completed for {len(enriched_items)} items "
                           f"in {book} ({conversion_count} with conversion data)")

            return enriched_items, conversion_count

        except Exception as e:
            self.logger.error(f"PIPELINE: Error during language conversion for {book}: {e}",
                            exc_info=True)
            # Return original items on error - processing can continue
            return items, 0

    def _update_conversion_data(self, items: List[Dict[str, Any]], sheet_id: str):
        """Update sheet with conversion data immediately.

        This writes GLQuote, OrigL, and ID columns to the sheet immediately
        after language conversion, before AI processing begins.

        Args:
            items: List of items with conversion_data
            sheet_id: Google Sheets ID
        """
        from .processing_utils import update_conversion_data_immediately

        try:
            count = update_conversion_data_immediately(
                items=items,
                sheet_id=sheet_id,
                sheet_manager=self.sheet_manager,
                config=self.config,
                logger=self.logger
            )
            self.logger.info(f"PIPELINE: Updated conversion data for {count} rows")
        except Exception as e:
            self.logger.error(f"PIPELINE: Error updating conversion data: {e}", exc_info=True)
            # Don't fail - AI processing can still continue
