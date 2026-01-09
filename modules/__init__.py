"""
Translation Notes AI - Modules Package
Contains all the core modules for the Translation Notes AI application.
"""

from .config_manager import ConfigManager
from .logger import setup_logging
from .sheet_manager import SheetManager
from .ai_service import AIService
from .cache_manager import CacheManager
from .batch_processor import BatchProcessor
from .continuous_batch_manager import ContinuousBatchManager
from .error_notifier import ErrorNotifier
from .prompt_manager import PromptManager
from .biblical_text_scraper import BiblicalTextScraper
from .security import SecurityValidator, ConfigSecurityValidator
from .text_utils import post_process_text, clean_sheet_value, normalize_biblical_reference
from .notification_system import NotificationSystem, CallbackNotificationSystem, get_notification_system
from .cli import TranslationNotesAICLI, create_cli, main_cli_entry_point
from .language_converter import LanguageConverter
from .tsv_notes_cache import TSVNotesCache

__all__ = [
    # Core modules
    'ConfigManager',
    'setup_logging',
    'SheetManager',
    'AIService',
    'CacheManager',
    'BatchProcessor',
    'ContinuousBatchManager',
    'ErrorNotifier',
    'PromptManager',
    'BiblicalTextScraper',

    # Language conversion
    'LanguageConverter',
    'TSVNotesCache',

    # Security and validation
    'SecurityValidator',
    'ConfigSecurityValidator',

    # Text processing utilities
    'post_process_text',
    'clean_sheet_value',
    'normalize_biblical_reference',

    # Notification system
    'NotificationSystem',
    'CallbackNotificationSystem',
    'get_notification_system',

    # Command-line interface
    'TranslationNotesAICLI',
    'create_cli',
    'main_cli_entry_point',
] 