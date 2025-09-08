"""
Error Notifier
Handles sending error notifications via email.
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional

from .config_manager import ConfigManager


class ErrorNotifier:
    """Handles error notifications via email."""
    
    def __init__(self, config: ConfigManager):
        """Initialize the error notifier.
        
        Args:
            config: Configuration manager
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Get email configuration
        self.email_config = config.get_email_config()
        self.enabled = config.get('logging.email_errors', False)
        
        if self.enabled and not self._validate_email_config():
            self.logger.warning("Email notifications disabled due to missing configuration")
            self.enabled = False
    
    def _validate_email_config(self) -> bool:
        """Validate email configuration.
        
        Returns:
            True if configuration is valid
        """
        required_fields = ['from_email', 'to_email', 'password']
        
        for field in required_fields:
            if not self.email_config.get(field):
                self.logger.warning(f"Missing email configuration: {field}")
                return False
        
        return True
    
    def send_error_notification(self, error: Exception, context: str, error_count: int):
        """Send an error notification email.
        
        Args:
            error: The exception that occurred
            context: Context where the error occurred
            error_count: Number of errors since last notification
        """
        if not self.enabled:
            return
        
        try:
            # Create email message
            msg = MIMEMultipart()
            msg['From'] = self.email_config['from_email']
            msg['To'] = self.email_config['to_email']
            msg['Subject'] = f"Translation Notes AI Error - {context}"
            
            # Create email body
            body = self._create_error_email_body(error, context, error_count)
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email
            self._send_email(msg)
            
            self.logger.info(f"Error notification sent for: {context}")
            
        except Exception as e:
            self.logger.error(f"Failed to send error notification: {e}")
    
    def _create_error_email_body(self, error: Exception, context: str, error_count: int) -> str:
        """Create the email body for error notification.
        
        Args:
            error: The exception that occurred
            context: Context where the error occurred
            error_count: Number of errors since last notification
            
        Returns:
            Email body text
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Get the current log file path if available, otherwise fall back to default
        current_log_file = self.config.get('runtime.current_log_file')
        if current_log_file:
            log_file_location = current_log_file
        else:
            # Fallback to default location
            log_dir = self.config.get('logging.log_dir', 'logs')
            log_file = self.config.get('logging.log_file', 'translation_notes.log')
            log_file_location = f"{log_dir}/{log_file}"
        
        body = f"""
Translation Notes AI Error Report

Timestamp: {timestamp}
Context: {context}
Error Count: {error_count}

Error Details:
Type: {type(error).__name__}
Message: {str(error)}

System Information:
- Application: Translation Notes AI
- Configuration: {self.config.config_path}

This is an automated error notification. Please check the application logs for more details.

Log file location: {log_file_location}
"""
        
        return body.strip()
    
    def _send_email(self, msg: MIMEMultipart):
        """Send an email message.
        
        Args:
            msg: Email message to send
        """
        smtp_server = self.email_config['smtp_server']
        smtp_port = self.email_config['smtp_port']
        use_tls = self.email_config['use_tls']
        
        # Create SMTP connection
        if use_tls:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        
        try:
            # Login and send
            server.login(
                self.email_config['from_email'],
                self.email_config['password']
            )
            
            server.send_message(msg)
            
        finally:
            server.quit()
    
    def test_email_configuration(self) -> bool:
        """Test email configuration by sending a test email.
        
        Returns:
            True if test email was sent successfully
        """
        if not self.enabled:
            self.logger.info("Email notifications are disabled")
            return False
        
        try:
            # Create test message
            msg = MIMEMultipart()
            msg['From'] = self.email_config['from_email']
            msg['To'] = self.email_config['to_email']
            msg['Subject'] = "Translation Notes AI - Test Email"
            
            body = f"""
This is a test email from Translation Notes AI.

Timestamp: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

If you receive this email, error notifications are configured correctly.
"""
            
            msg.attach(MIMEText(body.strip(), 'plain'))
            
            # Send test email
            self._send_email(msg)
            
            self.logger.info("Test email sent successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Test email failed: {e}")
            return False 