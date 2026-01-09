# Language Conversion (Roundtrip) Feature

## Overview

The **roundtrip language conversion** feature performs English→Hebrew/Greek→English conversion for translation notes. This enriches your translation notes with:

- **GLQuote**: Gateway Language (English) quote text (roundtripped)
- **OrigL**: Original Language (Hebrew/Greek) quote text
- **ID**: Unique identifier for each note

## How It Works

1. Takes English quotes from the `GLQuote` column (or `Quote` if GLQuote is empty)
2. Converts them to Hebrew/Greek using the Original Language Bible text
3. Converts back to English to verify the roundtrip
4. Populates the `GLQuote`, `OrigL`, and `ID` columns in your spreadsheet

This process uses the [tsv-quote-converters](https://github.com/unfoldingWord/tsv-quote-converters) library.

## Usage

### Standalone Command

Run the roundtrip conversion independently without AI processing:

```bash
# Convert all sheets
python3 main.py --convert-language

# Dry run (see what would be updated without making changes)
python3 main.py --convert-language --dry-run

# With debug logging
python3 main.py --convert-language --debug
```

### Automatic Processing

The roundtrip conversion runs **automatically** during normal AI processing:

```bash
# Runs conversion + AI processing
python3 main.py --mode complete

# Runs conversion + AI processing in continuous mode
python3 main.py --mode continuous
```

The conversion happens **before** AI processing, ensuring that GLQuote, OrigL, and ID are populated before the AI generates notes.

## What Gets Updated

The command updates these columns in your spreadsheet:

| Column | Description | Example |
|--------|-------------|---------|
| **GLQuote** | Roundtripped English text | "the word of Yahweh" |
| **OrigL** | Hebrew/Greek original text | "דְּבַר־יְהוָה" |
| **ID** | Unique 4-character ID | "abc1" |

## When to Use Standalone Mode

Use `--convert-language` by itself when you want to:

1. **Refresh conversion data** without running AI processing
2. **Test the conversion** with `--dry-run` to see what would change
3. **Update IDs** for notes that don't have them yet
4. **Fix conversion errors** by rerunning the conversion
5. **Prepare data** before AI processing (useful for debugging)

## Benefits

### ✅ Separation of Concerns
- Language conversion is independent of AI processing
- Test and debug conversion separately

### ✅ Fast Feedback
- See conversion results immediately without waiting for AI
- Verify Hebrew/Greek mappings are correct

### ✅ Reusable IDs
- Generated IDs are stable and unique
- Can be used for cross-referencing notes

### ✅ Future Integration
- Can be triggered from spreadsheet (future feature)
- Supports batch processing of multiple sheets

## Technical Details

### Book Detection
The system automatically detects the book being processed from the `Book` column in your spreadsheet. Supported books include:

- Old Testament: GEN, EXO, LEV, NUM, DEU, JOS, JDG, RUT, 1SA, 2SA, etc.
- New Testament: MAT, MRK, LUK, JHN, ACT, ROM, 1CO, 2CO, etc.

### ID Generation
IDs are generated using a deterministic algorithm that:
- Creates 4-character alphanumeric IDs (e.g., "a1b2")
- Ensures uniqueness within each book
- Checks against existing IDs in the sheet and upstream TSV files
- Uses fallback generation if primary method fails

### Caching
The conversion uses intelligent caching to:
- Cache Bible text lookups for better performance
- Avoid redundant API calls
- Store conversion results for reuse

## Examples

### Example 1: Basic Conversion

```bash
cd /home/bmw/Documents/Github/tnwriter-dev
python3 main.py --convert-language
```

Output:
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

### Example 2: Dry Run

```bash
python3 main.py --convert-language --dry-run
```

Output shows what would be updated without making changes:
```
🔄 Running roundtrip language conversion for 3 sheet(s)...

📋 Processing Editor 1 (1abc2def...)...
  📖 Book: JON
  📝 Items: 42
  🔍 DRY RUN: Would update 42 item(s)
```

### Example 3: With Debug Logging

```bash
python3 main.py --convert-language --debug
```

Shows detailed conversion information in logs.

## Troubleshooting

### "Could not detect book"

**Problem**: The system cannot determine which book is being processed.

**Solution**: 
- Ensure your spreadsheet has a `Book` column
- Use standard 3-letter book codes (GEN, EXO, MAT, MRK, etc.)
- Check that rows have valid book codes filled in

### "No items found"

**Problem**: The sheet appears empty or has no processable items.

**Solution**:
- Check that your spreadsheet has the correct tab name (default: "AI notes")
- Verify that there are rows with data (not just headers)
- Ensure columns are properly set up

### Conversion Errors

**Problem**: Some items fail to convert.

**Solution**:
- Check the log file for detailed error messages
- Verify that GLQuote values are valid English text
- Ensure Reference column has valid Bible references (e.g., "1:1")

## Integration with Spreadsheet (Future)

In the future, you'll be able to trigger this conversion directly from your Google Sheet by:
1. Setting a special flag in a designated cell
2. The system detecting the flag during its monitoring cycle
3. Running the conversion automatically
4. Clearing the flag when complete

This is already supported by the CLI infrastructure and can be easily added when needed.

## See Also

- **INTEGRATION_GUIDE.md**: Technical details on the tsv-quote-converters integration
- **README.md**: Main documentation
- **modules/language_converter.py**: Implementation details

