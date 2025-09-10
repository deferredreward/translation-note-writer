"""
Security utilities for Translation Notes AI
Handles input validation, sanitization, and security best practices.
"""

import re
import html
import logging
from typing import Any, Dict, List, Optional, Union
from pathlib import Path


class SecurityValidator:
    """Handles security validation and sanitization for user inputs."""
    
    # Common dangerous patterns to watch for
    DANGEROUS_PATTERNS = [
        r'<script[^>]*>.*?</script>',  # Script tags
        r'javascript:',                # JavaScript URLs
        r'data:text/html',            # Data URLs
        r'vbscript:',                 # VBScript
        r'onload\s*=',                # Event handlers
        r'onclick\s*=',
        r'onerror\s*=',
        r'eval\s*\(',                 # Code execution
        r'exec\s*\(',
        r'system\s*\(',
        r'__import__\s*\(',           # Python imports
        r'open\s*\(',                 # File operations
        r'file\s*\(',
    ]
    
    # Maximum lengths for different input types
    MAX_LENGTHS = {
        'reference': 100,      # Biblical references like "1 Cor 1:1"
        'note_text': 10000,    # Translation notes content
        'editor_name': 50,     # Editor names
        'sheet_name': 100,     # Google Sheets names
        'general_text': 5000,  # General text inputs
    }
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize the security validator.
        
        Args:
            logger: Logger instance for security warnings
        """
        self.logger = logger or logging.getLogger(__name__)
        self.dangerous_regex = re.compile('|'.join(self.DANGEROUS_PATTERNS), re.IGNORECASE)
    
    def sanitize_text_input(self, text: str, input_type: str = 'general_text') -> str:
        """Sanitize text input by removing dangerous content and limiting length.
        
        Args:
            text: Input text to sanitize
            input_type: Type of input for appropriate length limits
            
        Returns:
            Sanitized text
            
        Raises:
            ValueError: If input contains dangerous patterns or exceeds length limits
        """
        if not isinstance(text, str):
            raise ValueError(f"Expected string input, got {type(text)}")
        
        # Check for dangerous patterns
        if self.dangerous_regex.search(text):
            self.logger.warning(f"Dangerous pattern detected in {input_type} input: {text[:100]}...")
            raise ValueError(f"Input contains potentially dangerous content")
        
        # Check length limits
        max_length = self.MAX_LENGTHS.get(input_type, self.MAX_LENGTHS['general_text'])
        if len(text) > max_length:
            self.logger.warning(f"Input length {len(text)} exceeds maximum {max_length} for {input_type}")
            raise ValueError(f"Input too long: {len(text)} > {max_length} characters")
        
        # HTML escape to prevent injection
        sanitized = html.escape(text)
        
        # Remove or replace problematic characters
        sanitized = sanitized.replace('\x00', '')  # Null bytes
        sanitized = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', sanitized)  # Control characters
        
        return sanitized.strip()
    
    def validate_biblical_reference(self, reference: str) -> bool:
        """Validate that a string looks like a valid biblical reference.
        
        Args:
            reference: Reference string to validate (e.g., "1 Cor 1:1-5")
            
        Returns:
            True if reference format is valid
        """
        if not reference or not isinstance(reference, str):
            return False
        
        # Basic pattern for biblical references
        # Matches patterns like: "Gen 1:1", "1 Cor 2:3-5", "Psalm 23:1-6"
        pattern = r'^(?:1|2|3)?\s*[A-Za-z]+\s*\d+:\d+(?:-\d+)?(?:,\s*\d+:\d+(?:-\d+)?)*$'
        return bool(re.match(pattern, reference.strip()))
    
    def validate_sheet_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and sanitize data from Google Sheets.
        
        Args:
            data: Dictionary containing sheet data
            
        Returns:
            Sanitized data dictionary
            
        Raises:
            ValueError: If data validation fails
        """
        if not isinstance(data, dict):
            raise ValueError("Sheet data must be a dictionary")
        
        sanitized_data = {}
        
        for key, value in data.items():
            if isinstance(value, str):
                # Determine input type based on key name
                if 'ref' in key.lower():
                    input_type = 'reference'
                elif 'note' in key.lower() or 'text' in key.lower():
                    input_type = 'note_text'
                elif 'editor' in key.lower() or 'name' in key.lower():
                    input_type = 'editor_name'
                else:
                    input_type = 'general_text'
                
                try:
                    sanitized_data[key] = self.sanitize_text_input(value, input_type)
                except ValueError as e:
                    self.logger.warning(f"Validation failed for key '{key}': {e}")
                    # Skip invalid data rather than failing completely
                    continue
            elif isinstance(value, (int, float, bool)):
                sanitized_data[key] = value
            elif value is None:
                sanitized_data[key] = None
            else:
                # Convert other types to string and sanitize
                sanitized_data[key] = self.sanitize_text_input(str(value))
        
        return sanitized_data
    
    def validate_file_path(self, file_path: Union[str, Path], must_exist: bool = True) -> Path:
        """Validate that a file path is safe and exists.
        
        Args:
            file_path: Path to validate
            must_exist: Whether the file must already exist
            
        Returns:
            Validated Path object
            
        Raises:
            ValueError: If path is invalid or unsafe
        """
        if isinstance(file_path, str):
            path = Path(file_path)
        elif isinstance(file_path, Path):
            path = file_path
        else:
            raise ValueError(f"Expected string or Path, got {type(file_path)}")
        
        # Resolve to absolute path to check for directory traversal
        try:
            resolved_path = path.resolve()
        except (OSError, ValueError) as e:
            raise ValueError(f"Invalid file path: {e}")
        
        # Check for directory traversal attempts
        current_dir = Path.cwd().resolve()
        try:
            resolved_path.relative_to(current_dir)
        except ValueError:
            # Path is outside current directory tree
            self.logger.warning(f"Path outside project directory: {resolved_path}")
            raise ValueError("File path outside allowed directory")
        
        # Check if file exists when required
        if must_exist and not resolved_path.exists():
            raise ValueError(f"File does not exist: {resolved_path}")
        
        return resolved_path
    
    def sanitize_log_message(self, message: str) -> str:
        """Sanitize log messages to prevent log injection and remove sensitive data.
        
        Args:
            message: Log message to sanitize
            
        Returns:
            Sanitized log message
        """
        if not isinstance(message, str):
            message = str(message)
        
        # Remove line breaks to prevent log injection
        sanitized = message.replace('\n', ' ').replace('\r', ' ')
        
        # Remove or mask potentially sensitive information
        # API keys (typically 32+ character alphanumeric strings)
        sanitized = re.sub(r'\b[A-Za-z0-9]{32,}\b', '[API_KEY]', sanitized)
        
        # Email addresses
        sanitized = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', sanitized)
        
        # File paths that might contain usernames
        sanitized = re.sub(r'C:\\Users\\[^\\]+', 'C:\\Users\\[USER]', sanitized)
        sanitized = re.sub(r'/home/[^/]+', '/home/[USER]', sanitized)
        
        # Limit length of log messages
        if len(sanitized) > 1000:
            sanitized = sanitized[:997] + '...'
        
        return sanitized


