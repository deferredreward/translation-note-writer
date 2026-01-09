"""
Language Converter
Handles round-trip conversion of Gateway Language to Original Language and back.
"""

import html
import logging
import os
import sys
from typing import Dict, List, Optional, Any, Set

# Add parent directory to path for tsv_converter_wrapper import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tsv_converter_wrapper import TSVConverter
from .tsv_notes_cache import TSVNotesCache


class LanguageConverter:
    """Manages round-trip language conversion for translation notes."""

    def __init__(self, cache_manager=None):
        """Initialize the language converter.

        Args:
            cache_manager: Optional cache manager instance
        """
        self.logger = logging.getLogger(__name__)
        self.tsv_converter = TSVConverter(use_cache=True)
        self.notes_cache = TSVNotesCache()
        self.cache_manager = cache_manager

        # Default bible link for conversion
        self.default_bible_link = 'unfoldingWord/en_ult/master'

        self.logger.info("Language converter initialized")

    def prepare_tsv_from_items(self, items: List[Dict[str, Any]]) -> str:
        """Convert sheet items to TSV format for the converter.

        Args:
            items: List of sheet item dictionaries

        Returns:
            TSV string with headers and data rows
        """
        # TSV format: Reference\tID\tTags\tQuote\tOccurrence\tNote
        lines = ['Reference\tID\tTags\tQuote\tOccurrence\tNote']

        for item in items:
            ref = item.get('Ref', '').strip()
            item_id = item.get('ID', '').strip()  # May be empty, will be generated later
            tags = item.get('SRef', '').strip()
            quote = item.get('GLQuote', '').strip()
            quote = html.unescape(quote)  # Decode HTML entities like &amp; → &
            occurrence = item.get('Occurrence', '1').strip() or '1'  # Default to 1

            # Build note from available fields
            note_parts = []
            if item.get('Explanation'):
                note_parts.append(item['Explanation'].strip())
            if item.get('AT'):
                note_parts.append(f"AT: {item['AT'].strip()}")

            note = ' '.join(note_parts) if note_parts else ''

            # Build TSV line
            line = f"{ref}\t{item_id}\t{tags}\t{quote}\t{occurrence}\t{note}"
            lines.append(line)

        return '\n'.join(lines)

    def parse_roundtrip_results(self, tsv_output: str) -> List[Dict[str, str]]:
        """Parse round-trip TSV output to extract results.

        The output TSV will have additional columns:
        - OrigQuote: The original language (Hebrew/Greek) text
        - GLQuote: The roundtripped Gateway Language text
        - GLOccurrence: The occurrence in GL text

        Args:
            tsv_output: TSV string from round-trip conversion

        Returns:
            List of dictionaries with parsed data
        """
        lines = tsv_output.strip().split('\n')
        if len(lines) < 2:
            return []

        # Parse headers
        headers = lines[0].split('\t')

        # Parse data rows
        results = []
        for line in lines[1:]:
            if not line.strip():
                continue

            values = line.split('\t')
            row_data = {}
            for i, header in enumerate(headers):
                if i < len(values):
                    row_data[header] = values[i]
                else:
                    row_data[header] = ''

            results.append(row_data)

        return results

    def perform_roundtrip(self, items: List[Dict[str, Any]], book_code: str,
                         bible_link: Optional[str] = None,
                         verbose: bool = False) -> Optional[Dict[str, Any]]:
        """Perform round-trip conversion for items.

        Args:
            items: List of sheet item dictionaries
            book_code: 3-letter book code (e.g., 'GEN', 'JON')
            bible_link: DCS bible link (default: unfoldingWord/en_ult/master)
            verbose: Enable verbose logging

        Returns:
            Dict with 'output' (TSV string), 'errors' (list), 'parsed' (list of dicts)
            or None if conversion failed
        """
        if not items:
            return None

        bible_link = bible_link or self.default_bible_link

        try:
            # Prepare TSV from items
            tsv_content = self.prepare_tsv_from_items(items)

            if verbose:
                self.logger.debug(f"Prepared TSV content for {len(items)} items")
                self.logger.debug(f"TSV preview:\n{tsv_content[:500]}")

            # Perform round-trip conversion
            result = self.tsv_converter.roundtrip(
                bible_link=bible_link,
                book_code=book_code,
                tsv_content=tsv_content,
                use_cache=True,
                verbose=verbose
            )

            if not result:
                self.logger.error(f"Round-trip conversion failed for {book_code}")
                return None

            if result.get('errors'):
                self.logger.warning(f"Round-trip conversion had errors for {book_code}: {result['errors']}")

            # Parse the output
            if result.get('output'):
                parsed = self.parse_roundtrip_results(result['output'])
                result['parsed'] = parsed

                if verbose:
                    self.logger.debug(f"Parsed {len(parsed)} rows from conversion output")

            return result

        except Exception as e:
            self.logger.error(f"Error performing round-trip for {book_code}: {e}", exc_info=True)
            return None

    def get_existing_ids_from_items(self, items: List[Dict[str, Any]]) -> Set[str]:
        """Extract existing IDs from sheet items.

        Args:
            items: List of sheet item dictionaries

        Returns:
            Set of existing IDs
        """
        existing_ids = set()
        for item in items:
            item_id = item.get('ID', '').strip()
            if item_id:
                existing_ids.add(item_id)
        return existing_ids

    def enrich_items_with_conversion(self, items: List[Dict[str, Any]], book_code: str,
                                     sheet_manager=None, sheet_id: Optional[str] = None,
                                     bible_link: Optional[str] = None,
                                     verbose: bool = False) -> List[Dict[str, Any]]:
        """Main orchestration function: perform conversion and enrich items with results.

        This function:
        1. Gets existing IDs from sheet and upstream TSV
        2. Generates unique IDs for items that don't have them
        3. Performs round-trip conversion
        4. Enriches items with GLQuote, OrigL, and ID for updating

        Args:
            items: List of sheet item dictionaries
            book_code: 3-letter book code
            sheet_manager: Optional sheet manager for fetching existing IDs
            sheet_id: Optional sheet ID for fetching existing IDs
            bible_link: Optional bible link for conversion
            verbose: Enable verbose logging

        Returns:
            List of enriched items with conversion data
        """
        if not items:
            return items

        if not book_code:
            self.logger.warning("No book code provided, skipping language conversion")
            return items

        try:
            self.logger.info(f"Starting language conversion for {len(items)} items in {book_code}")

            # Step 1: Get existing IDs from sheet items
            sheet_ids = self.get_existing_ids_from_items(items)
            self.logger.debug(f"Found {len(sheet_ids)} existing IDs in sheet items")

            # Step 2: Get existing IDs from upstream TSV
            all_existing_ids = self.notes_cache.get_existing_ids(book_code, additional_ids=sheet_ids)
            self.logger.debug(f"Total existing IDs (sheet + upstream): {len(all_existing_ids)}")

            # Step 3: Generate IDs for items that don't have them
            for item in items:
                if not item.get('ID', '').strip():
                    new_id = self.notes_cache.generate_unique_id(all_existing_ids)
                    if not new_id:
                        # Fallback ID generation
                        new_id = self.notes_cache.generate_fallback_id()
                        self.logger.warning(f"Using fallback ID for row {item.get('row')}: {new_id}")

                    item['ID'] = new_id
                    all_existing_ids.add(new_id)  # Add to set to avoid duplicates
                    self.logger.debug(f"Generated ID '{new_id}' for row {item.get('row')}")

            # Step 4: Perform round-trip conversion
            conversion_result = self.perform_roundtrip(
                items=items,
                book_code=book_code,
                bible_link=bible_link,
                verbose=verbose
            )

            if not conversion_result:
                self.logger.error(f"Conversion failed for {book_code}, items will not be enriched")
                return items

            # Step 5: Enrich items with conversion results
            parsed_results = conversion_result.get('parsed', [])

            if len(parsed_results) != len(items):
                self.logger.warning(
                    f"Mismatch between items ({len(items)}) and conversion results ({len(parsed_results)})"
                )

            # Match results to items by row index
            for i, item in enumerate(items):
                if i < len(parsed_results):
                    result_row = parsed_results[i]

                    # Add conversion data to item for later update
                    if 'conversion_data' not in item:
                        item['conversion_data'] = {}

                    # Extract converted values
                    item['conversion_data']['GLQuote'] = result_row.get('GLQuote', '').strip()
                    item['conversion_data']['OrigL'] = result_row.get('Quote', '').strip()
                    item['conversion_data']['ID'] = item.get('ID', '').strip()

                    self.logger.debug(
                        f"Row {item.get('row')}: ID={item['conversion_data']['ID']}, "
                        f"OrigL='{item['conversion_data']['OrigL'][:50]}...'"
                    )
                else:
                    self.logger.warning(f"No conversion result for item index {i}")

            self.logger.info(f"Successfully enriched {len(items)} items with conversion data")

            return items

        except Exception as e:
            self.logger.error(f"Error enriching items with conversion: {e}", exc_info=True)
            # Return items unchanged if conversion fails
            return items

    def should_convert_item(self, item: Dict[str, Any]) -> bool:
        """Determine if an item should be converted.

        Currently converts all items. Can be extended with conditions.

        Args:
            item: Sheet item dictionary

        Returns:
            True if item should be converted
        """
        # Future: Add conditions like checking if GLQuote is not empty
        # For now, convert all items as per requirements
        return True
