# Quick Reference: Language Conversion Command

## Basic Usage

```bash
# Run for all sheets
python3 main.py --convert-language

# Test first (recommended)
python3 main.py --convert-language --dry-run

# With debug info
python3 main.py --convert-language --debug
```

## What It Updates

| Column | Description | Example |
|--------|-------------|---------|
| GLQuote | English text (roundtripped) | "the word of Yahweh" |
| OrigL | Hebrew/Greek text | "דְּבַר־יְהוָה" |
| ID | Unique 4-char identifier | "a1b2" |

## When to Use

✅ **Use `--convert-language` when you want to:**
- Refresh conversion data without AI processing
- Test conversions with `--dry-run`
- Generate/update IDs
- Fix conversion errors
- Prepare data before AI processing

❌ **Don't use it when:**
- You want AI processing too (use normal mode instead)
- Conversions are already correct and up-to-date

## Requirements

- ✅ `Book` column in your spreadsheet
- ✅ Valid book codes (GEN, EXO, MAT, etc.)
- ✅ At least some rows with data

## Common Issues

### "Could not detect book"
→ Check that `Book` column exists and has valid 3-letter codes

### "No items found"
→ Verify the sheet has data rows (not just headers)

### Conversion errors
→ Check logs for details: `logs/translation_notes_*.log`

## See Also

- **LANGUAGE_CONVERSION.md** - Full documentation
- **INTEGRATION_GUIDE.md** - Technical details
- **README.md** - Main documentation

