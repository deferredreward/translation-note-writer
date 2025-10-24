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
from .text_utils import parse_verse_reference


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

        # Check for translate-unknown with TW matches (but only if TWN is NOT in explanation)
        if 'translate-unknown' in sref.lower():
            has_twn = 'twn' in explanation.lower()
            logger.info(f"DEBUG: {ref} - translate-unknown found, explanation contains TWN: {has_twn}, explanation: '{explanation}'")
            
            if not has_twn:
                if tw_headwords is None:
                    tw_headwords = cache_manager.load_tw_headwords()
                
                from .tw_search import find_matches
                matches = find_matches(gl_quote, tw_headwords)
                if matches:
                    item['tw_matches'] = matches
                    logger.info(f"PROGRAMMATIC: {ref} - translate-unknown headword matches {matches}")
                    programmatic_items.append(item)
                    continue
            else:
                logger.info(f"AI NEEDED: {ref} - translate-unknown with TWN override in explanation")
        
        # Check for "see how" notes - these are always handled programmatically
        if explanation.lower().startswith('see how'):
            logger.info(f"PROGRAMMATIC: {ref} - 'see how' note, handling programmatically.")
            programmatic_items.append(item)
            continue
            
        # If we get here, send to AI (including translate-unknown with TWN in explanation)
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
    1. "See how" notes with proper reference formatting (no zero-padding)
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
        # Extract the reference (e.g., "see how 2" -> "2", "see how 3:3" -> "3:3", "see how exo 2:2" -> "exo 2:2")
        ref_match = explanation.replace('see how ', '').strip()
        
        note = _format_see_how_reference(ref_match, item)
        
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


def _format_see_how_reference(ref_match: str, item: Dict[str, Any] = None) -> str:
    """Format a 'see how' reference according to the new specification.
    
    Handles three formats:
    - Same chapter: 'see how 2' -> 'See how you translated the similar expression in [verse 2](../25/02.md)'
    - Different chapter: 'see how 3:3' -> 'See how you translated the similar expression in [3:3](../03/03.md)'
    - Different book: 'see how exo 2:2' -> 'See how you translated the similar expression in [Exodus 2:2](../../exo/02/02.md)'    
    
    Args:
        ref_match: The reference part after 'see how ' (e.g., '2', '3:3', 'exo 2:2')
        item: The current item data containing Book and Ref fields for context
        
    Returns:
        Formatted note text
    """
    # Get current book and chapter from item data
    current_book = 'jos'  # Default fallback
    current_chapter = '2'  # Default fallback
    
    if item:
        book_field = item.get('Book', '').strip().lower()
        ref_field = item.get('Ref', '').strip()
        
        # Get book code from Book field
        if book_field:
            current_book = book_field
            
        # Get chapter from Ref field (format like "25:3")
        if ref_field and ':' in ref_field:
            current_chapter = ref_field.split(':')[0]
    # Handle "verse N" pattern (e.g., "verse 4" means verse 4 in current chapter)
    if ref_match.lower().startswith('verse '):
        verse = ref_match[6:].strip()  # Remove "verse " prefix
        # Use 3-digit padding for Psalms, 2-digit for others
        if current_book.lower() == 'psa':
            chapter_padded = f"{int(current_chapter):03d}"
            verse_padded = f"{int(verse):02d}"
        else:
            chapter_padded = f"{int(current_chapter):02d}"
            verse_padded = f"{int(verse):02d}"
        return f"See how you translated the similar expression in [verse {verse}](../{chapter_padded}/{verse_padded}.md)."
    
    # Check if it's a different book (contains letters)
    elif any(c.isalpha() for c in ref_match):
        # Different book format: 'exo 2:2' or 'exodus 2:2'
        parts = ref_match.split()
        if len(parts) >= 2:
            book_input = parts[0]
            chapter_verse = ' '.join(parts[1:])
            book_code, book_name = _get_book_info(book_input)
            if ':' in chapter_verse:
                try:
                    chapter, verses = parse_verse_reference(chapter_verse)
                    # Use the first verse for the link (in case of ranges)
                    first_verse = verses[0]
                    # Use 3-digit padding for Psalms, 2-digit for others
                    if book_code.lower() == 'psa':
                        chapter_padded = f"{chapter:03d}"
                        verse_padded = f"{first_verse:02d}"
                    else:
                        chapter_padded = f"{chapter:02d}"
                        verse_padded = f"{first_verse:02d}"
                    return f"See how you translated the similar expression in [{book_name} {chapter_verse}](../../{book_code}/{chapter_padded}/{verse_padded}.md)."
                except ValueError:
                    # Fall back to original behavior if parsing fails
                    chapter, verse = chapter_verse.split(':', 1)
                    if book_code.lower() == 'psa':
                        chapter_padded = f"{int(chapter):03d}"
                        verse_padded = f"{int(verse):02d}"
                    else:
                        chapter_padded = f"{int(chapter):02d}"
                        verse_padded = f"{int(verse):02d}"
                    return f"See how you translated the similar expression in [{book_name} {chapter}:{verse}](../../{book_code}/{chapter_padded}/{verse_padded}.md)."
            else:
                # Just chapter reference in different book
                if book_code.lower() == 'psa':
                    chapter_padded = f"{int(chapter_verse):03d}"
                else:
                    chapter_padded = f"{int(chapter_verse):02d}"
                return f"See how you translated the similar expression in [{book_name} {chapter_verse}](../../{book_code}/{chapter_padded}/{chapter_padded}.md)."
        else:
            return f"See how you translated the similar expression in {ref_match}."
    
    elif ':' in ref_match:
        # Different chapter in same book: '3:3' or '3:3-5'
        try:
            chapter, verses = parse_verse_reference(ref_match)
            # Use the first verse for the link (in case of ranges)
            first_verse = verses[0]
            # Use 3-digit padding for Psalms, 2-digit for others
            if current_book.lower() == 'psa':
                chapter_padded = f"{chapter:03d}"
                verse_padded = f"{first_verse:02d}"
            else:
                chapter_padded = f"{chapter:02d}"
                verse_padded = f"{first_verse:02d}"
            return f"See how you translated the similar expression in [{ref_match}](../{chapter_padded}/{verse_padded}.md)."
        except ValueError:
            # Fall back to original behavior if parsing fails
            chapter, verse = ref_match.split(':', 1)
            if current_book.lower() == 'psa':
                chapter_padded = f"{int(chapter):03d}"
                verse_padded = f"{int(verse):02d}"
            else:
                chapter_padded = f"{int(chapter):02d}"
                verse_padded = f"{int(verse):02d}"
            return f"See how you translated the similar expression in [{chapter}:{verse}](../{chapter_padded}/{verse_padded}.md)."
    
    else:
        # Same chapter: '2'
        verse = ref_match
        # Use 3-digit padding for Psalms, 2-digit for others
        if current_book.lower() == 'psa':
            chapter_padded = f"{int(current_chapter):03d}"
            verse_padded = f"{int(verse):02d}"
        else:
            chapter_padded = f"{int(current_chapter):02d}"
            verse_padded = f"{int(verse):02d}"
        return f"See how you translated the similar expression in [verse {verse}](../{chapter_padded}/{verse_padded}.md)."


