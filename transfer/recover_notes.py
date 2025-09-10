#!/usr/bin/env python3
"""
Translation Notes Recovery Script
This script parses a log file to find AI-generated translation notes that may not have
been written to the Google Sheet due to a crash or error. It then attempts to
write these recovered notes to the correct sheet and row if they are missing.
"""

import os
import sys
import re
import argparse
import logging
from typing import List, Dict, Any

# Add the project root to the Python path to allow module imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from modules import ConfigManager, SheetManager, setup_logging
    from modules.processing_utils import (
        clean_ai_output, determine_note_type, format_final_note, 
        post_process_text, prepare_update_data
    )
except ImportError as e:
    print(f"Error: Failed to import necessary modules. Make sure this script is in the project root.")
    print(f"Details: {e}")
    sys.exit(1)

def parse_log_for_unwritten_notes(log_content: str) -> List[Dict[str, Any]]:
    """
    Parses the full content of a log file to extract notes that might be missing,
    including the raw AI output for proper reprocessing.

    Args:
        log_content: The string content of the log file.

    Returns:
        A list of dictionaries, where each dictionary represents a recovered note
        with its context (editor_key, verse, row, raw_ai_output, original_item_data).
    """
    recovered_notes = []
    
    # Enhanced pattern to capture both the raw AI output and any available original item context
    # Look for "Processing AI output" followed by raw output, and try to reconstruct context
    ai_output_pattern = re.compile(
        r"INFO - Processing AI output for (?P<verse>[\d:]+) \(row (?P<row>\d+)\):[^\n]*\n"
        r"(?P<ai_output>(?:(?!INFO - |ERROR - |WARNING - |DEBUG - ).*\n)*)"  # Capture multi-line AI output
    )
    
    # Pattern to find original item data from earlier in the log
    item_context_pattern = re.compile(
        r"INFO - Processing item: .*?Ref.*?(?P<verse>[\d:]+).*?row.*?(?P<row>\d+).*?\n"
        r"(?P<item_data>(?:.*?\n)*?)"
        r"(?=INFO - |ERROR - |WARNING - |DEBUG - )"
    )

    # Editor pattern remains the same
    editor_pattern = re.compile(r"INFO - Batch \S+ for .*?\((?P<editor_key>editor\d+)\) completed")

    for output_match in ai_output_pattern.finditer(log_content):
        verse = output_match.group('verse')
        row = int(output_match.group('row'))
        raw_ai_output = output_match.group('ai_output').strip()
        
        if not raw_ai_output:
            continue
            
        # Find the correct editor
        content_before_note = log_content[:output_match.start()]
        editor_key = None
        for editor_match in editor_pattern.finditer(content_before_note):
            editor_key = editor_match.group('editor_key')
            
        if not editor_key:
            logging.warning(f"Could not determine editor for note on row {row} for verse {verse}. Skipping.")
            continue
        
        # Try to reconstruct original item context
        original_item = reconstruct_original_item(verse, row, editor_key, content_before_note)
        
        recovered_notes.append({
            'editor_key': editor_key,
            'verse': verse,
            'row': row,
            'raw_ai_output': raw_ai_output,
            'original_item': original_item
        })

    return recovered_notes


def reconstruct_original_item(verse: str, row: int, editor_key: str, log_content: str) -> Dict[str, Any]:
    """
    Reconstruct original item context from log content.
    
    This creates a minimal but functional original_item dict that can be used
    with the processing pipeline.
    """
    # Base item with required fields
    original_item = {
        'row': row,
        'Ref': verse,
        'editor_key': editor_key
    }
    
    # Try to extract more context from logs if available
    # Look for SRef, GLQuote, AT, etc. in the log content
    sref_pattern = re.compile(rf"row {row}.*?SRef.*?:\s*([^\s,\n]+)")
    glquote_pattern = re.compile(rf"row {row}.*?GLQuote.*?:\s*([^\n]+)")
    at_pattern = re.compile(rf"row {row}.*?AT.*?:\s*([^\n]+)")
    explanation_pattern = re.compile(rf"row {row}.*?Explanation.*?:\s*([^\n]+)")
    
    for pattern, field in [(sref_pattern, 'SRef'), (glquote_pattern, 'GLQuote'), 
                          (at_pattern, 'AT'), (explanation_pattern, 'Explanation')]:
        match = pattern.search(log_content)
        if match:
            original_item[field] = match.group(1).strip()
    
    return original_item


