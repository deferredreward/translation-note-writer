# Linux Migration Guide for Translation Notes AI

This guide provides step-by-step instructions for migrating the Translation Notes AI system from Windows to Linux for production deployment with automated cron scheduling.

## 📋 Overview

The new **Complete Mode** makes this system perfect for Linux cron scheduling. It runs until no work is found, then exits cleanly - ideal for automated processing every 30 minutes without manual intervention.

## 🗂️ Files to Transfer

### ✅ Essential Files (Must Transfer)

```bash
# Core application files
main.py                    # Main application entry point
requirements.txt           # Python dependencies
setup.py                  # Setup script

# Application modules (entire directory)
modules/                   # All Python modules
├── __init__.py
├── ai_service.py
├── batch_processor.py
├── biblical_text_scraper.py
├── cache_manager.py
├── cli.py
├── config_manager.py
├── continuous_batch_manager.py
├── error_notifier.py
├── logger.py
├── notification_system.py
├── processing_utils.py
├── prompt_manager.py
├── security.py
├── sheet_manager.py
├── text_utils.py
└── tw_search.py

# Configuration files
config/
├── config.yaml           # Main configuration
├── prompts.yaml          # AI prompts configuration
└── google_credentials.json  # Google Sheets API credentials

# Environment configuration
.env                      # Environment variables (SECURE - see security notes)
env_example.txt          # Template file

# Recovery tools
recover_notes.py         # Recover from log files
recover_from_api.py      # Recover from Anthropic API

# Optional: Testing tools
tests/
├── test_sheets_access.py
├── test_suggestions.py
└── sref_conversion_demo.py
```

### ❌ Files to Leave Behind (Windows/Development Only)

```bash
# Windows-specific files
launch-writer.bat        # Windows batch file
venv/                   # Windows virtual environment

# Large cache/log files (will regenerate)
cache/                  # Will rebuild automatically
logs/                   # Historical logs (keep recent if needed)

# Development artifacts
*.json                  # Various test/debug files
prompt_simulation_output.txt
test_prompt_simulation.py
human-editor-prompt-feedback-*.txt

# Data files (will be fetched automatically)
data/                   # TW headwords (auto-downloaded)
scripts/                # Optional utility scripts
```

## 🐧 Linux Environment Setup

### Step 1: Create Project Directory

```bash
# Choose your deployment location
sudo mkdir -p /opt/translation-notes-ai
sudo chown $USER:$USER /opt/translation-notes-ai
cd /opt/translation-notes-ai

# Or use user directory
mkdir -p ~/translation-notes-ai
cd ~/translation-notes-ai
```

### Step 2: Transfer Files

```bash
# Using SCP (from your Windows machine)
scp -r main.py modules/ config/ .env requirements.txt setup.py recover*.py user@linux-server:/opt/translation-notes-ai/

# Or using rsync for better transfer control
rsync -av --exclude='venv/' --exclude='cache/' --exclude='logs/' \
    /path/to/windows/project/ user@linux-server:/opt/translation-notes-ai/
```

### Step 3: Install Python and Dependencies

```bash
# Install Python 3.8+ (Ubuntu/Debian)
sudo apt update
sudo apt install python3 python3-pip python3-venv

# Or for RHEL/CentOS/Rocky
sudo yum install python3 python3-pip
# or
sudo dnf install python3 python3-pip

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

### Step 4: Install System Dependencies

```bash
# For Selenium (web scraping) - Ubuntu/Debian
sudo apt install chromium-browser chromium-chromedriver

# Or install Chrome and ChromeDriver
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt update
sudo apt install google-chrome-stable

# For RHEL/CentOS/Rocky
sudo yum install chromium chromium-headless
# or
sudo dnf install chromium chromium-headless
```

### Step 5: Set Up Directory Structure

```bash
# Create necessary directories
mkdir -p cache logs

# Set proper permissions
chmod 755 main.py
chmod -R 755 modules/
chmod 600 .env              # Secure environment file
chmod 600 config/google_credentials.json  # Secure credentials
```

## 🔒 Security Configuration

### Environment Variables Security

```bash
# Secure the .env file
chmod 600 .env
chown $USER:$USER .env

