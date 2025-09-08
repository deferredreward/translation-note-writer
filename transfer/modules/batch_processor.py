"""
Batch Processor
Handles processing items in batches with the AI service and updating sheets.

This module provides batch processing capabilities for translation notes,
with support for both programmatic and AI-based processing.
"""

import logging
import time
import asyncio
import concurrent.futures
import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from .config_manager import ConfigManager
from .ai_service import AIService
from .sheet_manager import SheetManager
from .cache_manager import CacheManager
from .processing_utils import (
    post_process_text, separate_items_by_processing_type,
    format_alternate_translation, generate_programmatic_note,
    clean_ai_output, determine_note_type, format_final_note,
    prepare_update_data, ensure_biblical_text_cached,
    should_include_alternate_translation
)


# _post_process_text function moved to processing_utils.py as post_process_text
def _post_process_text_legacy(text: str) -> str:
    """Post-process text by removing curly braces and converting straight quotes to smart quotes.
    
    Args:
        text: Input text to process
        
    Returns:
        Processed text with curly braces removed and smart quotes
    """
    if not text:
        return text
    
    # Remove all curly braces
    processed = text.replace('{', '').replace('}', '')
    
    # Convert straight quotes to smart quotes
    # This handles nested quotes and alternates between single and double quotes appropriately
    
    # First handle double quotes
    # Use a simple state machine to alternate between opening and closing quotes
    result = []
    in_double_quotes = False
    i = 0
    
    while i < len(processed):
        char = processed[i]
        
        if char == '"':
            if in_double_quotes:
                # Closing double quote
                result.append('\u201D')  # RIGHT DOUBLE QUOTATION MARK
                in_double_quotes = False
            else:
                # Opening double quote
                result.append('\u201C')  # LEFT DOUBLE QUOTATION MARK
                in_double_quotes = True
        elif char == "'":
            # For single quotes, check context to determine if it's an apostrophe or quote
            if i > 0 and processed[i-1].isalnum():
                # Likely an apostrophe (preceded by alphanumeric)
                result.append('\u2019')  # RIGHT SINGLE QUOTATION MARK (apostrophe)
            elif i < len(processed) - 1 and processed[i+1].isalnum():
                # Likely opening single quote (followed by alphanumeric)
                result.append('\u2018')  # LEFT SINGLE QUOTATION MARK
            else:
                # Default to closing single quote
                result.append('\u2019')  # RIGHT SINGLE QUOTATION MARK
        else:
            result.append(char)
        
        i += 1
    
    return ''.join(result)


# Use the shared function instead of the legacy one
_post_process_text = post_process_text


