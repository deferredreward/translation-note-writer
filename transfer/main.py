#!/usr/bin/env python3
"""
Translation Notes AI - Main Application (Refactored)
Orchestrates the translation notes AI system with improved modularity and security.
"""

import os
import sys
import signal
import logging
import traceback
import atexit
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
        
        # Set up exit debugging
        self._setup_exit_debugging()
        
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
        self.immediate_mode_enabled = False
        
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
        self.logger.info(f"Immediate mode: {'DISABLED (will be enabled if --immediate-mode flag is used)' if not self.immediate_mode_enabled else 'ENABLED'}")
        self.logger.info(f"Process ID: {os.getpid()}")
        self.logger.info(f"Python version: {sys.version}")
        self.logger.info(f"Working directory: {os.getcwd()}")
        self.logger.info("Keyboard shortcuts: Ctrl+C (soft stop) -> Ctrl+C (graceful stop) -> Ctrl+C (force exit)")
    
    def _setup_exit_debugging(self):
        """Set up comprehensive exit and error debugging."""
        # Register exit handler
        atexit.register(self._on_exit)
        
        # Set up exception hook for unhandled exceptions
        original_excepthook = sys.excepthook
        def exception_handler(exc_type, exc_value, exc_traceback):
            if exc_type is KeyboardInterrupt:
                self.logger.info("KeyboardInterrupt received, shutting down...")
            else:
                self.logger.error(f"Unhandled exception: {exc_type.__name__}: {exc_value}")
                self.logger.error("Traceback:")
                for line in traceback.format_tb(exc_traceback):
                    self.logger.error(line.rstrip())
            original_excepthook(exc_type, exc_value, exc_traceback)
        
        sys.excepthook = exception_handler
        
        # Set up thread exception handler for Python 3.8+
        if hasattr(threading, 'excepthook'):
            def thread_exception_handler(args):
                self.logger.error(f"Unhandled exception in thread {args.thread.name}: {args.exc_type.__name__}: {args.exc_value}")
                if args.exc_traceback:
                    self.logger.error("Thread traceback:")
                    for line in traceback.format_tb(args.exc_traceback):
                        self.logger.error(line.rstrip())
            
            threading.excepthook = thread_exception_handler
    
    def _on_exit(self):
        """Called when the application is exiting."""
        self.logger.info("Application is exiting...")
        self.logger.info(f"Exit time: {datetime.now()}")
        
        # Log exit stack trace to see where exit came from
        import traceback
        self.logger.info("Exit called from:")
        for line in traceback.format_stack():
            self.logger.info(line.strip())
        
        # Log any active threads
        active_threads = threading.enumerate()
        self.logger.info(f"Active threads at exit: {len(active_threads)}")
        for thread in active_threads:
            if thread != threading.current_thread():
                self.logger.info(f"  Thread: {thread.name} (alive: {thread.is_alive()})")
        
        # Check continuous batch manager status
        if hasattr(self, 'continuous_batch_manager'):
            self.logger.info(f"Continuous batch manager running: {getattr(self.continuous_batch_manager, 'running', 'N/A')}")
            self.logger.info(f"Continuous batch manager shutdown requested: {getattr(self.continuous_batch_manager, 'shutdown_requested', 'N/A')}")
            
            # Log batch status
            running_batches = getattr(self.continuous_batch_manager, 'running_batches', {})
            self.logger.info(f"Running batches at exit: {len(running_batches)}")
            for batch_id, info in running_batches.items():
                self.logger.info(f"  - {batch_id}: user={getattr(info, 'user', 'unknown')}")
        
        self.logger.info("=== EXIT DEBUG COMPLETE ===")
    
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
    
    def enable_immediate_mode(self):
        """Enable immediate/synchronous AI processing for predictable timing."""
        self.immediate_mode_enabled = True
        self.logger.info("Immediate mode enabled - AI requests will be processed synchronously")
        self.logger.info("This provides predictable timing but may be slower for large batches")
    
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
        self._soft_stop_requested = False
        self._shutdown_timeout = 30  # seconds
        self._signal_count = 0
        
        def signal_handler(signum, frame):
            self._signal_count += 1
            
            if self._signal_count == 1:
                # First signal - soft stop (don't send new requests, wait for pending)
                self.logger.info("=== SOFT STOP REQUESTED ===")
                self.logger.info("No new AI requests will be sent. Waiting for pending responses...")
                self._soft_stop_requested = True
                
                # Signal continuous batch manager to stop accepting new work
                if hasattr(self, 'continuous_batch_manager'):
                    self.continuous_batch_manager.request_soft_stop()
                
                print("\n🛑 SOFT STOP: No new AI requests will be sent.")
                print("💾 Waiting for pending responses to complete...")
                print("🔴 Press Ctrl+C again for immediate hard stop")
                
            elif self._signal_count == 2:
                # Second signal - graceful shutdown (stop new work, finish current batches)
                self.logger.info("=== GRACEFUL SHUTDOWN REQUESTED ===")
                self.logger.info("Graceful shutdown initiated. Stopping all processing...")
                self._shutdown_requested = True
                self.running = False
                
                # Stop continuous batch manager if running
                if hasattr(self, 'continuous_batch_manager'):
                    self.continuous_batch_manager.stop()
                
                print("\n⚠️ GRACEFUL SHUTDOWN: Stopping all processing...")
                print("🔴 Press Ctrl+C again to force immediate exit")
                
                # Start a timer for forced shutdown
                def force_shutdown():
                    if self._shutdown_requested:
                        self.logger.error(f"Graceful shutdown timeout ({self._shutdown_timeout}s), forcing exit!")
                        sys.exit(1)
                
                timer = threading.Timer(self._shutdown_timeout, force_shutdown)
                timer.daemon = True
                timer.start()
                
            else:
                # Third signal - force immediate exit
                self.logger.warning("FORCE EXIT: Immediate termination requested!")
                print("\n💥 FORCE EXIT: Terminating immediately!")
                sys.exit(1)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def run_continuous(self):
        """Run in continuous monitoring mode."""
        try:
            self.running = True
            self.logger.info("=== STARTING CONTINUOUS MODE ===")
            
            if self.use_continuous_processing:
                self.logger.info("Starting continuous batch processing mode...")
                print("🚀 Starting continuous batch processing...")
                print("📋 Keyboard controls:")
                print("   🛑 Ctrl+C once:  SOFT STOP (no new requests, wait for pending)")
                print("   ⚠️  Ctrl+C twice: GRACEFUL SHUTDOWN (stop processing)")
                print("   💥 Ctrl+C three: FORCE EXIT (immediate termination)")
                print()
                
                # Log before starting continuous batch manager
                self.logger.info("About to start continuous batch manager...")
                self.continuous_batch_manager.start()
                self.logger.info("Continuous batch manager.start() returned - should not reach here unless shutdown")
                
                # Keep the main thread alive with periodic heartbeat logging
                loop_count = 0
                heartbeat_interval = 300  # Log heartbeat every 5 minutes
                
                while self.running and not getattr(self, '_shutdown_requested', False):
                    try:
                        time.sleep(self.timing_config['loop_sleep_interval'])
                        loop_count += 1
                        
                        # Handle soft stop - check if all batches are complete
                        if self._soft_stop_requested and not self._shutdown_requested:
                            with getattr(self.continuous_batch_manager, 'lock', threading.Lock()):
                                pending_batches = len(getattr(self.continuous_batch_manager, 'running_batches', {}))
                                
                            if pending_batches == 0:
                                self.logger.info("=== SOFT STOP COMPLETE ===")
                                self.logger.info("All pending batches completed. Exiting cleanly.")
                                print("\n✅ SOFT STOP COMPLETE: All pending responses received. Exiting cleanly.")
                                self.running = False
                                break
                            else:
                                # Log soft stop progress periodically
                                if loop_count % 30 == 0:  # Every 30 loops (roughly every 30 seconds)
                                    self.logger.info(f"Soft stop in progress: {pending_batches} pending batch(es) remaining...")
                                    print(f"💾 Soft stop: {pending_batches} pending batch(es) remaining...")
                        
                        # Log heartbeat periodically and perform health check
                        if loop_count % (heartbeat_interval // self.timing_config['loop_sleep_interval']) == 0:
                            self.logger.info(f"Heartbeat: Application running normally (loop #{loop_count})")
                            self.health_check()
                    
                    except Exception as loop_error:
                        self.logger.error(f"Error in main loop: {loop_error}")
                        self.logger.error("Main loop traceback:")
                        for line in traceback.format_exc().split('\n'):
                            if line.strip():
                                self.logger.error(line)
                        # Continue the loop unless it's a critical error
                        time.sleep(5)
                    
            else:
                self.logger.info("Starting legacy polling mode...")
                self._run_legacy_continuous()
                
        except KeyboardInterrupt:
            self.logger.info("KeyboardInterrupt in run_continuous - initiating shutdown")
        except Exception as e:
            self.logger.error(f"Critical error in continuous mode: {e}")
            self.logger.error("Critical error traceback:")
            for line in traceback.format_exc().split('\n'):
                if line.strip():
                    self.logger.error(line)
            raise
        finally:
            self.logger.info("=== CONTINUOUS MONITORING STOPPED ===")
            try:
                if hasattr(self, 'continuous_batch_manager'):
                    self.continuous_batch_manager.stop()
            except Exception as stop_error:
                self.logger.error(f"Error stopping continuous batch manager: {stop_error}")
    
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
    
    def run_complete(self, dry_run: bool = False):
        """Run processing until no work is found - suitable for cron jobs."""
        try:
            if dry_run:
                self.logger.info("Running in DRY RUN mode - no changes will be made")
            
            self.running = True
            cycle_count = 0
            total_processed = 0
            
            self.logger.info("=== STARTING COMPLETE MODE ===")
            self.logger.info("Processing will continue until no work is found across all sheets")
            
            while self.running and not getattr(self, '_shutdown_requested', False):
                cycle_count += 1
                self.logger.info(f"=== Processing cycle {cycle_count} ===")
                
                # Check for work and count items processed
                cycle_processed = self._check_for_work_with_count()
                total_processed += cycle_processed
                
                if cycle_processed == 0:
                    self.logger.info("No work found in this cycle - processing complete")
                    break
                else:
                    self.logger.info(f"Processed {cycle_processed} items in cycle {cycle_count}")
                    
                    # Small delay between cycles to avoid overwhelming the system
                    if self.running and not getattr(self, '_shutdown_requested', False):
                        import time
                        time.sleep(self.timing_config.get('cycle_delay', 2))
            
            self.logger.info(f"=== COMPLETE MODE FINISHED ===")
            self.logger.info(f"Total cycles: {cycle_count}")
            self.logger.info(f"Total items processed: {total_processed}")
            
            if getattr(self, '_shutdown_requested', False):
                self.logger.info("Processing stopped due to shutdown request")
            else:
                self.logger.info("Processing completed - no more work found")
            
        except KeyboardInterrupt:
            self.logger.info("Complete mode interrupted by user")
        except Exception as e:
            self.logger.error(f"Error in complete mode: {e}")
            raise
        finally:
            self.running = False
    
    def _check_for_work_with_count(self) -> int:
        """Check all sheets for new work and process it, returning count of processed items."""
        try:
            if getattr(self, '_shutdown_requested', False):
                self.logger.info("Shutdown requested, skipping work check")
                return 0
            
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
            
            return total_processed
                
        except Exception as e:
            self.logger.error(f"Error checking for work: {e}")
            self.handle_error(e, "Checking for work")
            return 0
    
    def check_for_work(self):
        """Check all sheets for new work and process it (legacy synchronous mode)."""
        self._check_for_work_with_count()
    
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
                if self.immediate_mode_enabled:
                    # Use immediate processing for predictable timing
                    processed_count = self._process_items_immediately(sanitized_items, sheet_id, editor_name)
                else:
                    # Use batch processing as normal
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
    
    def _process_items_immediately(self, items: List[Dict[str, Any]], sheet_id: str, editor_name: str) -> int:
        """Process items immediately using synchronous AI calls.
        
        Args:
            items: List of sanitized items to process
            sheet_id: Google Sheets ID
            editor_name: Editor name for logging
            
        Returns:
            Number of items successfully processed
        """
        from modules.processing_utils import prepare_update_data, ensure_biblical_text_cached
        
        self.logger.info(f"Processing {len(items)} items immediately for {editor_name}")
        
        try:
            # Initialize editor_key and book variables
            editor_key = None
            book = None
            
            # Ensure biblical text is cached (same as continuous batch processing)
            if items:
                # Get the editor key from sheet_id
                sheet_ids = self.config.get('google_sheets.sheet_ids', {})
                for key, sid in sheet_ids.items():
                    if sid == sheet_id:
                        editor_key = key
                        break
                
                if editor_key:
                    # Use the same book detection as continuous batch processing
                    _, book = self.cache_manager.detect_user_book_from_items(items)
                    if book:
                        self.logger.info(f"Ensuring biblical text cached for {editor_key}/{book}")
                        ensure_biblical_text_cached(editor_key, book, self.cache_manager, self.sheet_manager, self.config, self.logger)
                    else:
                        self.logger.warning("Could not determine book from items (missing Book column?)")
                else:
                    self.logger.warning(f"Could not determine editor key for sheet {sheet_id}")
            
            # Process items using immediate AI service with user/book context
            results = self.ai_service.process_items_immediately(items, user=editor_key, book=book)
            
            # Prepare updates for successful results
            updates = []
            success_count = 0
            
            for result in results:
                if result['success']:
                    # Use the same processing pipeline as batch processing
                    update_data = prepare_update_data(result['original_item'], result['output'], self.logger)
                    if update_data:
                        updates.append(update_data)
                        success_count += 1
                    else:
                        self.logger.error(f"Failed to prepare update data for item: {result['original_item'].get('Ref', 'unknown')}")
                else:
                    self.logger.error(f"AI processing failed for item {result['original_item'].get('Ref', 'unknown')}: {result.get('error', 'Unknown error')}")
            
            # Update the sheet with results
            if updates:
                if not self.config.get('debug.dry_run', False):
                    self.sheet_manager.batch_update_rows(sheet_id, updates)
                    self.logger.info(f"Successfully updated {len(updates)} rows in {editor_name}")
                    
                    # Call completion callback if set
                    if hasattr(self, 'batch_processor') and hasattr(self.batch_processor, 'completion_callback') and self.batch_processor.completion_callback:
                        self.batch_processor.completion_callback(len(updates), f"Immediate processing for {editor_name}")
                else:
                    self.logger.info(f"DRY RUN: Would update {len(updates)} rows in {editor_name}")
            
            return success_count
            
        except Exception as e:
            self.logger.error(f"Error during immediate processing for {editor_name}: {e}")
            self.handle_error(e, f"Immediate processing for {editor_name}")
            return 0
    
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
            
            self.logger.error(f"=== ERROR #{self.error_count} ===")
            self.logger.error(f"Context: {safe_context}")
            self.logger.error(f"Error type: {type(error).__name__}")
            self.logger.error(f"Error message: {safe_error_msg}")
            
            # Log full traceback for debugging
            if hasattr(error, '__traceback__') and error.__traceback__:
                self.logger.error("Full traceback:")
                for line in traceback.format_tb(error.__traceback__):
                    self.logger.error(line.rstrip())
            
            # Log current thread information
            current_thread = threading.current_thread()
            self.logger.error(f"Thread: {current_thread.name} (ID: {current_thread.ident})")
            
            # Send error notifications if configured
            if self.config.get('logging.email_errors', False):
                self._send_error_notification(safe_error_msg, safe_context)
            
        except Exception as e:
            self.logger.error(f"Error in error handler: {e}")
            self.logger.error("Error handler traceback:")
            for line in traceback.format_exc().split('\n'):
                if line.strip():
                    self.logger.error(line)
    
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
    
    def health_check(self):
        """Perform a comprehensive health check and log status."""
        try:
            self.logger.info("=== HEALTH CHECK ===")
            self.logger.info(f"Application running: {self.running}")
            self.logger.info(f"Error count: {self.error_count}")
            
            # Check thread status
            active_threads = threading.enumerate()
            self.logger.info(f"Active threads: {len(active_threads)}")
            for thread in active_threads:
                self.logger.info(f"  - {thread.name}: alive={thread.is_alive()}, daemon={thread.daemon}")
            
            # Check continuous batch manager status
            if hasattr(self, 'continuous_batch_manager'):
                self.logger.info(f"Continuous batch manager running: {getattr(self.continuous_batch_manager, 'running', 'N/A')}")
                self.logger.info(f"Continuous batch manager shutdown requested: {getattr(self.continuous_batch_manager, 'shutdown_requested', 'N/A')}")
            
            # Check cache status
            try:
                cache_info = self.cache_manager.get_cache_info()
                self.logger.info(f"Cache status: {len(cache_info)} caches")
                for cache_name, info in cache_info.items():
                    self.logger.info(f"  - {cache_name}: valid={info.get('valid', False)}")
            except Exception as cache_error:
                self.logger.warning(f"Could not check cache status: {cache_error}")
            
            self.logger.info("=== END HEALTH CHECK ===")
            
        except Exception as e:
            self.logger.error(f"Error during health check: {e}")


def main():
    """Main entry point using our new CLI system with enhanced error handling."""
    try:
        return main_cli_entry_point(TranslationNotesAI)
    except KeyboardInterrupt:
        print("\nApplication interrupted by user")
        return 0
    except SystemExit as e:
        print(f"\nApplication exited with code: {e.code}")
        return e.code
    except Exception as e:
        print(f"\nCritical error in main: {e}")
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main()) 