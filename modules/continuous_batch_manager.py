"""
Continuous Batch Manager
Manages a pool of running batches across all users, continuously submitting new work
as batches complete to maintain maximum throughput.
"""

import logging
import time
import threading
from typing import Dict, List, Any, Optional, Set, NamedTuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from queue import Queue, Empty
import json

from .config_manager import ConfigManager
from .ai_service import AIService
from .sheet_manager import SheetManager, SheetPermissionError
from .cache_manager import CacheManager


def _post_process_text(text: str) -> str:
    """Post-process text by removing curly braces and converting straight quotes to smart quotes.
    
    Args:
        text: Input text to process
        
    Returns:
        Processed text with curly braces removed and smart quotes
    """
    if not text:
        return text
    
    original_text = text
    
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
    
    final_text = ''.join(result)
    
    # Log post-processing changes for debugging
    if original_text != final_text:
        # Use a logger from the module (we can't access self.logger here)
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"POST-PROCESS: '{original_text[:100]}...' -> '{final_text[:100]}...'")
        if '{' in original_text or '}' in original_text:
            logger.info(f"POST-PROCESS: Removed curly braces from text")
        if '"' in original_text or "'" in original_text:
            logger.info(f"POST-PROCESS: Converted straight quotes to smart quotes")
    
    return final_text


@dataclass
class PendingWork:
    """Represents pending work from a user's sheet."""
    user: str
    sheet_id: str
    items: List[Dict[str, Any]]
    priority: int = 0  # Lower numbers = higher priority


@dataclass
class RunningBatch:
    """Represents a currently running batch."""
    batch_id: str
    user: str
    sheet_id: str
    book: str
    items: List[Dict[str, Any]]
    submitted_at: datetime
    batch_type: str  # 'programmatic' or 'ai'


