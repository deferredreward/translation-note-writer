#!/usr/bin/env python3
"""
Translation Notes API Recovery Script

This script recovers translation notes by directly interacting with the Anthropic API
for batches that were submitted but not fully processed before a crash.

It works by:
1. Parsing a log file to find all submitted batch jobs and their original row items.
2. Cross-referencing with log entries for batches that were already successfully processed.
3. For any "in-flight" batches, it fetches the results directly from Anthropic.
4. It then processes and writes these recovered notes to the Google Sheet.
"""

import os
import sys
import re
import argparse
import logging
import json
import time
from typing import List, Dict, Any, Set

# Add the project root for module imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from modules import (
        ConfigManager,
        SheetManager,
        AIService,
        CacheManager,
        setup_logging,
    )
    from modules.processing_utils import (
        clean_ai_output, determine_note_type, format_final_note,
        post_process_text, prepare_update_data
    )
except ImportError as e:
    print(f"Error: Failed to import modules. Ensure script is in the project root.")
    print(f"Details: {e}")
    sys.exit(1)


def parse_log_file(log_content: str) -> (Dict[str, str], Set[str], Dict[str, List[Dict]]):
    """
    Parses the log file to find submitted and completed batch jobs, and extract original item contexts.

    Args:
        log_content: The string content of the log file.

    Returns:
        A tuple containing:
        - A dictionary mapping submitted batch_id to editor_key.
        - A set of completed batch_ids.
        - A dictionary mapping batch_id to list of original items.
    """
    # Regex to find submitted batches. Captures batch_id and editor_key.
    # Example log: "INFO - Submitted AI batch 3 for Chris (editor1) (ID: msgbatch_..., 2 items)"
    submitted_pattern = re.compile(
        r"Submitted AI batch .*? for .*?\((?P<editor_key>editor\d+)\) \(ID: (?P<batch_id>msgbatch_\w+),"
    )

    # Regex to find batches whose results were fully processed.
    # Example log: "INFO - Processed batch msgbatch_... for Chris (editor1): 2/2 items"
    completed_pattern = re.compile(
        r"Processed batch (?P<batch_id>msgbatch_\w+) for"
    )
    
    # Regex to find original item data in batch submissions
    # Look for the batch request data that contains original items
    batch_items_pattern = re.compile(
        r"Submitting batch with (?P<count>\d+) requests:.*?batch_id.*?(?P<batch_id>msgbatch_\w+)"
    )

    submitted_batches = {}
    completed_batches = set()
    batch_original_items = {}

    for line in log_content.splitlines():
        submitted_match = submitted_pattern.search(line)
        if submitted_match:
            batch_id = submitted_match.group('batch_id')
            editor_key = submitted_match.group('editor_key')
            # We might see the same batch submitted multiple times in logs if restarted;
            # the first one is the source of truth.
            if batch_id not in submitted_batches:
                submitted_batches[batch_id] = editor_key
        
        completed_match = completed_pattern.search(line)
        if completed_match:
            batch_id = completed_match.group('batch_id')
            completed_batches.add(batch_id)
    
    # Try to extract original item contexts from the logs
    # This is a best-effort reconstruction since the original items may not be fully logged
    for batch_id in submitted_batches.keys():
        batch_original_items[batch_id] = []
            
    return submitted_batches, completed_batches, batch_original_items


def reconstruct_original_item_from_api_result(result_dict: Dict[str, Any], editor_key: str) -> Dict[str, Any]:
    """
    Reconstruct original item context from API result custom_id and editor context.
    
    Args:
        result_dict: API result dictionary
        editor_key: Editor key for context
        
    Returns:
        Reconstructed original item dictionary
    """
    # Extract row number from custom_id (e.g., "item_0_123")
    custom_id = result_dict.get('custom_id', '')
    row = None
    
    if custom_id:
        match = re.search(r'_(\d+)$', custom_id)
        if match:
            row = int(match.group(1))
    
    # Create minimal original item
    original_item = {
        'row': row,
        'editor_key': editor_key,
        'Ref': f"Unknown:{row}" if row else "Unknown:Unknown"
    }
    
    return original_item


