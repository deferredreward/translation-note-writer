# Translation Notes AI

A Python application that automates the creation of Bible translation notes using AI, with batch processing and intelligent caching to minimize costs and maximize efficiency.

## 🌟 Features

### Core Processing
- **Batch Processing**: Process 2 items at a time using Anthropic's Batch API for 50% cost savings
- **Immediate Mode**: NEW! Synchronous AI processing for predictable timing when you need results fast
- **Prompt Caching**: Cache biblical text and templates to reduce token usage
- **Continuous Monitoring**: Automatically monitors Google Sheets for new work
- **Multiple Editors**: Supports multiple editor sheets simultaneously

### AI & Templates
- **Intelligent Template Selection**: Dynamic system prompt selection and template type filtering
- **Enhanced Instruction Following**: Improved AI adherence to `t:` template hints and `i:` required information
- **Complete Processing Pipeline**: Consistent note formatting with smart quotes and proper post-processing

### Reliability & Recovery
- **Enhanced Debugging**: Comprehensive exit debugging, heartbeat logging, and health checks
- **Graceful Shutdown**: Multi-level shutdown controls (soft stop → graceful → force exit)
- **Recovery Scripts**: Recover lost notes from logs or API when processing is interrupted
- **Error Handling**: Robust error handling with email notifications

## 🚀 Quick Start

### 1. Setup

```bash
# Clone or download the project
cd translation_notes_ai

# Run the setup script
python setup.py
```

### 2. Configure API Keys

Edit the `.env` file:

```env
# Anthropic API Configuration
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Google Sheets Configuration - Editor Sheet IDs
SHEET_ID_EDITOR1=your_sheet_id_here
SHEET_ID_EDITOR2=your_sheet_id_here
SHEET_ID_EDITOR3=your_sheet_id_here
SHEET_ID_EDITOR4=your_sheet_id_here
SHEET_ID_EDITOR5=your_sheet_id_here

# Editor Names (for logging and display purposes)
EDITOR1_NAME=Alice
EDITOR2_NAME=Bob
EDITOR3_NAME=Charlie
EDITOR4_NAME=David
EDITOR5_NAME=Eve

# Reference sheets
SUPPORT_REFERENCES_SHEET_ID=your_sheet_id_here
TEMPLATES_SHEET_ID=your_sheet_id_here
SYSTEM_PROMPTS_SHEET_ID=your_sheet_id_here

# Email Configuration (for error notifications)
EMAIL_FROM=your_email@gmail.com
EMAIL_TO=your_notification_email@gmail.com
EMAIL_PASSWORD=your_app_password_here
```

**Note**: Use the `env_example.txt` file as a template for your environment configuration.

### 3. Setup Google Sheets API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the Google Sheets API
4. Create a service account
5. Download the credentials JSON file
6. Save it as `config/google_credentials.json`

### 4. Configure Environment Variables

Create your `.env` file from the template:

```bash
# Copy the example file  
cp env_example.txt .env
```

Edit `.env` to configure your sheet IDs and other sensitive settings:

```env
# Anthropic API Configuration
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Google Sheets Configuration - Editor Sheet IDs
SHEET_ID_EDITOR1=your_sheet_id_here
SHEET_ID_EDITOR2=your_sheet_id_here
SHEET_ID_EDITOR3=your_sheet_id_here
SHEET_ID_EDITOR4=your_sheet_id_here
SHEET_ID_EDITOR5=your_sheet_id_here

# Editor Names (for logging and display purposes)
EDITOR1_NAME=Alice
EDITOR2_NAME=Bob
EDITOR3_NAME=Charlie
EDITOR4_NAME=David
EDITOR5_NAME=Eve

# Reference sheets
SUPPORT_REFERENCES_SHEET_ID=your_sheet_id_here
TEMPLATES_SHEET_ID=your_sheet_id_here
SYSTEM_PROMPTS_SHEET_ID=your_sheet_id_here

# Email Configuration (for error notifications)
EMAIL_FROM=your_email@gmail.com
EMAIL_TO=your_notification_email@gmail.com
EMAIL_PASSWORD=your_app_password_here
```

