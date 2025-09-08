# Linux Setup Instructions

## Quick Setup (after transfer)

1. **Set up Python environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

2. **Set permissions:**
   ```bash
   chmod +x run_translation_notes.sh
   chmod 600 .env
   chmod 600 config/google_credentials.json
   ```

3. **Test the application:**
   ```bash
   source venv/bin/activate
   python main.py --mode complete --dry-run
   ```

4. **Set up cron job:**
   ```bash
   crontab -e
   # Add this line for every 30 minutes:
   */30 * * * * /full/path/to/run_translation_notes.sh
   ```

## Full instructions in LINUX_MIGRATION.md
