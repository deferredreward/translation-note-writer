# TSV Quote Converters - Integration Guide

This guide explains how to use the TSV Quote Converters from another Python project.

## Overview

The TSV Quote Converters provide two main functions:

1. **GL to OL Conversion** (`gl2ol`): Converts English (Gateway Language) quotes to Hebrew/Greek (Original Language) quotes
2. **Add GL Columns** (`addgl`): Converts OL quotes back to GL quotes and adds `GLQuote` and `GLOccurrence` columns

## Prerequisites

1. Node.js must be installed and available in PATH
2. The tsv-quote-converters project must be built:
   ```bash
   cd /path/to/tsv-quote-converters
   npm install --legacy-peer-deps
   npm run build
   ```

## Usage from Python

### Basic Setup

```python
import subprocess
import json
import os

def call_tsv_converter(converter_path, command, bible_link, book_code, tsv_content):
    """
    Call the TSV quote converter CLI.

    Args:
        converter_path: Absolute path to the tsv-quote-converters directory
        command: 'gl2ol' or 'addgl'
        bible_link: DCS link (e.g., 'unfoldingWord/en_ult/master')
        book_code: 3-letter book code (e.g., 'JON', 'GEN', 'MAT')
        tsv_content: String containing TSV data with headers

    Returns:
        dict with 'output' (TSV string) and 'errors' (list) keys
        None if the call failed
    """
    result = subprocess.run(
        ['node', 'cli.js', command, bible_link, book_code, tsv_content],
        capture_output=True,
        text=True,
        cwd=converter_path
    )

    if result.returncode != 0:
        print(f"Error calling converter: {result.stderr}")
        return None

    return json.loads(result.stdout)
```

### Example: Round-Trip Conversion

```python
# Set the path to the converter
CONVERTER_PATH = '/path/to/tsv-quote-converters'

# Your input TSV (must include header row)
input_tsv = """Reference\tID\tTags\tQuote\tOccurrence\tNote
1:3\tkrcb\trc://*/ta/man/translate/figs-metonymy\trun & face\t1\tThis is the note"""

# Step 1: Convert English to Hebrew
result1 = call_tsv_converter(
    CONVERTER_PATH,
    'gl2ol',
    'unfoldingWord/en_ult/master',
    'JON',  # Book code for Jonah
    input_tsv
)

if result1 and result1['errors']:
    print(f"Step 1 errors: {result1['errors']}")

# Step 2: Add GL quote columns (converts Hebrew back to English)
result2 = call_tsv_converter(
    CONVERTER_PATH,
    'addgl',
    'unfoldingWord/en_ult/master',
    'JON',
    result1['output']
)

if result2 and result2['errors']:
    print(f"Step 2 errors: {result2['errors']}")

# Final output includes GLQuote and GLOccurrence columns
final_tsv = result2['output']
print(final_tsv)
```

## Commands

### `gl2ol` - Convert Gateway Language to Original Language

Converts English quotes to Hebrew (Old Testament) or Greek (New Testament) quotes.

**Input TSV must include:**
- `Reference` column (e.g., "1:3", "1:1-5")
- `Quote` column (English text)
- `Occurrence` column (integer, usually 1)

**Output:**
- Same structure, but `Quote` column contains Hebrew/Greek text
- If quote not found, `Quote` will be prefixed with "QUOTE_NOT_FOUND: "

**Example:**
```python
result = call_tsv_converter(
    '/path/to/tsv-quote-converters',
    'gl2ol',
    'unfoldingWord/en_ult/master',
    'JON',
    input_tsv
)

# result['output'] contains the TSV with Hebrew quotes
# result['errors'] contains any error messages
```

### `addgl` - Add Gateway Language Columns

Converts Original Language quotes back to Gateway Language and adds columns.

**Input TSV must include:**
- `Reference` column
- `Quote` column (Hebrew/Greek text)
- `Occurrence` column

**Output:**
- Adds `GLQuote` column (English translation)
- Adds `GLOccurrence` column (occurrence number)
- Original columns are preserved

**Example:**
```python
result = call_tsv_converter(
    '/path/to/tsv-quote-converters',
    'addgl',
    'unfoldingWord/en_ult/master',
    'JON',
    hebrew_tsv
)

# result['output'] contains TSV with GLQuote and GLOccurrence columns
```

## Bible Links

The `bible_link` parameter specifies which translation to use:

- `unfoldingWord/en_ult/master` - unfoldingWord Literal Translation (English)
- Format: `{owner}/{repo}/{ref}`

## Book Codes

Use 3-letter book codes:

**Old Testament:** GEN, EXO, LEV, NUM, DEU, JOS, JDG, RUT, 1SA, 2SA, 1KI, 2KI, 1CH, 2CH, EZR, NEH, EST, JOB, PSA, PRO, ECC, SNG, ISA, JER, LAM, EZK, DAN, HOS, JOL, AMO, OBA, JON, MIC, NAM, HAB, ZEP, HAG, ZEC, MAL

**New Testament:** MAT, MRK, LUK, JHN, ACT, ROM, 1CO, 2CO, GAL, EPH, PHP, COL, 1TH, 2TH, 1TI, 2TI, TIT, PHM, HEB, JAS, 1PE, 2PE, 1JN, 2JN, 3JN, JUD, REV

## TSV Format Requirements

1. **Tab-separated** (use `\t` as delimiter)
2. **Must include header row** with column names
3. **Required columns:**
   - `Reference`: Bible verse reference (e.g., "1:3", "2:5-7")
   - `Quote`: The quote text (GL for gl2ol, OL for addgl)
   - `Occurrence`: Integer occurrence number (usually 1)

4. **Optional columns:** Any other columns (ID, Tags, Note, etc.) will be preserved

## Error Handling

The converter returns errors in the `errors` array:

```python
result = call_tsv_converter(...)

if result:
    if result['errors']:
        for error in result['errors']:
            print(f"Error: {error}")

    # Use the output even if there are errors
    # (some rows may succeed while others fail)
    output_tsv = result['output']
else:
    print("Converter call failed completely")
```

## Complete Example

```python
#!/usr/bin/env python3
import subprocess
import json

def call_tsv_converter(converter_path, command, bible_link, book_code, tsv_content):
    result = subprocess.run(
        ['node', 'cli.js', command, bible_link, book_code, tsv_content],
        capture_output=True,
        text=True,
        cwd=converter_path
    )

    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return None

    return json.loads(result.stdout)

# Configuration
CONVERTER_PATH = '/path/to/tsv-quote-converters'
BIBLE_LINK = 'unfoldingWord/en_ult/master'
BOOK_CODE = 'JON'

# Your TSV data
tsv_data = """Reference\tID\tTags\tQuote\tOccurrence\tNote
1:3\tkrcb\trc://*/ta/man/translate/figs-metonymy\trun & face\t1\tThis is the note
1:10\tabc1\trc://*/ta/man/translate/figs-idiom\tthe men\t1\tAnother note"""

# Step 1: English to Hebrew
print("Converting English to Hebrew...")
result1 = call_tsv_converter(CONVERTER_PATH, 'gl2ol', BIBLE_LINK, BOOK_CODE, tsv_data)

if not result1:
    print("Failed at step 1")
    exit(1)

if result1['errors']:
    print(f"Step 1 errors: {result1['errors']}")

# Save intermediate result
with open('intermediate_hebrew.tsv', 'w') as f:
    f.write(result1['output'])

# Step 2: Hebrew back to English with GL columns
print("Adding GL columns...")
result2 = call_tsv_converter(CONVERTER_PATH, 'addgl', BIBLE_LINK, BOOK_CODE, result1['output'])

if not result2:
    print("Failed at step 2")
    exit(1)

if result2['errors']:
    print(f"Step 2 errors: {result2['errors']}")

# Save final result
with open('final_with_gl_columns.tsv', 'w') as f:
    f.write(result2['output'])

print("Done!")
print(result2['output'])
```

## Files in tsv-quote-converters

- **cli.js** - Node.js CLI wrapper (don't modify)
- **dist/tsv-quote-converters.mjs** - Built module (generated by `npm run build`)
- **test_roundtrip.py** - Example Python usage

## Troubleshooting

### "Cannot find module" error
Run `npm run build` in the tsv-quote-converters directory.

### "QUOTE_NOT_FOUND" in output
The English quote doesn't exist in the specified verse. Check:
1. Correct book code (JON vs GEN vs MAT, etc.)
2. Correct reference format
3. Quote text matches the actual verse

### Empty JSON output
Check that:
1. TSV includes header row
2. TSV is tab-separated (not space or comma)
3. Book code is valid 3-letter code

### Process hangs
The converter downloads Bible resources on first run. This may take 30-60 seconds. Subsequent runs are cached and faster.

## Notes

- **Caching**: Downloaded resources are cached, so first run per book is slower
- **Testament Detection**: Old Testament books use Hebrew, New Testament uses Greek
- **Quote Separator**: Use ` & ` (space-ampersand-space) to separate multiple quote parts
- **Occurrence**: If a quote appears multiple times in a verse, use occurrence to specify which one
