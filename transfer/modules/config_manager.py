"""
Configuration Manager
Handles loading and accessing configuration from YAML files and environment variables.
"""

import os
import yaml
from typing import Any, Dict, Optional
from dotenv import load_dotenv


class ConfigManager:
    """Manages application configuration from YAML files and environment variables."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the configuration manager.
        
        Args:
            config_path: Path to the main config file. If None, uses default location.
        """
        # Load environment variables
        load_dotenv()
        
        # Determine config file path
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), 
                'config', 
                'config.yaml'
            )
        
        self.config_path = config_path
        self.config = self._load_config()
        self._apply_env_overrides()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in configuration file: {e}")
    
    def _apply_env_overrides(self):
        """Apply environment variable overrides to configuration."""
        # Map environment variables to config keys
        env_mappings = {
            'ANTHROPIC_API_KEY': 'anthropic.api_key',
            'ANTHROPIC_DISABLED': 'anthropic.disabled',
            'EMAIL_FROM': 'email.from_email',
            'EMAIL_TO': 'email.to_email',
            'EMAIL_PASSWORD': 'email.password',
            'GOOGLE_CREDENTIALS_PATH': 'google_sheets.credentials_file',
            'LOG_LEVEL': 'logging.level',
            'DRY_RUN': 'debug.dry_run',
            # Google Sheet IDs
            'SUPPORT_REFERENCES_SHEET_ID': 'google_sheets.support_references_sheet',
            'TEMPLATES_SHEET_ID': 'google_sheets.templates_sheet',
            'SYSTEM_PROMPTS_SHEET_ID': 'google_sheets.system_prompts_sheet',
        }
        
        for env_var, config_key in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                # Handle boolean values
                if env_var in ['DRY_RUN', 'ANTHROPIC_DISABLED']:
                    env_value = env_value.lower() in ('true', '1', 'yes', 'on')

                self.set(config_key, env_value)
        
        # Load editor sheet IDs and names from environment variables
        sheet_ids = {}
        editor_names = {}
        
        # Load generic editor pattern (SHEET_ID_EDITOR1, SHEET_ID_EDITOR2, etc.)
        for i in range(1, 6):  # Support up to 5 editors
            sheet_env_var = f'SHEET_ID_EDITOR{i}'
            name_env_var = f'EDITOR{i}_NAME'
            
            sheet_id = os.getenv(sheet_env_var)
            editor_name = os.getenv(name_env_var, f'Editor {i}')  # Default to "Editor N" if name not set
            
            if sheet_id:
                editor_key = f'editor{i}'
                sheet_ids[editor_key] = sheet_id
                editor_names[editor_key] = editor_name
        
        # Set the sheet_ids and editor_names in config
        if sheet_ids:
            self.set('google_sheets.sheet_ids', sheet_ids)
        if editor_names:
            self.set('google_sheets.editor_names', editor_names)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value using dot notation.
        
        Args:
            key: Configuration key in dot notation (e.g., 'google_sheets.credentials_file')
            default: Default value if key is not found
            
        Returns:
            Configuration value or default
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """Set a configuration value using dot notation.
        
        Args:
            key: Configuration key in dot notation
            value: Value to set
        """
        keys = key.split('.')
        config = self.config
        
        # Navigate to the parent of the target key
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # Set the value
        config[keys[-1]] = value
    
    def get_anthropic_config(self) -> Dict[str, Any]:
        """Get Anthropic-specific configuration."""
        return {
            'api_key': self.get('anthropic.api_key'),
            'model': self.get('anthropic.model', 'claude-3-5-sonnet-20241022'),
            'batch_size': self.get('anthropic.batch_size', 2),
            'max_batch_requests': self.get('anthropic.max_batch_requests', 100),
            'max_concurrent_batches': self.get('anthropic.max_concurrent_batches', 5),
            'batch_timeout_hours': self.get('anthropic.batch_timeout_hours', 1),
            'enable_prompt_caching': self.get('anthropic.enable_prompt_caching', True),
            'cache_ttl_minutes': self.get('anthropic.cache_ttl_minutes', 5),
        }
    
    def get_google_sheets_config(self) -> Dict[str, Any]:
        """Get Google Sheets-specific configuration."""
        return {
            'credentials_file': self.get('google_sheets.credentials_file'),
            'sheet_ids': self.get('google_sheets.sheet_ids', {}),
            'editor_names': self.get('google_sheets.editor_names', {}),
            'support_references_sheet': self.get('google_sheets.support_references_sheet'),
            'templates_sheet': self.get('google_sheets.templates_sheet'),
            'system_prompts_sheet': self.get('google_sheets.system_prompts_sheet'),
            'main_tab_name': self.get('google_sheets.main_tab_name', 'AI notes'),
            'ult_tab_name': self.get('google_sheets.ult_tab_name', 'ULT'),
            'ust_tab_name': self.get('google_sheets.ust_tab_name', 'UST'),
            'suggestions_tab_name': self.get('google_sheets.suggestions_tab_name', 'suggested notes'),
            'templates_tab_name': self.get('google_sheets.templates_tab_name', 'AI templates - Use this one'),
        }
    
    def get_cache_config(self) -> Dict[str, Any]:
        """Get cache-specific configuration."""
        return {
            'cache_dir': self.get('cache.cache_dir', 'cache'),
            'biblical_text_refresh': self.get('cache.biblical_text_refresh', 60),
            'templates_refresh': self.get('cache.templates_refresh', 1440),
            'support_refs_refresh': self.get('cache.support_refs_refresh', 1440),
            'ult_cache_file': self.get('cache.ult_cache_file', 'ult_chapters.json'),
            'ust_cache_file': self.get('cache.ust_cache_file', 'ust_chapters.json'),
            'templates_cache_file': self.get('cache.templates_cache_file', 'templates.json'),
            'support_refs_cache_file': self.get('cache.support_refs_cache_file', 'support_references.json'),
            'system_prompts_cache_file': self.get('cache.system_prompts_cache_file', 'system_prompts.json'),
        }
    
    def get_processing_config(self) -> Dict[str, Any]:
        """Get processing-specific configuration."""
        return {
            'poll_interval': self.get('processing.poll_interval', 60),
            'max_items_per_work_cycle': self.get('processing.max_items_per_work_cycle', 0),  # 0 means no limit
            'watch_columns': self.get('processing.watch_columns', ['Go?', 'SRef']),
            'process_go_values': self.get('processing.process_go_values', ['YES', 'GO']),
            'skip_go_values': self.get('processing.skip_go_values', ['AI']),
            'skip_ai_completed': self.get('processing.skip_ai_completed', True),
            'auto_convert_sref': self.get('processing.auto_convert_sref', True),
        }
    
    def get_logging_config(self) -> Dict[str, Any]:
        """Get logging-specific configuration."""
        return {
            'level': self.get('logging.level', 'INFO'),
            'log_dir': self.get('logging.log_dir', 'logs'),
            'log_file': self.get('logging.log_file', 'translation_notes.log'),
            'max_log_size_mb': self.get('logging.max_log_size_mb', 10),
            'backup_count': self.get('logging.backup_count', 5),
            'email_errors': self.get('logging.email_errors', True),
            'email_cooldown_minutes': self.get('logging.email_cooldown_minutes', 10),
            'max_errors_per_email': self.get('logging.max_errors_per_email', 10),
        }
    
    def get_email_config(self) -> Dict[str, Any]:
        """Get email-specific configuration."""
        return {
            'smtp_server': self.get('email.smtp_server', 'smtp.gmail.com'),
            'smtp_port': self.get('email.smtp_port', 587),
            'use_tls': self.get('email.use_tls', True),
            'from_email': self.get('email.from_email'),
            'to_email': self.get('email.to_email'),
            'password': self.get('email.password'),
        }
    
    def get_timing_config(self) -> Dict[str, Any]:
        """Get timing-specific configuration."""
        return {
            'work_check_interval': self.get('timing.work_check_interval', 60),
            'work_check_minimum_interval': self.get('timing.work_check_minimum_interval', 5),
            'error_retry_delay': self.get('timing.error_retry_delay', 10),
            'suggestion_poll_interval': self.get('timing.suggestion_poll_interval', 30),
            'suggestion_max_wait_minutes': self.get('timing.suggestion_max_wait_minutes', 30),
            'loop_sleep_interval': self.get('timing.loop_sleep_interval', 1),
            'shutdown_grace_period': self.get('timing.shutdown_grace_period', 2),
            'retry_delay_brief': self.get('timing.retry_delay_brief', 5),
            'api_rate_limit_delay': self.get('timing.api_rate_limit_delay', 2),
            'sheet_operation_delay': self.get('timing.sheet_operation_delay', 3),
        }
    
    def is_debug_mode(self) -> bool:
        """Check if debug mode is enabled."""
        return self.get('debug.enabled', False)
    
    def is_dry_run(self) -> bool:
        """Check if dry run mode is enabled."""
        return self.get('debug.dry_run', False)

    def is_ai_disabled(self) -> bool:
        """Check if Anthropic API usage is disabled."""
        return self.get('anthropic.disabled', False)
    
    def reload(self):
        """Reload configuration from file."""
        self.config = self._load_config()
        self._apply_env_overrides()

    def _load_prompts(self) -> Dict[str, Any]:
        """Load prompts from prompts.yaml file."""
        prompts_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'config', 
            'prompts.yaml'
        )
        
        try:
            with open(prompts_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            raise FileNotFoundError(f"Prompts file not found: {prompts_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in prompts file: {e}")
    
    def get_prompt(self, prompt_key: str) -> Optional[str]:
        """Get a prompt template from prompts.yaml.
        
        Args:
            prompt_key: Key of the prompt to retrieve
            
        Returns:
            Prompt template string or None if not found
        """
        try:
            prompts = self._load_prompts()
            
            # Handle nested keys with dot notation
            if '.' in prompt_key:
                keys = prompt_key.split('.')
                value = prompts
                for k in keys:
                    if isinstance(value, dict) and k in value:
                        value = value[k]
                    else:
                        return None
                return value
            else:
                return prompts.get(prompt_key)
                
        except Exception as e:
            # Log error but don't raise - return None to indicate failure
            return None 
    
    def get_editor_name_for_sheet(self, sheet_id: str, include_raw_id: bool = False) -> str:
        """Get the friendly editor name for a given sheet ID.
        
        Args:
            sheet_id: The Google Sheet ID
            include_raw_id: If True, include the raw editor ID in parentheses
            
        Returns:
            Friendly editor name or the sheet ID if not found
        """
        sheet_ids = self.get('google_sheets.sheet_ids', {})
        editor_names = self.get('google_sheets.editor_names', {})
        
        # Find the editor key for this sheet ID
        for editor_key, sid in sheet_ids.items():
            if sid == sheet_id:
                friendly_name = editor_names.get(editor_key, editor_key.capitalize())
                if include_raw_id:
                    return f"{friendly_name} ({editor_key})"
                return friendly_name
        
        # If not found, return a truncated sheet ID for debugging
        return f"Unknown({sheet_id[:8]})"
    
    def get_friendly_name_for_user(self, user: str) -> str:
        """Get the friendly name for a user/editor ID.
        
        Args:
            user: The raw editor ID (e.g., 'editor1')
            
        Returns:
            Friendly name for the user
        """
        editor_names = self.get('google_sheets.editor_names', {})
        return editor_names.get(user, user.capitalize())
    
    def get_friendly_name_with_id(self, user: str) -> str:
        """Get the friendly name with raw ID for a user/editor ID.
        
        Args:
            user: The raw editor ID (e.g., 'editor1')
            
        Returns:
            Friendly name with raw ID in parentheses (e.g., 'chris (editor1)')
        """
        editor_names = self.get('google_sheets.editor_names', {})
        friendly_name = editor_names.get(user, user.capitalize())
        return f"{friendly_name} ({user})"
    
    def get_all_editor_info(self) -> Dict[str, Dict[str, str]]:
        """Get all editor information (IDs and names) in a structured format.
        
        Returns:
            Dictionary mapping editor keys to their sheet IDs and names
        """
        sheet_ids = self.get('google_sheets.sheet_ids', {})
        editor_names = self.get('google_sheets.editor_names', {})
        
        result = {}
        for editor_key in sheet_ids.keys():
            result[editor_key] = {
                'sheet_id': sheet_ids[editor_key],
                'name': editor_names.get(editor_key, editor_key.capitalize())
            }
        return result 