**Note**: Use the `env_example.txt` file as a template for your environment configuration.

### 5. Test Configuration

Verify your configuration is working:

```bash
# Test configuration migration
python test_config_migration.py
```

### 6. Language Conversion (Optional)

Run the roundtrip English→Hebrew/Greek→English conversion to populate `GLQuote`, `OrigL`, and `ID` columns:

```bash
# Run language conversion for all sheets
python3 main.py --convert-language

# Test without making changes
python3 main.py --convert-language --dry-run
```

See [LANGUAGE_CONVERSION.md](LANGUAGE_CONVERSION.md) for detailed documentation.

### 7. Run the Application

```bash
# Activate virtual environment
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# Default mode - run until all work complete (perfect for cron)
python main.py

# Test run (dry run mode)
python main.py --mode once --dry-run --debug

# Disable AI calls entirely
python main.py --mode complete --noai

# Start continuous monitoring (old behavior)
python main.py --mode continuous

# Run language conversion only
python main.py --convert-language

# Convert SRef values
python main.py --convert-sref

# Show cache status
python main.py --cache-status

# Show batch processing status
python main.py --status
```

## 🔄 Processing Modes

The system supports three distinct processing modes to suit different workflows:

### Complete Mode (Default) ⭐ - Perfect for Cron Jobs

**Complete Mode** runs until no work is found across all sheets, then exits cleanly. This is the new default mode and is perfect for scheduled automation.

```bash
python main.py                    # Default complete mode
python main.py --mode complete    # Explicit complete mode
```

**Key Features:**
- Processes multiple cycles until no work remains
- Exits cleanly when done (perfect for cron scheduling)
- Processes all spreadsheets in each cycle
- Handles multiple chapters of work automatically
- Logs comprehensive cycle and item counts

**Ideal for:**
- Scheduled cron jobs (e.g., every 30 minutes)
- Automated processing without manual intervention  
- Processing batches of work that may span multiple chapters
- Production deployments on Linux servers

**Example cron setup:**
```bash
# Run every 30 minutes
*/30 * * * * cd /path/to/translation-note-writer && python main.py >> logs/cron.log 2>&1
```

### Continuous Mode - Long-Running Monitoring

**Continuous Mode** provides long-running monitoring that never stops, continuously watching for new work.

```bash
python main.py --mode continuous
```

**Key Features:**
- Runs indefinitely until manually stopped
- Real-time monitoring of all spreadsheets
- Advanced continuous batch processing
- Graceful shutdown controls (Ctrl+C sequences)

**Ideal for:**
- Development and testing environments
- Manual monitoring sessions
- When you need real-time responsiveness

### Once Mode - Single Cycle Processing

**Once Mode** processes a single cycle of work and exits immediately.

```bash
python main.py --mode once
```

**Ideal for:**
- Quick one-time processing
- Testing and debugging
- Processing specific batches manually

## 🚀 Advanced Batch Processing

The system features an advanced **continuous batch processing** engine that dramatically improves efficiency and responsiveness:

### Key Features

**🔄 Continuous Processing**: Instead of waiting for entire batch groups to complete, the system:
- Continuously monitors all user sheets for new work
- Submits new batches immediately when slots become available  
- Maintains maximum batch throughput at all times
- Processes multiple users simultaneously

**📊 Smart Queue Management**:
- Work from all users is queued and prioritized
- Automatic load balancing across users
- User-specific cache management for biblical text
- Proper tracking ensures results go to the correct sheet

**⚡ Improved Responsiveness**:
- New work is detected and processed much faster
- No waiting for batch groups to complete
- Optimal utilization of API rate limits
- Reduced overall processing time

### Usage

**Default Mode** (Continuous Processing):
```bash
python main.py --mode continuous
```

**Legacy Mode** (Synchronous Processing):
```bash
python main.py --mode continuous --legacy-processing
```

**Monitor Status**:
```bash
python main.py --status
```

### Configuration

Control the behavior in `config/config.yaml`:

