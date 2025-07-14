"""
Shared Processing Utilities

This module contains common functions used by both batch_processor and continuous_batch_manager
to eliminate code duplication and improve maintainability.

The utilities are organized into several categories:

1. Text Processing:
   - post_process_text(): Converts straight quotes to smart quotes and removes curly braces
   - clean_ai_output(): Cleans AI output by removing quotes and whitespace
   - format_alternate_translation(): Formats AT text with proper bracketing

2. Item Classification:
   - separate_items_by_processing_type(): Categorizes items as programmatic vs AI-based
   - determine_note_type(): Determines if a note is see_how, given_at, or writes_at
   - should_include_alternate_translation(): Checks if templates require AT

3. Note Generation:
   - generate_programmatic_note(): Creates notes for "see how" and translate-unknown items
   - format_final_note(): Formats the final note based on type and content

4. Data Management:
   - prepare_update_data(): Prepares sheet update data structures
   - get_row_identifier(): Creates unique row identifiers for tracking
   - ensure_biblical_text_cached(): Ensures ULT/UST text is cached

All functions are designed to be stateless and reusable across different processing contexts.
"""

import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime


def post_process_text(text: str) -> str:
    """Post-process text by removing curly braces and converting straight quotes to smart quotes.
    
    This function is used to clean up AI-generated text by:
    1. Removing all curly braces ({})
    2. Converting straight quotes to smart quotes using proper typographic formatting
    
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


def separate_items_by_processing_type(items: List[Dict[str, Any]], 
                                     ai_service,
                                     cache_manager,
                                     logger: Optional[logging.Logger] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Separate items into those that can be handled programmatically vs those needing AI.
    
    This function categorizes items based on their type:
    1. Programmatic items: "see how" notes and translate-unknown with TW matches
    2. AI items: Everything else that requires AI processing
    
    Args:
        items: List of all items to categorize
        ai_service: AI service instance for template checking
        cache_manager: Cache manager for TW headwords
        logger: Optional logger instance
        
    Returns:
        Tuple of (programmatic_items, ai_items)
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    programmatic_items = []
    ai_items = []
    
    logger.info(f"=== SEPARATING {len(items)} ITEMS BY PROCESSING TYPE ===")
    
    tw_headwords = None

    for item in items:
        explanation = item.get('Explanation', '').strip()
        sref = item.get('SRef', '').strip()
        at = item.get('AT', '').strip()
        gl_quote = item.get('GLQuote', '')
        ref = item.get('Ref', 'unknown')

        # Check for translate-unknown with TW matches
        if 'TWN' not in explanation.lower() and 'translate-unknown' in sref.lower():
            if tw_headwords is None:
                tw_headwords = cache_manager.load_tw_headwords()
            
            from .tw_search import find_matches
            matches = find_matches(gl_quote, tw_headwords)
            if matches:
                item['tw_matches'] = matches
                logger.info(f"PROGRAMMATIC: {ref} - translate-unknown headword matches {matches}")
                programmatic_items.append(item)
                continue
        
        # Check for "see how" notes
        if explanation.lower().startswith('see how'):
            templates = ai_service._get_templates_for_item(item)
            needs_at = should_include_alternate_translation(templates)

            if not needs_at:
                logger.info(f"PROGRAMMATIC: {ref} - 'see how' does not require an alternate translation based on templates.")
                programmatic_items.append(item)
            else:
                if at:
                    logger.info(f"PROGRAMMATIC: {ref} - 'see how' has a provided alternate translation.")
                    programmatic_items.append(item)
                else:
                    logger.info(f"AI NEEDED: {ref} - 'see how' requires an alternate translation, but it is missing.")
                    ai_items.append(item)
        else:
            logger.info(f"AI NEEDED: {ref} - General case: explanation: '{explanation[:50]}...'")
            ai_items.append(item)
    
    logger.info(f"SEPARATION COMPLETE: {len(programmatic_items)} programmatic, {len(ai_items)} need AI")
    return programmatic_items, ai_items


def should_include_alternate_translation(templates: List[Dict[str, Any]]) -> bool:
    """Check if any template contains "Alternate translation".
    
    Args:
        templates: List of templates to check
        
    Returns:
        True if alternate translation should be included
    """
    for template in templates:
        note_template = template.get('note_template', '')
        if 'Alternate translation' in note_template:
            return True
    return False


def format_alternate_translation(at: str) -> str:
    """Format the alternate translation text for appending to notes.
    
    This function handles:
    1. Multiple alternate translations separated by '/'
    2. Proper bracket formatting
    3. Empty/whitespace-only input
    
    Args:
        at: Alternate translation text from the AT column
        
    Returns:
        Formatted alternate translation string
    """
    if not at.strip():
        return ""
    
    # Handle multiple alternate translations separated by '/'
    if '/' in at:
        # Split by '/' and format each part
        parts = [part.strip() for part in at.split('/') if part.strip()]
        formatted_parts = [f"[{part}]" for part in parts]
        return f" Alternate translation: {' or '.join(formatted_parts)}"
    else:
        # Single alternate translation
        return f" Alternate translation: [{at.strip()}]"


def generate_programmatic_note(item: Dict[str, Any], logger: Optional[logging.Logger] = None) -> str:
    """Generate a note programmatically for "see how" or "translate-unknown" items.
    
    This function handles two types of programmatic notes:
    1. "See how" notes with proper reference formatting and zero-padding
    2. Translate-unknown notes with TW headword matches
    
    Args:
        item: Item data containing note information
        logger: Optional logger instance
        
    Returns:
        Generated note text
    """
    if logger is None:
        logger = logging.getLogger(__name__)
        
    explanation = item.get('Explanation', '').strip()
    at = item.get('AT', '').strip()
    
    if explanation.lower().startswith('see how'):
        # Extract the reference (e.g., "see how 20:3" -> "20:3")
        ref_match = explanation.replace('see how ', '').strip()
        
        if ':' in ref_match:
            chapter, verse = ref_match.split(':', 1)
            # Prepend zero if chapter or verse length equals one
            note = f"See how you translated the similar expression in [{chapter}:{verse}](../{chapter.zfill(2)}/{verse.zfill(2)}.md)."
        else:
            note = f"See how you translated the similar expression in {ref_match}."
        
        # Add alternate translation using the formatting function
        formatted_at = format_alternate_translation(at)
        note += formatted_at
        
        # Apply post-processing to clean up the note
        processed_note = post_process_text(note)

        logger.info(f"Generated programmatic note for {item.get('Ref', 'unknown')}: {processed_note}")
        return processed_note

    # Handle translate-unknown using pre-matched TW headwords
    if ('TWN' not in explanation and
            'translate-unknown' in item.get('SRef', '').lower()):
        matches = item.get('tw_matches') or []
        if matches:
            note = f"TW found: {', '.join(matches)}"
            processed_note = post_process_text(note)
            logger.info(
                f"Generated translate-unknown note for {item.get('Ref', 'unknown')}: {processed_note}")
            return processed_note
    
    return ""


def clean_ai_output(output: str) -> str:
    """Clean AI output by removing quotes and extra whitespace.
    
    This function standardizes AI output by:
    1. Removing surrounding quotes (both single and double)
    2. Removing trailing newlines
    3. Stripping whitespace
    
    Args:
        output: Raw AI output
        
    Returns:
        Cleaned output
    """
    # Remove surrounding quotes
    cleaned = output.strip()
    if cleaned.startswith('"') and cleaned.endswith('"'):
        cleaned = cleaned[1:-1]
    elif cleaned.startswith("'") and cleaned.endswith("'"):
        cleaned = cleaned[1:-1]
    
    # Remove trailing newlines
    cleaned = cleaned.rstrip('\n')
    
    return cleaned


def determine_note_type(item: Dict[str, Any]) -> str:
    """Determine the type of note based on item data.
    
    Note types:
    - see_how: "See how" explanation
    - given_at: Has alternate translation provided
    - writes_at: AI needs to write alternate translation
    
    Args:
        item: Original item data
        
    Returns:
        Note type string
    """
    explanation = item.get('Explanation', '').strip()
    at = item.get('AT', '').strip()
    
    if explanation.lower().startswith('see how'):
        return 'see_how'
    elif at:
        return 'given_at'
    else:
        return 'writes_at'


def format_final_note(original_item: Dict[str, Any], ai_output: str, note_type: str, 
                     logger: Optional[logging.Logger] = None) -> str:
    """Format the final note based on the note type.
    
    This function handles different note formatting strategies:
    1. see_how: Format reference with proper zero-padding and add AT
    2. given_at: Use AI output and append provided AT
    3. writes_at: Use AI output (should include AT already)
    
    Args:
        original_item: Original item data
        ai_output: AI-generated output
        note_type: Type of note (see_how, given_at, writes_at)
        logger: Optional logger instance
        
    Returns:
        Formatted final note
    """
    if logger is None:
        logger = logging.getLogger(__name__)
        
    try:
        explanation = original_item.get('Explanation', '').strip()
        at = original_item.get('AT', '').strip()
        
        if note_type == 'see_how':
            # For "see how" notes, format the reference
            if explanation.lower().startswith('see how'):
                # Extract the reference (e.g., "see how 20:3" -> "20:3")
                ref_match = explanation.replace('see how ', '').strip()
                if ':' in ref_match:
                    chapter, verse = ref_match.split(':', 1)
                    # Prepend zero if chapter or verse length equals one
                    note = f"See how you translated the similar expression in [{chapter}:{verse}](../{chapter.zfill(2)}/{verse.zfill(2)}.md)."
                else:
                    note = f"See how you translated the similar expression in {ref_match}."
            else:
                note = ai_output
            
            # Add alternate translation if provided
            if at:
                formatted_at = format_alternate_translation(at)
                note += formatted_at
            
            return post_process_text(note)
        
        elif note_type == 'given_at':
            # AI output should be the note, AT is already provided - append it
            note = ai_output
            
            if at:
                formatted_at = format_alternate_translation(at)
                note += formatted_at
            
            return post_process_text(note)
        
        elif note_type == 'writes_at':
            # AI should have written both note and alternate translation
            # Check if the output already contains "Alternate translation:"
            if 'Alternate translation:' in ai_output:
                return post_process_text(ai_output)
            else:
                # AI didn't include alternate translation, might need to add it
                # This shouldn't happen with proper prompts, but handle gracefully
                note = ai_output
                
                # If we have an AT value, append it
                if at:
                    formatted_at = format_alternate_translation(at)
                    note += formatted_at
                
                return post_process_text(note)
        
        else:
            # Default case - just append AT if provided
            note = ai_output
            if at:
                formatted_at = format_alternate_translation(at)
                note += formatted_at
            return post_process_text(note)
            
    except Exception as e:
        if logger:
            logger.error(f"Error formatting final note: {e}")
        return post_process_text(ai_output)


def prepare_update_data(original_item: Dict[str, Any], ai_output: str, 
                       logger: Optional[logging.Logger] = None) -> Optional[Dict[str, Any]]:
    """Prepare update data for a sheet row.
    
    This function creates the standardized update format used by the sheet manager.
    It handles different possible row number field names and formats the note properly.
    
    Args:
        original_item: Original item data
        ai_output: AI-generated output
        logger: Optional logger instance
        
    Returns:
        Update data dictionary or None if invalid
    """
    if logger is None:
        logger = logging.getLogger(__name__)
        
    try:
        # Try multiple possible row number field names
        row_number = (original_item.get('row') or 
                     original_item.get('row # for n8n hide, don\'t delete') or
                     original_item.get('row_number'))
        
        if not row_number:
            logger.warning(f"No row number found in original item. Available keys: {list(original_item.keys())}")
            return None
        
        # Clean the AI output
        cleaned_output = clean_ai_output(ai_output)
        
        logger.info(f"AI output for {original_item.get('Ref', 'unknown')}: {cleaned_output[:200]}{'...' if len(cleaned_output) > 200 else ''}")
        
        # Determine what type of note this is and format accordingly
        note_type = determine_note_type(original_item)
        final_note = format_final_note(original_item, cleaned_output, note_type, logger)
        
        logger.debug(f"Note type: {note_type}, Final note length: {len(final_note)}")
        logger.info(f"Final formatted note: {final_note[:200]}{'...' if len(final_note) > 200 else ''}")
        
        # Prepare the update
        update_data = {
            'row_number': row_number,
            'updates': {
                'Go?': 'AI',  # Mark as completed by AI
                'AI TN': final_note
            }
        }
        
        # Add SRef if it was updated
        if original_item.get('SRef'):
            update_data['updates']['SRef'] = original_item['SRef']
        
        return update_data
        
    except Exception as e:
        logger.error(f"Error preparing update data: {e}")
        return None


def get_row_identifier(sheet_id: str, item: Dict[str, Any]) -> str:
    """Create a unique identifier for a row.
    
    Args:
        sheet_id: Sheet ID
        item: Item containing row information
        
    Returns:
        Unique identifier string in format "sheet_id:row_number"
    """
    row_number = (item.get('row') or 
                 item.get('row # for n8n hide, don\'t delete') or
                 item.get('row_number') or
                 'unknown')
    return f"{sheet_id}:{row_number}"


def ensure_biblical_text_cached(user: str, book: str, cache_manager, sheet_manager, 
                                config, logger: Optional[logging.Logger] = None):
    """Ensure biblical text is cached for the user and book.
    
    This function checks if ULT and UST text is cached for the user/book combination.
    If not, it fetches the data and caches it for future use.
    
    Args:
        user: Username
        book: Book code
        cache_manager: Cache manager instance
        sheet_manager: Sheet manager instance
        config: Configuration manager instance
        logger: Optional logger instance
    """
    if logger is None:
        logger = logging.getLogger(__name__)
        
    for text_type in ['ULT', 'UST']:
        cached_data = cache_manager.get_biblical_text_for_user(text_type, user, book)
        if not cached_data:
            logger.info(f"No {text_type} cache found for {user}/{book}, fetching...")
            
            # Fetch biblical text for the specific book
            biblical_data = sheet_manager.fetch_biblical_text(text_type, book_code=book, user=user)
            if biblical_data:
                # We trust fetch_biblical_text to return data for the correct book or log errors
                cache_manager.set_biblical_text_for_user(text_type, user, book, biblical_data)
                logger.info(f"Cached {text_type} for {user}/{book}")
            else:
                logger.warning(f"Failed to fetch {text_type} for {user}/{book} to cache it.")