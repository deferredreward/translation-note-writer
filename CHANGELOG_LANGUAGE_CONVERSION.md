# Changelog: Language Conversion CLI Command

**Date**: December 9, 2025  
**Feature**: Standalone Language Roundtrip Conversion Command

## Summary

Added a new CLI command `--convert-language` that allows triggering the roundtrip English→Hebrew/Greek→English conversion independently, without running AI processing. This provides more flexibility and sets up infrastructure for future spreadsheet-triggered conversion.

## Changes Made

### 1. CLI Module (`modules/cli.py`)

**Added**:
- New command-line argument: `--convert-language`
- Help text: "Run roundtrip English→Hebrew/Greek→English conversion (updates GLQuote, OrigL, ID columns) and exit"
- Wired up the command in the utility commands handler
- Updated examples section to include the new command

**Lines Changed**: ~15 lines added

### 2. Main Application (`main.py`)

**Added**:
- New method: `convert_language_roundtrip()`
  - Processes all configured sheets
  - Detects book from sheet items
  - Runs language converter enrichment
  - Updates sheets with conversion data
  - Provides progress output with emojis for clarity
  - Respects `--dry-run` flag
  - Returns success/failure status

**Lines Changed**: ~95 lines added

### 3. Documentation

**Created**:
- `LANGUAGE_CONVERSION.md` - Comprehensive documentation including:
  - Overview and how it works
  - Usage examples (standalone and automatic)
  - Technical details (book detection, ID generation, caching)
  - Troubleshooting guide
  - Future integration plans
  - Examples with expected output

**Updated**:
- `README.md` - Added:
  - New Quick Start step for language conversion
  - Command examples for `--convert-language`
  - Reference to detailed documentation

## Usage

### Basic Usage

```bash
# Run language conversion for all sheets
python3 main.py --convert-language

# Test without making changes
python3 main.py --convert-language --dry-run

# With debug logging
python3 main.py --convert-language --debug
```

### What It Does

1. Reads all items from each configured Google Sheet
2. Detects the book being processed (e.g., GEN, JON, MAT)
3. Performs roundtrip conversion:
   - English → Hebrew/Greek
   - Hebrew/Greek → English
4. Updates three columns:
   - `GLQuote`: Roundtripped English text
   - `OrigL`: Hebrew/Greek original text
   - `ID`: Unique 4-character identifier
5. Writes results back to the spreadsheet

### Example Output

```
🔄 Running roundtrip language conversion for 3 sheet(s)...

📋 Processing Editor 1 (1abc2def...)...
  📖 Book: JON
  📝 Items: 42
  ✅ Successfully updated 42 item(s)

📋 Processing Editor 2 (3ghi4jkl...)...
  📖 Book: GEN
  📝 Items: 156
  ✅ Successfully updated 156 item(s)

✨ Language conversion complete!
   Successfully processed: 2/3 sheet(s)
```

## Benefits

### 1. **Independence**
- Run language conversion without AI processing
- Useful for testing, debugging, or preparing data

### 2. **Speed**
- Fast feedback on conversion results
- No waiting for AI processing

### 3. **Flexibility**
- Can be triggered manually
- Infrastructure ready for spreadsheet-triggered conversion
- Works with `--dry-run` for testing

### 4. **Separation of Concerns**
- Language conversion is separate from AI note generation
- Easier to debug issues
- Can update IDs independently

## Future Integration

The CLI infrastructure is already set up to support triggering from the spreadsheet:

1. User sets a flag in a designated cell (e.g., "Run Language Conversion")
2. Continuous monitoring detects the flag
3. System runs `convert_language_roundtrip()`
4. Flag is cleared when complete

This can be implemented by:
- Adding a method to check for the conversion flag
- Calling it in the main monitoring loop
- Using the existing `convert_language_roundtrip()` method

## Testing

### Manual Testing

```bash
# Test with dry run
python3 main.py --convert-language --dry-run

# Check help text
python3 main.py --help | grep convert-language

# Run with debug logging
python3 main.py --convert-language --debug
```

### Expected Behavior

- ✅ Command appears in help output
- ✅ Initializes application without errors
- ✅ Detects books from sheet items
- ✅ Runs conversion for each sheet
- ✅ Updates sheets with conversion data
- ✅ Respects `--dry-run` flag
- ✅ Exits cleanly with appropriate status code

## Compatibility

- **Python Version**: Python 3.6+
- **Dependencies**: Uses existing language converter and sheet manager
- **Configuration**: Uses existing config files (no new config needed)
- **Backward Compatibility**: Does not affect existing functionality

## Files Changed

1. `modules/cli.py` - Added CLI argument and handler
2. `main.py` - Added `convert_language_roundtrip()` method
3. `LANGUAGE_CONVERSION.md` - New documentation file (created)
4. `README.md` - Updated with new command examples
5. `CHANGELOG_LANGUAGE_CONVERSION.md` - This file (created)

## Related Files (No Changes)

These files are used by the feature but were not modified:

- `modules/language_converter.py` - Core conversion logic
- `modules/sheet_manager.py` - Sheet reading/writing
- `modules/processing_utils.py` - Update helper functions
- `tsv_converter_wrapper.py` - TSV conversion wrapper

## Rollback

To remove this feature:

1. Revert changes to `modules/cli.py` (remove `--convert-language` argument)
2. Revert changes to `main.py` (remove `convert_language_roundtrip()` method)
3. Delete `LANGUAGE_CONVERSION.md`
4. Revert changes to `README.md`

The feature is isolated and can be removed without affecting other functionality.

## Notes

- The feature uses the existing `LanguageConverter` class
- No new dependencies required
- No database or cache changes needed
- Works with existing Google Sheets API setup
- Respects all existing configuration options