```yaml
# Processing Configuration
processing:
  use_continuous_batch_processing: true  # Enable continuous mode
  permission_block_hours: 1  # Block sheets for 1 hour after 403 errors
  
# Anthropic Configuration  
anthropic:
  max_concurrent_batches: 8  # Max simultaneous batches
  batch_poll_interval: 60    # How often to check batch status
  batch_group_poll_interval: 60  # Polling frequency
```

### Error Handling

**Permission Error Protection**: The system automatically handles permission denied errors:
- If a sheet returns a 403 permission error, it's blocked for 1 hour (configurable)
- System continues processing other sheets normally
- Blocked sheets are automatically retried after the block period expires
- Status command shows which sheets are currently blocked

### Example Workflow

1. **Alice** adds 5 items to their sheet
2. **Bob** adds 3 items to their sheet  
3. System immediately:
   - Detects work from both users (logs show "Alice" and "Bob" instead of "editor1", "editor2")
   - Submits batches for both (respecting max concurrent limit)
   - Continues monitoring for more work
4. As batches complete:
   - Results are written to correct user's sheet
   - New batch slots become available
   - System immediately fills slots with queued work

This ensures maximum efficiency and eliminates the bottleneck of waiting for batch groups to complete sequentially.

## ⚡ Immediate Mode Processing

When you need predictable timing instead of cost optimization, **immediate mode** provides synchronous AI processing for urgent work.

### When to Use Immediate Mode

**Use Immediate Mode when:**
- You need results within minutes, not hours
- Processing small numbers of items (≤10)
- Batch queue timing is unpredictable
- Working on urgent/time-sensitive translations

**Use Batch Mode when:**
- Cost optimization is priority
- Processing large numbers of items
- Can wait for optimal batch timing
- Normal production workflow

### Usage

```bash
# Enable immediate mode for predictable timing
python main.py --mode continuous --immediate-mode

# Immediate mode respects the same keyboard controls:
# Ctrl+C once:  Soft stop (finish current items)
# Ctrl+C twice: Graceful shutdown  
# Ctrl+C three: Force exit
```

### How It Works

**Immediate Mode:**
- Makes synchronous API calls (1-2 seconds per item)
- No batching delays or queue waiting
- Rate limited (1 second between requests by default)
- Safety limit (max 10 items by default)
- Same processing pipeline as batch mode

**Configuration:**
```yaml
anthropic:
  immediate_mode_delay: 1.0        # Seconds between immediate requests
  immediate_mode_max_items: 10     # Safety limit per work cycle
```

## 🔧 Recovery Scripts

When processing is interrupted, two specialized recovery scripts help recover lost work:

### recover_notes.py - Recover from Log Files
**Purpose**: Extract completed AI responses from logs that failed to write to sheets

```bash
# Recover notes from recent logs
python recover_notes.py logs/translation_notes_20250821_143022.log

# Dry run to see what would be recovered
python recover_notes.py logs/recent.log --dry-run

# Verify complete processing pipeline
python recover_notes.py logs/recent.log --verify
```

**When to use:**
- App crashed after AI processing but before sheet updates
- You see "Final formatted note for X:Y:" in logs
- Network issues prevented sheet writing

### recover_from_api.py - Recover from Anthropic API
**Purpose**: Fetch results directly from Anthropic for submitted but unprocessed batches

```bash
# Recover batches from API
python recover_from_api.py logs/translation_notes_20250821_143022.log

# Preview what would be recovered
python recover_from_api.py logs/recent.log --dry-run --verify
```

**When to use:**
- Batches were submitted but app crashed before processing results
- You see "Submitted AI batch... ID: msgbatch_xxxxx" without corresponding "Processed batch"
- Batch processing was interrupted mid-flight

### Recovery Script Features

Both scripts now include:
- **Complete Processing Pipeline**: Same formatting as normal processing
- **Smart Context Reconstruction**: Rebuilds original item context from logs
- **Verification Mode**: `--verify` flag shows complete processing steps
- **Enhanced Error Handling**: Detailed logging and recovery information
- **Dry Run Support**: Preview recovery without making changes

### Usage Tips

1. **Check logs first**: `grep "Final formatted note\|Submitted AI batch" logs/recent.log`
2. **Use dry run**: Always test with `--dry-run` first
3. **Verify processing**: Use `--verify` to see the complete pipeline
4. **Check timing**: Recover recent logs first (API batch results expire after 24 hours)