class BatchProcessor:
    """Processes translation note items in batches."""
    
    def __init__(self, config: ConfigManager, ai_service: AIService, sheet_manager: SheetManager, cache_manager: CacheManager, completion_callback=None):
        """Initialize the batch processor.
        
        Args:
            config: Configuration manager
            ai_service: AI service for processing
            sheet_manager: Sheet manager for updates
            cache_manager: Cache manager for biblical text
            completion_callback: Optional callback for when results are written to sheet
        """
        self.config = config
        self.ai_service = ai_service
        self.sheet_manager = sheet_manager
        self.cache_manager = cache_manager
        self.completion_callback = completion_callback
        self.logger = logging.getLogger(__name__)
        
        # Get batch configuration
        anthropic_config = config.get_anthropic_config()
        self.batch_size = anthropic_config['batch_size']
        self.batch_timeout_hours = anthropic_config['batch_timeout_hours']
        
        self.logger.info(f"Batch processor initialized with batch size: {self.batch_size}")
    
    def process_items(self, items: List[Dict[str, Any]], sheet_id: str) -> int:
        """Process a list of items in batches with parallel processing.
        
        Args:
            items: List of items to process
            sheet_id: Google Sheets ID for updates
            
        Returns:
            Number of items successfully processed
        """
        if not items:
            return 0
        
        # Step 1: Separate items that can be handled programmatically vs need AI
        programmatic_items, ai_items = self._separate_items_by_processing_type(items)
        
        total_processed = 0
        
        # Step 2: Handle programmatic items immediately (no AI needed)
        if programmatic_items:
            self.logger.info(f"Processing {len(programmatic_items)} items programmatically (no AI needed)")
            programmatic_processed = self._process_programmatic_items(programmatic_items, sheet_id)
            total_processed += programmatic_processed
            self.logger.info(f"Programmatically processed {programmatic_processed}/{len(programmatic_items)} items")
        
        # Step 3: Process AI items in parallel batches
        if ai_items:
            self.logger.info(f"Processing {len(ai_items)} items that require AI in parallel batches")
            
            if self.config.get('debug.dry_run', False):
                ai_processed = self._process_ai_items_dry_run(ai_items, sheet_id)
            else:
                ai_processed = self._process_ai_items_parallel(ai_items, sheet_id)
            
            total_processed += ai_processed
            self.logger.info(f"AI processed {ai_processed}/{len(ai_items)} items")
        
        return total_processed

    def _separate_items_by_processing_type(self, items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Separate items into those that can be handled programmatically vs those needing AI.
        
        Args:
            items: List of all items
            
        Returns:
            Tuple of (programmatic_items, ai_items)
        """
        return separate_items_by_processing_type(items, self.ai_service, self.cache_manager, self.logger)

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
                note = self._generate_programmatic_note(item)
                
                if note:
                    update_data = self._prepare_update_data(item, note)
                    if update_data:
                        updates.append(update_data)
                        success_count += 1
                        self.logger.debug(f"Prepared programmatic update for row {update_data['row_number']}")
                
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

    def _generate_programmatic_note(self, item: Dict[str, Any]) -> str:
        """Generate a note programmatically for 'see how' or 'translate-unknown' items.
        
        Args:
            item: Item data
            
        Returns:
            Generated note text
        """
        return generate_programmatic_note(item, self.logger)

    def _process_ai_items_parallel(self, items: List[Dict[str, Any]], sheet_id: str) -> int:
        """Process AI items using parallel batch submission.
        
        Args:
            items: List of items that need AI processing
            sheet_id: Google Sheets ID
            
        Returns:
            Number of items successfully processed
        """
        if not items:
            return 0
        
        batch_size = self.config.get('anthropic.batch_size', 3)
        max_concurrent_batches = self.config.get('anthropic.max_concurrent_batches', 5)  # Use config setting
        
        # Create batches
        batches = []
        for i in range(0, len(items), batch_size):
            batch_items = items[i:i + batch_size]
            batches.append(batch_items)
        
        self.logger.info(f"Created {len(batches)} batches for parallel processing")
        
        # Process batches in groups of max_concurrent_batches
        total_processed = 0
        
        for i in range(0, len(batches), max_concurrent_batches):
            batch_group = batches[i:i + max_concurrent_batches]
            group_num = (i // max_concurrent_batches) + 1
            
            self.logger.info(f"Processing batch group {group_num} with {len(batch_group)} batches")
            
            # Submit all batches in this group simultaneously
            batch_submissions = []
            for j, batch_items in enumerate(batch_group):
                batch_num = i + j + 1
                try:
                    self.logger.debug(f"Submitting batch {batch_num} with {len(batch_items)} items")
                    
                    # Create and submit batch
                    requests = self.ai_service.create_batch_requests(batch_items)
                    if requests:
                        batch_id = self.ai_service.submit_batch(requests)
                        batch_submissions.append({
                            'batch_id': batch_id,
                            'batch_num': batch_num,
                            'items': batch_items
                        })
                        self.logger.info(f"Submitted batch {batch_num} (ID: {batch_id})")
                    else:
                        self.logger.warning(f"No valid requests for batch {batch_num}")
                        
                except Exception as e:
                    self.logger.error(f"Error submitting batch {batch_num}: {e}")
            
            # Wait for all batches in this group to complete
            if batch_submissions:
                group_processed = self._wait_for_batch_group_completion(batch_submissions, sheet_id)
                total_processed += group_processed
                
                # Small delay between batch groups
                if i + max_concurrent_batches < len(batches):
                    time.sleep(1)
        
        return total_processed

    def _wait_for_batch_group_completion(self, batch_submissions: List[Dict], sheet_id: str) -> int:
        """Wait for a group of batches to complete and process results.
        
        Args:
            batch_submissions: List of batch submission info
            sheet_id: Google Sheets ID
            
        Returns:
            Number of items successfully processed
        """
        total_processed = 0
        completed_batches = set()
        max_wait_time = self.batch_timeout_hours * 3600  # Convert to seconds
        start_time = time.time()
        
        # Get polling interval from config
        poll_interval = self.config.get('anthropic.batch_group_poll_interval', 10)
        
        self.logger.info(f"Waiting for {len(batch_submissions)} batches to complete...")
        
        while len(completed_batches) < len(batch_submissions):
            if time.time() - start_time > max_wait_time:
                self.logger.error(f"Timeout waiting for batches to complete")
                break
            
            for submission in batch_submissions:
                batch_id = submission['batch_id']
                batch_num = submission['batch_num']
                
                if batch_id in completed_batches:
                    continue
                
                try:
                    # Check if batch is complete
                    batch_status = self.ai_service.get_batch_status(batch_id)
                    
                    if batch_status.processing_status == 'ended':
                        self.logger.info(f"Batch {batch_num} (ID: {batch_id}) completed")
                        
                        # Process results immediately
                        raw_results = self.ai_service.get_batch_results(batch_status)
                        processed_results = self.ai_service.process_batch_results(raw_results, submission['items'])
                        
                        # Update sheet with results
                        success_count = self._update_sheet_with_results(processed_results, sheet_id)
                        total_processed += success_count
                        
                        completed_batches.add(batch_id)
                        self.logger.info(f"Batch {batch_num} processed: {success_count}/{len(submission['items'])} items")
                        
                    elif batch_status.processing_status in ['canceled', 'expired']:
                        self.logger.error(f"Batch {batch_num} (ID: {batch_id}) has status: {batch_status.processing_status}")
                        completed_batches.add(batch_id)
                        
                    else:
                        # Log current status for debugging
                        self.logger.debug(f"Batch {batch_num} status: {batch_status.processing_status}")
                        
                except Exception as e:
                    self.logger.error(f"Error checking batch {batch_num} status: {e}")
            
            # Sleep before checking again
            time.sleep(poll_interval)  # Use configurable interval
        
        self.logger.info(f"Batch group completed: {total_processed} total items processed")
        return total_processed

    def _process_ai_items_dry_run(self, items: List[Dict[str, Any]], sheet_id: str) -> int:
        """Process AI items in dry run mode.
        
        Args:
            items: List of items that would need AI processing
            sheet_id: Google Sheets ID
            
        Returns:
            Number of items that would be processed
        """
        batch_size = self.config.get('anthropic.batch_size', 3)
        total_items = 0
        
        for i in range(0, len(items), batch_size):
            batch_items = items[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            
            self.logger.info(f"=== DRY RUN BATCH {batch_num} - AI items ===")
            processed_count = self._process_batch_dry_run(batch_items, sheet_id)
            total_items += processed_count
        
        return total_items
    
    def _process_batch_dry_run(self, items: List[Dict[str, Any]], sheet_id: str) -> int:
        """Process a batch in dry run mode (no AI calls).
        
        Args:
            items: List of items to process
            sheet_id: Google Sheets ID
            
        Returns:
            Number of items that would be processed
        """
        self.logger.info("=== DRY RUN MODE - No AI calls will be made ===")
        
        processed_count = 0
        
        for i, item in enumerate(items):
            try:
                self.logger.info(f"--- Processing item {i+1}/{len(items)} ---")
                self.logger.info(f"Row: {item.get('row', 'unknown')}")
                self.logger.info(f"Ref: {item.get('Ref', '')}")
                self.logger.info(f"SRef: {item.get('SRef', '')}")
                self.logger.info(f"GLQuote: {item.get('GLQuote', '')}")
                self.logger.info(f"AT: {item.get('AT', '')}")
                self.logger.info(f"Explanation: {item.get('Explanation', '')}")
                
                # Determine note type
                note_type = self.ai_service._determine_note_type(item)
                self.logger.info(f"Note type: {note_type}")
                
                # Get templates
                templates = self.ai_service._get_templates_for_item(item)
                self.logger.debug(f"Templates found: {len(templates)}")
                if templates:
                    for j, template in enumerate(templates):
                        self.logger.info(f"  Template {j+1}: Type='{template.get('issue_type', '')}', Template='{template.get('note_template', '')[:100]}...'")
                else:
                    self.logger.warning("No templates found for this item!")
                
                # Get biblical text
                biblical_text = self.ai_service._get_biblical_text_for_item(item)
                self.logger.info(f"Biblical text fields: {list(biblical_text.keys())}")
                
                # Build prompt (but don't send it)
                prompt, system_message = self.ai_service._build_prompt(item, note_type)
                self.logger.debug(f"Prompt length: {len(prompt)} characters")
                self.logger.debug(f"System message length: {len(system_message) if system_message else 0} characters")
                
                # Show formatted templates
                formatted_templates = self.ai_service._format_templates(templates)
                self.logger.info(f"Formatted templates:\n{formatted_templates}")
                
                # Simulate successful processing
                processed_count += 1
                self.logger.info(f"DRY RUN: Would process this item successfully")
                
            except Exception as e:
                self.logger.error(f"Error in dry run processing for item {i}: {e}")
        
        self.logger.info(f"DRY RUN COMPLETE: Would process {processed_count}/{len(items)} items")
        return processed_count
    
    def _update_sheet_with_results(self, results: List[Dict[str, Any]], sheet_id: str) -> int:
        """Update the sheet with batch results.
        
        Args:
            results: Processed batch results
            sheet_id: Sheet ID to update
            
        Returns:
            Number of successful updates
        """
        if self.config.is_dry_run():
            self.logger.info("DRY RUN: Would update sheet with results")
            return len([r for r in results if r['success']])
        
        success_count = 0
        updates = []
        
        for result in results:
            try:
                if not result['success']:
                    self.logger.warning(f"Skipping failed result: {result.get('error', 'Unknown error')}")
                    continue
                
                original_item = result['original_item']
                output = result['output']
                
                self.logger.debug(f"Processing successful result for item: {original_item.get('Ref', 'unknown')}")
                self.logger.debug(f"AI output length: {len(output)} characters")
                
                # Prepare update data
                update_data = self._prepare_update_data(original_item, output)
                
                if update_data:
                    updates.append(update_data)
                    success_count += 1
                    self.logger.debug(f"Prepared update for row {update_data['row_number']}")
                else:
                    self.logger.warning("Failed to prepare update data for result")
                
            except Exception as e:
                self.logger.error(f"Error preparing update for result: {e}")
                import traceback
                self.logger.debug(f"Full traceback: {traceback.format_exc()}")
        
        # Perform batch update to sheet
        if updates:
            try:
                self.sheet_manager.batch_update_rows(sheet_id, updates, self.completion_callback)
                self.logger.info(f"Successfully updated {len(updates)} rows in sheet")
            except Exception as e:
                self.logger.error(f"Error updating sheet: {e}")
                success_count = 0  # Reset count if update failed
        
        return success_count
    
    def _prepare_update_data(self, original_item: Dict[str, Any], ai_output: str) -> Optional[Dict[str, Any]]:
        """Prepare update data for a sheet row.
        
        Args:
            original_item: Original item data
            ai_output: AI-generated output
            
        Returns:
            Update data dictionary or None if invalid
        """
        return prepare_update_data(original_item, ai_output, self.logger)
    
    def _clean_ai_output(self, output: str) -> str:
        """Clean AI output by removing quotes and extra whitespace.
        
        Args:
            output: Raw AI output
            
        Returns:
            Cleaned output
        """
        return clean_ai_output(output)
    
    def _determine_note_type(self, item: Dict[str, Any]) -> str:
        """Determine the type of note based on item data.
        
        Args:
            item: Original item data
            
        Returns:
            Note type string
        """
        return determine_note_type(item)
    
    def _format_final_note(self, original_item: Dict[str, Any], ai_output: str, note_type: str) -> str:
        """Format the final note based on the note type.
        
        Args:
            original_item: Original item data
            ai_output: AI-generated output
            note_type: Type of note
            
        Returns:
            Formatted final note
        """
        return format_final_note(original_item, ai_output, note_type, self.logger)

    def _format_alternate_translation(self, at: str) -> str:
        """Format the alternate translation text for appending to notes.
        
        Args:
            at: Alternate translation text from the AT column
            
        Returns:
            Formatted alternate translation string
        """
        return format_alternate_translation(at)
    
    def _should_include_alternate_translation(self, templates: List[Dict[str, Any]]) -> bool:
        """Check if any template contains "Alternate translation".
        
        Args:
            templates: List of templates
            
        Returns:
            True if alternate translation should be included
        """
        return should_include_alternate_translation(templates)

    def process_items_for_user(self, user: str, items: List[Dict[str, Any]], dry_run: bool = False):
        """Process items for a specific user.
        
        Args:
            user: Username
            items: List of items to process
            dry_run: If True, don't make actual API calls
        """
        if not items:
            self.logger.info(f"No items to process for {user}")
            return
        
        self.logger.info(f"Processing {len(items)} items for {user}")
        
        # Get sheet_id for user
        sheet_id = self.config.get_google_sheets_config()['sheet_ids'].get(user)
        if not sheet_id:
            self.logger.error(f"No sheet ID configured for user {user}")
            return
        
        # Detect the current book from items
        _, book = self.cache_manager.detect_user_book_from_items(items)
        if not book:
            self.logger.error(f"Could not detect book for user {user}")
            return
        
        self.logger.info(f"Detected book {book} for user {user}")
        
        # Ensure biblical text is cached for this user and book
        self._ensure_biblical_text_cached(user, book)
        
        # Separate items by processing type
        programmatic_items, ai_items = self._separate_items_by_processing_type(items)
        
        # Process programmatic items first
        if programmatic_items:
            self.logger.info(f"=== PROCESSING {len(programmatic_items)} PROGRAMMATIC ITEMS FOR {user.upper()} ===")
            if not dry_run:
                self._process_programmatic_items(programmatic_items, sheet_id)
            else:
                self.logger.info(f"DRY RUN: Would process {len(programmatic_items)} programmatic items")
        
        # Process AI items
        if ai_items:
            self.logger.info(f"=== PROCESSING {len(ai_items)} AI ITEMS FOR {user.upper()} ===")
            if not dry_run:
                self._process_ai_items_parallel(ai_items, sheet_id)
            else:
                self._dry_run_ai_items(ai_items, user, book)
        
        total_processed = len(programmatic_items) + len(ai_items)
        self.logger.info(f"Processed {total_processed} items for {user}")

    def _ensure_biblical_text_cached(self, user: str, book: str):
        """Ensure biblical text is cached for the user and book.
        
        Args:
            user: Username
            book: Book code
        """
        ensure_biblical_text_cached(user, book, self.cache_manager, self.sheet_manager, self.config, self.logger)

    def _dry_run_ai_items(self, items: List[Dict[str, Any]], user: str, book: str):
        """Perform dry run of AI items processing.
        
        Args:
            items: List of items to process
            user: Username
            book: Book code
        """
        self.logger.info(f"=== DRY RUN MODE - No AI calls will be made ===")
        
        # Process items in batches for dry run testing
        for i in range(0, len(items), self.batch_size):
            batch_items = items[i:i + self.batch_size]
            batch_num = (i // self.batch_size) + 1
            
            self.logger.info(f"=== DRY RUN BATCH {batch_num} - AI items ===")
            
            for j, item in enumerate(batch_items, 1):
                self.logger.info(f"--- Processing item {j}/{len(batch_items)} ---")
                self.logger.info(f"Row: {item.get('row', 'unknown')}")
                self.logger.info(f"Ref: {item.get('Ref', 'unknown')}")
                self.logger.info(f"SRef: {item.get('SRef', '')}")
                self.logger.info(f"GLQuote: {item.get('GLQuote', '')}")
                self.logger.info(f"AT: {item.get('AT', '')}")
                self.logger.info(f"Explanation: {item.get('Explanation', '')}")
                
                # Determine note type
                note_type = self.ai_service._determine_note_type(item)
                self.logger.info(f"Note type: {note_type}")
                
                # Get templates
                templates = self.ai_service._get_templates_for_item(item)
                self.logger.debug(f"Templates found: {len(templates)}")
                for k, template in enumerate(templates, 1):
                    template_preview = template.get('note_template', '')[:100] + '...' if len(template.get('note_template', '')) > 100 else template.get('note_template', '')
                    self.logger.info(f"  Template {k}: Type='{template.get('issue_type', '')}', Template='{template_preview}'")
                
                # Get biblical text (user-specific)
                biblical_text = self._get_biblical_text_for_user_item(item, user, book)
                self.logger.info(f"Biblical text fields: {list(biblical_text.keys())}")
                
                # Build prompt
                try:
                    prompt, system_message = self.ai_service._build_prompt(item, note_type)
                    self.logger.debug(f"Prompt length: {len(prompt)} characters")
                    self.logger.debug(f"System message length: {len(system_message) if system_message else 0} characters")
                    
                    # Show formatted templates
                    formatted_templates = self.ai_service._format_templates(templates)
                    self.logger.info(f"Formatted templates:\n{formatted_templates}")
                    
                    self.logger.info("DRY RUN: Would process this item successfully")
                except Exception as e:
                    self.logger.error(f"DRY RUN: Error building prompt: {e}")
            
            self.logger.info(f"DRY RUN COMPLETE: Would process {len(batch_items)}/{len(batch_items)} items")

    def _get_biblical_text_for_user_item(self, item: Dict[str, Any], user: str, book: str) -> Dict[str, str]:
        """Get biblical text for an item using user-specific cache.
        
        Args:
            item: Item data
            user: Username
            book: Book code
            
        Returns:
            Dictionary with biblical text fields
        """
        try:
            # Get user-specific cached data
            ult_data = self.cache_manager.get_biblical_text_for_user('ULT', user, book)
            ust_data = self.cache_manager.get_biblical_text_for_user('UST', user, book)
            
            # Extract verse content using AI service method
            ref = item.get('Ref', '')
            if not ref or ':' not in ref:
                self.logger.warning(f"Invalid ref format: '{ref}'")
                return {}
            
            chapter, verse = ref.split(':', 1)
            try:
                chapter = int(chapter)
                verse = int(verse)
            except ValueError:
                self.logger.error(f"Invalid chapter:verse format: '{ref}'")
                return {}
            
            result = {}
            
            # Get ULT text
            if ult_data:
                ult_verse_content, ult_verse_in_context = self.ai_service._extract_verse_content(
                    ult_data, book, chapter, verse
                )
                result['ult_verse_content'] = ult_verse_content
                result['ult_verse_in_context'] = ult_verse_in_context
            
            # Get UST text
            if ust_data:
                ust_verse_content, ust_verse_in_context = self.ai_service._extract_verse_content(
                    ust_data, book, chapter, verse
                )
                result['ust_verse_content'] = ust_verse_content
                result['ust_verse_in_context'] = ust_verse_in_context
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error getting biblical text for user item: {e}")
            return {} 