# Optionally, move sensitive config to system location
sudo mkdir -p /etc/translation-notes-ai
sudo mv .env /etc/translation-notes-ai/
sudo chmod 600 /etc/translation-notes-ai/.env
sudo chown root:$USER /etc/translation-notes-ai/.env

# Update config to point to new location (modify config.yaml):
# environment_file: "/etc/translation-notes-ai/.env"
```

### Google Credentials Security

```bash
# Secure Google credentials
chmod 600 config/google_credentials.json
chown $USER:$USER config/google_credentials.json
```

## ⏰ Cron Job Setup with Process Checking

### Step 1: Create Run Script with Lock File

Create `/opt/translation-notes-ai/run_translation_notes.sh`:

```bash
#!/bin/bash

# Configuration
PROJECT_DIR="/opt/translation-notes-ai"
LOCK_FILE="/tmp/translation-notes-ai.lock"
LOG_FILE="$PROJECT_DIR/logs/cron.log"
PYTHON_PATH="$PROJECT_DIR/venv/bin/python"

# Function to log with timestamp
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$LOG_FILE"
}

# Check if lock file exists and process is running
if [ -f "$LOCK_FILE" ]; then
    PID=$(cat "$LOCK_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        log_message "Translation Notes AI is already running (PID: $PID). Skipping execution."
        exit 0
    else
        log_message "Stale lock file found. Removing and continuing."
        rm -f "$LOCK_FILE"
    fi
fi

# Change to project directory
cd "$PROJECT_DIR" || {
    log_message "ERROR: Cannot change to project directory: $PROJECT_DIR"
    exit 1
}

# Activate virtual environment
source venv/bin/activate || {
    log_message "ERROR: Cannot activate virtual environment"
    exit 1
}

# Create lock file with current PID
echo $$ > "$LOCK_FILE"

# Cleanup function
cleanup() {
    log_message "Cleaning up and removing lock file"
    rm -f "$LOCK_FILE"
}

# Set up trap to cleanup on exit
trap cleanup EXIT INT TERM

# Log start
log_message "Starting Translation Notes AI (Complete Mode)"

# Run the application in complete mode
if "$PYTHON_PATH" main.py --mode complete; then
    log_message "Translation Notes AI completed successfully"
    exit_code=0
else
    log_message "Translation Notes AI failed with exit code: $?"
    exit_code=1
fi

# Log completion
log_message "Translation Notes AI finished with exit code: $exit_code"

exit $exit_code
```

Make it executable:

```bash
chmod +x /opt/translation-notes-ai/run_translation_notes.sh
```

### Step 2: Set Up Cron Job

```bash
# Edit crontab
crontab -e

# Add this line for every 30 minutes
*/30 * * * * /opt/translation-notes-ai/run_translation_notes.sh

# Alternative schedules:
# Every 15 minutes: */15 * * * *
# Every hour: 0 * * * *
# Every 2 hours: 0 */2 * * *
# Business hours only (8 AM - 6 PM, weekdays): */30 8-18 * * 1-5
```

### Step 3: Set Up Log Rotation

Create `/etc/logrotate.d/translation-notes-ai`:

```bash
/opt/translation-notes-ai/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    notifempty
    create 0644 username username
    postrotate
        # Optional: restart or signal if needed
    endscript
}
```

## 🧪 Testing and Verification

### Step 1: Test Basic Functionality

```bash
# Test dry run
cd /opt/translation-notes-ai
source venv/bin/activate
python main.py --mode complete --dry-run --debug

# Test configuration access
python tests/test_sheets_access.py
```

### Step 2: Test Cron Script

```bash
# Test the run script manually
./run_translation_notes.sh

# Check logs
tail -f logs/cron.log
tail -f logs/translation_notes.log
```

### Step 3: Test Cron Job

```bash
# Add temporary test cron (every 5 minutes for testing)
*/5 * * * * /opt/translation-notes-ai/run_translation_notes.sh