## 📋 How It Works

### Workflow Overview

1. **Monitor Sheets**: Continuously checks Google Sheets for rows where `Go?` column contains any value except "AI"
2. **Fetch Context**: Retrieves cached biblical text (ULT/UST), templates, and support references
3. **Batch Processing**: Groups items into batches of 2 for cost-effective AI processing
4. **AI Generation**: Uses Claude 3.5 Sonnet with prompt caching to generate translation notes
5. **Update Sheets**: Updates the sheets with generated notes and marks `Go?` as "AI"

### Note Types

The system handles three types of translation notes:

- **Given AT**: When an alternate translation is already provided
- **Writes AT**: When the AI needs to create both the note and alternate translation
- **See How**: Reference notes that point to similar expressions in other verses

### Intelligent Template Selection

The system now features intelligent template selection based on:

- **Dynamic System Prompt Selection**: Automatically chooses between system prompts that generate alternate translations vs. those that use provided ones, based on whether the template contains "Alternate translation:"
- **Template Type Filtering**: When editors provide `t:` instructions (e.g., `t:cognate accusative`), the system uses a two-tier approach:
  1. **Exact Match**: Finds templates with exactly matching `type` field
  2. **AI-Assisted Selection**: If no exact match, provides enhanced instructions for the AI to select from available templates based on the hint
- **Improved Instruction Following**: Enhanced template text generation provides clearer directives to the AI for better adherence to specific template requirements

### Caching Strategy

- **Biblical Text**: ULT and UST chapters are cached and refreshed hourly
- **Templates**: Translation note templates are cached and refreshed daily
- **Support References**: Cached for 1 year (rarely change, ~2x per year) - use manual refresh
- **Content-Based Updates**: Only updates caches when content actually changes
- **Smart Anthropic Caching**: Updates Anthropic prompt cache only when content changes
- **Prompt Caching**: Uses Anthropic's prompt caching for system messages and biblical context

### Intelligent Cache Management

The system now features intelligent caching that:

1. **Compares Content**: Uses SHA256 hashes to detect actual content changes
2. **Minimizes API Calls**: Only refreshes when content has actually changed
3. **Preserves Anthropic Cache**: Maintains Anthropic prompt cache efficiency across runs
4. **Time-Based Fallback**: Still respects time-based refresh intervals as a safety net
5. **Manual Override**: Allows force refresh when needed
6. **Stable Data Optimization**: Support references cached for 1 year since they rarely change

### SRef Conversion

The system includes automatic conversion of short SRef values to full support reference names:

**URL Path Trimming**: RC URL patterns are automatically processed:
- `rc://*/ta/man/translate/figs-ellipsis` → `figs-ellipsis`
- `rc://*/ta/man/translate/figs-abstractnouns` → `figs-abstractnouns`
- Any URL starting with `rc://` is trimmed to extract only the final part after the last `/`

**Short Form Mappings**: Common abbreviations are automatically converted:
- `you` → `figs-you`
- `metaphor` → `figs-metaphor`
- `pronouns` → `writing-pronouns`
- `quotations` → `figs-quotations`
- `connecting` → `grammar-connect-words-phrases`
- `background` → `writing-background`
- And many more...

**Support Reference Matching**: The system also matches partial strings against the full support references database to find the correct full reference name.

**Usage**: 
- Run `python main.py --convert-sref` to convert all SRef values across all sheets
- Works regardless of `Go?` column status - processes all rows with SRef fields
- Use `--dry-run` flag to preview changes without applying them
- Automatically fetches support references if not cached

## ⚙️ Configuration

### Main Configuration (`config/config.yaml`)

Key settings you might want to adjust:

```yaml
# Processing settings
processing:
  poll_interval: 60  # Check for work every 60 seconds
  
  # Flexible processing filters
  process_go_values: ["*"]  # "*" processes any non-empty value
                            # Or specify exact values: ["YES", "GO", "READY"]
  skip_go_values: ["AI"]    # Skip these values (case-insensitive)
  
# Batch settings
anthropic:
  batch_size: 2  # Process 2 items at a time
  model: "claude-3-5-sonnet-20241022"
  
# Cache settings
cache:
  biblical_text_refresh: 60    # Refresh ULT/UST every hour
  templates_refresh: 1440      # Refresh templates daily (24 hours)
  support_refs_refresh: 525600 # Refresh support references yearly (rarely change)
  enable_content_comparison: true  # Compare content hashes
  force_anthropic_cache_update: true  # Update Anthropic cache when content changes
```

### Prompts Configuration (`config/prompts.yaml`)

Customize AI prompts and system messages:

```yaml
# NOTE: System prompts are now fetched from Google Sheets
# Configure the system_prompts_sheet in config.yaml

note_prompts:
  given_at_prompt: |
    Create a note to help Bible translators...
```

**System Prompts**: System prompts are now fetched from the Google Sheet specified in `config.yaml` under `google_sheets.system_prompts_sheet`. The sheet should have this format:
- Row 1: Headers (e.g., "Given AT", "AI writes AT")  
- Row 2: Prompt content (the actual system messages)

Example sheet layout:
| A1: Given AT | B1: AI writes AT |
|--------------|------------------|
| A2: You are an expert Bible translation consultant... | B2: You are an expert Bible translation consultant specializing in creating alternate translations... |

This allows you to update system prompts without modifying code files.

## 🔧 Command Line Options

```bash
python main.py [OPTIONS]

Options:
  --mode {continuous,once,complete}  Run mode (default: complete)
  --config PATH            Path to config file
  --debug                  Enable debug logging
  --dry-run               Dry run mode (no actual updates)
  --noai                  Disable all AI API calls for testing
  
  # Processing Options
  --legacy-processing     Use legacy synchronous processing instead of continuous batch processing
  --immediate-mode        NEW! Use immediate/synchronous AI processing for predictable timing
  --sound-notifications   Play sound notifications when AI writes results to spreadsheet
  --status                Show current batch processing status and exit
  
  # Cache Management Options
  --force-refresh-templates  Force refresh template cache and exit
  --force-refresh-support-refs Force refresh support references cache and exit
  --cache-status            Show cache status and exit
  --clear-cache {all,templates,ult_chapters,ust_chapters,support_references,system_prompts}
                           Clear specified cache and exit
  --convert-sref           Convert short SRef values to full support reference names and exit
  --help                   Show help message
```

### Examples

```bash
# Basic Usage
python main.py                            # Default: complete mode (run until no work found)
python main.py --mode once --debug        # Run once in debug mode
python main.py --dry-run                  # Dry run to test without making changes
python main.py --mode continuous --debug  # Continuous monitoring with debug logging

# Processing Mode Options  
python main.py --mode complete                        # Complete until no work (default)
python main.py --mode continuous                      # Continuous monitoring
python main.py --mode once                           # Single cycle only
python main.py --mode continuous --immediate-mode     # NEW! Immediate processing for predictable timing
python main.py --mode continuous --legacy-processing  # Legacy synchronous processing

# Enhanced Debugging & Control
python main.py --mode continuous --sound-notifications  # Enable sound notifications
python main.py --status                                # Check batch processing status
python main.py --noai                                  # Disable AI calls for testing

# Cache Management
python main.py --cache-status              # Show cache status
python main.py --force-refresh-templates   # Force refresh templates
python main.py --force-refresh-support-refs # Force refresh support references
python main.py --clear-cache templates     # Clear template cache
python main.py --clear-cache all          # Clear all caches

# SRef Conversion
python main.py --convert-sref             # Convert short SRef values to full names
python main.py --convert-sref --dry-run   # Preview SRef conversions without applying
```

## 📊 Monitoring and Logs

### Enhanced Debugging Features

The system now includes comprehensive debugging and monitoring:

**Exit Debugging:**
- Catches all unhandled exceptions and thread failures
- Logs exactly when and why the application exits
- Provides detailed stack traces for silent exits

**Heartbeat Monitoring:**
- Logs application status every 5 minutes
- Shows active threads, batch manager status, and health checks
- Helps identify when and where processing stops

