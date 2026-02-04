"""
Write processed results to TSV file.

This module provides a TSVResultWriter class that writes processing results
to a TSV file in the translation notes format (7 columns with headers).
"""

import csv
import logging
from typing import List, Dict, Any


class TSVResultWriter:
    """Writes processing results to TSV file.

    Output format (7 columns with headers):
    Reference\\tID\\tTags\\tSupportReference\\tQuote\\tOccurrence\\tNote

    Example row:
    65:1\\ta1b2\\t\\trc://*/ta/man/translate/figs-activepassive\\t[Hebrew]\\t1\\t[AI-generated TN]
    """

    # TN TSV column order
    COLUMNS = ['Reference', 'ID', 'Tags', 'SupportReference', 'Quote', 'Occurrence', 'Note']

    def __init__(self, output_path: str):
        """Initialize the result writer.

        Args:
            output_path: Path to the output TSV file
        """
        self.output_path = output_path
        self.logger = logging.getLogger(__name__)

    def write_results(self, items: List[Dict[str, Any]]):
        """Write processed items to TSV.

        Args:
            items: List of processed item dictionaries with conversion_data
                   and AI TN fields populated
        """
        self.logger.info(f"Writing {len(items)} results to {self.output_path}")

        with open(self.output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=self.COLUMNS, delimiter='\t')
            writer.writeheader()

            written_count = 0
            for item in items:
                row = self._format_item(item)
                if row:
                    writer.writerow(row)
                    written_count += 1

        self.logger.info(f"Wrote {written_count} rows to {self.output_path}")
        return written_count

    def _format_item(self, item: Dict[str, Any]) -> Dict[str, str]:
        """Format an item for TSV output.

        Args:
            item: Processed item dictionary

        Returns:
            Dictionary with TSV column values
        """
        # Extract reference without book code
        ref = item.get('Ref', '')
        if ' ' in ref:
            ref = ref.split(' ', 1)[1]  # Remove book prefix if present

        # Build SupportReference with rc:// prefix
        sref = item.get('SRef', '')
        if sref and not sref.startswith('rc://'):
            sref = f'rc://*/ta/man/translate/{sref}'

        # Get conversion data if available
        conversion_data = item.get('conversion_data', {})

        # Get Hebrew quote - prefer conversion_data, fall back to OrigL or empty
        quote = conversion_data.get('OrigL', '') or item.get('OrigL', '')

        # Get ID - prefer conversion_data, fall back to item ID
        item_id = conversion_data.get('ID', '') or item.get('ID', '')

        # Get the AI-generated note
        note = item.get('AI TN', '') or item.get('Note', '')

        return {
            'Reference': ref,
            'ID': item_id,
            'Tags': '',  # Tags column typically empty
            'SupportReference': sref,
            'Quote': quote,  # Hebrew from converter
            'Occurrence': '1',  # Default occurrence
            'Note': note,  # AI-generated translation note
        }

    def write_partial_results(self, items: List[Dict[str, Any]], include_incomplete: bool = False):
        """Write results, optionally including items without AI notes.

        This is useful for debugging or when you want to see conversion
        results even if AI processing failed.

        Args:
            items: List of processed item dictionaries
            include_incomplete: If True, include items without AI notes
        """
        if include_incomplete:
            self.write_results(items)
        else:
            # Filter to only items with AI notes
            complete_items = [
                item for item in items
                if item.get('AI TN') or item.get('Note')
            ]
            self.write_results(complete_items)