def _get_book_info(book_input: str) -> tuple[str, str]:
    """Get book code and name from either a book code or full name.
    
    Args:
        book_input: Either a book code (e.g., 'exo') or full name (e.g., 'exodus')
        
    Returns:
        Tuple of (book_code, book_name)
    """
    book_mappings = {
        'gen': 'Genesis', 'genesis': ('gen', 'Genesis'),
        'exo': 'Exodus', 'exodus': ('exo', 'Exodus'),
        'lev': 'Leviticus', 'leviticus': ('lev', 'Leviticus'),
        'num': 'Numbers', 'numbers': ('num', 'Numbers'),
        'deu': 'Deuteronomy', 'deuteronomy': ('deu', 'Deuteronomy'),
        'jos': 'Joshua', 'joshua': ('jos', 'Joshua'),
        'jdg': 'Judges', 'judges': ('jdg', 'Judges'),
        'rut': 'Ruth', 'ruth': ('rut', 'Ruth'),
        '1sa': '1 Samuel', '1 samuel': ('1sa', '1 Samuel'),
        '2sa': '2 Samuel', '2 samuel': ('2sa', '2 Samuel'),
        '1ki': '1 Kings', '1 kings': ('1ki', '1 Kings'),
        '2ki': '2 Kings', '2 kings': ('2ki', '2 Kings'),
        '1ch': '1 Chronicles', '1 chronicles': ('1ch', '1 Chronicles'),
        '2ch': '2 Chronicles', '2 chronicles': ('2ch', '2 Chronicles'),
        'ezr': 'Ezra', 'ezra': ('ezr', 'Ezra'),
        'neh': 'Nehemiah', 'nehemiah': ('neh', 'Nehemiah'),
        'est': 'Esther', 'esther': ('est', 'Esther'),
        'job': 'Job', 'job': ('job', 'Job'),
        'psa': 'Psalms', 'psalms': ('psa', 'Psalms'), 'psalm': ('psa', 'Psalms'),
        'pro': 'Proverbs', 'proverbs': ('pro', 'Proverbs'),
        'ecc': 'Ecclesiastes', 'ecclesiastes': ('ecc', 'Ecclesiastes'),
        'sng': 'Song of Songs', 'song of songs': ('sng', 'Song of Songs'),
        'isa': 'Isaiah', 'isaiah': ('isa', 'Isaiah'),
        'jer': 'Jeremiah', 'jeremiah': ('jer', 'Jeremiah'),
        'lam': 'Lamentations', 'lamentations': ('lam', 'Lamentations'),
        'ezk': 'Ezekiel', 'ezekiel': ('ezk', 'Ezekiel'),
        'dan': 'Daniel', 'daniel': ('dan', 'Daniel'),
        'hos': 'Hosea', 'hosea': ('hos', 'Hosea'),
        'jol': 'Joel', 'joel': ('jol', 'Joel'),
        'amo': 'Amos', 'amos': ('amo', 'Amos'),
        'oba': 'Obadiah', 'obadiah': ('oba', 'Obadiah'),
        'jon': 'Jonah', 'jonah': ('jon', 'Jonah'),
        'mic': 'Micah', 'micah': ('mic', 'Micah'),
        'nam': 'Nahum', 'nahum': ('nam', 'Nahum'),
        'hab': 'Habakkuk', 'habakkuk': ('hab', 'Habakkuk'),
        'zep': 'Zephaniah', 'zephaniah': ('zep', 'Zephaniah'),
        'hag': 'Haggai', 'haggai': ('hag', 'Haggai'),
        'zec': 'Zechariah', 'zechariah': ('zec', 'Zechariah'),
        'mal': 'Malachi', 'malachi': ('mal', 'Malachi'),
        'mat': 'Matthew', 'matthew': ('mat', 'Matthew'),
        'mrk': 'Mark', 'mark': ('mrk', 'Mark'),
        'luk': 'Luke', 'luke': ('luk', 'Luke'),
        'jhn': 'John', 'john': ('jhn', 'John'),
        'act': 'Acts', 'acts': ('act', 'Acts'),
        'rom': 'Romans', 'romans': ('rom', 'Romans'),
        '1co': '1 Corinthians', '1 corinthians': ('1co', '1 Corinthians'),
        '2co': '2 Corinthians', '2 corinthians': ('2co', '2 Corinthians'),
        'gal': 'Galatians', 'galatians': ('gal', 'Galatians'),
        'eph': 'Ephesians', 'ephesians': ('eph', 'Ephesians'),
        'php': 'Philippians', 'philippians': ('php', 'Philippians'),
        'col': 'Colossians', 'colossians': ('col', 'Colossians'),
        '1th': '1 Thessalonians', '1 thessalonians': ('1th', '1 Thessalonians'),
        '2th': '2 Thessalonians', '2 thessalonians': ('2th', '2 Thessalonians'),
        '1ti': '1 Timothy', '1 timothy': ('1ti', '1 Timothy'),
        '2ti': '2 Timothy', '2 timothy': ('2ti', '2 Timothy'),
        'tit': 'Titus', 'titus': ('tit', 'Titus'),
        'phm': 'Philemon', 'philemon': ('phm', 'Philemon'),
        'heb': 'Hebrews', 'hebrews': ('heb', 'Hebrews'),
        'jas': 'James', 'james': ('jas', 'James'),
        '1pe': '1 Peter', '1 peter': ('1pe', '1 Peter'),
        '2pe': '2 Peter', '2 peter': ('2pe', '2 Peter'),
        '1jn': '1 John', '1 john': ('1jn', '1 John'),
        '2jn': '2 John', '2 john': ('2jn', '2 John'),
        '3jn': '3 John', '3 john': ('3jn', '3 John'),
        'jud': 'Jude', 'jude': ('jud', 'Jude'),
        'rev': 'Revelation', 'revelation': ('rev', 'Revelation')
    }
    
    book_input_lower = book_input.lower()
    
    # Check if it's a full name first (returns tuple)
    if book_input_lower in book_mappings and isinstance(book_mappings[book_input_lower], tuple):
        return book_mappings[book_input_lower]
    
    # Check if it's a book code (returns string, we need to make tuple)
    if book_input_lower in book_mappings and isinstance(book_mappings[book_input_lower], str):
        return (book_input_lower, book_mappings[book_input_lower])
    
    # Default fallback
    return (book_input.lower(), book_input.capitalize())


