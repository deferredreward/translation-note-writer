"""
Prompt Manager
Handles loading and formatting prompts for AI interactions.
"""

import os
import yaml
import logging
from typing import Dict, Any, Optional, List

from .config_manager import ConfigManager


class PromptManager:
    """Manages AI prompts and templates."""
    
    def __init__(self, config: ConfigManager, cache_manager=None):
        """Initialize the prompt manager.
        
        Args:
            config: Configuration manager
            cache_manager: Cache manager for fetching system prompts
        """
        self.config = config
        self.cache_manager = cache_manager
        self.logger = logging.getLogger(__name__)
        
        # Load prompts from configuration
        self.prompts = self._load_prompts()
        
        self.logger.info("Prompt manager initialized")
    
    def _load_prompts(self) -> Dict[str, Any]:
        """Load prompts from the prompts configuration file.
        
        Returns:
            Dictionary of prompts
        """
        try:
            prompts_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'config',
                'prompts.yaml'
            )
            
            with open(prompts_path, 'r', encoding='utf-8') as f:
                prompts = yaml.safe_load(f) or {}
            
            # Remove hardcoded system prompts - we'll fetch these from cache/sheets
            if 'system_prompts' in prompts:
                del prompts['system_prompts']
                self.logger.info("Removed hardcoded system prompts - will fetch from Google Sheets")
            
            return prompts
                
        except FileNotFoundError:
            self.logger.warning(f"Prompts file not found: {prompts_path}")
            return {}
        except yaml.YAMLError as e:
            self.logger.error(f"Error loading prompts: {e}")
            return {}
    
    def _get_system_prompts_from_cache(self) -> Dict[str, Any]:
        """Get system prompts from cache (which fetches from Google Sheets).
        
        Returns:
            Dictionary of system prompts
        """
        if not self.cache_manager:
            self.logger.warning("No cache manager available for system prompts")
            return {}
        
        try:
            # Try to get from cache first
            system_prompts = self.cache_manager.get_cached_data('system_prompts')
            
            if not system_prompts:
                # If not in cache, refresh it
                self.logger.info("System prompts not in cache, refreshing...")
                refreshed = self.cache_manager.refresh_if_needed()
                if 'system_prompts' in refreshed:
                    system_prompts = self.cache_manager.get_cached_data('system_prompts')
            
            return system_prompts or {}
            
        except Exception as e:
            self.logger.error(f"Error getting system prompts from cache: {e}")
            return {}
    
    def get_prompt(self, note_type: str, template_vars: Dict[str, Any]) -> str:
        """Get a formatted prompt for a specific note type.
        
        Args:
            note_type: Type of note (given_at, writes_at, see_how_at, etc.)
            template_vars: Variables to substitute in the prompt
            
        Returns:
            Formatted prompt string
        """
        try:
            # Map note types to prompt keys
            prompt_mapping = {
                'given_at': 'given_at_prompt',
                'writes_at': 'writes_at_prompt',
                'see_how_at': 'see_how_at_prompt',
                'see_how': 'given_at_prompt',  # Use given_at for see_how with AT
                'review': 'review_prompt'
            }
            
            prompt_key = prompt_mapping.get(note_type, 'writes_at_prompt')
            
            # Get the prompt template
            prompt_template = self.prompts.get('note_prompts', {}).get(prompt_key, '')
            
            if not prompt_template:
                self.logger.warning(f"No prompt found for note type: {note_type}")
                return "Create a translation note for this item."
            
            # Format the prompt with template variables
            formatted_prompt = self._format_prompt(prompt_template, template_vars)
            
            return formatted_prompt
            
        except Exception as e:
            self.logger.error(f"Error getting prompt for {note_type}: {e}")
            return "Create a translation note for this item."
    
    def get_system_message(self, note_type: str, templates: List[Dict[str, Any]] = None) -> Optional[str]:
        """Get the system message for a specific note type.
        
        Args:
            note_type: Type of note
            templates: List of templates to check for AT requirements
            
        Returns:
            System message string or None
        """
        try:
            # Check if any template contains "Alternate translation:" to determine system prompt
            needs_at_generation = False
            if templates:
                for template in templates:
                    template_text = template.get('note_template', '')
                    if 'Alternate translation:' in template_text:
                        needs_at_generation = True
                        break
            
            # Select system prompt based on AT requirement
            if needs_at_generation:
                system_key = 'ai_writes_at_agent'  # Generate alternate translations
            else:
                system_key = 'given_at_agent'      # Use provided alternate translations (or none)
            
            # Override for specific note types that should always use given_at_agent
            if note_type in ['given_at', 'see_how', 'review']:
                system_key = 'given_at_agent'
            
            # Get system prompts from cache (Google Sheets)
            system_prompts = self._get_system_prompts_from_cache()
            
            # Get the system message
            system_message = system_prompts.get(system_key, '')
            
            if not system_message:
                self.logger.warning(f"No system message found for {note_type} (key: {system_key})")
                return None
            
            return system_message
            
        except Exception as e:
            self.logger.error(f"Error getting system message for {note_type}: {e}")
            return None
    
    def get_review_prompt(self, template_vars: Dict[str, Any]) -> str:
        """Get the review prompt for suggesting additional notes.
        
        Args:
            template_vars: Variables for the prompt
            
        Returns:
            Formatted review prompt
        """
        try:
            prompt_template = self.prompts.get('review_prompt', '')
            
            if not prompt_template:
                return "Review the text and suggest additional translation notes."
            
            return self._format_prompt(prompt_template, template_vars)
            
        except Exception as e:
            self.logger.error(f"Error getting review prompt: {e}")
            return "Review the text and suggest additional translation notes."
    
    def _format_prompt(self, template: str, variables: Dict[str, Any]) -> str:
        """Format a prompt template with variables.
        
        Args:
            template: Prompt template string
            variables: Variables to substitute
            
        Returns:
            Formatted prompt
        """
        try:
            # Clean variables - replace None with empty string
            clean_vars = {}
            for key, value in variables.items():
                if value is None:
                    clean_vars[key] = ''
                else:
                    clean_vars[key] = str(value)
            
            # Format the template
            formatted = template.format(**clean_vars)
            
            return formatted
            
        except KeyError as e:
            self.logger.error(f"Missing variable in prompt template: {e}")
            # Return template with missing variables as placeholders
            return template
        except Exception as e:
            self.logger.error(f"Error formatting prompt: {e}")
            return template
    
    def get_cache_markers(self) -> Dict[str, str]:
        """Get cache markers for prompt caching.
        
        Returns:
            Dictionary of cache markers
        """
        return self.prompts.get('cache_markers', {})
    
    def reload_prompts(self):
        """Reload prompts from configuration file."""
        self.prompts = self._load_prompts()
        self.logger.info("Prompts reloaded") 