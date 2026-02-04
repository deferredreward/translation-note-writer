"""
TSV-based work provider - alternative to SheetManager for TSV input.

This module provides a TSVWorkProvider class that loads items from a TSV file
and returns them in the same format as SheetManager.get_pending_work().
This enables the entire tnwriter processing pipeline to work with TSV files
instead of Google Sheets.
"""

import logging
from typing import List, Dict, Any, Optional


class TSVWorkProvider:
    """Provides work items from TSV file in same format as SheetManager.

    This class reads TSV files in the cSkillBP issue identification format
    (headerless, positional columns) and converts them to the tnwriter-dev
    item format for processing through the existing pipeline.

    cSkillBP format (no headers, positional):
    [book]\\t[chapter:verse]\\t[issue-type]\\t[ULT text]\\t[Go?]\\t[AT]\\t[explanation]

    tnwriter-dev format:
    {
        'Book': 'PSA',
        'Ref': '78:17',
        'SRef': 'writing-pronouns',
        'GLQuote': 'And they added',
        'Go?': 'LA',
        'AT': '',
        'Explanation': 'ancestors/israelites',
        'AI TN': '',
        'row': 1,
        'processing_mode': 'language_and_ai'
    }
    """

    def __init__(self, tsv_path: str, book_code: Optional[str] = None):
        """Initialize the TSV work provider.

        Args:
            tsv_path: Path to the input TSV file
            book_code: Optional book code to use if not in TSV (e.g., 'PSA')
        """
        self.tsv_path = tsv_path
        self.book_code = book_code
        self.items: List[Dict[str, Any]] = []
        self.logger = logging.getLogger(__name__)
        self._load_tsv()

    def _load_tsv(self):
        """Load headerless TSV and convert to tnwriter-dev format.

        cSkillBP format (no headers, positional):
        [book]\\t[chapter:verse]\\t[issue-type]\\t[ULT text]\\t\\t\\t[explanation]

        Maps to tnwriter-dev columns:
        Book, Ref, SRef, GLQuote, Go?, AT, Explanation, AI TN
        """
        self.logger.info(f"Loading TSV from {self.tsv_path}")

        with open(self.tsv_path, 'r', encoding='utf-8') as f:
            for row_num, line in enumerate(f, start=2):  # Start at 2 to match sheet row numbers
                line = line.rstrip('\n')
                if not line.strip():
                    continue

                cols = line.split('\t')
                # Pad to 7 columns if shorter
                while len(cols) < 7:
                    cols.append('')

                # Map positional columns to tnwriter-dev format
                book = cols[0].upper() if cols[0] else (self.book_code or 'UNK')

                item = {
                    'Book': book,
                    'Ref': cols[1],                    # chapter:verse
                    'SRef': cols[2],                   # issue type
                    'GLQuote': cols[3],                # English text
                    'Go?': cols[4] if cols[4] else 'LA',  # Default to language + AI
                    'AT': cols[5],                     # Alternate translation (usually empty)
                    'Explanation': cols[6],            # Explanation/guidance
                    'AI TN': '',                       # To be filled by processor
                    'row': row_num,
                    'ID': '',                          # To be generated
                    'OrigL': '',                       # To be filled by language conversion
                }

                # Set processing mode based on Go? value
                go_val = item['Go?'].upper() if item['Go?'] else 'LA'
                if go_val == 'L':
                    item['processing_mode'] = 'language_only'
                elif go_val == 'LA':
                    item['processing_mode'] = 'language_and_ai'
                else:
                    item['processing_mode'] = 'ai_only'

                self.items.append(item)

        self.logger.info(f"Loaded {len(self.items)} items from TSV")

    def get_pending_work(self, max_items: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return items in same format as SheetManager.get_pending_work().

        Args:
            max_items: Optional limit on number of items to return

        Returns:
            List of item dictionaries ready for processing
        """
        if max_items:
            return self.items[:max_items]
        return self.items

    def get_all_items(self) -> List[Dict[str, Any]]:
        """Return all loaded items.

        Returns:
            List of all item dictionaries
        """
        return self.items

    def __len__(self) -> int:
        """Return the number of items loaded."""
        return len(self.items)