def _get_book_name(book_code: str) -> str:
    """Get the full book name from a book code (legacy function for compatibility).
    
    Args:
        book_code: Three-letter book code (e.g., 'exo', 'jos')
        
    Returns:
        Full book name (e.g., 'Exodus', 'Joshua')
    """
    _, book_name = _get_book_info(book_code)
    return book_name


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
                ref_match = explanation.replace('see how ', '').strip()
                note = _format_see_how_reference(ref_match, original_item)
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
    If not, it fetches the data concurrently and caches it for future use.
    
    Args:
        user: Username
        book: Book code
        cache_manager: Cache manager instance
        sheet_manager: Sheet manager instance
        config: Configuration manager instance
        logger: Optional logger instance
    """
    import threading
    import concurrent.futures
    
    if logger is None:
        logger = logging.getLogger(__name__)
    
    def _check_and_fetch_text_type(text_type: str):
        """Check cache and fetch biblical text for a specific type."""
        try:
            cached_data = cache_manager.get_biblical_text_for_user(text_type, user, book)
            
            # Check for cache corruption by looking for suspicious verse gaps
            # Note: UST/ULT may legitimately combine verses (e.g., "41-42"), so check for combined verse patterns
            cache_corrupted = False
            if cached_data:
                chapters = cached_data.get('chapters', [])
                for ch in chapters:
                    verses = ch.get('verses', [])
                    verse_nums = [v.get('number') for v in verses]
                    
                    # Look for gaps in verse numbering
                    for i in range(len(verse_nums)-1):
                        current_verse = verse_nums[i]
                        next_verse = verse_nums[i+1]
                        gap_size = next_verse - current_verse
                        
                        # If there's a gap of 2+ verses, check if it's a combined verse situation
                        if gap_size > 1:
                            # Check if any verse content contains combined verse notation (e.g., "41-42")
                            combined_verse_found = False
                            for v in verses:
                                content = v.get('content', '')
                                # Look for patterns like "41-42" in content or verse numbering
                                if f"{current_verse}-{next_verse-1}" in str(v.get('number', '')) or \
                                   f"\\v {current_verse}-{next_verse-1}" in content:
                                    combined_verse_found = True
                                    break
                            
                            # If no combined verse pattern found, this might be corruption
                            if not combined_verse_found and gap_size > 2:  # Only flag gaps > 2 verses as suspicious
                                logger.warning(f"Potential cache corruption: Large verse gap in {text_type} {user}/{book} chapter {ch.get('chapter')}: verses {current_verse} -> {next_verse}")
                                # Don't mark as corrupted yet - this might be legitimate
            
            if not cached_data or cache_corrupted:
                if cache_corrupted:
                    logger.info(f"{text_type} cache for {user}/{book} is corrupted, re-fetching...")
                else:
                    logger.info(f"No {text_type} cache found for {user}/{book}, fetching...")
                
                # Fetch biblical text for the specific book
                biblical_data = sheet_manager.fetch_biblical_text(text_type, book_code=book, user=user)
                if biblical_data:
                    # We trust fetch_biblical_text to return data for the correct book or log errors
                    cache_manager.set_biblical_text_for_user(text_type, user, book, biblical_data)
                    logger.info(f"Cached {text_type} for {user}/{book}")
                    return True
                else:
                    logger.warning(f"Failed to fetch {text_type} for {user}/{book} to cache it.")
                    return False
            else:
                logger.debug(f"{text_type} for {user}/{book} already cached")
                return True
                
        except Exception as e:
            logger.error(f"Error processing {text_type} for {user}/{book}: {e}")
            return False
    
    # Use ThreadPoolExecutor to fetch ULT and UST concurrently
    logger.debug(f"Checking biblical text cache for {user}/{book} (threaded)")
    start_time = datetime.now()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix=f"BiblicalText-{user}-{book}") as executor:
        # Submit both ULT and UST fetching tasks
        future_ult = executor.submit(_check_and_fetch_text_type, 'ULT')
        future_ust = executor.submit(_check_and_fetch_text_type, 'UST')
        
        # Wait for both to complete
        results = {
            'ULT': future_ult.result(),
            'UST': future_ust.result()
        }
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    # Log results
    success_count = sum(1 for success in results.values() if success)
    logger.info(f"Biblical text caching for {user}/{book} completed in {duration:.2f}s: {success_count}/2 successful ({', '.join(text_type for text_type, success in results.items() if success)})")
    
    if success_count == 0:
        logger.warning(f"Failed to cache any biblical text for {user}/{book}")
    elif success_count == 1:
        logger.warning(f"Only partial biblical text cached for {user}/{book}")
    else:
        logger.debug(f"All biblical text successfully cached for {user}/{book}")