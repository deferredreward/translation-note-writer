#!/bin/bash

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