def main():
    """Main function to execute the API recovery script."""
    parser = argparse.ArgumentParser(
        description="Recover unwritten translation notes from the Anthropic API using a log file.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "logfile",
        help="Path to the log file to parse."
    )
    parser.add_argument(
        "-d", "--dry-run",
        action="store_true",
        help="Run without writing changes to the Google Sheet. "
             "This will print the actions that would be taken."
    )
    parser.add_argument(
        "-v", "--verify",
        action="store_true",
        help="Verify recovered notes by showing the complete processing pipeline output."
    )
    args = parser.parse_args()

    # --- Initialization ---
    config = ConfigManager()
    logger = setup_logging(config)
    
    if args.dry_run:
        logger.info("DRY RUN mode enabled. No changes will be written to Google Sheets.")
    if args.verify:
        logger.info("VERIFY mode enabled. Will show complete processing pipeline output.")

    if not os.path.exists(args.logfile):
        logger.error(f"Log file not found at: {args.logfile}")
        sys.exit(1)
        
    try:
        sheet_manager = SheetManager(config)
        cache_manager = CacheManager(config, sheet_manager)
        ai_service = AIService(config, cache_manager)
    except Exception as e:
        logger.error(f"Failed to initialize core services: {e}", exc_info=True)
        sys.exit(1)

    logger.info(f"Starting API recovery for log file: {args.logfile}")
    
    # --- Log Parsing ---
    with open(args.logfile, 'r', encoding='utf-8') as f:
        log_content = f.read()

    submitted_batches, completed_batches, batch_original_items = parse_log_file(log_content)
    
    # Determine which batches need recovery
    batches_to_recover = submitted_batches.keys() - completed_batches

    logger.info(f"Found {len(submitted_batches)} submitted batches.")
    logger.info(f"Found {len(completed_batches)} completed batches.")

    if not batches_to_recover:
        logger.info("No batches require recovery. Exiting.")
        sys.exit(0)

    logger.info(f"Found {len(batches_to_recover)} batches to recover: {', '.join(batches_to_recover)}")

    # --- Recovery Processing ---
    recovered_count = 0
    skipped_count = 0
    failed_count = 0

    # Get all sheet and name configurations once
    sheet_ids = config.get('google_sheets.sheet_ids', {})
    editor_names = config.get('google_sheets.editor_names', {})

    for batch_id in batches_to_recover:
        editor_key = submitted_batches[batch_id]
        sheet_id = sheet_ids.get(editor_key)
        friendly_name = editor_names.get(editor_key, editor_key) # Fallback to key if name not found
        
        if not sheet_id:
            logger.warning(f"No sheet ID for editor '{editor_key}' (batch: {batch_id}). Skipping.")
            failed_count += 1
            continue

        logger.info(f"Processing batch {batch_id} for {friendly_name}...")

        try:
            # 1. Fetch the full batch status object first
            batch_status = ai_service.get_batch_status(batch_id)
            if not batch_status:
                logger.warning(f"Could not retrieve status for batch {batch_id}. It may have expired or failed.")
                failed_count += 1
                continue

            # 2. Fetch results using the full batch object
            results = ai_service.get_batch_results(batch_status)
            if not results:
                logger.warning(f"No results returned for batch {batch_id}. It might still be processing or failed.")
                failed_count += 1
                continue
            
            logger.info(f"Retrieved {len(results)} results from API for batch {batch_id}.")

            # Convert Pydantic objects to dictionaries
            results_as_dicts = [json.loads(result.to_json()) for result in results]

            # --- Define column names from config once per batch ---
            tn_col_name = config.get('google_sheets.tn_column_name', 'AI TN')
            sref_col_name = config.get('google_sheets.sref_column_name', 'SRef')
            status_col_name = config.get('google_sheets.status_column_name', 'Go?')

            # 3. Process each result item
            updates_for_sheet = []
            for result_dict in results_as_dicts:
                # --- Add a small delay to avoid hitting Google Sheets API rate limits ---
                time.sleep(0.5)  # 500ms delay

                # Extract row number from custom_id (e.g., "item_0_123")
                custom_id = result_dict.get('custom_id', '')
                if not custom_id:
                    logger.warning(f"Could not find custom_id in result object. Skipping.")
                    continue
                
                match = re.search(r'_(\d+)$', custom_id)
                if not match:
                    logger.warning(f"Could not parse row number from custom_id: '{custom_id}'. Skipping.")
                    continue
                row = int(match.group(1))

                # Extract AI response from the nested dictionary
                ai_output = None
                result_data = result_dict.get('result')
                if result_data and result_data.get('type') == 'succeeded':
                    message_data = result_data.get('message')
                    if message_data and message_data.get('content'):
                        content_list = message_data.get('content', [])
                        if content_list and content_list[0].get('type') == 'text':
                            ai_output = content_list[0].get('text')

                if not ai_output:
                    # Log the error if present
                    error_data = None
                    if result_data and result_data.get('type') == 'error':
                         error_data = result_data.get('error')

                    if error_data:
                        logger.warning(f"AI response for row {row} failed. Error: {error_data.get('message', 'Unknown error')}")
                    else:
                        logger.warning(f"No content found in AI response for row {row} (batch {batch_id}). Skipping.")
                    continue

                # --- Check if the note already exists in the sheet ---
                # This logic is more complex now because we don't have a direct get_cell_value method
                current_status = ""
                try:
                    sheet_name = sheet_manager.sheets_config['main_tab_name']
                    status_col_name = config.get('google_sheets.status_column_name', 'Go?')
                    
                    # Get the 0-based index of the status column
                    col_index = sheet_manager._get_column_index(sheet_id, sheet_name, status_col_name)
                    
                    if col_index is not None:
                        # Fetch the entire row's data
                        row_data = sheet_manager._get_row_data(sheet_id, sheet_name, row)
                        if row_data and col_index < len(row_data):
                            current_status = row_data[col_index]
                        else:
                            logger.warning(f"Could not retrieve status for row {row}. It may be empty or out of bounds.")
                    else:
                        logger.warning(f"Could not find column index for '{status_col_name}'.")

                except Exception as e:
                    logger.error(f"Error checking sheet status for row {row}: {e}")
                    # Decide if we should skip or proceed with caution
                    # For now, we'll assume it's not written and proceed
                
                # If status is 'AI' or 'SKIP', we assume it's done.
                if current_status.upper() in ['AI', 'SKIP']:
                    logger.info(f"Skipping row {row} for {friendly_name}: Note already marked as 'AI' or 'SKIP'.")
                    skipped_count += 1
                    continue
                
                logger.info(f"Found unwritten note for {friendly_name} at row {row}.")
                
                # Reconstruct original item for processing pipeline
                original_item = reconstruct_original_item_from_api_result(result_dict, editor_key)
                
                # Apply complete processing pipeline
                if args.verify:
                    logger.info("=== PROCESSING PIPELINE VERIFICATION ===")
                    logger.info(f"Raw AI output: {ai_output}")
                    logger.info(f"Original item context: {original_item}")
                
                # Step 1: Clean AI output
                cleaned_output = clean_ai_output(ai_output)
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
                    logger.debug(f"Processing pipeline complete. Final note: {final_note[:100]}...")
                
                # Step 5: Prepare update data using the standard pipeline
                update_data = prepare_update_data(original_item, final_note, logger)
                if update_data:
                    updates_for_sheet.append(update_data)
                    logger.info(f"Prepared update for {friendly_name} at row {row}.")
                else:
                    logger.error(f"Failed to prepare update data for row {row}")
                    continue

            # After processing all results in the batch, send the updates to the sheet
            if updates_for_sheet:
                if not args.dry_run:
                    logger.info(f"Writing {len(updates_for_sheet)} notes to sheet for batch {batch_id}...")
                    sheet_manager.batch_update_rows(sheet_id, updates_for_sheet)
                    logger.info(f"Successfully wrote {len(updates_for_sheet)} notes for batch {batch_id}.")
                else:
                    logger.info(f"[DRY RUN] Would write {len(updates_for_sheet)} notes for batch {batch_id}.")

        except Exception as e:
            logger.error(f"Failed to process batch {batch_id}: {e}")
            failed_count += 1

    logger.info("=" * 30)
    logger.info("API Recovery process completed.")
    logger.info(f"Notes recovered: {recovered_count}")
    logger.info(f"Notes skipped (already written): {skipped_count}")
    logger.info(f"Batches failed to process: {failed_count}")
    logger.info("=" * 30)


if __name__ == '__main__':
    main() 