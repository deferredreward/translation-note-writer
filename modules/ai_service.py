"""
AI Service
Handles interactions with Anthropic's Claude API using batch processing and prompt caching.
"""

import json
import time
import logging
import os
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import anthropic

from .config_manager import ConfigManager
from .cache_manager import CacheManager
from .prompt_manager import PromptManager


class AIService:
    """Handles AI interactions with batch processing and prompt caching."""
    
    def __init__(self, config: ConfigManager, cache_manager: CacheManager):
        """Initialize the AI service with configuration.
        
        Args:
            config: Configuration manager
            cache_manager: Cache manager for accessing cached data
        """
        self.config = config
        self.cache_manager = cache_manager
        self.logger = logging.getLogger(__name__)
        
        # Get configuration
        anthropic_config = config.get_anthropic_config()
        timing_config = config.get_timing_config()
        
        # Set up Anthropic configuration
        self.api_key = anthropic_config.get('api_key') or os.getenv('ANTHROPIC_API_KEY')
        self.model = anthropic_config.get('model', 'claude-3-5-sonnet-20241022')
        self.batch_size = anthropic_config['batch_size']
        self.enable_prompt_caching = anthropic_config.get('enable_prompt_caching', True)
        
        # Timing configuration
        self.error_retry_delay = timing_config['error_retry_delay']
        
        if not self.api_key:
            raise ValueError("Anthropic API key not found in configuration or environment variables")
        
        # Initialize Anthropic client
        self.client = anthropic.Anthropic(api_key=self.api_key)
        
        # Initialize prompt manager
        self.prompt_manager = PromptManager(config, cache_manager)
        
        self.logger.info(f"AI Service initialized with model: {self.model}")
        if self.enable_prompt_caching:
            self.logger.info("Prompt caching enabled")
    
    def create_batch_requests(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create batch requests for Anthropic API.
        
        Args:
            items: List of items to process
            
        Returns:
            List of batch request objects
        """
        # Check if templates are available before creating requests
        templates = self.cache_manager.get_cached_data('templates')
        pause_on_missing = self.config.get('anthropic.pause_on_missing_templates', True)
        
        if not templates and pause_on_missing:
            self.logger.error("=" * 80)
            self.logger.error("TEMPLATES NOT AVAILABLE!")
            self.logger.error("No templates found in cache. Sending requests to AI without templates")
            self.logger.error("will waste money as the AI will receive 'No templates available'.")
            self.logger.error("=" * 80)
            
            # Try one more refresh attempt
            self.logger.info("Attempting final template cache refresh...")
            refreshed = self.cache_manager.force_refresh_templates()
            if refreshed:
                templates = self.cache_manager.get_cached_data('templates')
                if templates:
                    self.logger.info(f"SUCCESS: Templates now available ({len(templates)} templates loaded)")
                else:
                    self.logger.error("FAILED: Templates cache refresh succeeded but no templates found")
            else:
                self.logger.error("FAILED: Template cache refresh failed")
            
            if not templates:
                self.logger.error("PAUSING: Please fix template loading issue before continuing.")
                
                # Interactive pause
                try:
                    response = input("\nTemplates are missing! Continue anyway and waste money? (y/N): ").strip().lower()
                    if response not in ['y', 'yes']:
                        self.logger.info("Processing cancelled by user")
                        return []
                    else:
                        self.logger.warning("User chose to continue without templates - money will be wasted!")
                except (EOFError, KeyboardInterrupt):
                    self.logger.info("Processing cancelled by user")
                    return []
        
        requests = []
        
        for i, item in enumerate(items):
            try:
                # Determine the type of note to create
                note_type = self._determine_note_type(item)
                
                # Get the appropriate prompt and system message
                prompt, system_message = self._build_prompt(item, note_type)
                
                # Log the prompt details for debugging
                item_ref = item.get('Ref', 'unknown')
                item_row = item.get('row', 'unknown')
                
                self.logger.info(f"=== PROMPT DEBUG - Item {i+1} ===")
                self.logger.info(f"Row: {item_row}")
                self.logger.info(f"Ref: {item_ref}")
                self.logger.info(f"Note Type: {note_type}")
                self.logger.info(f"SRef: {item.get('SRef', '')}")
                self.logger.info(f"GLQuote: {item.get('GLQuote', '')}")
                self.logger.info(f"AT: {item.get('AT', '')}")
                self.logger.info(f"Explanation: {item.get('Explanation', '')}")
                
                self.logger.info(f"--- SYSTEM MESSAGE ---")
                # Log system message directly (preserving Unicode characters)
                self.logger.info(system_message if system_message else 'None')
                
                self.logger.info(f"--- USER PROMPT ---")
                # Log prompt directly (preserving Unicode characters)
                self.logger.info(prompt)
                self.logger.info(f"--- END PROMPT DEBUG ---")
                
                # Create the request
                request = {
                    "custom_id": f"item_{i}_{item.get('row', 'unknown')}",
                    "params": {
                        "model": self.model,
                        "max_tokens": 2048,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ]
                    }
                }
                
                # Add system message if provided
                if system_message:
                    if self.enable_prompt_caching:
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
                self.logger.error(f"Error creating request for item {i}: {e}")
                # Create a placeholder request that will fail gracefully
                requests.append({
                    "custom_id": f"item_{i}_error",
                    "params": {
                        "model": self.model,
                        "max_tokens": 100,
                        "messages": [{"role": "user", "content": "Error in request creation"}]
                    }
                })
        
        return requests
    
    def _determine_note_type(self, item: Dict[str, Any]) -> str:
        """Determine what type of note to create based on the item data.
        
        Args:
            item: Item data from the sheet
            
        Returns:
            Note type string
        """
        explanation = item.get('Explanation', '').strip()
        at = item.get('AT', '').strip()
        
        # Check if this is a "see how" reference note
        if explanation.lower().startswith('see how'):
            if not at:
                return 'see_how_at'  # Need to generate AT
            else:
                return 'see_how'     # AT already provided
        
        # Check if AT is provided
        if at:
            return 'given_at'  # AT provided, just need note
        else:
            return 'writes_at'  # Need to write both note and AT
    
    def _build_prompt(self, item: Dict[str, Any], note_type: str, user: str = None, book: str = None) -> Tuple[str, Optional[str]]:
        """Build the prompt and system message for an item.
        
        Args:
            item: Item data from the sheet
            note_type: Type of note to create
            user: Username for user-specific biblical text (optional)
            book: Book code for user-specific biblical text (optional)
            
        Returns:
            Tuple of (prompt, system_message)
        """
        # Get cached data
        templates = self._get_templates_for_item(item)
        biblical_text = self._get_biblical_text_for_item(item, user=user, book=book)
        
        # Log template and biblical text details
        self.logger.debug(f"Building prompt for {item.get('Ref', 'unknown')}:")
        self.logger.debug(f"  Found {len(templates)} templates")
        for i, template in enumerate(templates):
            self.logger.debug(f"    Template {i+1}: {template.get('issue_type', 'Unknown')} - {template.get('note_template', '')[:100]}...")
        
        self.logger.debug(f"  Biblical text keys: {list(biblical_text.keys())}")
        if 'ult_verse_content' in biblical_text:
            self.logger.debug(f"    ULT: {biblical_text['ult_verse_content'][:100]}...")
        if 'ust_verse_content' in biblical_text:
            self.logger.debug(f"    UST: {biblical_text['ust_verse_content'][:100]}...")
        
        # If GLQuote is empty, use the entire verse text from ULT
        gl_quote = item.get('GLQuote', '').strip()
        if not gl_quote and biblical_text.get('ult_verse_content'):
            gl_quote = biblical_text['ult_verse_content']
            self.logger.info(f"Using entire verse text as GLQuote: {gl_quote[:100]}...")
        
        # Prepare template variables
        template_vars = {
            'book': item.get('Book', ''),
            'ref': item.get('Ref', ''),
            'sref': item.get('SRef', ''),
            'gl_quote': gl_quote,  # Use potentially modified GLQuote
            'at': item.get('AT', ''),
            'explanation': item.get('Explanation', ''),
            'ai_tn': item.get('AI TN', ''),
            'templates': self._format_templates(templates),
            **biblical_text
        }
        
        self.logger.debug(f"  Template variables prepared:")
        for key, value in template_vars.items():
            if isinstance(value, str) and len(value) > 100:
                self.logger.debug(f"    {key}: {value[:100]}...")
            else:
                self.logger.debug(f"    {key}: {value}")
        
        # Get the appropriate prompt
        prompt = self.prompt_manager.get_prompt(note_type, template_vars)
        
        # Get system message
        system_message = self.prompt_manager.get_system_message(note_type)
        
        self.logger.debug(f"  Final prompt length: {len(prompt)} characters")
        self.logger.debug(f"  System message length: {len(system_message) if system_message else 0} characters")
        
        return prompt, system_message
    
    def _get_templates_for_item(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get relevant templates for an item.
        
        Args:
            item: Item data from the sheet
            
        Returns:
            List of relevant templates
        """
        try:
            templates = self.cache_manager.get_cached_data('templates')
            
            # If no templates in cache, try to fetch them directly
            if not templates:
                self.logger.warning("No templates found in cache")
                
                # Try to force refresh templates
                self.logger.info("Attempting to refresh templates cache...")
                try:
                    # Import here to avoid circular imports
                    from .sheet_manager import SheetManager
                    sheet_manager = SheetManager(self.config)
                    templates = sheet_manager.fetch_templates()
                    
                    if templates:
                        self.logger.info(f"Fetched {len(templates)} templates directly from sheets")
                        # Try to cache them (but continue even if caching fails)
                        try:
                            self.cache_manager.set_cached_data('templates', templates)
                            self.logger.info("Successfully cached templates")
                        except Exception as cache_error:
                            self.logger.warning(f"Failed to cache templates: {cache_error}")
                            # Continue with templates anyway
                    else:
                        self.logger.error("Failed to fetch templates from sheets")
                        return []
                        
                except Exception as fetch_error:
                    self.logger.error(f"Error fetching templates: {fetch_error}")
                    return []
            
            if not templates:
                self.logger.error("Still no templates available after fetch attempt")
                return []
                
            self.logger.debug(f"Total templates available: {len(templates)}")
            
            sref = item.get('SRef', '').strip()
            if not sref:
                self.logger.debug("No SRef found in item")
                return []
            
            self.logger.info(f"Looking for templates matching SRef: '{sref}'")
            
            # Debug: Show first few templates to understand structure
            if templates:
                self.logger.debug("Sample templates structure:")
                for i, template in enumerate(templates[:3]):
                    support_ref = template.get('support reference', '').strip()
                    note_template = template.get('note template', '')
                    template_type = template.get('type', '')
                    self.logger.debug(f"  Template {i+1}: support_ref='{support_ref}', type='{template_type}', template='{note_template[:50]}...'")
            
            # Find templates that match the SRef
            # Templates are stored as a flat array with "support reference" field
            matching_templates = []
            all_support_refs = []
            
            for template in templates:
                template_sref = template.get('support reference', '').strip()
                all_support_refs.append(template_sref)
                
                if template_sref == sref:
                    matching_templates.append({
                        'issue_type': template.get('type', ''),
                        'note_template': template.get('note template', '')
                    })
                    self.logger.info(f"MATCH FOUND: template_sref='{template_sref}' == item_sref='{sref}'")
            
            self.logger.info(f"Found {len(matching_templates)} matching templates for SRef: '{sref}'")
            
            if matching_templates:
                for i, template in enumerate(matching_templates):
                    self.logger.info(f"  Match {i+1}: Type='{template['issue_type']}', Template='{template['note_template'][:100]}...'")
            else:
                # Get unique support references for debugging
                unique_refs = sorted(list(set(all_support_refs)))
                self.logger.warning(f"No templates found matching SRef '{sref}'. Available support references ({len(unique_refs)}): {unique_refs[:20]}")
                
                # Check for close matches (case insensitive, extra whitespace, etc.)
                close_matches = []
                for ref in unique_refs:
                    if ref.lower() == sref.lower():
                        close_matches.append(f"'{ref}' (case difference)")
                    elif ref.replace(' ', '').replace('-', '') == sref.replace(' ', '').replace('-', ''):
                        close_matches.append(f"'{ref}' (spacing/dash difference)")
                
                if close_matches:
                    self.logger.warning(f"Possible close matches found: {close_matches}")
            
            return matching_templates
            
        except Exception as e:
            self.logger.error(f"Error getting templates for item: {e}")
            import traceback
            self.logger.debug(f"Full traceback: {traceback.format_exc()}")
            return []
    
    def _get_biblical_text_for_item(self, item: Dict[str, Any], user: str = None, book: str = None) -> Dict[str, str]:
        """Get biblical text context for an item.
        
        Args:
            item: Item data from the sheet
            user: Username for user-specific cache (optional)
            book: Book code for user-specific cache (optional)
            
        Returns:
            Dictionary with biblical text fields
        """
        try:
            # Get cached ULT and UST data (user-specific if available)
            if user and book:
                ult_data = self.cache_manager.get_biblical_text_for_user('ULT', user, book)
                ust_data = self.cache_manager.get_biblical_text_for_user('UST', user, book)
            else:
                # Fallback to global cache
                ult_data = self.cache_manager.get_cached_data('ult_chapters')
                ust_data = self.cache_manager.get_cached_data('ust_chapters')
            
            item_book = item.get('Book', '')
            ref = item.get('Ref', '')
            
            self.logger.debug(f"Getting biblical text for Book: '{item_book}', Ref: '{ref}'" + 
                             (f" (user: {user}, book: {book})" if user and book else ""))
            self.logger.debug(f"ULT data available: {ult_data is not None}")
            self.logger.debug(f"UST data available: {ust_data is not None}")
            
            if ult_data:
                self.logger.debug(f"ULT data structure: {type(ult_data)}")
                if isinstance(ult_data, dict):
                    self.logger.debug(f"ULT data keys: {list(ult_data.keys())}")
                    if 'book' in ult_data:
                        self.logger.debug(f"ULT book in data: '{ult_data['book']}'")
            
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
            
            self.logger.debug(f"Parsed ref: chapter={chapter}, verse={verse}")
            
            result = {}
            
            # Get ULT text
            if ult_data:
                ult_verse_content, ult_verse_in_context = self._extract_verse_content(
                    ult_data, item_book or book, chapter, verse
                )
                result['ult_verse_content'] = ult_verse_content
                result['ult_verse_in_context'] = ult_verse_in_context
                self.logger.debug(f"ULT verse content: '{ult_verse_content[:100]}...' (length: {len(ult_verse_content)})")
            else:
                self.logger.warning("No ULT data available in cache")
            
            # Get UST text
            if ust_data:
                ust_verse_content, ust_verse_in_context = self._extract_verse_content(
                    ust_data, item_book or book, chapter, verse
                )
                result['ust_verse_content'] = ust_verse_content
                result['ust_verse_in_context'] = ust_verse_in_context
                self.logger.debug(f"UST verse content: '{ust_verse_content[:100]}...' (length: {len(ust_verse_content)})")
            else:
                self.logger.warning("No UST data available in cache")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error getting biblical text for item: {e}")
            import traceback
            self.logger.debug(f"Full traceback: {traceback.format_exc()}")
            return {}
    
    def _extract_verse_content(self, data: Dict[str, Any], book: str, chapter: int, verse: int) -> Tuple[str, str]:
        """Extract verse content and context from biblical text data.
        
        Args:
            data: Biblical text data
            book: Book abbreviation
            chapter: Chapter number
            verse: Verse number
            
        Returns:
            Tuple of (verse_content, verse_in_context)
        """
        try:
            self.logger.debug(f"Extracting verse for book='{book}', chapter={chapter}, verse={verse}")
            
            # Check if data has the expected structure
            if not isinstance(data, dict):
                self.logger.error(f"Biblical text data is not a dict: {type(data)}")
                return "broken", "broken"
            
            # Check if book matches (if book info is in data)
            data_book = data.get('book', '')
            if data_book and book and data_book.upper() != book.upper():
                self.logger.warning(f"Book mismatch: requested '{book}' but data contains '{data_book}'")
                # Continue anyway - maybe the data is for the right book but book field is wrong
            
            # Find the chapter
            chapters = data.get('chapters', [])
            if not chapters:
                self.logger.error("No chapters found in biblical text data")
                return "broken", "broken"
            
            self.logger.debug(f"Found {len(chapters)} chapters in data")
            
            target_chapter = None
            for ch in chapters:
                ch_num = ch.get('chapter')
                self.logger.debug(f"Checking chapter: {ch_num} (type: {type(ch_num)})")
                if ch_num == chapter:
                    target_chapter = ch
                    break
            
            if not target_chapter:
                self.logger.error(f"Chapter {chapter} not found. Available chapters: {[ch.get('chapter') for ch in chapters]}")
                return "broken", "broken"
            
            verses = target_chapter.get('verses', [])
            if not verses:
                self.logger.error(f"No verses found in chapter {chapter}")
                return "broken", "broken"
            
            self.logger.debug(f"Found {len(verses)} verses in chapter {chapter}")
            
            # Find the target verse
            target_verse_index = -1
            verse_content = "broken"
            
            for i, v in enumerate(verses):
                v_num = v.get('number')
                self.logger.debug(f"Checking verse: {v_num} (type: {type(v_num)})")
                if v_num == verse:
                    target_verse_index = i
                    verse_content = v.get('content', '')
                    self.logger.debug(f"Found target verse {verse} at index {i}: '{verse_content[:100]}...'")
                    break
            
            if target_verse_index == -1:
                available_verses = [v.get('number') for v in verses]
                self.logger.error(f"Verse {verse} not found in chapter {chapter}. Available verses: {available_verses}")
                return "broken", "broken"
            
            # Build context (5 verses before and after)
            start_index = max(0, target_verse_index - 5)
            end_index = min(len(verses) - 1, target_verse_index + 5)
            
            context_verses = []
            for i in range(start_index, end_index + 1):
                v = verses[i]
                v_content = v.get('content', '')
                context_verses.append(f"[{v.get('number')}] {v_content}")
            
            verse_in_context = ' '.join(context_verses)
            
            self.logger.debug(f"Successfully extracted verse {verse} from chapter {chapter}")
            return verse_content, verse_in_context
            
        except Exception as e:
            self.logger.error(f"Error extracting verse content: {e}")
            import traceback
            self.logger.debug(f"Full traceback: {traceback.format_exc()}")
            return "broken", "broken"
    
    def _format_templates(self, templates: List[Dict[str, Any]]) -> str:
        """Format templates for inclusion in prompts.
        
        Args:
            templates: List of template dictionaries
            
        Returns:
            Formatted template string
        """
        if not templates:
            return "No templates available"
        
        formatted = []
        for template in templates:
            issue_type = template.get('issue_type', '')
            note_template = template.get('note_template', '')
            
            # Remove "Alternate translation" section if present
            if 'Alternate translation' in note_template:
                note_template = note_template.split('Alternate translation')[0].strip()
            
            formatted.append(f"{issue_type}: {note_template}")
        
        return '\n\n'.join(formatted)
    
    def submit_batch(self, requests: List[Dict[str, Any]]) -> str:
        """Submit a batch of requests to Anthropic.
        
        Args:
            requests: List of request objects
            
        Returns:
            Batch ID
        """
        try:
            batch = self.client.beta.messages.batches.create(
                requests=requests
            )
            
            self.logger.info(f"Submitted batch with {len(requests)} requests. Batch ID: {batch.id}")
            return batch.id
            
        except Exception as e:
            self.logger.error(f"Error submitting batch: {e}")
            raise

    def get_batch_status(self, batch_id: str) -> Any:
        """Get the current status of a batch.
        
        Args:
            batch_id: Batch ID to check
            
        Returns:
            Batch object with current status
        """
        try:
            batch = self.client.beta.messages.batches.retrieve(batch_id)
            return batch
            
        except Exception as e:
            self.logger.error(f"Error getting batch status for {batch_id}: {e}")
            raise

    def wait_for_batch_completion(self, batch_id: str, timeout_hours: int = 1) -> Any:
        """Wait for a batch to complete.
        
        Args:
            batch_id: Batch ID to wait for
            timeout_hours: Maximum time to wait in hours
            
        Returns:
            Completed batch object
        """
        start_time = datetime.now()
        timeout = timedelta(hours=timeout_hours)
        
        # Get polling interval from config
        poll_interval = self.config.get('anthropic.batch_poll_interval', 30)
        
        self.logger.info(f"Waiting for batch {batch_id} to complete...")
        
        while datetime.now() - start_time < timeout:
            try:
                batch = self.client.beta.messages.batches.retrieve(batch_id)
                
                if batch.processing_status == "ended":
                    self.logger.info(f"Batch {batch_id} completed successfully")
                    return batch
                elif batch.processing_status in ["canceled", "expired"]:
                    raise Exception(f"Batch {batch_id} failed with status: {batch.processing_status}")
                
                # Log progress
                counts = batch.request_counts
                total = counts.processing + counts.succeeded + counts.errored + counts.canceled + counts.expired
                completed = counts.succeeded + counts.errored + counts.canceled + counts.expired
                
                if total > 0:
                    progress = (completed / total) * 100
                    self.logger.debug(f"Batch {batch_id} progress: {progress:.1f}% ({completed}/{total})")
                
                # Wait before checking again
                time.sleep(poll_interval)  # Use configurable interval
                
            except Exception as e:
                self.logger.error(f"Error checking batch status: {e}")
                time.sleep(self.error_retry_delay)  # Use configurable error retry delay
        
        raise TimeoutError(f"Batch {batch_id} did not complete within {timeout_hours} hours")
    
    def get_batch_results(self, batch: Any) -> List[Any]:
        """
        Retrieves the results for a completed batch job.
        This function polls for the results URL to be available and then fetches the results.
        """
        max_retries = 5
        retry_delay_seconds = 5
        retries = 0

        while retries < max_retries:
            # First, check that the batch is actually complete, using the correct attribute.
            if batch.processing_status != 'ended':
                self.logger.warning(f"Batch {batch.id} is not completed. Status: {batch.processing_status}")
                return []

            # If it's complete, check if the results_url is populated.
            if hasattr(batch, 'results_url') and batch.results_url:
                break

            # If not, wait and retry.
            retries += 1
            if retries >= max_retries:
                self.logger.error(f"Batch {batch.id} is completed but results URL not found after {max_retries} retries. Giving up.")
                return []

            self.logger.info(f"Batch {batch.id} is completed but no results URL yet. Retrying in {retry_delay_seconds}s... ({retries}/{max_retries})")
            time.sleep(retry_delay_seconds)
            
            # Refresh the batch status from the API
            batch = self.get_batch_status(batch.id)

        # Now, fetch the results using the results() endpoint.
        try:
            results = []
            for result in self.client.beta.messages.batches.results(batch.id):
                results.append(result)
            
            self.logger.info(f"Retrieved {len(results)} results from batch {batch.id}")
            return results
        except Exception as e:
            self.logger.error(f"Error fetching results for batch {batch.id} using results() endpoint: {e}")
            return []

    def process_batch_results(self, results: List[Any], original_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process batch results and match them with original items.
        
        Args:
            results: Raw batch results (MessageBatchIndividualResponse objects)
            original_items: Original items that were processed
            
        Returns:
            List of processed results with original item data
        """
        processed_results = []
        
        # Create a mapping from custom_id to original item
        item_map = {}
        for i, item in enumerate(original_items):
            custom_id = f"item_{i}_{item.get('row', 'unknown')}"
            item_map[custom_id] = item
        
        for result in results:
            try:
                # Access attributes directly from MessageBatchIndividualResponse object
                custom_id = result.custom_id
                original_item = item_map.get(custom_id, {})
                
                processed_result = {
                    'custom_id': custom_id,
                    'original_item': original_item,
                    'success': False,
                    'output': '',
                    'error': None
                }
                
                # Log the result details
                item_ref = original_item.get('Ref', 'unknown')
                self.logger.info(f"=== AI RESPONSE DEBUG - {item_ref} ===")
                self.logger.info(f"Custom ID: {custom_id}")
                
                # Check if the result has a successful message
                if hasattr(result, 'result') and hasattr(result.result, 'message'):
                    # Successful result
                    message = result.result.message
                    if hasattr(message, 'content') and message.content:
                        # Get the text content from the first content block
                        content_block = message.content[0]
                        if hasattr(content_block, 'text'):
                            output = content_block.text
                            processed_result['output'] = output
                            processed_result['success'] = True
                            
                            self.logger.info(f"SUCCESS - AI Response:")
                            self.logger.info(f"{output}")
                        else:
                            processed_result['error'] = 'No text content in response'
                            self.logger.error(f"ERROR - No text content in response")
                    else:
                        processed_result['error'] = 'No content in message'
                        self.logger.error(f"ERROR - No content in message")
                elif hasattr(result, 'result') and hasattr(result.result, 'error'):
                    # Error result
                    error = result.result.error
                    if hasattr(error, 'message'):
                        processed_result['error'] = error.message
                        self.logger.error(f"ERROR - API Error: {error.message}")
                    else:
                        processed_result['error'] = str(error)
                        self.logger.error(f"ERROR - API Error: {str(error)}")
                else:
                    processed_result['error'] = 'Unknown result format'
                    self.logger.error(f"ERROR - Unknown result format")
                
                self.logger.info(f"--- END AI RESPONSE DEBUG ---")
                processed_results.append(processed_result)
                
            except Exception as e:
                self.logger.error(f"Error processing result: {e}")
                processed_results.append({
                    'custom_id': getattr(result, 'custom_id', 'unknown'),
                    'original_item': {},
                    'success': False,
                    'output': '',
                    'error': str(e)
                })
        
        return processed_results 