class ConfigSecurityValidator:
    """Validates configuration security and best practices."""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize the config security validator."""
        self.logger = logger or logging.getLogger(__name__)
    
    def validate_config_security(self, config: Dict[str, Any]) -> List[str]:
        """Validate configuration for security issues.
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            List of security warnings
        """
        warnings = []
        
        # Check for hardcoded API keys in config
        api_key = config.get('anthropic', {}).get('api_key', '')
        if api_key and len(api_key) > 10:  # Looks like an actual key
            warnings.append("API key found in config file - should use environment variables")
        
        # Check for email credentials in config
        email_config = config.get('email', {})
        if email_config.get('password'):
            warnings.append("Email password in config file - should use environment variables")
        
        # Check file permissions on sensitive files
        sensitive_files = [
            'config/google_credentials.json',
            '.env',
            'config/config.yaml'
        ]
        
        for file_path in sensitive_files:
            path = Path(file_path)
            if path.exists():
                # On Unix systems, check file permissions
                import stat
                try:
                    mode = path.stat().st_mode
                    permissions = stat.filemode(mode)
                    
                    # Check if file is readable by others
                    if mode & stat.S_IROTH:
                        warnings.append(f"File {file_path} is readable by others: {permissions}")
                    
                    # Check if file is writable by others
                    if mode & stat.S_IWOTH:
                        warnings.append(f"File {file_path} is writable by others: {permissions}")
                        
                except (AttributeError, OSError):
                    # Windows or other systems without Unix permissions
                    pass
        
        # Check for debug mode in production
        if config.get('debug', {}).get('dry_run', False):
            self.logger.info("Debug dry_run mode is enabled")
        
        return warnings 