**Graceful Shutdown Controls:**
```bash
# Three-level shutdown system:
Ctrl+C once:  🛑 SOFT STOP (no new requests, wait for pending)
Ctrl+C twice: ⚠️  GRACEFUL SHUTDOWN (stop processing) 
Ctrl+C three: 💥 FORCE EXIT (immediate termination)
```

**Startup Information:**
- Process ID, Python version, working directory
- Processing mode status (batch/immediate/legacy)
- Keyboard shortcut reminders

### Log Files

Logs are stored in the `logs/` directory:

- `translation_notes.log`: Main application log
- `translation_notes_YYYYMMDD_HHMMSS.log`: Timestamped logs
- Automatic log rotation when files get too large
- Enhanced debugging shows:
  - Thread status and health checks
  - Batch processing progress
  - Silent exit causes and timing
  - Complete error stack traces

### Error Notifications

When enabled, the system will email error notifications:

- Maximum one email per 10 minutes
- Collects multiple errors into a single email
- Enhanced error context and debugging information
- Configurable in `config/config.yaml`

## 💰 Cost Optimization

### Batch Processing Benefits

- **50% Cost Reduction**: Anthropic's Batch API offers 50% discount
- **Efficient Processing**: Process multiple items together
- **Reduced API Calls**: Fewer individual requests

### Prompt Caching Benefits

- **Reduced Token Usage**: Cache biblical text and templates
- **Faster Processing**: Cached content doesn't count toward input tokens
- **Smart Caching**: Automatically manages cache expiration

### Estimated Costs

With batch processing and caching, typical costs per note:

- **Input tokens**: ~500-1000 tokens (with caching)
- **Output tokens**: ~200-500 tokens
- **Cost per note**: ~$0.01-0.03 (with batch discount)

## 🛠️ Development

### Project Structure

```
translation_notes_ai/
├── main.py                          # Main application entry point
├── setup.py                        # Setup script
├── requirements.txt                # Python dependencies
├── env_example.txt                 # Environment variables template
├── config/
│   ├── config.yaml                 # Main configuration
│   ├── prompts.yaml                # AI prompts
│   └── google_credentials.json     # Google API credentials (not in git)
├── modules/
│   ├── config_manager.py           # Configuration management
│   ├── ai_service.py               # Anthropic API integration
│   ├── batch_processor.py          # Legacy batch processing logic
│   ├── continuous_batch_manager.py # New continuous batch processing
│   ├── sheet_manager.py            # Google Sheets integration
│   ├── cache_manager.py            # Caching system
│   ├── prompt_manager.py           # Prompt management
│   ├── biblical_text_scraper.py    # ULT/UST text scraping
│   ├── logger.py                   # Logging setup
│   └── error_notifier.py           # Error notifications
├── tests/
│   ├── test_sheets_access.py       # Google Sheets access verification
│   ├── test_suggestions.py         # Suggestion system component tests
│   └── sref_conversion_demo.py     # SRef conversion demonstration
├── cache/                          # Cached data (not in git)
└── logs/                           # Log files (not in git)
```

### Adding New Features

1. **New Note Types**: Add to `prompt_manager.py` and `config/prompts.yaml`
2. **New Data Sources**: Extend `cache_manager.py`
3. **New Integrations**: Add modules in `modules/` directory

## 🧪 Testing

The `tests/` directory contains scripts to verify system functionality and diagnose issues:

### Available Tests

#### Google Sheets Access Test
```bash
python tests/test_sheets_access.py
```

**Purpose**: Verifies Google Sheets API connectivity and permissions  
**What it checks**:
- Service account authentication
- Access to all configured editor sheets
- Access to reference sheets (templates, support references, system prompts)
- Provides sharing instructions if access fails

**When to use**: 
- Initial setup verification
- Troubleshooting "Google Sheets authentication failed" errors
- After adding new sheets to configuration

#### Suggestion System Test
```bash
python tests/test_suggestions.py
```

**Purpose**: Tests the suggestion functionality components  
**What it checks**:
- Translation issue descriptions loading
- Sheet Manager initialization
- Cache Manager initialization
- Component integration

**When to use**:
- Verifying suggestion system setup
- After configuration changes
- Troubleshooting suggestion-related issues

