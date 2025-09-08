"""
Text processing utilities for Translation Notes AI
Handles text formatting, cleaning, and transformation operations.
"""

import re
from typing import Optional, List


def post_process_text(text: str) -> str:
    """Post-process text by removing curly braces and converting straight quotes to smart quotes.
    
    This function is optimized and more robust than the original version in main.py.
    
    Args:
        text: Input text to process
        
    Returns:
        Processed text with curly braces removed and smart quotes
    """
    if not text or not isinstance(text, str):
        return text or ""
    
    # Remove all curly braces
    processed = text.replace('{', '').replace('}', '')
    
    # Convert straight quotes to smart quotes using a more efficient approach
    result = _convert_quotes_to_smart(processed)
    
    return result


def _convert_quotes_to_smart(text: str) -> str:
    """Convert straight quotes to smart quotes efficiently.
    
    Args:
        text: Input text with straight quotes
        
    Returns:
        Text with smart quotes
    """
    if not text:
        return text
    
    result = []
    in_double_quotes = False
    
    for i, char in enumerate(text):
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
            # Handle single quotes/apostrophes with better context detection
            if i > 0 and text[i-1].isalnum():
                # Likely an apostrophe (preceded by alphanumeric)
                result.append('\u2019')  # RIGHT SINGLE QUOTATION MARK (apostrophe)
            elif i < len(text) - 1 and text[i+1].isalnum():
                # Likely opening single quote (followed by alphanumeric)
                result.append('\u2018')  # LEFT SINGLE QUOTATION MARK
            else:
                # Check for common contractions
                if _is_contraction_apostrophe(text, i):
                    result.append('\u2019')  # RIGHT SINGLE QUOTATION MARK (apostrophe)
                else:
                    # Default to closing single quote
                    result.append('\u2019')  # RIGHT SINGLE QUOTATION MARK
        else:
            result.append(char)
    
    return ''.join(result)


def _is_contraction_apostrophe(text: str, pos: int) -> bool:
    """Check if an apostrophe at given position is part of a contraction.
    
    Args:
        text: Full text string
        pos: Position of the apostrophe
        
    Returns:
        True if it's likely a contraction apostrophe
    """
    if pos <= 0 or pos >= len(text) - 1:
        return False
    
    # Common contraction patterns
    before = text[max(0, pos-3):pos].lower()
    after = text[pos+1:pos+3].lower()
    
    # Common contractions: don't, can't, won't, it's, etc.
    contraction_patterns = [
        ('n', 't'),      # don't, can't, won't
        ('t', 's'),      # it's, that's
        ('l', 'l'),      # we'll, I'll
        ('v', 'e'),      # I've, we've
        ('r', 'e'),      # you're, they're
        ('d', ' '),      # I'd, he'd (followed by space)
        ('s', ' '),      # let's (followed by space)
    ]
    
    for before_char, after_char in contraction_patterns:
        if before.endswith(before_char) and after.startswith(after_char):
            return True
    
    return False


def clean_sheet_value(value: str) -> str:
    """Clean and normalize values from Google Sheets.
    
    Args:
        value: Raw value from sheet
        
    Returns:
        Cleaned value
    """
    if not value or not isinstance(value, str):
        return ""
    
    # Strip whitespace
    cleaned = value.strip()
    
    # Remove extra whitespace (multiple spaces, tabs, newlines)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    # Remove non-printable characters except common ones
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', cleaned)
    
    return cleaned


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text to a maximum length with an optional suffix.
    
    Args:
        text: Text to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to add if text is truncated
        
    Returns:
        Truncated text
    """
    if not text or len(text) <= max_length:
        return text
    
    if len(suffix) >= max_length:
        return text[:max_length]
    
    return text[:max_length - len(suffix)] + suffix


def normalize_biblical_reference(reference: str) -> str:
    """Normalize biblical reference formatting.
    
    Args:
        reference: Biblical reference string
        
    Returns:
        Normalized reference
    """
    if not reference or not isinstance(reference, str):
        return ""
    
    # Basic normalization
    normalized = reference.strip()
    
    # Standardize spacing around colons and hyphens
    normalized = re.sub(r'\s*:\s*', ':', normalized)
    normalized = re.sub(r'\s*-\s*', '-', normalized)
    
    # Standardize book name formatting (title case)
    parts = normalized.split()
    if parts:
        # Handle numbered books (1 Cor, 2 Tim, etc.)
        if parts[0].isdigit():
            if len(parts) > 1:
                parts[1] = parts[1].title()
        else:
            parts[0] = parts[0].title()
        
        normalized = ' '.join(parts)
    
    return normalized


def extract_biblical_references(text: str) -> list[str]:
    """Extract biblical references from text.
    
    Args:
        text: Text that may contain biblical references
        
    Returns:
        List of found biblical references
    """
    if not text:
        return []
    
    # Pattern for biblical references
    # Matches: "Gen 1:1", "1 Cor 2:3-5", "Psalm 23:1-6", etc.
    pattern = r'\b(?:1|2|3)?\s*[A-Za-z]+\s*\d+:\d+(?:-\d+)?(?:,\s*\d+:\d+(?:-\d+)?)*\b'
    
    matches = re.findall(pattern, text)
    
    # Normalize and deduplicate
    references = []
    for match in matches:
        normalized = normalize_biblical_reference(match)
        if normalized and normalized not in references:
            references.append(normalized)
    
    return references


def mask_sensitive_content(text: str) -> str:
    """Mask potentially sensitive content in text for logging/display.
    
    Args:
        text: Text that may contain sensitive information
        
    Returns:
        Text with sensitive content masked
    """
    if not text:
        return text
    
    masked = text
    
    # Mask email addresses
    masked = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', masked)
    
    # Mask potential API keys (long alphanumeric strings)
    masked = re.sub(r'\b[A-Za-z0-9]{32,}\b', '[API_KEY]', masked)
    
    # Mask potential passwords (password= patterns)
    masked = re.sub(r'(password\s*[=:]\s*)[^\s]+', r'\1[REDACTED]', masked, flags=re.IGNORECASE)

    return masked


def find_matches(text: str, words: List[str]) -> List[str]:
    """Find exact word matches from a list within the given text."""
    if not text or not words:
        return []

    text_lower = text.lower()
    matches = []

    for word in words:
        if not word:
            continue
        pattern = r'\b{}\b'.format(re.escape(word.lower()))
        if re.search(pattern, text_lower):
            matches.append(word)

    return matches
