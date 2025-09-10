#!/usr/bin/env python3
"""
Setup script for Translation Notes AI
Helps users set up the environment and configuration.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


def create_venv():
    """Create a virtual environment."""
    print("Creating virtual environment...")
    
    venv_path = Path("venv")
    if venv_path.exists():
        print("Virtual environment already exists.")
        return
    
    try:
        subprocess.run([sys.executable, "-m", "venv", "venv"], check=True)
        print("✓ Virtual environment created successfully")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to create virtual environment: {e}")
        sys.exit(1)


def install_requirements():
    """Install required packages."""
    print("Installing requirements...")
    
    # Determine pip path
    if os.name == 'nt':  # Windows
        pip_path = Path("venv/Scripts/pip")
    else:  # Unix/Linux/macOS
        pip_path = Path("venv/bin/pip")
    
    try:
        subprocess.run([str(pip_path), "install", "-r", "requirements.txt"], check=True)
        print("✓ Requirements installed successfully")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install requirements: {e}")
        sys.exit(1)


def create_directories():
    """Create necessary directories."""
    print("Creating directories...")
    
    directories = [
        "cache",
        "logs",
        "config"
    ]
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
    
    print("✓ Directories created")


def copy_example_files():
    """Copy example files if they don't exist."""
    print("Setting up configuration files...")
    
    # Copy .env example
    env_example = Path("env_example.txt")
    env_file = Path(".env")
    
    if env_example.exists() and not env_file.exists():
        shutil.copy(env_example, env_file)
        print("✓ Created .env file from example")
    
    print("✓ Configuration files ready")


def print_next_steps():
    """Print next steps for the user."""
    print("\n" + "="*60)
    print("🎉 Setup completed successfully!")
    print("="*60)
    print("\nNext steps:")
    print("1. Edit the .env file with your API keys:")
    print("   - Add your Anthropic API key")
    print("   - Add your email settings for error notifications")
    print()
    print("2. Set up Google Sheets API:")
    print("   - Go to Google Cloud Console")
    print("   - Enable Google Sheets API")
    print("   - Create service account credentials")
    print("   - Download credentials JSON file")
    print("   - Save as config/google_credentials.json")
    print()
    print("3. Review and customize config/config.yaml:")
    print("   - Update sheet IDs for your editors")
    print("   - Adjust processing settings")
    print("   - Customize cache settings")
    print()
    print("4. Review and customize config/prompts.yaml:")
    print("   - Modify AI prompts as needed")
    print("   - Adjust system messages")
    print()
    print("5. Run the application:")
    print("   # Activate virtual environment:")
    if os.name == 'nt':
        print("   venv\\Scripts\\activate")
    else:
        print("   source venv/bin/activate")
    print()
    print("   # Test run (dry run mode):")
    print("   python main.py --mode once --dry-run --debug")
    print()
    print("   # Start continuous monitoring:")
    print("   python main.py --mode continuous")
    print()
    print("📚 See README.md for detailed documentation")
    print("="*60)


def main():
    """Main setup function."""
    print("Translation Notes AI - Setup")
    print("="*40)
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("✗ Python 3.8 or higher is required")
        sys.exit(1)
    
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor} detected")
    
    # Run setup steps
    create_venv()
    install_requirements()
    create_directories()
    copy_example_files()
    
    # Print next steps
    print_next_steps()


if __name__ == "__main__":
    main() 