# Monitor logs
tail -f /opt/translation-notes-ai/logs/cron.log

# Remove test cron after verification
crontab -e
# Change back to */30 for production
```

## 📊 Monitoring and Maintenance

### Check Cron Job Status

```bash
# View cron logs (Ubuntu/Debian)
sudo tail -f /var/log/syslog | grep CRON

# View application logs
tail -f /opt/translation-notes-ai/logs/cron.log
tail -f /opt/translation-notes-ai/logs/translation_notes.log

# Check if process is running
ps aux | grep python | grep main.py

# Check lock file
ls -la /tmp/translation-notes-ai.lock
```

### Application Status Commands

```bash
# Manual status check
cd /opt/translation-notes-ai
source venv/bin/activate
python main.py --status

# Cache status
python main.py --cache-status

# Convert SRef values (maintenance task)
python main.py --convert-sref --dry-run  # Preview
python main.py --convert-sref            # Apply
```

## 🔧 Troubleshooting

### Common Issues

**Cron job not running:**
```bash
# Check cron service status
sudo systemctl status cron    # Ubuntu/Debian
sudo systemctl status crond   # RHEL/CentOS

# Check user's crontab
crontab -l

# Check system logs
sudo tail -f /var/log/syslog | grep CRON
```

**Permission errors:**
```bash
# Fix file permissions
chmod 755 /opt/translation-notes-ai/run_translation_notes.sh
chmod 600 /opt/translation-notes-ai/.env
chmod 644 /opt/translation-notes-ai/config/config.yaml
```

**Python environment issues:**
```bash
# Recreate virtual environment
rm -rf venv/
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**Google Sheets access:**
```bash
# Test credentials
python tests/test_sheets_access.py

# Check service account email from error messages
# Share sheets with the service account email
```

**Lock file issues:**
```bash
# Remove stale lock file
rm -f /tmp/translation-notes-ai.lock

# Check for stuck processes
ps aux | grep translation-notes-ai
kill -9 <PID>  # if needed
```

## 🎯 Production Best Practices

### Security Checklist

- ✅ Environment file permissions (600)
- ✅ Google credentials permissions (600)  
- ✅ Run as non-root user
- ✅ Regular security updates
- ✅ Log rotation configured
- ✅ Limited file system access

### Monitoring Checklist

- ✅ Cron job logs monitored
- ✅ Application logs reviewed regularly
- ✅ Disk space monitored (logs/cache)
- ✅ Error notifications configured
- ✅ Lock file cleanup verified

### Maintenance Schedule

**Daily:**
- Check application logs for errors
- Verify cron job execution

**Weekly:**
- Review processed item counts
- Check disk space usage
- Verify cache refresh operations

**Monthly:**
- Update Python dependencies
- Rotate and archive old logs
- Review system security updates

## 📈 Performance Optimization

### System Resources

```bash
# Monitor resource usage
htop
iotop  # IO monitoring

# Check Python process resources
ps aux | grep python
pstree -p | grep python
```

### Cron Frequency Tuning

```bash
# High activity periods - every 15 minutes
*/15 8-18 * * 1-5 /opt/translation-notes-ai/run_translation_notes.sh

# Low activity periods - every hour  
0 19-7 * * * /opt/translation-notes-ai/run_translation_notes.sh
0 * * * 6,0 /opt/translation-notes-ai/run_translation_notes.sh
```

## 🚀 Deployment Summary

Your Translation Notes AI system is now configured for robust Linux production deployment with:

- **Complete Mode**: Processes all available work, then exits cleanly
- **Smart Cron Scheduling**: Prevents multiple instances, handles failures gracefully
- **Comprehensive Logging**: Full audit trail of all operations
- **Security Hardening**: Proper permissions and credential protection
- **Easy Monitoring**: Clear status reporting and log analysis
- **Automatic Recovery**: Handles temporary failures and lock file cleanup

The system will automatically process translation work every 30 minutes, handling multiple chapters efficiently, and exit when no work remains - perfect for unattended operation on your Linux server.