#!/usr/bin/env python3
"""
Translation Notes AI - Main Application (Refactored)
Orchestrates the translation notes AI system with improved modularity and security.
"""

import os
import sys
import signal
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import threading
import time

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import our well-organized modules
from modules import (
    ConfigManager, setup_logging, SheetManager, AIService, CacheManager,
    BatchProcessor, ContinuousBatchManager, ErrorNotifier,
    SecurityValidator, ConfigSecurityValidator,
    NotificationSystem, post_process_text,
    TranslationNotesAICLI, main_cli_entry_point
)


class TranslationNotesAI:
    """Main application class that orchestrates the translation notes AI system.
    
    This refactored version is much cleaner and uses proper separation of concerns.
    """
    
    def __init__(self):
        """Initialize the application with proper error handling and security validation."""
        # Initialize core configuration and logging
        self.config = ConfigManager()
        self.logger = setup_logging(self.config)
        
        # Get timing configuration
        self.timing_config = self.config.get_timing_config()
        
        # Initialize security components
        self.security_validator = SecurityValidator(self.logger)
        self.config_security = ConfigSecurityValidator(self.logger)
        
        # Validate configuration security
        self._validate_configuration_security()
        
        # Initialize application state
        self.running = False
        self.last_error_notification = None
        self.error_count = 0
        self.use_continuous_processing = self.config.get('processing.use_continuous_batch_processing', True)
        
        # Initialize notification system
        self.notification_system = NotificationSystem(
            logger=self.logger,
            enabled=False  # Will be enabled via command line if requested
        )
        
        # Permission error tracking for legacy mode
        self.blocked_sheets: Dict[str, datetime] = {}
        self.permission_block_hours = self.config.get('processing.permission_block_hours', 1)
        
        # Initialize core components
        self._initialize_components()
        
        self.logger.info("Translation Notes AI initialized successfully")
        self.logger.info(f"Continuous processing: {'ENABLED' if self.use_continuous_processing else 'DISABLED'}")
    
    def _validate_configuration_security(self):
        """Validate configuration for security issues."""
        try:
            warnings = self.config_security.validate_config_security(self.config.config)
            
            if warnings:
                self.logger.warning("Configuration security warnings:")
                for warning in warnings:
                    self.logger.warning(f"  - {warning}")
                    
        except Exception as e:
            self.logger.warning(f"Error during security validation: {e}")
    
    def _initialize_components(self):
        """Initialize all core components with proper error handling."""
        try:
            # Initialize sheet manager and cache
            self.sheet_manager = SheetManager(self.config)
            self.cache_manager = CacheManager(self.config, self.sheet_manager)
            
            # Initialize AI service
            self.ai_service = AIService(self.config, self.cache_manager)
            if self.ai_service.disabled:
                self.logger.warning("AI service is disabled. No API calls will be made.")
            
            # Initialize batch processors
            self.batch_processor = BatchProcessor(
                config=self.config,
                ai_service=self.ai_service,
                sheet_manager=self.sheet_manager,
                cache_manager=self.cache_manager
            )
            
            self.continuous_batch_manager = ContinuousBatchManager(
                config=self.config,
                ai_service=self.ai_service,
                sheet_manager=self.sheet_manager,
                cache_manager=self.cache_manager
            )
            
            # Initialize error notifier
            self.error_notifier = ErrorNotifier(self.config)
            
            # Initialize caches on startup
            self._initialize_caches()
            
        except Exception as e:
            self.logger.error(f"Failed to initialize components: {e}")
            raise
    
    def _initialize_caches(self):
        """Initialize caches with proper error handling."""
        try:
            self.logger.info("Initializing caches...")
            refreshed, content_changed = self.cache_manager.refresh_if_needed()
            
            if refreshed:
                self.logger.info(f"Initialized caches: {', '.join(refreshed)}")
            else:
                self.logger.info("All caches are up to date")
                
        except Exception as e:
            self.logger.warning(f"Error during cache initialization: {e}")
            # Continue anyway - caches will be refreshed on first use
    
    def enable_sound_notifications(self):
        """Enable sound notifications for AI results."""
        self.notification_system.enable()
        self.logger.info("Sound notifications enabled")
        
        # Set up notification callbacks for batch processors
        self.batch_processor.completion_callback = self._on_processing_complete
        self.continuous_batch_manager.completion_callback = self._on_processing_complete
    
    def _on_processing_complete(self, count: int = 1, context: str = ""):
        """Handle processing completion notifications.
        
        Args:
            count: Number of items processed
            context: Context description
        """
        self.notification_system.notify_completion(count, context, "translation note")
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        self._shutdown_requested = False
        self._shutdown_timeout = 30  # seconds
        
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, shutting down gracefully...")
            
            if self._shutdown_requested:
                # Second signal - force immediate exit
                self.logger.warning("Second interrupt signal received, forcing immediate exit!")
                sys.exit(1)
            
            self._shutdown_requested = True
            self.running = False
            
            # Stop continuous batch manager if running
            if hasattr(self, 'continuous_batch_manager'):
                self.continuous_batch_manager.stop()
            
            # Start a timer for forced shutdown
            def force_shutdown():
                if self._shutdown_requested:
                    self.logger.error(f"Graceful shutdown timeout ({self._shutdown_timeout}s), forcing exit!")
                    sys.exit(1)
            
            timer = threading.Timer(self._shutdown_timeout, force_shutdown)
            timer.daemon = True
            timer.start()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def run_continuous(self):
        """Run in continuous monitoring mode."""
        try:
            self.running = True
            
            if self.use_continuous_processing:
                self.logger.info("Starting continuous batch processing mode...")
                self.continuous_batch_manager.start()
                
                # Keep the main thread alive
                while self.running and not getattr(self, '_shutdown_requested', False):
                    time.sleep(self.timing_config['loop_sleep_interval'])
                    
            else:
                self.logger.info("Starting legacy polling mode...")
                self._run_legacy_continuous()
                
        except Exception as e:
            self.logger.error(f"Error in continuous mode: {e}")
            raise
        finally:
            self.logger.info("Continuous monitoring stopped")
    
    def _run_legacy_continuous(self):
        """Run legacy continuous processing with polling."""
        import schedule
        
        # Schedule periodic checks
        poll_interval = self.config.get('processing.poll_interval', 60)
        schedule.every(poll_interval).seconds.do(self.check_for_work)
        
        self.logger.info(f"Starting continuous monitoring (polling every {poll_interval}s)...")
        
        while self.running and not getattr(self, '_shutdown_requested', False):
            try:
                schedule.run_pending()
                time.sleep(self.timing_config['loop_sleep_interval'])
                
            except Exception as e:
                self.logger.error(f"Error in polling cycle: {e}")
                time.sleep(self.timing_config['retry_delay_brief'])  # Brief pause before retrying
    
    def run_once(self, dry_run: bool = False):
        """Run one-time processing."""
        try:
            if dry_run:
                self.logger.info("Running in DRY RUN mode - no changes will be made")
            
            self.check_for_work()
            self.logger.info("One-time processing completed")
            
        except Exception as e:
            self.logger.error(f"Error in one-time processing: {e}")
            raise
    
    def check_for_work(self):
        """Check all sheets for new work and process it (legacy synchronous mode)."""
        try:
            if getattr(self, '_shutdown_requested', False):
                self.logger.info("Shutdown requested, skipping work check")
                return
            
            self.logger.debug("Checking for new work...")
            
            # Get sheet IDs and ensure caches are ready
            sheet_ids = self.config.get('google_sheets.sheet_ids', {})
            self._ensure_support_references()
            
            # Process each sheet
            total_processed = 0
            auto_convert_sref = self.config.get('processing.auto_convert_sref', True)
            
            for editor_key, sheet_id in sheet_ids.items():
                if getattr(self, '_shutdown_requested', False):
                    break
                
                # Get friendly name for logging
                friendly_name = self.config.get_friendly_name_with_id(editor_key)
                
                # Check if sheet is blocked
                if self._is_sheet_blocked(sheet_id, editor_key):
                    continue
                
                try:
                    # Process suggestions and regular work
                    processed_count = self._process_sheet_work(sheet_id, friendly_name, auto_convert_sref)
                    total_processed += processed_count
                    
                except Exception as e:
                    if self._is_permission_error(e):
                        self._block_sheet_for_permission_error(sheet_id, editor_key)
                    else:
                        self.logger.error(f"Error processing {friendly_name}: {e}")
                        self.handle_error(e, f"Processing work for {friendly_name}")
            
            if total_processed > 0:
                self.logger.info(f"Processed {total_processed} items across all sheets")
            else:
                self.logger.debug("No work found")
                
        except Exception as e:
            self.logger.error(f"Error checking for work: {e}")
            self.handle_error(e, "Checking for work")
    
    def _ensure_support_references(self):
        """Ensure support references are cached."""
        support_references = self.cache_manager.get_cached_data('support_references')
        if not support_references:
            self.logger.debug("Support references not cached, fetching...")
            support_references = self.sheet_manager.fetch_support_references()
            if support_references:
                self.cache_manager.set_cached_data('support_references', support_references)
            else:
                self.logger.warning("Failed to fetch support references - SRef conversion may not work properly")
    
    def _process_sheet_work(self, sheet_id: str, editor_name: str, auto_convert_sref: bool) -> int:
        """Process work for a single sheet.
        
        Args:
            sheet_id: Google Sheets ID
            editor_name: Editor name
            auto_convert_sref: Whether to auto-convert SRef values
            
        Returns:
            Number of items processed
        """
        processed_count = 0
        
        # Check for suggestion requests first
        # (Implementation would be extracted to a separate suggestion handler module)
        # self._check_and_process_suggestion_requests(sheet_id, editor_name)
        
        # Convert SRef values if enabled
        if auto_convert_sref:
            self._convert_sref_values_for_sheet(sheet_id, editor_name)
        
        # Get and process pending work (with optional limit)
        processing_config = self.config.get_processing_config()
        max_items = processing_config.get('max_items_per_work_cycle', 0)
        max_items = max_items if max_items > 0 else None  # Convert 0 to None for no limit
        
        pending_items = self.sheet_manager.get_pending_work(sheet_id, max_items=max_items)
        if pending_items:
            self.logger.info(f"Found {len(pending_items)} pending items for {editor_name}")
            
            # Validate and sanitize the data
            sanitized_items = self._sanitize_sheet_data(pending_items)
            
            if sanitized_items:
                processed_count = self.batch_processor.process_items(sanitized_items, sheet_id)
                self.logger.info(f"Processed {processed_count} items for {editor_name}")
        
        return processed_count
    
    def _sanitize_sheet_data(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sanitize sheet data using our security validator.
        
        Args:
            items: List of sheet data items
            
        Returns:
            List of sanitized items
        """
        sanitized_items = []
        
        for item in items:
            try:
                sanitized_item = self.security_validator.validate_sheet_data(item)
                sanitized_items.append(sanitized_item)
                
            except ValueError as e:
                self.logger.warning(f"Skipping invalid item: {e}")
                continue
        
        return sanitized_items
    
    def _convert_sref_values_for_sheet(self, sheet_id: str, editor_name: str):
        """Convert SRef values for a specific sheet."""
        try:
            support_references = self.cache_manager.get_cached_data('support_references')
            if not support_references:
                return
            
            all_items = self.sheet_manager.get_all_rows_for_sref_conversion(sheet_id)
            if not all_items:
                return
            
            updates_needed = self.sheet_manager.convert_sref_values(all_items, support_references)
            if updates_needed:
                self.logger.info(f"Converting {len(updates_needed)} SRef values for {editor_name}")
                
                if not self.config.get('debug.dry_run', False):
                    self.sheet_manager.batch_update_rows(sheet_id, updates_needed)
                    self.logger.info(f"Successfully updated {len(updates_needed)} SRef values for {editor_name}")
                else:
                    self.logger.info("DRY RUN: Would update SRef values")
                    
        except Exception as e:
            self.logger.warning(f"Error during SRef conversion for {editor_name}: {e}")
    
    def _is_sheet_blocked(self, sheet_id: str, editor_name: str) -> bool:
        """Check if a sheet is blocked due to permission errors."""
        if sheet_id in self.blocked_sheets:
            blocked_until = self.blocked_sheets[sheet_id]
            if datetime.now() < blocked_until:
                remaining = (blocked_until - datetime.now()).total_seconds() / 60
                self.logger.debug(f"Sheet {editor_name} blocked for {remaining:.1f} more minutes")
                return True
            else:
                # Block expired, remove it
                del self.blocked_sheets[sheet_id]
        
        return False
    
    def _block_sheet_for_permission_error(self, sheet_id: str, editor_name: str):
        """Block a sheet due to permission errors."""
        block_until = datetime.now() + timedelta(hours=self.permission_block_hours)
        self.blocked_sheets[sheet_id] = block_until
        friendly_name_with_id = self.config.get_friendly_name_with_id(editor_name)
        self.logger.warning(f"Blocked {friendly_name_with_id} for {self.permission_block_hours} hour(s) due to permission error")
    
    def _is_permission_error(self, error: Exception) -> bool:
        """Check if an error is a permission-related error."""
        error_str = str(error).lower()
        permission_indicators = [
            'permission denied',
            'insufficient permissions',
            '403',
            'forbidden',
            'access denied'
        ]
        return any(indicator in error_str for indicator in permission_indicators)
    
    def handle_error(self, error: Exception, context: str = ""):
        """Handle errors with proper logging and notification.
        
        Args:
            error: The exception that occurred
            context: Context description for the error
        """
        try:
            self.error_count += 1
            
            # Sanitize error message for logging
            safe_error_msg = self.security_validator.sanitize_log_message(str(error))
            safe_context = self.security_validator.sanitize_log_message(context)
            
            self.logger.error(f"Error in {safe_context}: {safe_error_msg}")
            
            # Send error notifications if configured
            if self.config.get('logging.email_errors', False):
                self._send_error_notification(safe_error_msg, safe_context)
            
        except Exception as e:
            self.logger.error(f"Error in error handler: {e}")
    
    def _send_error_notification(self, error_msg: str, context: str):
        """Send error notification email if appropriate."""
        try:
            # Implement cooldown to avoid spam
            now = datetime.now()
            cooldown_minutes = self.config.get('logging.email_cooldown_minutes', 10)
            
            if (self.last_error_notification and 
                (now - self.last_error_notification).total_seconds() < cooldown_minutes * 60):
                return
            
            self.error_notifier.send_error_notification(
                f"Translation Notes AI Error in {context}",
                error_msg
            )
            
            self.last_error_notification = now
            
        except Exception as e:
            self.logger.error(f"Failed to send error notification: {e}")
    
    # Utility methods for CLI commands
    def force_refresh_templates(self) -> bool:
        """Force refresh template cache."""
        try:
            self.cache_manager.clear_cache('templates')
            templates = self.sheet_manager.fetch_templates()
            if templates:
                self.cache_manager.set_cached_data('templates', templates)
                self.logger.info("Template cache refreshed successfully")
                return True
            else:
                self.logger.error("Failed to refresh template cache")
                return False
        except Exception as e:
            self.logger.error(f"Error refreshing template cache: {e}")
            return False
    
    def force_refresh_support_refs(self) -> bool:
        """Force refresh support references cache."""
        try:
            self.cache_manager.clear_cache('support_references')
            support_refs = self.sheet_manager.fetch_support_references()
            if support_refs:
                self.cache_manager.set_cached_data('support_references', support_refs)
                self.logger.info("Support references cache refreshed successfully")
                return True
            else:
                self.logger.error("Failed to refresh support references cache")
                return False
        except Exception as e:
            self.logger.error(f"Error refreshing support references cache: {e}")
            return False
    
    def get_cache_status(self):
        """Display cache status information."""
        try:
            cache_info = self.cache_manager.get_cache_info()
            
            print("\n=== Cache Status ===")
            for cache_name, info in cache_info.items():
                status = "✓ Valid" if info['valid'] else "✗ Invalid/Missing"
                size_mb = info.get('size_mb', 0)
                last_updated = info.get('last_updated', 'Never')
                
                print(f"{cache_name}: {status}")
                print(f"  Size: {size_mb:.2f} MB")
                print(f"  Last Updated: {last_updated}")
                print()
                
        except Exception as e:
            self.logger.error(f"Error getting cache status: {e}")
    
    def convert_sref_values(self) -> bool:
        """Convert SRef values for all sheets."""
        try:
            sheet_ids = self.config.get('google_sheets.sheet_ids', {})
            total_converted = 0
            
            for editor_key, sheet_id in sheet_ids.items():
                friendly_name = self.config.get_friendly_name_with_id(editor_key)
                self.logger.info(f"Converting SRef values for {friendly_name}...")
                self._convert_sref_values_for_sheet(sheet_id, friendly_name)
                
            return True
            
        except Exception as e:
            self.logger.error(f"Error converting SRef values: {e}")
            return False


def main():
    """Main entry point using our new CLI system."""
    return main_cli_entry_point(TranslationNotesAI)


if __name__ == '__main__':
    sys.exit(main()) 