#### SRef Conversion Demo
```bash
python tests/sref_conversion_demo.py
```

**Purpose**: Demonstrates and tests SRef (Support Reference) conversion functionality  
**What it shows**:
- Converting short SRef forms to full reference names
- Support reference mapping examples
- Sample conversion results

**When to use**:
- Understanding SRef conversion behavior
- Before running `--convert-sref` on production data
- Troubleshooting SRef conversion issues

### Running Tests

1. **Prerequisites**: Ensure your environment is set up with:
   - Valid `.env` file with API keys
   - Configured `config/config.yaml`
   - Google credentials in `config/google_credentials.json`

2. **Run individual tests**:
   ```bash
   # Test Google Sheets access
   python tests/test_sheets_access.py
   
   # Test suggestion components
   python tests/test_suggestions.py
   
   # Demo SRef conversion
   python tests/sref_conversion_demo.py
   ```

3. **Interpreting results**:
   - ✅ **SUCCESS**: Component working correctly
   - ⚠️ **WARNING**: Partial functionality (check configuration)
   - ❌ **ERROR**: Component failed (check setup)

### Test Output Examples

**Successful Google Sheets test**:
```
✅ SUCCESS: Can access 'Editor1 Translation Notes'
✅ SUCCESS: Can read data
```

**Failed access requiring sharing**:
```
❌ ERROR: Cannot access sheet: Requested entity was not found
📧 Service Account Email: your-service@project.iam.gserviceaccount.com
```

## 🔍 Troubleshooting

### Common Issues

**"No API key configured"**
- Check your `.env` file has `ANTHROPIC_API_KEY` set
- Ensure the `.env` file is in the project root

**"Google Sheets authentication failed"**
- Verify `config/google_credentials.json` exists
- Check the service account has access to your sheets
- Ensure Google Sheets API is enabled

**"No pending work found"**
- Check sheet IDs in `config/config.yaml`
- Verify `Go?` column contains any value except "AI" (or values in `skip_go_values`)
- Check the sheet structure matches expected format

**Application silently exits**
- NEW: Check logs for exit debugging information
- Look for "Application is exiting..." and "Unhandled exception" messages
- Review heartbeat logs to see when processing stopped
- Check thread status in health check logs

**Batch processing fails or takes too long**
- Check Anthropic API quota and limits
- Verify network connectivity
- Review logs for specific error messages
- Consider using `--immediate-mode` for urgent small batches

**Recovery after crashes**
- Use `recover_notes.py` for completed processing that didn't write to sheets
- Use `recover_from_api.py` for submitted batches that weren't processed
- Check recent logs first: `grep "Final formatted note\|Submitted AI batch" logs/recent.log`

### Debug Mode

Run with `--debug` flag for detailed logging:

```bash
python main.py --debug --dry-run
```

### Dry Run Mode

The `--dry-run` flag enables a safe testing mode that:
- Prevents all AI API calls
- Prevents any changes to Google Sheets
- Shows detailed information about what would happen
- Logs what templates would be used
- Shows what prompts would be sent
- Simulates the entire processing flow

This is perfect for:
- Testing configuration changes
- Verifying template matching
- Checking prompt construction
- Debugging without using API credits
- Validating sheet access

Example:
```bash
python main.py --mode once --dry-run
```

## 📝 Sheet Format

Expected Google Sheets format:

| Column | Description |
|--------|-------------|
| `row # for n8n hide, don't delete` | Row identifier |
| `SRef` | Scripture reference |
| `Go?` | Processing trigger (any value except "AI" to process) |
| `GLQuote` | Text to be addressed |
| `AT` | Alternate translation (optional) |
| `Explanation` | Additional context (supports `i:` for required info, `t:` for template type hints) |
| `AI TN` | Generated translation note (output) |

## 🤝 Support

For issues and questions:

1. Check the logs in `logs/translation_notes.log`
2. Run with `--debug` for detailed information
3. Use `--dry-run` to test without making changes
4. Review configuration files for correct settings

## 📄 License

This project is provided as-is for Bible translation work. Please ensure compliance with Anthropic's and Google's terms of service when using their APIs.