class ContinuousBatchManager:
    """Manages continuous batch processing across all users."""
    
    def __init__(self, config: ConfigManager, ai_service: AIService, sheet_manager: SheetManager, cache_manager: CacheManager, completion_callback=None):
        """Initialize the continuous batch manager.
        
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
        
        # Get configuration
        anthropic_config = config.get_anthropic_config()
        self.batch_size = anthropic_config['batch_size']
        self.max_concurrent_batches = anthropic_config['max_concurrent_batches']
        self.batch_timeout_hours = anthropic_config['batch_timeout_hours']
        self.poll_interval = self.config.get('anthropic.batch_group_poll_interval', 30)
        
        # Running state
        self.running_batches: Dict[str, RunningBatch] = {}  # batch_id -> RunningBatch
        self.work_queue = Queue()  # Queue of PendingWork objects
        self.running = False
        self.shutdown_requested = False
        
        # Permission error tracking
        self.blocked_sheets: Dict[str, datetime] = {}  # sheet_id -> blocked_until_time
        self.permission_block_hours = self.config.get('processing.permission_block_hours', 1)  # Read from config
        
        # Track rows currently being processed to prevent duplicates
        self.rows_in_progress: Set[str] = set()  # Set of "sheet_id:row_number" strings
        
        # Threading
        self.lock = threading.RLock()
        self.monitor_thread = None
        self.work_checker_thread = None
        
        self.logger.info(f"Continuous batch manager initialized - max concurrent: {self.max_concurrent_batches}")
    
    def start(self):
        """Start the continuous batch processing."""
        if self.running:
            self.logger.warning("Continuous batch manager is already running")
            return
        
        self.running = True
        self.shutdown_requested = False
        
        # Start monitoring threads
        self.monitor_thread = threading.Thread(target=self._monitor_batches, daemon=True)
        self.work_checker_thread = threading.Thread(target=self._check_for_work, daemon=True)
        
        self.monitor_thread.start()
        self.work_checker_thread.start()
        
        self.logger.info("Continuous batch processing started")
    
    def stop(self):
        """Stop the continuous batch processing."""
        if not self.running:
            return
        
        self.logger.info("Stopping continuous batch processing...")
        self.shutdown_requested = True
        self.running = False
        
        # Wait for threads to finish (with timeout)
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=10)
        if self.work_checker_thread and self.work_checker_thread.is_alive():
            self.work_checker_thread.join(timeout=10)
        
        # Clear rows in progress
        with self.lock:
            self.rows_in_progress.clear()
            self.logger.info("Cleared all rows in progress")
        
        self.logger.info("Continuous batch processing stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of the batch manager."""
        with self.lock:
            # Get blocked sheets info
            blocked_info = {}
            now = datetime.now()
            for sheet_id, blocked_until in self.blocked_sheets.items():
                remaining_minutes = (blocked_until - now).total_seconds() / 60
                blocked_info[sheet_id] = {
                    'blocked_until': blocked_until.isoformat(),
                    'remaining_minutes': max(0, remaining_minutes)
                }
            
            return {
                'running': self.running,
                'running_batches': len(self.running_batches),
                'max_concurrent': self.max_concurrent_batches,
                'available_slots': max(0, self.max_concurrent_batches - len(self.running_batches)),
                'work_queue_size': self.work_queue.qsize(),
                'rows_in_progress': len(self.rows_in_progress),
                'blocked_sheets': blocked_info,
                'batches': {
                    batch_id: {
                        'user': batch.user,
                        'items_count': len(batch.items),
                        'submitted_at': batch.submitted_at.isoformat(),
                        'type': batch.batch_type
                    }
                    for batch_id, batch in self.running_batches.items()
                }
            }
    
    def _check_for_work(self):
        """Continuously check all user sheets for new work."""
        while self.running and not self.shutdown_requested:
            try:
                self._scan_all_sheets_for_work()
                self._process_work_queue()
                
                # Sleep for the poll interval
                time.sleep(max(5, self.poll_interval // 6))  # Check for new work more frequently
                
            except Exception as e:
                self.logger.error(f"Error in work checker thread: {e}")
                time.sleep(10)  # Wait longer on error
    
    def _scan_all_sheets_for_work(self):
        """Scan all configured user sheets for pending work."""
        sheet_ids = self.config.get('google_sheets.sheet_ids', {})
        support_references = self.cache_manager.get_cached_data('support_references')
        
        # Fetch support references if not cached (needed for SRef conversion)
        if not support_references:
            self.logger.debug("Support references not cached, fetching...")
            support_references = self.sheet_manager.fetch_support_references()
            if support_references:
                self.cache_manager.set_cached_data('support_references', support_references)
            else:
                self.logger.warning("Failed to fetch support references - SRef conversion may not work properly")
                support_references = []
        
        auto_convert_sref = self.config.get('processing.auto_convert_sref', True)
        
        for user, sheet_id in sheet_ids.items():
            if self.shutdown_requested:
                break
            
            # Check if sheet is blocked due to permission errors
            if self._is_sheet_blocked(sheet_id, user):
                continue
            
            try:
                # First check for suggestion requests (this can also cause permission errors)
                try:
                    self._check_and_process_suggestion_requests(sheet_id, user)
                except Exception as e:
                    if self._is_permission_error(e):
                        self.logger.warning(f"Permission error during suggestion check for {user}")
                        self._block_sheet_for_permission_error(sheet_id, user)
                        continue
                    else:
                        self.logger.warning(f"Error checking suggestion requests for {user}: {e}")
                
                # Step 1: Convert SRef values if needed
                if support_references and auto_convert_sref:
                    try:
                        all_items = self.sheet_manager.get_all_rows_for_sref_conversion(sheet_id)
                        if all_items:
                            updates_needed = self.sheet_manager.convert_sref_values(all_items, support_references)
                            if updates_needed and not self.config.get('debug.dry_run', False):
                                self.sheet_manager.batch_update_rows(sheet_id, updates_needed)
                                self.logger.debug(f"Updated {len(updates_needed)} SRef values for {user}")
                    except Exception as e:
                        if self._is_permission_error(e):
                            self.logger.warning(f"Permission error during SRef conversion for {user}")
                            self._block_sheet_for_permission_error(sheet_id, user)
                            continue
                
                # Step 2: Get pending work
                try:
                    pending_items = self.sheet_manager.get_pending_work(sheet_id)
                except Exception as e:
                    if self._is_permission_error(e):
                        self.logger.warning(f"Permission error during get_pending_work for {user}")
                        self._block_sheet_for_permission_error(sheet_id, user)
                        continue
                    else:
                        self.logger.error(f"Error getting pending work for {user}: {e}")
                        continue
                
                if pending_items:
                    # Step 3: Filter out rows that are already being processed
                    filtered_items = []
                    with self.lock:
                        for item in pending_items:
                            row_id = self._get_row_identifier(sheet_id, item)
                            if row_id not in self.rows_in_progress:
                                filtered_items.append(item)
                            else:
                                self.logger.debug(f"Skipping row {item.get('row', 'unknown')} for {user} - already being processed")
                    
                    if filtered_items:
                        # Detect the book for this user
                        _, book = self.cache_manager.detect_user_book_from_items(filtered_items)
                        if book:
                            # Ensure biblical text is cached
                            self._ensure_biblical_text_cached(user, book)
                        
                        # Add to work queue
                        work = PendingWork(
                            user=user,
                            sheet_id=sheet_id,
                            items=filtered_items,
                            priority=0  # Could be made configurable
                        )
                        
                        # Only add if we don't already have work queued for this user
                        if not self._has_queued_work_for_user(user):
                            self.work_queue.put(work)
                            self.logger.info(f"Queued {len(filtered_items)} items for {user} (filtered from {len(pending_items)} pending)")
            
            except Exception as e:
                if self._is_permission_error(e):
                    self._block_sheet_for_permission_error(sheet_id, user)
                else:
                    self.logger.error(f"Error scanning work for {user}: {e}")
    
    def _get_row_identifier(self, sheet_id: str, item: Dict[str, Any]) -> str:
        """Create a unique identifier for a row.
        
        Args:
            sheet_id: Sheet ID
            item: Item containing row information
            
        Returns:
            Unique identifier string
        """
        row_number = (item.get('row') or 
                     item.get('row # for n8n hide, don\'t delete') or
                     item.get('row_number') or
                     'unknown')
        return f"{sheet_id}:{row_number}"
    
    def _has_queued_work_for_user(self, user: str) -> bool:
        """Check if there's already work queued for this user."""
        # Create a temporary queue to check contents
        temp_items = []
        has_work = False
        
        try:
            # Check all items in queue
            while True:
                try:
                    item = self.work_queue.get_nowait()
                    temp_items.append(item)
                    if item.user == user:
                        has_work = True
                except Empty:
                    break
            
            # Put all items back
            for item in temp_items:
                self.work_queue.put(item)
        
        except Exception as e:
            self.logger.error(f"Error checking queued work: {e}")
        
        return has_work
    
    def _process_work_queue(self):
        """Process items from the work queue when batch slots are available."""
        with self.lock:
            available_slots = self.max_concurrent_batches - len(self.running_batches)
        
        if available_slots <= 0:
            return  # No slots available
        
        # Process up to available_slots items from the queue
        for _ in range(available_slots):
            try:
                work = self.work_queue.get_nowait()
                
                # Process this work
                self._process_pending_work(work)
                
            except Empty:
                break  # No more work in queue
            except Exception as e:
                self.logger.error(f"Error processing work from queue: {e}")
    
    def _process_pending_work(self, work: PendingWork):
        """Process pending work by creating and submitting batches."""
        try:
            # Mark all rows as being processed
            with self.lock:
                for item in work.items:
                    row_id = self._get_row_identifier(work.sheet_id, item)
                    self.rows_in_progress.add(row_id)
                    self.logger.debug(f"Marked row {item.get('row', 'unknown')} as being processed for {work.user}")
            
            # Separate items by processing type
            programmatic_items, ai_items = self._separate_items_by_processing_type(work.items)
            
            # Process programmatic items immediately (they don't need AI batches)
            if programmatic_items:
                self._process_programmatic_items_immediately(programmatic_items, work.user, work.sheet_id)
            
            # Submit AI items as batches
            if ai_items:
                self._submit_ai_batches(ai_items, work.user, work.sheet_id)
        
        except Exception as e:
            self.logger.error(f"Error processing pending work for {work.user}: {e}")
            # If there's an error, make sure to unmark the rows
            with self.lock:
                for item in work.items:
                    row_id = self._get_row_identifier(work.sheet_id, item)
                    self.rows_in_progress.discard(row_id)
    
    def _separate_items_by_processing_type(self, items: List[Dict[str, Any]]) -> tuple:
        """Separate items into programmatic vs AI processing."""
        programmatic_items = []
        ai_items = []
        
        for item in items:
            explanation = item.get('Explanation', '').strip()
            at = item.get('AT', '').strip()
            
            # Check if this is a "see how" note with AT filled
            if explanation.lower().startswith('see how') and at:
                programmatic_items.append(item)
            else:
                ai_items.append(item)
        
        return programmatic_items, ai_items
    
    def _process_programmatic_items_immediately(self, items: List[Dict[str, Any]], user: str, sheet_id: str):
        """Process programmatic items immediately without batching."""
        if not items:
            return
        
        try:
            # Get friendly name for logging
            friendly_name = self.config.get_editor_name_for_sheet(sheet_id)
            
            self.logger.info(f"Processing {len(items)} programmatic items for {friendly_name}")
            
            # Process each item
            updates = []
            for item in items:
                try:
                    # Generate the programmatic note
                    note = self.ai_service.generate_programmatic_note(item)
                    if note:
                        update_data = {
                            'row': item['row'],
                            'ai_tn': note,
                            'go_value': 'AI'
                        }
                        updates.append(update_data)
                except Exception as e:
                    self.logger.error(f"Error processing programmatic item {item.get('row', 'unknown')} for {friendly_name}: {e}")
            
            # Update the sheet with all results
            if updates:
                success_count = self.sheet_manager.update_sheet_with_results(sheet_id, updates)
                self.logger.info(f"Updated {len(updates)} programmatic items for {friendly_name}")
                
                # Call completion callback if provided
                if self.completion_callback:
                    try:
                        self.completion_callback()
                    except Exception as e:
                        self.logger.error(f"Error in completion callback: {e}")
            
        finally:
            # Always unmark the rows from being processed
            with self.lock:
                for item in items:
                    row_id = self._get_row_identifier(sheet_id, item)
                    self.rows_in_progress.discard(row_id)
                    self.logger.debug(f"Unmarked row {item.get('row', 'unknown')} after programmatic processing for {friendly_name}")
    
    def _submit_ai_batches(self, items: List[Dict[str, Any]], user: str, sheet_id: str):
        """Submit AI batches for the given items."""
        try:
            # Get friendly name for logging
            friendly_name = self.config.get_editor_name_for_sheet(sheet_id)
            
            # Detect book from items
            user_detected, book = self.cache_manager.detect_user_book_from_items(items)
            if not book:
                self.logger.warning(f"Could not detect book from items for {friendly_name}")
                return
            
            # Ensure biblical text is cached
            self._ensure_biblical_text_cached(user, book)
            
            # Group into batches
            batch_num = 1
            for i in range(0, len(items), self.batch_size):
                batch_items = items[i:i + self.batch_size]
                
                try:
                    # Create batch requests
                    requests = self._create_user_batch_requests(batch_items, user, book)
                    if not requests:
                        self.logger.warning(f"No valid requests for {friendly_name} batch {batch_num}")
                        continue
                    
                    # Submit the batch
                    self.logger.debug(f"Submitting AI batch {batch_num} for {friendly_name} ({len(requests)} requests)")
                    batch_id = self.ai_service.submit_batch(requests)
                    
                    # Track the running batch
                    running_batch = RunningBatch(
                        batch_id=batch_id,
                        user=user,
                        sheet_id=sheet_id,
                        book=book,
                        items=batch_items,
                        submitted_at=datetime.now(),
                        batch_type='ai'
                    )
                    
                    with self.lock:
                        self.running_batches[batch_id] = running_batch
                    
                    self.logger.info(f"Submitted AI batch {batch_num} for {friendly_name} (ID: {batch_id}, {len(batch_items)} items)")
                    batch_num += 1
                except Exception as e:
                    self.logger.error(f"Error submitting batch for {friendly_name}: {e}")
                    # Unmark rows since batch submission failed
                    with self.lock:
                        for item in batch_items:
                            row_id = self._get_row_identifier(sheet_id, item)
                            self.rows_in_progress.discard(row_id)
            
        except Exception as e:
            self.logger.error(f"Error submitting batch for {friendly_name}: {e}")
            # Unmark rows since batch submission failed
            with self.lock:
                for item in items:
                    row_id = self._get_row_identifier(sheet_id, item)
                    self.rows_in_progress.discard(row_id)
    
    def _create_user_batch_requests(self, items: List[Dict[str, Any]], user: str, book: str) -> List[Dict[str, Any]]:
        """Create batch requests with user-specific context."""
        requests = []
        
        for i, item in enumerate(items):
            try:
                # Determine the type of note to create
                note_type = self.ai_service._determine_note_type(item)
                
                # Get the appropriate prompt and system message with user context
                prompt, system_message = self.ai_service._build_prompt(item, note_type, user=user, book=book)
                
                # Log the prompt details for debugging
                item_ref = item.get('Ref', 'unknown')
                item_row = item.get('row', 'unknown')
                
                self.logger.debug(f"Creating batch request for {user}/{item_ref} (row {item_row})")
                
                # Create the request
                request = {
                    "custom_id": f"item_{i}_{item.get('row', 'unknown')}",
                    "params": {
                        "model": self.ai_service.model,
                        "max_tokens": 2048,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ]
                    }
                }
                
                # Add system message if provided
                if system_message:
                    if self.ai_service.enable_prompt_caching:
                        # Use prompt caching for system message
                        request["params"]["system"] = [
                            {
                                "type": "text",
                                "text": system_message,
                                "cache_control": {"type": "ephemeral"}
                            }
                        ]
                    else:
                        request["params"]["system"] = system_message
                
                requests.append(request)
                
            except Exception as e:
                self.logger.error(f"Error creating request for {user} item {i}: {e}")
                # Create a placeholder request that will fail gracefully
                requests.append({
                    "custom_id": f"item_{i}_error",
                    "params": {
                        "model": self.ai_service.model,
                        "max_tokens": 100,
                        "messages": [{"role": "user", "content": "Error in request creation"}]
                    }
                })
        
        return requests
    
    def _monitor_batches(self):
        """Monitor running batches and process completed ones."""
        while self.running and not self.shutdown_requested:
            try:
                completed_batches = []
                
                with self.lock:
                    batch_items = list(self.running_batches.items())
                
                for batch_id, batch_info in batch_items:
                    try:
                        # Check batch status
                        batch_status = self.ai_service.get_batch_status(batch_id)
                        
                        if batch_status.processing_status == 'ended':
                            # Batch completed successfully
                            friendly_name = self.config.get_editor_name_for_sheet(batch_info.sheet_id)
                            self.logger.info(f"Batch {batch_id} for {friendly_name} completed")
                            
                            # Process results
                            self._process_completed_batch(batch_id, batch_info, batch_status)
                            completed_batches.append(batch_id)
                        
                        elif batch_status.processing_status in ['canceled', 'expired']:
                            # Batch failed
                            friendly_name = self.config.get_editor_name_for_sheet(batch_info.sheet_id)
                            self.logger.error(f"Batch {batch_id} for {friendly_name} failed: {batch_status.processing_status}")
                            
                            # Unmark the rows since they failed
                            with self.lock:
                                for item in batch_info.items:
                                    row_id = self._get_row_identifier(batch_info.sheet_id, item)
                                    self.rows_in_progress.discard(row_id)
                                    self.logger.debug(f"Unmarked row {item.get('row', 'unknown')} after batch {batch_id} failure for {friendly_name}")
                            
                            completed_batches.append(batch_id)
                        
                        elif batch_status.processing_status in ['processing', 'validating']:
                            # Still processing - check for timeout
                            elapsed = datetime.now() - batch_info.submitted_at
                            if elapsed > timedelta(hours=self.batch_timeout_hours):
                                friendly_name = self.config.get_editor_name_for_sheet(batch_info.sheet_id)
                                self.logger.error(f"Batch {batch_id} for {friendly_name} timed out")
                                
                                # Unmark the rows since they timed out
                                with self.lock:
                                    for item in batch_info.items:
                                        row_id = self._get_row_identifier(batch_info.sheet_id, item)
                                        self.rows_in_progress.discard(row_id)
                                        self.logger.debug(f"Unmarked row {item.get('row', 'unknown')} after batch {batch_id} timeout for {friendly_name}")
                                
                                completed_batches.append(batch_id)
                    
                    except Exception as e:
                        self.logger.error(f"Error checking batch {batch_id}: {e}")
                
                # Remove completed batches
                with self.lock:
                    for batch_id in completed_batches:
                        if batch_id in self.running_batches:
                            del self.running_batches[batch_id]
                
                if completed_batches:
                    self.logger.info(f"Removed {len(completed_batches)} completed batches - {len(self.running_batches)} still running")
                
                # Sleep before next check
                time.sleep(self.poll_interval)
            
            except Exception as e:
                self.logger.error(f"Error in batch monitor: {e}")
                time.sleep(10)
    
    def _process_completed_batch(self, batch_id: str, batch_info: RunningBatch, batch_status):
        """Process a completed batch and update the sheet."""
        try:
            # Get friendly name for logging
            friendly_name = self.config.get_editor_name_for_sheet(batch_info.sheet_id)
            
            # Get results
            raw_results = self.ai_service.get_batch_results(batch_status)
            processed_results = self.ai_service.process_batch_results(raw_results, batch_info.items)
            
            # Update sheet with results
            success_count = self._update_sheet_with_results(processed_results, batch_info.sheet_id)
            
            self.logger.info(f"Processed batch {batch_id} for {friendly_name}: {success_count}/{len(batch_info.items)} items")
            
        except Exception as e:
            friendly_name = self.config.get_editor_name_for_sheet(batch_info.sheet_id)
            self.logger.error(f"Error processing completed batch {batch_id}: {e}")
        
        finally:
            # Always unmark the rows from being processed, regardless of success or failure
            with self.lock:
                for item in batch_info.items:
                    row_id = self._get_row_identifier(batch_info.sheet_id, item)
                    self.rows_in_progress.discard(row_id)
                    self.logger.debug(f"Unmarked row {item.get('row', 'unknown')} after batch {batch_id} completion for {friendly_name}")
    
    def _ensure_biblical_text_cached(self, user: str, book: str):
        """Ensure biblical text is cached for the user and book."""
        sheet_id = self.config.get('google_sheets.sheet_ids', {}).get(user)
        if not sheet_id:
            self.logger.warning(f"No sheet_id configured for user {user}, cannot cache biblical text or block on permission error.")
            return

        for text_type in ['ULT', 'UST']:
            if self._is_sheet_blocked(sheet_id, user):
                self.logger.debug(f"Skipping cache check for {text_type} for {user}/{book} as sheet {sheet_id} is currently blocked.")
                continue

            cached_data = self.cache_manager.get_biblical_text_for_user(text_type, user, book)
            if not cached_data:
                self.logger.debug(f"Caching {text_type} for {user}/{book}")
                
                try:
                    biblical_data = self.sheet_manager.fetch_biblical_text(text_type, book_code=book)
                    if biblical_data:
                        self.cache_manager.set_biblical_text_for_user(text_type, user, book, biblical_data)
                        self.logger.info(f"Successfully cached {text_type} for {user}/{book}.")
                    else:
                        self.logger.warning(f"Failed to fetch biblical text for {text_type} {user}/{book} to cache it.")
                except SheetPermissionError as e:
                    self.logger.error(f"Permission error while trying to cache {text_type} for {user}/{book}: {e}")
                    self._block_sheet_for_permission_error(sheet_id, user)
                    # No point trying the other text_type if this one failed due to permissions
                    break 
                except Exception as e:
                    self.logger.error(f"Error caching {text_type} for {user}/{book}: {e}")
                    # Potentially break or continue depending on desired resilience for other errors
    
    def _generate_programmatic_note(self, item: Dict[str, Any]) -> str:
        """Generate a note programmatically for 'see how' items."""
        explanation = item.get('Explanation', '').strip()
        at = item.get('AT', '').strip()
        
        if explanation.lower().startswith('see how') and at:
            ref_match = explanation.replace('see how ', '').strip()
            
            if ':' in ref_match:
                chapter, verse = ref_match.split(':', 1)
                note = f"See how you translated the similar expression in [{chapter}:{verse}](../{chapter}/{verse}.md)."
            else:
                note = f"See how you translated the similar expression in {ref_match}."
            
            # Add alternate translation
            formatted_at = self._format_alternate_translation(at)
            note += formatted_at
            
            return _post_process_text(note)
        
        return ""
    
    def _format_alternate_translation(self, at: str) -> str:
        """Format the alternate translation text."""
        if not at.strip():
            return ""
        
        if '/' in at:
            parts = [part.strip() for part in at.split('/') if part.strip()]
            formatted_parts = [f"[{part}]" for part in parts]
            return f" Alternate translation: {' or '.join(formatted_parts)}"
        else:
            return f" Alternate translation: [{at.strip()}]"
    
    def _prepare_update_data(self, original_item: Dict[str, Any], ai_output: str) -> Optional[Dict[str, Any]]:
        """Prepare update data for a sheet row."""
        try:
            row_number = (original_item.get('row') or 
                         original_item.get('row # for n8n hide, don\'t delete') or
                         original_item.get('row_number'))
            
            if not row_number:
                self.logger.warning(f"No row number found in original item")
                return None
            
            # Log the original AI output for debugging
            ref = original_item.get('Ref', 'unknown')
            self.logger.info(f"Processing AI output for {ref} (row {row_number}): {ai_output[:100]}{'...' if len(ai_output) > 100 else ''}")
            
            # Clean the AI output
            cleaned_output = self._clean_ai_output(ai_output)
            self.logger.info(f"Cleaned AI output for {ref}: {cleaned_output[:100]}{'...' if len(cleaned_output) > 100 else ''}")
            
            # Format the final note
            final_note = self._format_final_note(original_item, cleaned_output)
            self.logger.info(f"Final formatted note for {ref}: {final_note[:200]}{'...' if len(final_note) > 200 else ''}")
            
            return {
                'row_number': row_number,
                'updates': {
                    'Go?': 'AI',
                    'AI TN': final_note
                }
            }
        except Exception as e:
            self.logger.error(f"Error in _prepare_update_data: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    
    def _clean_ai_output(self, output: str) -> str:
        """Clean AI output by removing quotes and extra whitespace."""
        # Remove surrounding quotes
        cleaned = output.strip()
        if cleaned.startswith('"') and cleaned.endswith('"'):
            cleaned = cleaned[1:-1]
        elif cleaned.startswith("'") and cleaned.endswith("'"):
            cleaned = cleaned[1:-1]
        
        # Remove trailing newlines
        cleaned = cleaned.rstrip('\n')
        
        return cleaned
    
    def _format_final_note(self, original_item: Dict[str, Any], ai_output: str) -> str:
        """Format the final note based on the item type."""
        try:
            explanation = original_item.get('Explanation', '').strip()
            at = original_item.get('AT', '').strip()
            
            # Determine note type
            if explanation.lower().startswith('see how'):
                # For "see how" notes, format the reference
                if ':' in explanation.replace('see how ', '').strip():
                    ref_match = explanation.replace('see how ', '').strip()
                    chapter, verse = ref_match.split(':', 1)
                    note = f"See how you translated the similar expression in [{chapter}:{verse}](../{chapter}/{verse}.md)."
                else:
                    note = ai_output
                
                # Add alternate translation if provided
                if at:
                    formatted_at = self._format_alternate_translation(at)
                    note += formatted_at
                
                return _post_process_text(note)
            
            else:
                # Regular AI note - append AT if provided
                note = ai_output
                
                if at:
                    formatted_at = self._format_alternate_translation(at)
                    note += formatted_at
                
                return _post_process_text(note)
                
        except Exception as e:
            self.logger.error(f"Error formatting final note: {e}")
            return _post_process_text(ai_output)
    
    def _update_sheet_with_results(self, results: List[Dict[str, Any]], sheet_id: str) -> int:
        """Update the sheet with batch results."""
        if self.config.get('debug.dry_run', False):
            return len([r for r in results if r['success']])
        
        updates = []
        for result in results:
            if result['success']:
                update_data = self._prepare_update_data(result['original_item'], result['output'])
                if update_data:
                    updates.append(update_data)
        
        if updates:
            try:
                self.sheet_manager.batch_update_rows(sheet_id, updates, self.completion_callback)
                return len(updates)
            except Exception as e:
                self.logger.error(f"Error updating sheet: {e}")
                return 0
        
        return 0
    
    def _is_sheet_blocked(self, sheet_id: str, user: str) -> bool:
        """Check if a sheet is currently blocked due to permission errors."""
        if sheet_id not in self.blocked_sheets:
            return False
        
        blocked_until = self.blocked_sheets[sheet_id]
        if datetime.now() >= blocked_until:
            # Block has expired, remove it
            del self.blocked_sheets[sheet_id]
            friendly_name = self.config.get_editor_name_for_sheet(sheet_id)
            self.logger.info(f"Permission block expired for {friendly_name} - resuming sheet monitoring")
            return False
        
        # Still blocked
        remaining = blocked_until - datetime.now()
        remaining_minutes = remaining.total_seconds() / 60
        friendly_name = self.config.get_editor_name_for_sheet(sheet_id)
        self.logger.debug(f"Skipping {friendly_name} sheet - blocked for {remaining_minutes:.1f} more minutes due to permission error")
        return True
    
    def _block_sheet_for_permission_error(self, sheet_id: str, user: str):
        """Block a sheet for a period due to permission errors."""
        blocked_until = datetime.now() + timedelta(hours=self.permission_block_hours)
        self.blocked_sheets[sheet_id] = blocked_until
        
        friendly_name = self.config.get_editor_name_for_sheet(sheet_id)
        self.logger.warning(f"Snoozing {friendly_name}'s sheet (ID: {sheet_id}) for {self.permission_block_hours} hour(s) due to permission error.")
        self.logger.warning(f"Will retry {friendly_name}'s sheet at {blocked_until.strftime('%Y-%m-%d %H:%M:%S')}")
    
    def _is_permission_error(self, error: Exception) -> bool:
        """Check if an error is a permission-related error.
        
        Args:
            error: Exception to check
            
        Returns:
            True if it's a permission error
        """
        error_str = str(error).lower()
        return any(phrase in error_str for phrase in [
            'permission',
            'forbidden',
            'access denied',
            'insufficient permissions',
            'the caller does not have permission'
        ])

    def _check_and_process_suggestion_requests(self, sheet_id: str, user: str):
        """Check for suggestion requests and process them if conditions are met.
        
        Args:
            sheet_id: Google Sheets ID
            user: Name of the user
        """
        try:
            # Check if suggestion request exists
            if not self._has_suggestion_request(sheet_id):
                return
            
            self.logger.info(f"Found suggestion request for {user}")
            
            # Check if other work is in progress
            if self._is_other_work_in_progress(sheet_id):
                self.logger.info(f"Other work in progress for {user}, skipping suggestions")
                return
            
            # Process the suggestion request
            self._process_suggestion_request(sheet_id, user)
            
        except Exception as e:
            self.logger.error(f"Error checking suggestion requests for {user}: {e}")

    def _has_suggestion_request(self, sheet_id: str) -> bool:
        """Check if there's a suggestion request (YES in suggested notes tab, column D, row 2).
        
        Args:
            sheet_id: Google Sheets ID
            
        Returns:
            True if suggestion request exists
        """
        try:
            # Read from suggested notes tab, column D, row 2
            range_name = "'suggested notes'!D2"
            
            result = self.sheet_manager.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            if values and len(values) > 0 and len(values[0]) > 0:
                value = values[0][0].strip().upper()
                return value == 'YES'
            
            return False
            
        except Exception as e:
            self.logger.debug(f"Error checking suggestion request: {e}")
            return False

    def _is_other_work_in_progress(self, sheet_id: str) -> bool:
        """Check if other work is in progress (Go? column has non-AI values).
        
        Args:
            sheet_id: Google Sheets ID
            
        Returns:
            True if other work is in progress
        """
        try:
            # Read from AI notes tab, column F (Go?)
            range_name = "'AI notes'!F:F"
            
            result = self.sheet_manager.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            # Skip header row (index 0) and check all other rows
            for i, row in enumerate(values[1:], start=2):
                if row and len(row) > 0:
                    go_value = row[0].strip()
                    if go_value and go_value.upper() != 'AI':
                        self.logger.debug(f"Found non-AI work in progress: row {i}, Go? = '{go_value}'")
                        return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking work in progress: {e}")
            return True  # Assume work in progress on error

    def _process_suggestion_request(self, sheet_id: str, user: str):
        """Process suggestion request for a user's sheet."""
        self.logger.info(f"Processing suggestion request for {user} (Sheet: {sheet_id})")
        
        try:
            # Step 1: Fetch existing notes first. This will be used for book/chapter detection and for the prompt.
            existing_notes = self._get_existing_notes(sheet_id) # Contains 'Ref', 'Book' etc.

            # Step 2: Determine Target Book
            current_book_for_user = None
            # Check running batches for this user's current book
            for batch_info in self.running_batches.values():
                if batch_info.user == user and batch_info.book:
                    current_book_for_user = batch_info.book
                    self.logger.info(f"Found current book '{current_book_for_user}' for user '{user}' from running batches for suggestions.")
                    break
            
            if not current_book_for_user and existing_notes:
                # Try to detect book from existing notes if not found in running batches
                _, detected_book = self.cache_manager.detect_user_book_from_items(existing_notes)
                if detected_book:
                    current_book_for_user = detected_book
                    self.logger.info(f"Detected book '{current_book_for_user}' for user '{user}' from existing notes for suggestions.")

            if not current_book_for_user:
                # Fallback to a default book if no other info is available
                default_suggestion_book = self.config.get('suggestions.default_book', 'GEN') # Default to GEN if not configured
                current_book_for_user = default_suggestion_book
                self.logger.warning(f"Could not determine current book for {user} for suggestions, defaulting to '{current_book_for_user}'.")
            
            target_book = current_book_for_user

            # Step 3: Determine Target Chapter from existing notes (highest chapter)
            target_chapter = self.config.get('suggestions.default_chapter', 1) # Default chapter
            max_chapter_found = 0
            if existing_notes:
                for note in existing_notes:
                    ref = note.get('Ref', '')
                    if ':' in ref:
                        try:
                            chapter_num_str = ref.split(':')[0]
                            chapter_num = int(chapter_num_str)
                            if chapter_num > max_chapter_found:
                                max_chapter_found = chapter_num
                        except ValueError:
                            self.logger.debug(f"Could not parse chapter from Ref '{ref}' in existing notes.")
                if max_chapter_found > 0:
                    target_chapter = max_chapter_found
                    self.logger.info(f"Determined target chapter for suggestions for {user} as {target_chapter} from existing notes (book: {target_book}).")
                else:
                    self.logger.info(f"No valid chapter found in existing notes for {user}, using default chapter {target_chapter} for suggestions (book: {target_book}).")
            else:
                self.logger.info(f"No existing notes found for {user}, using default chapter {target_chapter} for suggestions (book: {target_book}).")

            self.logger.info(f"Proceeding with suggestion generation for {user} - {target_book} chapter {target_chapter}")

            # Step 4: Fetch ULT and UST text for the determined target chapter
            ult_text = self._get_chapter_text(target_book, target_chapter, 'ULT', user)
            ust_text = self._get_chapter_text(target_book, target_chapter, 'UST', user)
            
            if not ult_text or not ust_text:
                self.logger.error(f"Could not get ULT/UST text for {target_book} chapter {target_chapter} for user {user}. Aborting suggestion.")
                self._turn_off_suggestion_request(sheet_id) # Turn off to prevent loops
                return

            # Step 5: Get other necessary data (existing_notes already fetched)
            existing_suggestions = self._get_existing_suggestions(sheet_id)
            translation_issues = self._get_translation_issue_descriptions() # This is global

            # Step 6: Generate AI suggestions
            suggestions = self._generate_ai_suggestions(
                ult_text, ust_text, existing_notes, existing_suggestions, translation_issues, target_book, target_chapter
            )
            
            if suggestions:
                self._write_suggestions_to_sheet(sheet_id, suggestions)
                self.logger.info(f"Wrote {len(suggestions)} suggestions to sheet for {user}")
            else:
                self.logger.info(f"No new suggestions generated for {user}")
            
        except Exception as e:
            self.logger.error(f"Error processing suggestion request for {user}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
        finally:
            # Turn off the request flag in the sheet to prevent re-processing immediately
            self._turn_off_suggestion_request(sheet_id)
            self.logger.info(f"Turned off suggestion request for {user} sheet {sheet_id}")

    def _get_existing_notes(self, sheet_id: str) -> List[Dict[str, Any]]:
        """Get existing notes from AI notes tab.
        
        Args:
            sheet_id: Google Sheets ID
            
        Returns:
            List of existing note dictionaries
        """
        try:
            # Read from AI notes tab, columns B, C, D, E, I
            range_name = "'AI notes'!B:I"
            
            result = self.sheet_manager.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            if not values:
                return []
            
            # Get headers
            headers = values[0] if values else []
            notes = []
            
            # Debug: show what headers we found
            self.logger.debug(f"Sheet headers found: {headers}")
            
            # Process each row
            for i, row in enumerate(values[1:], start=2):
                try:
                    # Create note dictionary
                    note = {}
                    for j, header in enumerate(headers):
                        if j < len(row):
                            note[header] = row[j]
                        else:
                            note[header] = ''
                    
                    # Debug: show first few rows of data
                    if i <= 3:
                        self.logger.debug(f"Row {i} data: {note}")
                    
                    # Only include rows with AI TN content
                    if note.get('AI TN', '').strip():
                        notes.append(note)
                
                except Exception as e:
                    self.logger.warning(f"Error processing note row {i}: {e}")
            
            return notes
            
        except Exception as e:
            self.logger.error(f"Error getting existing notes: {e}")
            return []

    def _get_chapter_text(self, book: str, chapter: int, text_type: str, user: str) -> Optional[str]:
        """Get chapter text for ULT or UST for a specific user and book.
        
        Args:
            book: Book abbreviation
            chapter: Chapter number
            text_type: 'ult' or 'ust'
            user: Username for user-specific caching and permission error handling
            
        Returns:
            Chapter text or None if not found
        """
        sheet_id = self.config.get('google_sheets.sheet_ids', {}).get(user)
        if not sheet_id:
            self.logger.warning(f"No sheet_id for user {user}, cannot get chapter text or handle permissions.")
            return None

        if self._is_sheet_blocked(sheet_id, user):
            self.logger.debug(f"Skipping _get_chapter_text for {text_type} {book} Ch {chapter} for {user} as sheet {sheet_id} is blocked.")
            return None

        try:
            biblical_text_data = self.cache_manager.get_biblical_text_for_user(text_type, user, book)
            
            if not biblical_text_data:
                self.logger.info(f"{text_type.upper()} for {book} not cached for user {user}, fetching...")
                fetched_data = self.sheet_manager.fetch_biblical_text(text_type, book_code=book)
                if fetched_data:
                    self.cache_manager.set_biblical_text_for_user(text_type, user, book, fetched_data)
                    biblical_text_data = fetched_data
                    self.logger.info(f"Successfully fetched and cached {text_type.upper()} for {user}/{book}.")
                else:
                    self.logger.warning(f"Failed to fetch {text_type.upper()} for {book} for user {user}.")
                    return None # Failed to fetch, data remains unavailable
            
            if not biblical_text_data:
                self.logger.error(f"Cache and fetch ultimately failed for {text_type.upper()} {book} for user {user}.")
                return None

            if biblical_text_data.get('book') != book:
                self.logger.error(f"CRITICAL: Biblical text data for user {user} is for book '{biblical_text_data.get('book')}', not '{book}'. Clearing cache.")
                self.cache_manager.clear_user_cache(user, book=book)
                return None 
            
            chapters_list = biblical_text_data.get('chapters', [])
            self.logger.info(f"DEBUG: Biblical text data for {user}/{book} has {len(chapters_list)} chapters")
            available_chapters = [ch.get('chapter') for ch in chapters_list]
            self.logger.info(f"DEBUG: Available chapters for {user}/{book} {text_type.upper()}: {sorted(available_chapters)}")
            self.logger.info(f"DEBUG: Looking for chapter {chapter}")
            
            # Check if the requested chapter is missing from the cache
            if chapter not in available_chapters:
                self.logger.warning(f"Chapter {chapter} not found in cached {text_type.upper()} for {user}/{book}. Attempting to refresh cache...")
                
                # Clear the current cache and fetch fresh data
                self.cache_manager.clear_user_cache(user, book=book)
                
                try:
                    fetched_data = self.sheet_manager.fetch_biblical_text(text_type, book_code=book)
                    if fetched_data:
                        self.cache_manager.set_biblical_text_for_user(text_type, user, book, fetched_data)
                        biblical_text_data = fetched_data
                        self.logger.info(f"Successfully refreshed {text_type.upper()} cache for {user}/{book}.")
                        
                        # Update our local variables with the refreshed data
                        chapters_list = biblical_text_data.get('chapters', [])
                        available_chapters = [ch.get('chapter') for ch in chapters_list]
                        self.logger.info(f"DEBUG: After refresh, {user}/{book} {text_type.upper()} has {len(chapters_list)} chapters: {sorted(available_chapters)}")
                    else:
                        self.logger.error(f"Failed to refresh {text_type.upper()} for {book} for user {user}.")
                        return None
                except SheetPermissionError as e:
                    self.logger.error(f"Permission error while refreshing {text_type.upper()} cache for {user}/{book}: {e}")
                    self._block_sheet_for_permission_error(sheet_id, user)
                    return None
                except Exception as e:
                    self.logger.error(f"Error refreshing {text_type.upper()} cache for {user}/{book}: {e}")
                    return None
            
            for chapter_data in chapters_list:
                if chapter_data.get('chapter') == chapter:
                    verses = chapter_data.get('verses', [])
                    self.logger.info(f"DEBUG: Found chapter {chapter} with {len(verses)} verses")
                    chapter_text_content = f"{book}\n"
                    for verse_item in verses:
                        verse_num = verse_item.get('number', 0)
                        content = verse_item.get('content', '')
                        chapter_text_content += f"{chapter}:{verse_num} {content}\n"
                    return chapter_text_content.strip()
            
            self.logger.warning(f"Chapter {chapter} not found in {text_type.upper()} for book {book} (user: {user})")
            self.logger.warning(f"DEBUG: Available chapters were: {sorted(available_chapters)}")
            return None
            
        except SheetPermissionError as e:
            self.logger.error(f"Permission error in _get_chapter_text for {user}/{book} Ch {chapter} ({text_type}): {e}")
            if sheet_id: # Should always have sheet_id from above
                self._block_sheet_for_permission_error(sheet_id, user)
            return None # Cannot proceed
        except Exception as e:
            self.logger.error(f"Error getting {text_type.upper()} chapter text for {book} Ch {chapter} (user: {user}): {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None

    def _get_existing_suggestions(self, sheet_id: str) -> List[Dict[str, Any]]:
        """Get existing suggestions to avoid duplicates.
        
        Args:
            sheet_id: Google Sheets ID
            
        Returns:
            List of existing suggestion dictionaries
        """
        try:
            # Read from suggested notes tab
            range_name = "'suggested notes'!A:F"
            
            result = self.sheet_manager.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            if not values:
                return []
            
            # Skip header rows (first 2 rows)
            suggestions = []
            for i, row in enumerate(values[2:], start=3):
                if len(row) >= 6:  # Ensure we have all columns
                    suggestion = {
                        'reference': row[0] if len(row) > 0 else '',
                        'issuetype': row[1] if len(row) > 1 else '',
                        'quote': row[2] if len(row) > 2 else '',
                        'Go?': row[3] if len(row) > 3 else '',
                        'AT': row[4] if len(row) > 4 else '',
                        'explanation': row[5] if len(row) > 5 else ''
                    }
                    suggestions.append(suggestion)
            
            return suggestions
            
        except Exception as e:
            self.logger.error(f"Error getting existing suggestions: {e}")
            return []

    def _get_translation_issue_descriptions(self) -> List[Dict[str, Any]]:
        """Get translation issue descriptions from cache file.
        
        Returns:
            List of translation issue descriptions
        """
        try:
            import json
            import os
            
            cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache')
            cache_file = os.path.join(cache_dir, 'translation_issue_descriptions.json')
            
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                self.logger.warning("Translation issue descriptions file not found")
                return []
                
        except Exception as e:
            self.logger.error(f"Error loading translation issue descriptions: {e}")
            return []

    def _generate_ai_suggestions(self, ult_text: str, ust_text: str, existing_notes: List[Dict[str, Any]], 
                               existing_suggestions: List[Dict[str, Any]], translation_issues: List[Dict[str, Any]],
                               book: str, chapter: int) -> List[Dict[str, Any]]:
        """Generate AI suggestions for missing translation notes.
        
        Args:
            ult_text: ULT chapter text
            ust_text: UST chapter text
            existing_notes: List of existing notes for the target chapter
            existing_suggestions: List of existing suggestions
            translation_issues: List of translation issue descriptions
            book: The target book for which suggestions are being made
            chapter: The target chapter for which suggestions are being made
            
        Returns:
            List of suggestion dictionaries
        """
        try:
            # Format existing notes for prompt (filter for current chapter if necessary, though _get_existing_notes might do it)
            # For now, assume existing_notes are relevant to the chapter text provided.
            notes_text = ""
            for note in existing_notes:
                ref = note.get('Ref', '')
                sref = note.get('SRef', '')
                quote = note.get('GLQuote', '') # Ensuring correct GLQuote is used
                tn = note.get('AI TN', '')
                
                self.logger.debug(f"Note data for suggestion prompt: Ref='{ref}', SRef='{sref}', GLQuote='{quote}', AI TN='{tn[:50]}...'")
                
                if ref and sref and tn:
                    notes_text += f"{ref}\\t{sref}\\t{quote}\\t{tn}\\n"
            
            self.logger.info(f"Formatted {len(existing_notes)} notes for suggestion prompt (Book: {book}, Chapter: {chapter}).")
            
            # Format existing suggestions for prompt
            suggestions_text = ""
            for suggestion in existing_suggestions:
                ref = suggestion.get('reference', '')
                issuetype = suggestion.get('issuetype', '')
                quote = suggestion.get('quote', '')
                go = suggestion.get('Go?', '')
                at = suggestion.get('AT', '')
                explanation = suggestion.get('explanation', '')
                if ref and issuetype:
                    suggestions_text += f"{ref}\\t{issuetype}\\t{quote}\\t{go}\\t{at}\\t{explanation}\\n"
            
            # Build the prompt
            import json
            import time
            
            # Load the review prompt from configuration
            try:
                review_prompt_template = self.config.get_prompt('review_prompt')
                if not review_prompt_template:
                    self.logger.error("Review prompt not found in configuration for suggestions")
                    return []
                
                # Format the prompt with variables
                prompt = review_prompt_template.format(
                    book=book, # Add book to prompt context
                    chapter=chapter, # Add chapter to prompt context
                    translation_issues=json.dumps(translation_issues, indent=2),
                    ult_text=ult_text,
                    ust_text=ust_text,
                    notes_text=notes_text,
                    suggestions_text=suggestions_text # Assuming suggestions_text formatting is correct
                )
            except KeyError as e:
                self.logger.error(f"Missing key in review_prompt.format(...) for suggestions: {e}. Check prompt template variables.")
                return []
            except Exception as e:
                self.logger.error(f"Error loading/formatting review prompt for suggestions: {e}")
                return []
            
            # Create batch requests
            requests = [
                {
                    "custom_id": "suggestion_request",
                    "params": {
                        "model": self.ai_service.model,
                        "max_tokens": 4096,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ]
                    }
                }
            ]
            
            # Add dummy prompt to make it a proper batch (saves money)
            requests.append({
                "custom_id": "dummy_request",
                "params": {
                    "model": self.ai_service.model,
                    "max_tokens": 50,
                    "messages": [
                        {"role": "user", "content": "What is the capital of Texas?"}
                    ]
                }
            })
            
            # Submit batch
            batch_id = self.ai_service.submit_batch(requests)
            self.logger.info(f"Submitted suggestion batch: {batch_id}")
            self.logger.info(f"Suggestion prompt (first 500 chars): {prompt[:500]}...")
            
            # Debug logging to show full prompt sections
            self.logger.info("=== FULL SUGGESTION PROMPT DEBUG ===")
            self.logger.info(f"Existing notes section:\n{notes_text}")
            self.logger.info(f"Existing suggestions section:\n{suggestions_text}")
            self.logger.info(f"ULT text (first 300 chars): {ult_text[:300]}...")
            self.logger.info(f"UST text (first 300 chars): {ust_text[:300]}...")
            self.logger.info(f"Translation issues count: {len(translation_issues)}")
            self.logger.info("=== FULL PROMPT ===")
            self.logger.info(prompt)
            self.logger.info("=== END FULL PROMPT ===")
            
            # Wait for batch to complete (polling)
            max_wait_time = 30 * 60  # 30 minutes
            poll_interval = 30  # 30 seconds
            elapsed = 0
            
            while elapsed < max_wait_time:
                time.sleep(poll_interval)
                elapsed += poll_interval
                
                try:
                    batch_status = self.ai_service.get_batch_status(batch_id)
                    
                    if batch_status.processing_status == 'ended':
                        # Get and process results
                        raw_results = self.ai_service.get_batch_results(batch_status)
                        self.logger.info(f"Got {len(raw_results)} batch results")
                        
                        # Find the suggestion result (ignore dummy)
                        for i, result in enumerate(raw_results):
                            self.logger.debug(f"Result {i}: type={type(result)}, custom_id={getattr(result, 'custom_id', 'unknown')}")
                            
                            if hasattr(result, 'custom_id') and result.custom_id == 'suggestion_request':
                                self.logger.info("Found suggestion request result")
                                
                                if hasattr(result, 'result') and result.result:
                                    self.logger.info(f"Result structure: {type(result.result)}")
                                    
                                    try: # Outer try for accessing message content
                                        if hasattr(result.result, 'message') and hasattr(result.result.message, 'content'):
                                            content = result.result.message.content
                                            if isinstance(content, list) and len(content) > 0:
                                                text_content = content[0].text if hasattr(content[0], 'text') else str(content[0])
                                            else:
                                                text_content = str(content)
                                            
                                            self.logger.info(f"AI Response content: {text_content[:500]}...")
                                            
                                            # Inner try for JSON parsing of the extracted text_content
                                            try:
                                                suggestions = []
                                                import re
                                                json_pattern = r'\{[^}]*"reference"[^}]*\}'
                                                json_matches = re.findall(json_pattern, text_content, re.DOTALL)
                                                
                                                self.logger.info(f"Found {len(json_matches)} potential JSON objects in AI response.")
                                                
                                                for match in json_matches:
                                                    try:
                                                        cleaned_match = match.strip()
                                                        suggestion = json.loads(cleaned_match)
                                                        suggestions.append(suggestion)
                                                        self.logger.debug(f"Parsed suggestion: {suggestion}")
                                                    except json.JSONDecodeError as e_json_obj:
                                                        self.logger.warning(f"Failed to parse individual JSON object: {match[:100]}... Error: {e_json_obj}")
                                                        continue # Try next match
                                                
                                                if not suggestions:
                                                    self.logger.info("No individual JSON objects parsed, attempting to parse entire response as JSON array or object.")
                                                    try:
                                                        if text_content.strip().startswith('['):
                                                            suggestions = json.loads(text_content)
                                                        elif text_content.strip().startswith('{'):
                                                            suggestions = [json.loads(text_content)] # Wrap single object in a list
                                                        else:
                                                            self.logger.warning("AI response content does not start with [ or {. Could not identify JSON format.")
                                                            return [] # No valid suggestions if format is unexpected
                                                    except json.JSONDecodeError as e_json_full:
                                                        self.logger.warning(f"Full AI response is not valid JSON. Error: {e_json_full}. Content: {text_content[:200]}...")
                                                        return [] # No valid suggestions if not parseable
                                                
                                                self.logger.info(f"Successfully generated {len(suggestions)} valid suggestions from AI response.")
                                                return suggestions
                                                
                                            except Exception as e_parse: # Catch other errors during parsing/regex
                                                self.logger.error(f"Error parsing AI suggestion response (text_content): {e_parse}. Content: {text_content[:200]}...")
                                                return []
                                        else:
                                            self.logger.error("AI result.result object does not have 'message' or 'message.content' attributes.")
                                            return []
                                    except Exception as e_outer_access: # Catch errors from the outer try (accessing message.content)
                                        self.logger.error(f"Error accessing AI suggestion result content: {e_outer_access}")
                                        import traceback
                                        self.logger.debug(f"Traceback for content access error: {traceback.format_exc()}")
                                        return []
                                else:
                                    self.logger.error("Suggestion request result has no 'result' attribute or 'result' is None.")
                                    return []
                        
                        # If loop completes without finding 'suggestion_request' result
                        self.logger.warning("Suggestion result not found in batch results")
                        return []
                    
                    elif batch_status.processing_status in ['canceled', 'expired', 'failed']:
                        self.logger.error(f"Suggestion batch failed: {batch_status.processing_status}")
                        return []
                    
                    else:
                        self.logger.debug(f"Suggestion batch still processing: {batch_status.processing_status}")
                
                except Exception as e:
                    self.logger.error(f"Error checking suggestion batch status: {e}")
                    return []
            
            self.logger.error("Suggestion batch timed out")
            return []
            
        except Exception as e:
            self.logger.error(f"Error generating AI suggestions: {e}")
            return []

    def _write_suggestions_to_sheet(self, sheet_id: str, suggestions: List[Dict[str, Any]]):
        """Write suggestions to the suggested notes tab.
        
        Args:
            sheet_id: Google Sheets ID
            suggestions: List of suggestion dictionaries
        """
        try:
            if not suggestions:
                return
            
            # Get existing data to find next available row
            range_name = "'suggested notes'!A:F"
            
            result = self.sheet_manager.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            
            existing_values = result.get('values', [])
            next_row = max(3, len(existing_values) + 1)  # Start at row 3 minimum
            
            # Prepare data to write
            values_to_write = []
            suggestions_with_at = 0
            for suggestion in suggestions:
                alternate_translation = suggestion.get('alternate translation', '')
                if alternate_translation:
                    suggestions_with_at += 1
                
                # Apply post-processing to text fields
                row_data = [
                    _post_process_text(suggestion.get('reference', '')),
                    _post_process_text(suggestion.get('issuetype', '')),
                    _post_process_text(suggestion.get('quote', '')),
                    '',  # Go? column (column D) - leave empty
                    _post_process_text(alternate_translation),  # AT column (column E) - get from suggestion
                    _post_process_text(suggestion.get('explanation', ''))
                ]
                values_to_write.append(row_data)
            
            self.logger.info(f"Writing {len(suggestions)} suggestions, {suggestions_with_at} with alternate translations")
            
            # Write to sheet
            if values_to_write:
                range_to_write = f"'suggested notes'!A{next_row}:F{next_row + len(values_to_write) - 1}"
                
                body = {
                    'values': values_to_write
                }
                
                self.sheet_manager.service.spreadsheets().values().append(
                    spreadsheetId=sheet_id,
                    range=range_to_write,
                    valueInputOption='RAW',
                    body=body
                ).execute()
                
                self.logger.info(f"Successfully wrote {len(suggestions)} suggestions starting at row {next_row}")
            
        except Exception as e:
            self.logger.error(f"Error writing suggestions to sheet: {e}")
            raise

    def _turn_off_suggestion_request(self, sheet_id: str):
        """Turn off the suggestion request by changing YES to NO.
        
        Args:
            sheet_id: Google Sheets ID
        """
        try:
            # Write 'NO' to suggested notes tab, column D, row 2
            range_name = "'suggested notes'!D2"
            
            body = {
                'values': [['NO']]
            }
            
            self.sheet_manager.service.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()
            
            self.logger.info("Successfully turned off suggestion request")
            
        except Exception as e:
            self.logger.error(f"Error turning off suggestion request: {e}")
            raise 