"""
Logger Setup
Configures logging for the application.
"""

import os
import logging
import logging.handlers
from pathlib import Path
from typing import Optional
from datetime import datetime

from .config_manager import ConfigManager


def setup_logging(config: ConfigManager) -> logging.Logger:
    """Setup logging configuration.
    
    Args:
        config: Configuration manager
        
    Returns:
        Configured logger
    """
    # Get logging configuration
    log_config = config.get_logging_config()
    
    # Create logs directory
    log_dir = Path(log_config['log_dir'])
    log_dir.mkdir(exist_ok=True)
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_config['level'].upper()))
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Create unique log file name with timestamp
    base_log_file = log_config['log_file']
    # Remove extension if present
    if base_log_file.endswith('.log'):
        base_name = base_log_file[:-4]
    else:
        base_name = base_log_file
    
    # Generate timestamp for unique filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_log_file = f"{base_name}_{timestamp}.log"
    log_file = log_dir / unique_log_file
    
    # Store the current log file path in config for other components to access
    config.set('runtime.current_log_file', str(log_file))
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=log_config['max_log_size_mb'] * 1024 * 1024,
        backupCount=log_config['backup_count'],
        encoding='utf-8'
    )
    file_handler.setFormatter(detailed_formatter)
    logger.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(simple_formatter)
    
    # Set console level based on debug mode
    if config.is_debug_mode():
        console_handler.setLevel(logging.DEBUG)
    else:
        console_handler.setLevel(logging.INFO)
    
    logger.addHandler(console_handler)
    
    # Log startup message
    logger.info("Logging initialized")
    logger.info(f"Log level: {log_config['level']}")
    logger.info(f"Log file: {log_file}")
    
    return logger 