# Integration Setup - Copy to Your Project

This guide explains how to integrate the TSV Quote Converters into your project while keeping the upstream repo clean.

## Architecture

```
your-project/                           # Your integration project
├── cli.js                             # Copy cli_for_integration.js here
├── tsv_converter_wrapper.py           # Copy this file here
└── .cache/
    └── tsv_resources/                 # Auto-created cache directory

tsv-quote-converters/                  # Kept pristine
├── dist/tsv-quote-converters.mjs      # Built module
├── src/                               # Source (update from upstream)
└── package.json
```

## Setup Steps

### 1. Build the Converter (One-time)

```bash
cd tsv-quote-converters
npm install --legacy-peer-deps
npm run build
```

This creates `dist/tsv-quote-converters.mjs` that your integration will use.

### 2. Copy Integration Files to Your Project

```bash
# From tsv-quote-converters directory
cp cli_for_integration.js /path/to/your-project/cli.js
cp tsv_converter_wrapper.py /path/to/your-project/
```

### 3. Update Path in cli.js

Edit `cli.js` in your project and update the `CONVERTER_PATH`:

```javascript
// If tsv-quote-converters is in parent directory:
const CONVERTER_PATH = '../tsv-quote-converters/dist/tsv-quote-converters.mjs';

// If in same directory:
const CONVERTER_PATH = './tsv-quote-converters/dist/tsv-quote-converters.mjs';

// Or use absolute path:
const CONVERTER_PATH = '/home/user/projects/tsv-quote-converters/dist/tsv-quote-converters.mjs';
```

### 4. Install Python Dependencies (if needed)

```bash
pip install requests  # Only needed for cache checking
```

## Usage in Your Python Project

```python
from tsv_converter_wrapper import TSVConverter

# Initialize
converter = TSVConverter()

# Your TSV data
tsv_data = """Reference\tID\tTags\tQuote\tOccurrence\tNote
1:3\tkrcb\trc://*/ta/man/translate/figs-metonymy\trun & face\t1\tThis is the note"""

# Option 1: Round-trip with caching
result = converter.roundtrip(
    bible_link='unfoldingWord/en_ult/master',
    book_code='JON',
    tsv_content=tsv_data,
    use_cache=True,
    verbose=True
)

print(result['output'])  # TSV with GLQuote and GLOccurrence columns

# Option 2: Just GL to OL conversion
result = converter.convert_gl_to_ol(
    bible_link='unfoldingWord/en_ult/master',
    book_code='JON',
    tsv_content=tsv_data,
    use_cache=True,
    verbose=True
)

print(result['output'])  # TSV with Hebrew/Greek quotes
```

## How Caching Works

The Python wrapper:

1. **Checks Git commits** - Queries DCS API for latest commit SHA of the specific book file
2. **Compares with cache** - If cached SHA matches latest SHA, uses cache
3. **Auto-updates** - If upstream has new commits, re-downloads automatically
4. **Per-book caching** - Each book/translation combination is cached separately

### Cache Management

```python
from tsv_converter_wrapper import TSVConverter

converter = TSVConverter()

# View cache stats
stats = converter.cache.get_stats()
print(f"Cached files: {stats['total_files']}")
print(f"Total size: {stats['total_size']:,} bytes")

# Clear cache (force re-download)
converter.cache.clear_cache()

# Disable cache for one call
result = converter.convert_gl_to_ol(..., use_cache=False)
```

## Updating from Upstream

When the tsv-quote-converters upstream is updated:

```bash
cd tsv-quote-converters
git pull origin main
npm install --legacy-peer-deps  # if package.json changed
npm run build

# That's it! Your integration files stay untouched
```

The cache will automatically detect the new commits and re-download as needed.

## Advantages of This Setup

✅ **Clean upstream repo** - No merge conflicts, just pull updates
✅ **Intelligent caching** - Only downloads when upstream actually changes
✅ **Per-book granularity** - Each book cached separately
✅ **Works offline** - Uses cache when network unavailable
✅ **Automatic updates** - Detects upstream changes automatically
✅ **Zero configuration** - Cache location and management handled automatically

## Files You Should Copy

From `tsv-quote-converters/` to your project:

1. ✅ `cli_for_integration.js` → `cli.js` (update path inside)
2. ✅ `tsv_converter_wrapper.py` (use as-is)
3. ❌ Don't copy anything else - reference the built module directly

## Troubleshooting

### "Cannot find module" error

- Check `CONVERTER_PATH` in `cli.js` points to correct location
- Verify `tsv-quote-converters/dist/tsv-quote-converters.mjs` exists
- Run `npm run build` in tsv-quote-converters if needed

### Cache not working

- Check `.cache/tsv_resources/` directory is writable
- Install `requests`: `pip install requests`
- Run with `verbose=True` to see cache status messages

### "Network timeout" errors

The cache manager will fall back to cached data if the network check fails, so your code continues working even with network issues.

## Example Integration Project Structure

```
my-translation-project/
├── cli.js                          # From cli_for_integration.js
├── tsv_converter_wrapper.py        # Caching wrapper
├── my_main_script.py               # Your code using the wrapper
├── .cache/
│   └── tsv_resources/
│       ├── abc123.json             # Cached JON resources
│       └── def456.json             # Cached GEN resources
└── tsv-quote-converters/           # Git submodule or sibling directory
    ├── dist/
    │   └── tsv-quote-converters.mjs
    └── ...
```

## Git Submodule Option (Advanced)

If you want to manage tsv-quote-converters as a submodule:

```bash
cd your-project
git submodule add https://github.com/username/tsv-quote-converters.git
cd tsv-quote-converters
npm install --legacy-peer-deps
npm run build
cd ..

# Update cli.js:
# const CONVERTER_PATH = './tsv-quote-converters/dist/tsv-quote-converters.mjs';
```

Then update with:
```bash
git submodule update --remote
cd tsv-quote-converters && npm run build
```
