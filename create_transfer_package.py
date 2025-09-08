#!/usr/bin/env python3
"""
Transfer Package Creator for Translation Notes AI
Creates a 'transfer' directory with all files needed for Linux deployment
"""

import os
import shutil
import sys
from pathlib import Path

def create_transfer_package():
    """Create transfer package with all necessary files for Linux deployment"""
    
    # Get the current directory (project root)
    project_root = Path(__file__).parent
    transfer_dir = project_root / "transfer"
    
    print(f"Creating transfer package in: {transfer_dir}")
    
    # Remove existing transfer directory if it exists
    if transfer_dir.exists():
        print("Removing existing transfer directory...")
        shutil.rmtree(transfer_dir)
    
    # Create transfer directory
    transfer_dir.mkdir()
    
    # Files and directories to copy
    items_to_copy = [
        # Core application files
        "main.py",
        "requirements.txt", 
        "setup.py",
        
        # Configuration files (entire directory)
        "config",
        
        # Environment file (template and actual)
        "env_example.txt",
        ".env",
        
        # Application modules (entire directory)
        "modules",
        
        # Recovery tools
        "recover_notes.py",
        "recover_from_api.py",
        
        # Documentation
        "README.md",
        "LINUX_MIGRATION.md",
        
        # Testing tools (optional but useful)
        "tests",
    ]
    
    # Copy each item
    copied_files = []
    skipped_files = []
    
    for item in items_to_copy:
        source_path = project_root / item
        dest_path = transfer_dir / item
        
        try:
            if source_path.is_file():
                # Copy file
                shutil.copy2(source_path, dest_path)
                copied_files.append(f"📄 {item}")
                print(f"✅ Copied file: {item}")
                
            elif source_path.is_dir():
                # Copy directory
                shutil.copytree(source_path, dest_path)
                copied_files.append(f"📁 {item}/")
                print(f"✅ Copied directory: {item}/")
                
            else:
                print(f"⚠️  Skipped (not found): {item}")
                skipped_files.append(item)
                
        except Exception as e:
            print(f"❌ Error copying {item}: {e}")
            skipped_files.append(f"{item} (ERROR: {e})")
    
    # Create additional directories that will be needed on Linux
    additional_dirs = ["cache", "logs"]
    for dir_name in additional_dirs:
        dir_path = transfer_dir / dir_name
        dir_path.mkdir(exist_ok=True)
        print(f"✅ Created directory: {dir_name}/")
        copied_files.append(f"📁 {dir_name}/ (empty)")
    
    # Create the run script for Linux
    run_script_content = '''#!/bin/bash

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
'''
    
    run_script_path = transfer_dir / "run_translation_notes.sh"
    run_script_path.write_text(run_script_content)
    # Make it executable (will need chmod +x on Linux)
    print(f"✅ Created Linux run script: run_translation_notes.sh")
    copied_files.append("📄 run_translation_notes.sh (Linux cron script)")
    
    # Create setup instructions file
    setup_instructions = '''# Linux Setup Instructions

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
'''
    
    setup_file = transfer_dir / "SETUP_LINUX.md"
    setup_file.write_text(setup_instructions)
    print(f"✅ Created setup instructions: SETUP_LINUX.md")
    copied_files.append("📄 SETUP_LINUX.md (quick setup guide)")
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"📦 TRANSFER PACKAGE CREATED SUCCESSFULLY")
    print(f"{'='*60}")
    print(f"Location: {transfer_dir}")
    print(f"Total items: {len(copied_files)}")
    
    print(f"\n📋 COPIED ITEMS:")
    for item in copied_files:
        print(f"  {item}")
    
    if skipped_files:
        print(f"\n⚠️  SKIPPED ITEMS:")
        for item in skipped_files:
            print(f"  ❌ {item}")
    
    # Get directory size
    total_size = sum(f.stat().st_size for f in transfer_dir.rglob('*') if f.is_file())
    size_mb = total_size / (1024 * 1024)
    
    print(f"\n📊 PACKAGE STATS:")
    print(f"  Size: {size_mb:.2f} MB")
    print(f"  Files: {len([f for f in transfer_dir.rglob('*') if f.is_file()])}")
    print(f"  Directories: {len([d for d in transfer_dir.rglob('*') if d.is_dir()])}")
    
    print(f"\n🚀 NEXT STEPS:")
    print(f"1. Copy the entire 'transfer' directory to your Linux server")
    print(f"2. Follow the instructions in SETUP_LINUX.md")
    print(f"3. Or see the full guide in LINUX_MIGRATION.md")
    
    print(f"\n✨ Ready for USB transfer! ✨")
    
    return transfer_dir

if __name__ == "__main__":
    try:
        create_transfer_package()
        print(f"\n🎉 SUCCESS: Transfer package created!")
        sys.exit(0)
        
    except Exception as e:
        print(f"\n💥 ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)