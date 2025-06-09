"""
Sheet Manager
Handles all Google Sheets interactions including reading data and updating results.
"""

import logging
import time
from typing import Dict, List, Any, Optional
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from googleapiclient.errors import HttpError

from .config_manager import ConfigManager

# Custom exception for permission errors
class SheetPermissionError(Exception):
    """Custom exception for sheet permission errors."""
    pass

class SheetManager:
    """Manages Google Sheets operations."""
    
    def __init__(self, config: ConfigManager):
        """Initialize the sheet manager.
        
        Args:
            config: Configuration manager
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Get Google Sheets configuration
        self.sheets_config = config.get_google_sheets_config()
        
        # Initialize Google Sheets service
        self.service = self._initialize_sheets_service()
        
        self.logger.info("Sheet manager initialized")
    
    def _initialize_sheets_service(self):
        """Initialize Google Sheets service.
        
        Returns:
            Google Sheets service object
        """
        try:
            credentials_file = self.sheets_config['credentials_file']
            
            # Define the scope
            scopes = ['https://www.googleapis.com/auth/spreadsheets']
            
            # Load credentials
            credentials = Credentials.from_service_account_file(
                credentials_file, scopes=scopes
            )
            
            # Build the service
            service = build('sheets', 'v4', credentials=credentials)
            
            self.logger.info("Google Sheets service initialized successfully")
            return service
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Google Sheets service: {e}")
            raise
    
    def get_pending_work(self, sheet_id: str, max_items: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get pending work items from a sheet.
        
        Args:
            sheet_id: Google Sheets ID
            max_items: Maximum number of items to return (None for no limit)
            
        Returns:
            List of pending work items
        """
        try:
            # Get the main sheet data
            sheet_name = self.sheets_config['main_tab_name']
            escaped_sheet_name = self._escape_sheet_name(sheet_name)
            range_name = f"{escaped_sheet_name}!A:Z"  # Get all columns
            
            result = self.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            if not values:
                self.logger.debug(f"No data found in sheet {sheet_id}")
                return []
            
            # Parse the data
            headers = values[0] if values else []
            pending_items = []
            
            processing_config = self.config.get_processing_config()
            process_go_values = processing_config['process_go_values']
            skip_go_values = processing_config.get('skip_go_values', ['AI'])
            skip_ai_completed = processing_config['skip_ai_completed']
            
            for i, row in enumerate(values[1:], start=2):  # Start from row 2 (skip header)
                try:
                    # Create item dictionary
                    item = {}
                    for j, header in enumerate(headers):
                        if j < len(row):
                            item[header] = row[j]
                        else:
                            item[header] = ''
                    
                    # Add row number for updates
                    item['row'] = i
                    
                    # Check if this item should be processed
                    go_value = item.get('Go?', '').strip()
                    
                    # Skip empty Go? values
                    if not go_value:
                        continue
                    
                    # Skip if in skip list (case-insensitive)
                    if go_value.upper() in [v.upper() for v in skip_go_values]:
                        continue
                    
                    # Legacy check for AI completed
                    if skip_ai_completed and go_value.upper() == 'AI':
                        continue
                    
                    # Check if it should be processed
                    should_process = False
                    if '*' in process_go_values:
                        # Process any non-empty value that's not in skip list
                        should_process = True
                    else:
                        # Process only specific values
                        should_process = go_value.upper() in [v.upper() for v in process_go_values]
                    
                    if should_process:
                        # Validate required fields
                        if self._validate_item(item):
                            pending_items.append(item)
                            
                            # Check if we've reached the max items limit
                            if max_items and len(pending_items) >= max_items:
                                self.logger.debug(f"Reached max items limit ({max_items}) for sheet {sheet_id}")
                                break
                        else:
                            self.logger.warning(f"Invalid item in row {i}: missing required fields")
                
                except Exception as e:
                    self.logger.error(f"Error processing row {i}: {e}")
            
            total_found = len(pending_items)
            if max_items and total_found >= max_items:
                self.logger.debug(f"Limited to first {total_found} of available pending items in sheet {sheet_id}")
            else:
                self.logger.debug(f"Found {total_found} pending items in sheet {sheet_id}")
            return pending_items
            
        except HttpError as e:
            if e.resp.status == 403:
                self.logger.error(f"Permission denied getting pending work from sheet {sheet_id}: {e}")
                raise SheetPermissionError(f"Permission denied for sheet {sheet_id} while getting pending work.") from e
            else:
                self.logger.error(f"HTTP error getting pending work from sheet {sheet_id}: {e}")
                return [] # For other HTTP errors, return empty list
        except Exception as e:
            self.logger.error(f"Error getting pending work from sheet {sheet_id}: {e}")
            return []
    
    def _validate_item(self, item: Dict[str, Any]) -> bool:
        """Validate that an item has required fields.
        
        Args:
            item: Item to validate
            
        Returns:
            True if item is valid
        """
        required_fields = ['Ref']  # Only require Ref field, GLQuote can be empty
        
        for field in required_fields:
            if not item.get(field, '').strip():
                return False
        
        return True
    
    def batch_update_rows(self, sheet_id: str, updates: List[Dict[str, Any]], completion_callback=None):
        """Batch update multiple rows in a sheet.
        
        Args:
            sheet_id: Google Sheets ID
            updates: List of update dictionaries
            completion_callback: Optional callback function to call after successful update.
                                Should accept (count: int, context: str) parameters.
        """
        if not updates:
            return
        
        try:
            sheet_name = self.sheets_config['main_tab_name']
            
            # Define allowed columns and their letters
            allowed_columns = {
                'SRef': 'D',      # Column D
                'Go?': 'F',       # Column F  
                'AI TN': 'I'      # Column I
            }
            
            # Prepare batch update data for only allowed columns
            data = []
            
            for update in updates:
                row_number = update['row_number']
                
                # NEVER modify row 1 (header row)
                if row_number <= 1:
                    self.logger.warning(f"Skipping update for row {row_number} - header row should never be modified")
                    continue
                    
                update_values = update['updates']
                
                # Only process updates for allowed columns
                for column_name, value in update_values.items():
                    if column_name in allowed_columns:
                        column_letter = allowed_columns[column_name]
                        
                        # Create individual cell update for each allowed column
                        escaped_sheet_name = self._escape_sheet_name(sheet_name)
                        range_name = f"{escaped_sheet_name}!{column_letter}{row_number}"
                        
                        data.append({
                            'range': range_name,
                            'values': [[value]]
                        })
                        
                        self.logger.debug(f"Preparing update for row {row_number}, column {column_name} ({column_letter}): {value[:50] if isinstance(value, str) else value}")
                    else:
                        self.logger.warning(f"Skipping update for unauthorized column: {column_name}")
            
            # Execute batch update for allowed columns only
            if data:
                body = {
                    'valueInputOption': 'RAW',
                    'data': data
                }
                
                try:
                    self.logger.debug(f"Attempting to batch update sheet {sheet_id} with body: {body}")
                    self.service.spreadsheets().values().batchUpdate(
                        spreadsheetId=sheet_id,
                        body=body
                    ).execute()
                except Exception as e:
                    import traceback
                    self.logger.error(f"Full traceback of sheet update error: {traceback.format_exc()}")
                    self.logger.error(f"Error batch updating rows in sheet {sheet_id}: {e}")
                    raise

                self.logger.info(f"Successfully updated {len(data)} cells in {len(updates)} rows (only allowed columns: D, F, I)")
                
                # Call completion callback if provided
                if completion_callback:
                    # Count how many AI TN updates were made (these are the main AI results)
                    ai_tn_count = sum(1 for update in updates if 'AI TN' in update.get('updates', {}))
                    if ai_tn_count > 0:
                        completion_callback(ai_tn_count, "AI translation notes")
            else:
                self.logger.warning("No valid updates for allowed columns")
            
        except Exception as e:
            self.logger.error(f"Error preparing batch update for sheet {sheet_id}: {e}")
            raise
    
    def _get_headers_once(self, sheet_id: str, sheet_name: str) -> List[str]:
        """Get headers for a sheet in a single API call and cache them.
        
        Args:
            sheet_id: Google Sheets ID
            sheet_name: Sheet name
            
        Returns:
            List of header names
        """
        try:
            # Cache key for headers
            cache_key = f"headers_{sheet_id}_{sheet_name}"
            
            # Check if we have cached headers (simple in-memory cache)
            if not hasattr(self, '_headers_cache'):
                self._headers_cache = {}
            
            if cache_key in self._headers_cache:
                return self._headers_cache[cache_key]
            
            # Get header row
            escaped_sheet_name = self._escape_sheet_name(sheet_name)
            range_name = f"{escaped_sheet_name}!1:1"
            
            result = self.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            
            headers = result.get('values', [[]])[0]
            
            # Cache the headers
            self._headers_cache[cache_key] = headers
            
            return headers
            
        except Exception as e:
            self.logger.error(f"Error getting headers: {e}")
            return []
    
    def _get_row_data(self, sheet_id: str, sheet_name: str, row_number: int) -> List[str]:
        """Get current data for a specific row.
        
        Args:
            sheet_id: Google Sheets ID
            sheet_name: Sheet name
            row_number: Row number (1-indexed)
            
        Returns:
            List of cell values for the row
        """
        try:
            escaped_sheet_name = self._escape_sheet_name(sheet_name)
            range_name = f"{escaped_sheet_name}!A{row_number}:Z{row_number}"
            
            result = self.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            return values[0] if values else []
            
        except Exception as e:
            self.logger.error(f"Error getting row data: {e}")
            return []
    
    def _get_column_index(self, sheet_id: str, sheet_name: str, column_name: str) -> Optional[int]:
        """Get the index of a column by name.
        
        Args:
            sheet_id: Google Sheets ID
            sheet_name: Sheet name
            column_name: Column name to find
            
        Returns:
            Column index (0-based) or None if not found
        """
        try:
            # Get header row
            escaped_sheet_name = self._escape_sheet_name(sheet_name)
            range_name = f"{escaped_sheet_name}!1:1"
            
            result = self.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            
            headers = result.get('values', [[]])[0]
            
            try:
                return headers.index(column_name)
            except ValueError:
                self.logger.warning(f"Column '{column_name}' not found in sheet")
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting column index: {e}")
            return None
    
    def _column_letter(self, column_index: int) -> str:
        """Convert column index to letter (A, B, C, ..., AA, AB, etc.).
        
        Args:
            column_index: Column index (0-based)
            
        Returns:
            Column letter
        """
        result = ""
        while column_index >= 0:
            result = chr(column_index % 26 + ord('A')) + result
            column_index = column_index // 26 - 1
        return result
    
    def _escape_sheet_name(self, sheet_name: str) -> str:
        """Escape sheet name for use in range notation.
        
        Args:
            sheet_name: Raw sheet name
            
        Returns:
            Properly escaped sheet name
        """
        # If the sheet name contains spaces or special characters, wrap it in single quotes
        if any(char in sheet_name for char in [' ', "'", '"', '-', '!', '(', ')', '[', ']']):
            # Escape any single quotes in the name by doubling them
            escaped_name = sheet_name.replace("'", "''")
            return f"'{escaped_name}'"
        return sheet_name

    def fetch_biblical_text(self, text_type: str, book_code: str, user: str = None) -> Optional[Dict[str, Any]]:
        """Fetch biblical text for a specific book.
        
        Args:
            text_type: 'ULT' or 'UST'
            book_code: The 3-letter book code (e.g., 'GEN', 'NUM')
            user: Username to fetch from user's specific sheet (optional)
            
        Returns:
            Biblical text data or None
        """
        try:
            # Attempt to fetch from specific sheet tabs first
            data = self._fetch_from_sheet_tabs(text_type, book_code, user=user)
            if data:
                return data
            
            # If not found or tabs not configured, try scraping Door43
            self.logger.info(f"Biblical text for {book_code} not found in sheet tabs, trying Door43 scraping for {text_type}")
            data = self._fetch_from_door43(text_type, book_code)
            if data:
                return data

            # If still not found, use fallback (which is currently DEU, not ideal but better than error)
            self.logger.warning(f"Could not fetch {text_type} for {book_code} from any source, using fallback.")
            return self._get_fallback_biblical_text(text_type) # Fallback doesn't know book

        except Exception as e:
            self.logger.error(f"Error fetching biblical text for {book_code} ({text_type}): {e}")
            return None

    def _fetch_from_sheet_tabs(self, text_type: str, book_code: str, user: str = None) -> Optional[Dict[str, Any]]:
        """Fetch biblical text from specific sheet tabs for ULT or UST.
        
        Args:
            text_type: 'ULT' or 'UST'
            book_code: The 3-letter book code
            user: Username to fetch from user's specific sheet (optional)
            
        Returns:
            Biblical text data or None
        """
        # If user is provided, use their specific sheet
        if user:
            sheet_id = self.sheets_config.get('sheet_ids', {}).get(user)
            if not sheet_id:
                self.logger.info(f"No sheet ID configured for user '{user}'. Cannot fetch from sheet tabs.")
                return None
            # Use the configured tab name from config, or default to just the text type
            tab_name = self.sheets_config.get(f'{text_type.lower()}_sheet_name', text_type)
            self.logger.info(f"DEBUG: User-specific fetch - user='{user}' -> sheet_id='{sheet_id}', looking for tab='{tab_name}'")
        else:
            # Legacy: try to find a global ULT/UST sheet (this path shouldn't be used anymore)
            if text_type == 'ULT':
                sheet_key = 'ult_sheet'
                default_tab_name = 'ULT'
            elif text_type == 'UST':
                sheet_key = 'ust_sheet'
                default_tab_name = 'UST'
            else:
                self.logger.error(f"Invalid text_type for fetching biblical text: {text_type}")
                return None

            sheet_id = self.sheets_config.get(sheet_key)
            tab_name = self.sheets_config.get(f'{text_type.lower()}_tab_name', default_tab_name)
            self.logger.warning(f"DEBUG: Legacy fetch (shouldn't happen) - sheet_key='{sheet_key}', sheet_id='{sheet_id}', tab_name='{tab_name}'")

        self.logger.info(f"DEBUG: Fetching {text_type} for {book_code} from user='{user}', sheet_id='{sheet_id}', tab='{tab_name}'")

        if not sheet_id:
            if user:
                self.logger.info(f"No sheet ID configured for user '{user}'. Cannot fetch from sheet tabs.")
            else:
                self.logger.info(f"{text_type} sheet ID not configured. Cannot fetch from sheet tabs.")
            return None
            
        self.logger.info(f"Fetching {text_type} for {book_code} from sheet: {sheet_id}, tab: {tab_name}")
        
        try:
            escaped_tab_name = self._escape_sheet_name(tab_name)
            range_name = f"{escaped_tab_name}!A:Z"  # Assuming text is in columns A-Z
            
            self.logger.info(f"DEBUG: Using range: {range_name}")
            
            result = self.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            self.logger.info(f"DEBUG: Retrieved {len(values)} rows from {text_type} tab")
            
            if not values:
                self.logger.warning(f"No data found in {text_type} tab '{tab_name}' for book {book_code}")
                return None
            
            # Show first few rows for debugging
            if len(values) > 0:
                self.logger.info(f"DEBUG: First row (headers): {values[0]}")
            if len(values) > 1:
                self.logger.info(f"DEBUG: Second row (sample data): {values[1]}")
            
            # Validate if this data looks like biblical text
            if not self._validate_biblical_text_data(values):
                self.logger.warning(f"Data in {text_type} tab '{tab_name}' does not look like valid biblical text for {book_code}")
                return None

            parsed_data = self._parse_sheet_biblical_text(values, text_type, book_code)
            
            # Ensure the parsed data matches the requested book
            if parsed_data and parsed_data.get('book') == book_code:
                self.logger.info(f"Successfully parsed {text_type} for {book_code} from sheet tab.")
                return parsed_data
            else:
                self.logger.warning(f"Parsed data from sheet tab is for book {parsed_data.get('book')}, expected {book_code}. Discarding.")
                #This can happen if the sheet has the wrong book, or _parse_sheet_biblical_text is wrong.
                return None

        except HttpError as e:
            if e.resp.status == 403:
                self.logger.error(f"Permission denied accessing {text_type} sheet: {sheet_id} for book {book_code}. Check sheet permissions.")
                raise SheetPermissionError(f"Permission denied for {text_type} sheet {sheet_id} (book {book_code})") from e
            elif e.resp.status == 400 and 'Unable to parse range' in str(e):
                 self.logger.error(f"Error fetching {text_type} for {book_code}: Tab '{tab_name}' not found in sheet {sheet_id}. Error: {e}")
                 # This is not necessarily a permission error, so don't raise SheetPermissionError
            else:
                self.logger.error(f"Error fetching {text_type} for {book_code} from sheet: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error fetching {text_type} for {book_code} from sheet: {e}")
            return None
    
    def _validate_biblical_text_data(self, values: List[List[str]]) -> bool:
        """Validate if the raw sheet data looks like biblical text.
        This is a basic check based on structure (e.g., chapter/verse markers).
        
        Args:
            values: Sheet values
            
        Returns:
            True if data looks like biblical text
        """
        try:
            # Skip header row
            data_rows = values[1:] if len(values) > 1 else []
            
            if len(data_rows) < 5:  # Need at least a few verses
                return False
            
            # Check if rows have verse-like content
            verse_count = 0
            for row in data_rows[:10]:  # Check first 10 rows
                if len(row) >= 1:
                    content = ' '.join(row).strip()
                    # Look for verse-like content (reasonable length, contains words)
                    if len(content) > 10 and len(content.split()) > 3:
                        verse_count += 1
            
            # If at least half the rows look like verses
            return verse_count >= len(data_rows[:10]) // 2
            
        except Exception:
            return False
    
    def _parse_sheet_biblical_text(self, values: List[List[str]], text_type: str, book_code: str) -> Dict[str, Any]:
        """Parse biblical text from sheet format.
        
        Args:
            values: Sheet values
            text_type: 'ULT' or 'UST'
            book_code: The 3-letter book code for which text is being parsed
            
        Returns:
            Structured biblical text data
        """
        try:
            if not values:
                self.logger.warning(f"No values provided for parsing {text_type} text")
                return {'book': book_code, 'chapters': []}
            
            # Get headers
            headers = values[0] if values else []
            if not headers:
                self.logger.warning(f"No headers found in {text_type} sheet data")
                return {'book': book_code, 'chapters': []}
            
            self.logger.info(f"DEBUG: Headers found in {text_type} sheet: {headers}")
            
            # Find column indices for Reference and Verse
            reference_col = None
            verse_col = None
            
            for i, header in enumerate(headers):
                header_lower = header.lower().strip()
                self.logger.debug(f"DEBUG: Checking header {i}: '{header}' (normalized: '{header_lower}')")
                if 'reference' in header_lower or 'ref' in header_lower:
                    reference_col = i
                    self.logger.info(f"DEBUG: Found Reference column at index {i}: '{header}'")
                elif 'verse' in header_lower:
                    verse_col = i
                    self.logger.info(f"DEBUG: Found Verse column at index {i}: '{header}'")
            
            if reference_col is None or verse_col is None:
                self.logger.warning(f"Could not find Reference or Verse columns in {text_type} sheet. Headers: {headers}")
                self.logger.warning(f"DEBUG: reference_col={reference_col}, verse_col={verse_col}")
                # Fall back to old parsing method
                return self._parse_sheet_biblical_text_fallback(values, text_type, book_code)
            
            self.logger.info(f"Found Reference column at index {reference_col} and Verse column at index {verse_col}")
            
            # Skip header row
            data_rows = values[1:] if len(values) > 1 else []
            self.logger.info(f"DEBUG: Processing {len(data_rows)} data rows for {text_type} {book_code}")
            
            verses = []
            detected_chapters = set()
            
            for row_idx, row in enumerate(data_rows, start=2):
                if not row or len(row) <= max(reference_col, verse_col):
                    continue
                
                reference = row[reference_col].strip() if reference_col < len(row) else ''
                verse_content = row[verse_col].strip() if verse_col < len(row) else ''
                
                if not reference or not verse_content:
                    continue
                
                # Debug first few rows
                if row_idx <= 5:
                    self.logger.debug(f"DEBUG: Row {row_idx}: reference='{reference}', verse_content='{verse_content[:50]}...'")
                
                # Debug specifically for chapter 21 references
                if '21:' in reference:
                    self.logger.info(f"DEBUG {text_type}: Found chapter 21 reference at row {row_idx}: '{reference}' -> '{verse_content[:100]}...'")
                
                # Parse the reference
                chapter_num = None
                verse_num = None
                
                try:
                    # Check if reference contains book code (e.g., "2SA 21:1") or just chapter:verse (e.g., "21:1")
                    if ' ' in reference:
                        # Format: "2SA 21:1" - extract the chapter:verse part
                        ref_parts = reference.split(' ', 1)
                        if len(ref_parts) == 2:
                            book_part, chapter_verse = ref_parts
                            # Validate that this matches our expected book
                            if book_part.upper() == book_code.upper():
                                reference = chapter_verse
                                self.logger.debug(f"DEBUG {text_type}: Extracted chapter:verse '{chapter_verse}' from full reference '{book_part} {chapter_verse}'")
                            else:
                                self.logger.debug(f"Book in reference '{book_part}' doesn't match expected book '{book_code}' at row {row_idx}")
                                continue
                    
                    # Now parse chapter:verse format
                    if ':' in reference:
                        chapter_verse_parts = reference.split(':', 1)
                        if len(chapter_verse_parts) == 2:
                            chapter_num = int(chapter_verse_parts[0])
                            verse_num = int(chapter_verse_parts[1])
                            detected_chapters.add(chapter_num)
                            
                            # Debug chapter detection, especially for chapter 21
                            if row_idx <= 5 or chapter_num == 21:
                                self.logger.info(f"DEBUG {text_type}: Row {row_idx}: detected chapter={chapter_num}, verse={verse_num}")
                        else:
                            self.logger.debug(f"Invalid chapter:verse format '{reference}' at row {row_idx}")
                            continue
                    else:
                        self.logger.debug(f"No colon found in reference '{reference}' at row {row_idx}")
                        continue
                        
                except (ValueError, IndexError) as e:
                    self.logger.debug(f"Error parsing reference '{reference}' at row {row_idx}: {e}")
                    continue
                
                verses.append({
                    'number': verse_num,
                    'content': verse_content,
                    'chapter': chapter_num
                })
            
            self.logger.info(f"DEBUG: Detected chapters: {sorted(detected_chapters)}")
            self.logger.info(f"DEBUG: Total verses parsed: {len(verses)}")
            
            # Group verses by chapter
            chapters = []
            for chapter_num in sorted(detected_chapters):
                chapter_verses = [v for v in verses if v['chapter'] == chapter_num]
                # Sort verses by verse number
                chapter_verses.sort(key=lambda x: x['number'])
                # Remove chapter info from verses (not needed in final structure)
                clean_verses = [{'number': v['number'], 'content': v['content']} for v in chapter_verses]
                
                chapters.append({
                    'chapter': chapter_num,
                    'verses': clean_verses
                })
                
                self.logger.info(f"DEBUG: Chapter {chapter_num} has {len(clean_verses)} verses")
            
            total_verses = sum(len(ch['verses']) for ch in chapters)
            self.logger.info(f"Parsed {total_verses} verses across {len(chapters)} chapters from {text_type} sheet for book {book_code}")
            
            return {
                'book': book_code, 
                'chapters': chapters
            }
            
        except Exception as e:
            self.logger.error(f"Error parsing sheet biblical text for {book_code}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return {'book': book_code, 'chapters': []} # Return with the correct book_code even on error

    def _parse_sheet_biblical_text_fallback(self, values: List[List[str]], text_type: str, book_code: str) -> Dict[str, Any]:
        """Fallback parsing method for biblical text when column headers are not found.
        
        Args:
            values: Sheet values
            text_type: 'ULT' or 'UST'
            book_code: The 3-letter book code for which text is being parsed
            
        Returns:
            Structured biblical text data
        """
        try:
            # Skip header row
            data_rows = values[1:] if len(values) > 1 else []
            
            verses = []
            detected_chapter = None
            
            for row in data_rows:
                if not row:
                    continue
                
                content = ' '.join(row).strip()
                if not content:
                    continue
                
                # Try to detect chapter and verse from content like "20:1 verse text..."
                verse_number = None
                if ':' in content and content.split(':')[0].isdigit():
                    try:
                        chapter_verse = content.split(' ')[0]  # Get first word like "20:1"
                        if ':' in chapter_verse:
                            chapter_part, verse_part = chapter_verse.split(':', 1)
                            detected_chapter = int(chapter_part)
                            verse_number = int(verse_part)
                            # Remove the chapter:verse prefix from content
                            content = content[len(chapter_verse):].strip()
                    except (ValueError, IndexError):
                        pass
                
                # If we couldn't detect verse number, use sequential numbering
                if verse_number is None:
                    verse_number = len(verses) + 1
                
                verses.append({
                    'number': verse_number,
                    'content': content
                })
            
            # Use detected chapter or default to 1
            chapter_number = detected_chapter if detected_chapter is not None else 1
            
            chapters = [{
                'chapter': chapter_number,
                'verses': verses
            }]
            
            self.logger.info(f"Parsed {len(verses)} verses from sheet for chapter {chapter_number} of book {book_code} (fallback method)")
            
            return {
                'book': book_code, 
                'chapters': chapters
            }
            
        except Exception as e:
            self.logger.error(f"Error in fallback parsing for {book_code}: {e}")
            return {'book': book_code, 'chapters': []}
    
    def _fetch_from_door43(self, text_type: str, book_code: str) -> Optional[Dict[str, Any]]:
        """Fetch biblical text from Door43 using the scraper.
        
        Args:
            text_type: 'ULT' or 'UST'
            book_code: The 3-letter book code
            
        Returns:
            Biblical text data or None
        """
        try:
            # Import the scraper
            from .biblical_text_scraper import BiblicalTextScraper
            
            scraper = BiblicalTextScraper()
            
            # Use the provided book_code
            self.logger.info(f"Scraping {text_type} for {book_code} from Door43")
            result = scraper.scrape_biblical_text(book_code, text_type)
            
            if result:
                self.logger.info(f"Successfully scraped {text_type} from Door43: {len(result.get('chapters', []))} chapters")
                return result
            else:
                self.logger.warning(f"Door43 scraping failed for {text_type}")
                return None
                
        except ImportError as e:
            self.logger.error(f"Could not import biblical text scraper: {e}")
            self.logger.error("Make sure selenium is installed: pip install selenium")
            return None
        except Exception as e:
            self.logger.error(f"Error scraping from Door43: {e}")
            return None
    
    def fetch_templates(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch translation note templates.
        
        Returns:
            List of template data or None
        """
        try:
            sheet_id = self.sheets_config['templates_sheet']
            
            self.logger.info("Fetching translation note templates")
            
            # Use the correct tab name "AI templates - use these"
            sheet_name = "AI templates - use these"
            escaped_sheet_name = self._escape_sheet_name(sheet_name)
            range_name = f"{escaped_sheet_name}!A:Z"
            
            result = self.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            if not values:
                return []
            
            # Parse templates (simplified implementation)
            # You would implement the actual parsing logic based on your template structure
            templates = []
            headers = values[0] if values else []
            
            for row in values[1:]:
                if len(row) >= len(headers):
                    template = {}
                    for i, header in enumerate(headers):
                        template[header] = row[i] if i < len(row) else ''
                    templates.append(template)
            
            self.logger.info(f"Fetched {len(templates)} templates")
            return templates
            
        except Exception as e:
            self.logger.error(f"Error fetching templates: {e}")
            return None
    
    def fetch_support_references(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch support references from the support references sheet.
        
        Returns:
            List of support reference data or None
        """
        try:
            sheet_id = self.sheets_config['support_references_sheet']
            
            self.logger.info("Fetching support references")
            
            # Fetch data from the main sheet (Sheet1)
            range_name = "Sheet1!A:Z"
            
            result = self.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            if not values or len(values) <= 1:
                self.logger.warning("No support references data found in sheet")
                return []
            
            # Parse support references
            # Expected format: headers in first row, data in subsequent rows
            headers = values[0]
            support_references = []
            
            # Find the relevant column indices
            issue_col = None
            type_col = None
            description_col = None
            
            for i, header in enumerate(headers):
                header_lower = header.lower().strip()
                if 'issue' in header_lower or 'reference' in header_lower:
                    issue_col = i
                elif 'type' in header_lower or 'category' in header_lower:
                    type_col = i
                elif 'description' in header_lower or 'note' in header_lower:
                    description_col = i
            
            # Process each data row
            for row_idx, row in enumerate(values[1:], start=2):
                if not row:  # Skip empty rows
                    continue
                
                # Extract the issue/reference name
                issue = row[issue_col].strip() if issue_col is not None and issue_col < len(row) else ''
                
                if not issue:  # Skip rows without an issue name
                    continue
                
                # Extract additional fields
                issue_type = row[type_col].strip() if type_col is not None and type_col < len(row) else ''
                description = row[description_col].strip() if description_col is not None and description_col < len(row) else ''
                
                support_ref = {
                    'Issue': issue,
                    'Type': issue_type,
                    'Description': description,
                    'row': row_idx
                }
                
                # Add any additional columns as extra fields
                for i, header in enumerate(headers):
                    if i not in [issue_col, type_col, description_col] and i < len(row) and row[i].strip():
                        support_ref[header.strip()] = row[i].strip()
                
                support_references.append(support_ref)
            
            self.logger.info(f"Fetched {len(support_references)} support references")
            return support_references
            
        except Exception as e:
            self.logger.error(f"Error fetching support references: {e}")
            return None
    
    def fetch_system_prompts(self) -> Optional[Dict[str, Any]]:
        """Fetch system prompts from the system prompts sheet.
        
        Returns:
            System prompts data or None
        """
        try:
            sheet_id = self.sheets_config['system_prompts_sheet']
            
            self.logger.info("Fetching system prompts from Google Sheet")
            
            # Fetch data from the sheet (assuming it's in Sheet1)
            range_name = "Sheet1!A:Z"
            
            result = self.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            if not values or len(values) < 2:
                self.logger.warning("No system prompts data found in sheet or missing content rows")
                return {}
            
            # Parse system prompts
            # Expected format: Row 1 = headers, Row 2+ = content
            headers = values[0]  # First row contains headers
            system_prompts = {}
            
            # Process each content row
            for row_idx, row in enumerate(values[1:], start=2):
                if not row:  # Skip empty rows
                    continue
                    
                # Map each column to its header
                for col_idx, header in enumerate(headers):
                    if col_idx < len(row) and header and row[col_idx]:
                        header_clean = header.strip()
                        prompt_content = row[col_idx].strip()
                        
                        # Map the sheet headers to our internal keys
                        if header_clean in ['Given AT', 'given_at', 'given_at_agent']:
                            system_prompts['given_at_agent'] = prompt_content
                        elif header_clean in ['AI writes AT', 'ai_writes_at', 'ai_writes_at_agent']:
                            system_prompts['ai_writes_at_agent'] = prompt_content
                        else:
                            # Use the header as-is for other prompts
                            system_prompts[header_clean] = prompt_content
            
            self.logger.info(f"Fetched {len(system_prompts)} system prompts")
            return system_prompts
            
        except Exception as e:
            self.logger.error(f"Error fetching system prompts: {e}")
            return None
    
    def _get_fallback_biblical_text(self, text_type: str) -> Dict[str, Any]:
        """Get fallback biblical text when sheets are not available.
        
        Args:
            text_type: 'ULT' or 'UST'
            
        Returns:
            Fallback biblical text data
        """
        # Provide some basic Deuteronomy 22:1 content as fallback
        if text_type == 'ULT':
            verse_content = "If you see your brother's ox or his sheep wandering away, you must not ignore them; you must surely bring them back to your brother."
        else:  # UST
            verse_content = "If you see that someone's cow or sheep has wandered away, do not pretend that you did not see it. Take the animal back to its owner."
        
        return {
            'book': 'DEU',
            'chapters': [
                {
                    'chapter': 22,
                    'verses': [
                        {
                            'number': 1,
                            'content': verse_content
                        }
                    ]
                }
            ]
        }

    def get_all_rows_for_sref_conversion(self, sheet_id: str) -> List[Dict[str, Any]]:
        """Get all rows from a sheet for SRef conversion, regardless of Go? status.
        
        Args:
            sheet_id: Google Sheets ID
            
        Returns:
            List of all row items with SRef field
        """
        try:
            # Get the main sheet data
            sheet_name = self.sheets_config['main_tab_name']
            escaped_sheet_name = self._escape_sheet_name(sheet_name)
            range_name = f"{escaped_sheet_name}!A:Z"  # Get all columns
            
            result = self.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            if not values:
                self.logger.debug(f"No data found in sheet {sheet_id}")
                return []
            
            # Parse the data
            headers = values[0] if values else []
            all_items = []
            
            for i, row in enumerate(values[1:], start=2):  # Start from row 2 (skip header)
                try:
                    # Create item dictionary
                    item = {}
                    for j, header in enumerate(headers):
                        if j < len(row):
                            item[header] = row[j]
                        else:
                            item[header] = ''
                    
                    # Add row number for updates
                    item['row'] = i
                    
                    # Only include rows that have an SRef field (even if empty)
                    if 'SRef' in item:
                        all_items.append(item)
                
                except Exception as e:
                    self.logger.error(f"Error processing row {i}: {e}")
            
            self.logger.debug(f"Found {len(all_items)} rows with SRef field in sheet {sheet_id}")
            return all_items
            
        except Exception as e:
            self.logger.error(f"Error getting all rows from sheet {sheet_id}: {e}")
            return []

    def convert_sref_values(self, items: List[Dict[str, Any]], support_references: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert short SRef values to full support reference names.
        
        Args:
            items: List of items with SRef fields
            support_references: List of support reference data
            
        Returns:
            List of items that need SRef updates
        """
        # Create mapping for short forms to full forms
        short_to_full_mapping = {
            'you': 'figs-you',
            'explicit': 'figs-explicit', 
            'pronouns': 'writing-pronouns',
            'quotations': 'figs-quotations',
            'connecting': 'grammar-connect-words-phrases',
            'background': 'writing-background',
            'metaphor': 'figs-metaphor',
            'metonymy': 'figs-metonymy',
            'hyperbole': 'figs-hyperbole',
            'idiom': 'figs-idiom',
            'simile': 'figs-simile',
            'irony': 'figs-irony',
            'parallelism': 'figs-parallelism',
            'poetry': 'writing-poetry',
            'participants': 'writing-participants',
            'newevent': 'writing-newevent',
            'endofstory': 'writing-endofstory',
            'proverbs': 'writing-proverbs',
            'symlanguage': 'writing-symlanguage',
            'politeness': 'writing-politeness',
            'oathformula': 'writing-oathformula',
            'activepassive': 'figs-activepassive',
            'abstractnouns': 'figs-abstractnouns',
            'ellipsis': 'figs-ellipsis',
            'hendiadys': 'figs-hendiadys',
            'doublet': 'figs-doublet',
            'merism': 'figs-merism',
            'synecdoche': 'figs-synecdoche',
            'euphemism': 'figs-euphemism',
            'litotes': 'figs-litotes',
            'apostrophe': 'figs-apostrophe',
            'personification': 'figs-personification',
            'rhetorical': 'figs-rquestion',
            'question': 'figs-rquestion'
        }
        
        updates_needed = []
        
        for item in items:
            sref_value = str(item.get('SRef', '')).strip()
            
            if not sref_value:
                continue
                
            original_sref = sref_value
            updated_sref = sref_value
            
            # First, check if it's a short form that needs conversion
            sref_lower = sref_value.lower()
            if sref_lower in short_to_full_mapping:
                updated_sref = short_to_full_mapping[sref_lower]
                self.logger.debug(f"Converted short form '{sref_value}' to '{updated_sref}'")
            
            # Then, find a matching support reference item where Issue includes the SRef
            if updated_sref:
                matched_item = None
                for ref in support_references:
                    ref_issue = ref.get('Issue', '')
                    if ref_issue and updated_sref in ref_issue:
                        matched_item = ref
                        break
                
                if matched_item:
                    updated_sref = matched_item['Issue']
                    self.logger.debug(f"Found support reference match: '{sref_value}' -> '{updated_sref}'")
            
            # Only add to updates if the SRef actually changed
            if updated_sref != original_sref:
                updates_needed.append({
                    'row_number': item['row'],
                    'original_sref': original_sref,
                    'updated_sref': updated_sref,
                    'updates': {'SRef': updated_sref}
                })
                self.logger.info(f"Row {item['row']}: SRef conversion '{original_sref}' -> '{updated_sref}'")
        
        return updates_needed 