def main():
    """Main function to execute the recovery script."""
    parser = argparse.ArgumentParser(
        description="Recover unwritten translation notes from a log file.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "logfile",
        help="Path to the log file to parse (e.g., logs/translation_notes_20250606_080008.log)"
    )
    parser.add_argument(
        "-d", "--dry-run",
        action="store_true",
        help="Run the script without writing any changes to the Google Sheet. "
             "This will print the actions that would be taken."
    )
    parser.add_argument(
        "-v", "--verify",
        action="store_true",
        help="Verify recovered notes by showing the complete processing pipeline output."
    )
    args = parser.parse_args()

    # Set up basic configuration and logging
    config = ConfigManager()
    logger = setup_logging(config)

    if not os.path.exists(args.logfile):
        logger.error(f"Log file not found at: {args.logfile}")
        sys.exit(1)

    logger.info(f"Starting recovery process for log file: {args.logfile}")
    if args.dry_run:
        logger.info("DRY RUN mode enabled. No changes will be written to Google Sheets.")
    if args.verify:
        logger.info("VERIFY mode enabled. Will show complete processing pipeline output.")

    # Initialize SheetManager
    try:
        sheet_manager = SheetManager(config)
    except Exception as e:
        logger.error(f"Failed to initialize SheetManager: {e}")
        sys.exit(1)

    # Parse the log file
    with open(args.logfile, 'r', encoding='utf-8') as f:
        log_content = f.read()
    
    recovered_notes = parse_log_for_unwritten_notes(log_content)

    if not recovered_notes:
        logger.info("No recoverable notes found in the log file.")
        sys.exit(0)

    logger.info(f"Found {len(recovered_notes)} potentially recoverable notes.")

    # Process each recovered note with complete processing pipeline
    written_count = 0
    skipped_count = 0
    for note_info in recovered_notes:
        editor_key = note_info['editor_key']
        row = note_info['row']
        raw_ai_output = note_info['raw_ai_output']
        original_item = note_info['original_item']

        try:
            sheet_id = config.get_sheet_id(editor_key)
            if not sheet_id:
                logger.warning(f"No sheet ID found for editor '{editor_key}'. Skipping row {row}.")
                skipped_count += 1
                continue

            friendly_name = config.get_friendly_name(editor_key)
            
            # Check if the note is already written
            status_col_name = config.get('sheets.column_names.go_column', 'Go?')
            status = sheet_manager.get_cell_value(sheet_id, f"{status_col_name}{row}")

            if status and status.strip().upper() == 'AI':
                logger.info(f"Skipping row {row} for {friendly_name}: Note already marked as 'AI'.")
                skipped_count += 1
                continue
            
            logger.info(f"Found unwritten note for {friendly_name} at row {row}. Verse: {note_info['verse']}.")
            
            # Apply complete processing pipeline
            if args.verify:
                logger.info("=== PROCESSING PIPELINE VERIFICATION ===")
                logger.info(f"Raw AI output: {raw_ai_output}")
                logger.info(f"Original item context: {original_item}")
            
            # Step 1: Clean AI output
            cleaned_output = clean_ai_output(raw_ai_output)
            if args.verify:
                logger.info(f"Step 1 - Cleaned output: {cleaned_output}")
            
            # Step 2: Determine note type
            note_type = determine_note_type(original_item)
            if args.verify:
                logger.info(f"Step 2 - Determined note type: {note_type}")
            
            # Step 3: Format final note
            formatted_note = format_final_note(original_item, cleaned_output, note_type, logger)
            if args.verify:
                logger.info(f"Step 3 - Formatted note: {formatted_note}")
            
            # Step 4: Apply post-processing (smart quotes, etc.)
            final_note = post_process_text(formatted_note)
            if args.verify:
                logger.info(f"Step 4 - Final processed note: {final_note}")
                logger.info("=== END PIPELINE VERIFICATION ===")
            else:
                logger.debug(f"Final processed note: {final_note[:100]}...")

            if not args.dry_run:
                # Step 5: Prepare update data using the standard pipeline
                update_data = prepare_update_data(original_item, final_note, logger)
                if update_data:
                    # Convert to the batch update format expected by sheet_manager
                    sheet_manager.batch_update_rows(sheet_id, [update_data])
                    logger.info(f"Successfully wrote processed note to row {row} for {friendly_name}.")
                    written_count += 1
                else:
                    logger.error(f"Failed to prepare update data for row {row}")
                    skipped_count += 1
            else:
                logger.info(f"DRY RUN: Would write processed note to row {row} for {friendly_name}.")
                logger.info(f"DRY RUN: Final note would be: {final_note}")
                written_count += 1

        except Exception as e:
            logger.error(f"Failed to process or write note for row {row} of editor {editor_key}: {e}")
            logger.error(f"Error details: {e}", exc_info=True)
            skipped_count += 1

    logger.info("=" * 30)
    logger.info("Recovery process completed.")
    logger.info(f"Total notes processed: {len(recovered_notes)}")
    logger.info(f"Notes written (or that would be written): {written_count}")
    logger.info(f"Notes skipped (already written or errors): {skipped_count}")
    logger.info("=" * 30)


if __name__ == '__main__':
    main() 