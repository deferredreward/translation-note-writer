#!/usr/bin/env python3
"""
Translation Notes AI - Main Application
Monitors Google Sheets and processes translation notes using AI with continuous batch processing.
"""

import os
import sys
import time
import signal
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import schedule
import json

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.config_manager import ConfigManager
from modules.logger import setup_logging
from modules.sheet_manager import SheetManager
from modules.ai_service import AIService
from modules.cache_manager import CacheManager
from modules.batch_processor import BatchProcessor
from modules.continuous_batch_manager import ContinuousBatchManager
from modules.error_notifier import ErrorNotifier


def _post_process_text(text: str) -> str:
    """Post-process text by removing curly braces and converting straight quotes to smart quotes.
    
    Args:
        text: Input text to process
        
    Returns:
        Processed text with curly braces removed and smart quotes
    """
    if not text:
        return text
    
    # Remove all curly braces
    processed = text.replace('{', '').replace('}', '')
    
    # Convert straight quotes to smart quotes
    # This handles nested quotes and alternates between single and double quotes appropriately
    
    # First handle double quotes
    # Use a simple state machine to alternate between opening and closing quotes
    result = []
    in_double_quotes = False
    i = 0
    
    while i < len(processed):
        char = processed[i]
        
        if char == '"':
            if in_double_quotes:
                # Closing double quote
                result.append('\u201D')  # RIGHT DOUBLE QUOTATION MARK
                in_double_quotes = False
            else:
                # Opening double quote
                result.append('\u201C')  # LEFT DOUBLE QUOTATION MARK
                in_double_quotes = True
        elif char == "'":
            # For single quotes, check context to determine if it's an apostrophe or quote
            if i > 0 and processed[i-1].isalnum():
                # Likely an apostrophe (preceded by alphanumeric)
                result.append('\u2019')  # RIGHT SINGLE QUOTATION MARK (apostrophe)
            elif i < len(processed) - 1 and processed[i+1].isalnum():
                # Likely opening single quote (followed by alphanumeric)
                result.append('\u2018')  # LEFT SINGLE QUOTATION MARK
            else:
                # Default to closing single quote
                result.append('\u2019')  # RIGHT SINGLE QUOTATION MARK
        else:
            result.append(char)
        
        i += 1
    
    return ''.join(result)


class TranslationNotesAI:
    """Main application class that orchestrates the translation notes AI system."""
    
    def __init__(self):
        """Initialize the application."""
        self.config = ConfigManager()
        self.logger = setup_logging(self.config)
        self.running = False
        self.last_error_notification = None
        self.error_count = 0
        self.use_continuous_processing = self.config.get('processing.use_continuous_batch_processing', True)  # Read from config
        self.sound_notifications = False  # Will be set by command line argument
        
        # Permission error tracking (for legacy mode)
        self.blocked_sheets: Dict[str, datetime] = {}  # sheet_id -> blocked_until_time
        self.permission_block_hours = self.config.get('processing.permission_block_hours', 1)  # Read from config
        
        # Initialize components
        try:
            self.sheet_manager = SheetManager(self.config)
            self.cache_manager = CacheManager(self.config, self.sheet_manager)
            self.ai_service = AIService(self.config, self.cache_manager)
            
            # Initialize both batch processors
            self.batch_processor = BatchProcessor(
                config=self.config, 
                ai_service=self.ai_service, 
                sheet_manager=self.sheet_manager,
                cache_manager=self.cache_manager
            )
            
            # Initialize the new continuous batch manager
            self.continuous_batch_manager = ContinuousBatchManager(
                config=self.config,
                ai_service=self.ai_service,
                sheet_manager=self.sheet_manager,
                cache_manager=self.cache_manager
            )
            
            self.error_notifier = ErrorNotifier(self.config)
            
            # Initialize caches on startup
            self.logger.info("Initializing caches...")
            try:
                refreshed, content_changed = self.cache_manager.refresh_if_needed()
                if refreshed:
                    self.logger.info(f"Initialized caches: {', '.join(refreshed)}")
                else:
                    self.logger.info("All caches are up to date")
            except Exception as e:
                self.logger.warning(f"Error during cache initialization: {e}")
                # Continue anyway - caches will be refreshed on first use
            
            self.logger.info("Translation Notes AI initialized successfully")
            self.logger.info(f"Continuous processing: {'ENABLED' if self.use_continuous_processing else 'DISABLED'}")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize application: {e}")
            raise
    
    def enable_sound_notifications(self):
        """Enable sound notifications for AI results."""
        self.sound_notifications = True
        self.logger.info("Sound notifications enabled - will play sound when AI writes results to spreadsheet")
        
        # Pass the notification callback to components that write to sheets
        self.batch_processor.completion_callback = self.play_notification_sound
        self.continuous_batch_manager.completion_callback = self.play_notification_sound
    
    def play_notification_sound(self, count: int = 1, context: str = ""):
        """Play a notification sound when AI writes results to spreadsheet.
        
        Args:
            count: Number of items written (affects sound duration/repetition)
            context: Context description for logging
        """
        if not self.sound_notifications:
            return
            
        try:
            import platform
            system = platform.system().lower()
            
            if system == "windows":
                # Use winsound for Windows
                try:
                    import winsound
                    # Play a system sound - SystemQuestion is a pleasant notification sound
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                    if count > 1:
                        # For multiple items, play an additional beep
                        time.sleep(0.2)
                        winsound.MessageBeep(winsound.MB_ICONASTERISK)
                    
                    context_msg = f" ({context})" if context else ""
                    self.logger.info(f"🔊 Played notification sound for {count} AI result(s) written to spreadsheet{context_msg}")
                    
                except ImportError:
                    self.logger.debug("winsound not available, trying alternative...")
                    self._play_fallback_sound()
                    
            elif system == "darwin":  # macOS
                try:
                    import subprocess
                    # Use macOS say command or afplay for system sounds
                    subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], 
                                 check=False, capture_output=True)
                    context_msg = f" ({context})" if context else ""
                    self.logger.info(f"🔊 Played notification sound for {count} AI result(s) written to spreadsheet{context_msg}")
                except Exception:
                    self._play_fallback_sound()
                    
            elif system == "linux":
                try:
                    import subprocess
                    # Try different Linux sound methods
                    for cmd in [["paplay", "/usr/share/sounds/alsa/Front_Right.wav"],
                               ["aplay", "/usr/share/sounds/alsa/Front_Right.wav"], 
                               ["espeak", "AI results ready"]]:
                        try:
                            subprocess.run(cmd, check=False, capture_output=True, timeout=3)
                            context_msg = f" ({context})" if context else ""
                            self.logger.info(f"🔊 Played notification sound for {count} AI result(s) written to spreadsheet{context_msg}")
                            break
                        except (subprocess.TimeoutExpired, FileNotFoundError):
                            continue
                    else:
                        self._play_fallback_sound()
                except Exception:
                    self._play_fallback_sound()
                    
            else:
                self._play_fallback_sound()
                
        except Exception as e:
            self.logger.debug(f"Error playing notification sound: {e}")
            # Don't let sound errors interrupt the main workflow
    
    def _play_fallback_sound(self):
        """Fallback method to create an audible notification."""
        try:
            # Try the cross-platform pygame method
            try:
                import pygame
                pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
                
                # Generate a simple beep sound
                import numpy as np
                duration = 0.3  # seconds
                sample_rate = 22050
                frequency = 800  # Hz
                
                frames = int(duration * sample_rate)
                arr = np.zeros(frames)
                for i in range(frames):
                    arr[i] = np.sin(2 * np.pi * frequency * i / sample_rate)
                arr = (arr * 32767).astype(np.int16)
                
                # Convert to stereo
                stereo_arr = np.zeros((frames, 2), dtype=np.int16)
                stereo_arr[:, 0] = arr
                stereo_arr[:, 1] = arr
                
                sound = pygame.sndarray.make_sound(stereo_arr)
                sound.play()
                time.sleep(duration)
                pygame.mixer.quit()
                
                self.logger.info("🔊 Played fallback notification sound")
                return
                
            except ImportError:
                pass
            
            # If all else fails, just print a visual notification
            self.logger.info("🔊 *** AI RESULTS WRITTEN TO SPREADSHEET *** 🔊")
            print("\a", end="", flush=True)  # Terminal bell character
            
        except Exception as e:
            self.logger.debug(f"Fallback sound method failed: {e}")
            # Final fallback - just log
            self.logger.info("🔊 *** AI RESULTS WRITTEN TO SPREADSHEET *** 🔊")
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        import threading
        
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
    
    def check_for_work(self):
        """Check all sheets for new work and process it (legacy synchronous mode)."""
        try:
            # Check if shutdown was requested
            if getattr(self, '_shutdown_requested', False):
                self.logger.info("Shutdown requested, skipping work check")
                return
                
            self.logger.debug("Checking for new work...")
            
            # Get all sheet IDs to monitor
            sheet_ids = self.config.get('google_sheets.sheet_ids', {})
            
            # First, ensure we have support references for SRef conversion
            support_references = self.cache_manager.get_cached_data('support_references')
            if not support_references:
                self.logger.debug("Support references not cached, fetching...")
                support_references = self.sheet_manager.fetch_support_references()
                if support_references:
                    self.cache_manager.set_cached_data('support_references', support_references)
                else:
                    self.logger.warning("Failed to fetch support references - SRef conversion may not work properly")
                    support_references = []
            
            # Check for shutdown before continuing
            if getattr(self, '_shutdown_requested', False):
                self.logger.info("Shutdown requested during cache fetch")
                return
            
            # Check if automatic SRef conversion is enabled
            auto_convert_sref = self.config.get('processing.auto_convert_sref', True)
            
            total_processed = 0
            
            for editor_key, sheet_id in sheet_ids.items():
                # Get friendly name for logging
                friendly_name = self.config.get_editor_name_for_sheet(sheet_id)
                
                # Check for shutdown before processing each sheet
                if getattr(self, '_shutdown_requested', False):
                    self.logger.info(f"Shutdown requested, stopping at {friendly_name}")
                    break
                
                # Check if sheet is blocked due to permission errors
                if self._is_sheet_blocked(sheet_id, editor_key):
                    continue
                    
                try:
                    # First check for suggestion requests
                    self._check_and_process_suggestion_requests(sheet_id, friendly_name)
                    
                    # Step 1: Convert SRef values BEFORE getting pending work
                    if support_references and auto_convert_sref:
                        self.logger.debug(f"Converting SRef values for {friendly_name}...")
                        try:
                            # Get all rows for SRef conversion
                            all_items = self.sheet_manager.get_all_rows_for_sref_conversion(sheet_id)
                            
                            if all_items:
                                # Convert SRef values
                                updates_needed = self.sheet_manager.convert_sref_values(all_items, support_references)
                                
                                if updates_needed:
                                    self.logger.info(f"Converting {len(updates_needed)} SRef values for {friendly_name}")
                                    
                                    if not self.config.get('debug.dry_run', False):
                                        # Apply the updates (no sound notification for SRef conversions)
                                        self.sheet_manager.batch_update_rows(sheet_id, updates_needed)
                                        self.logger.info(f"Successfully updated {len(updates_needed)} SRef values for {friendly_name}")
                                    else:
                                        self.logger.info("DRY RUN: Would update SRef values")
                                        for update in updates_needed:
                                            self.logger.info(f"  Row {update['row_number']}: '{update['original_sref']}' -> '{update['updated_sref']}'")
                                else:
                                    self.logger.debug(f"No SRef conversions needed for {friendly_name}")
                        except Exception as e:
                            if self._is_permission_error(e):
                                self._block_sheet_for_permission_error(sheet_id, editor_key)
                                continue
                            else:
                                self.logger.warning(f"Error during SRef conversion for {friendly_name}: {e}")
                                # Continue with processing even if SRef conversion fails
                    
                    # Check for shutdown again
                    if getattr(self, '_shutdown_requested', False):
                        self.logger.info(f"Shutdown requested during SRef conversion for {friendly_name}")
                        break
                    
                    # Step 2: Get pending work from this sheet (now with updated SRef values)
                    pending_items = self.sheet_manager.get_pending_work(sheet_id)
                    
                    if pending_items:
                        self.logger.info(f"Found {len(pending_items)} pending items for {friendly_name}")
                        
                        # Check for shutdown before processing
                        if getattr(self, '_shutdown_requested', False):
                            self.logger.info(f"Shutdown requested, skipping processing for {friendly_name}")
                            break
                        
                        # Step 3: Process in batches (templates will now match properly with full SRef values)
                        processed_count = self.batch_processor.process_items(pending_items, sheet_id)
                        total_processed += processed_count
                        
                        self.logger.info(f"Processed {processed_count} items for {friendly_name}")
                    
                except Exception as e:
                    if self._is_permission_error(e):
                        self._block_sheet_for_permission_error(sheet_id, editor_key)
                    else:
                        self.logger.error(f"Error processing sheet for {friendly_name}: {e}")
                        self.handle_error(e, f"Processing sheet for {friendly_name}")
            
            if total_processed > 0:
                self.logger.info(f"Total items processed this cycle: {total_processed}")
            else:
                self.logger.debug("No pending work found")
                
        except Exception as e:
            self.logger.error(f"Error in check_for_work: {e}")
            self.handle_error(e, "Checking for work")
    
    def refresh_caches(self, force_refresh: List[str] = None):
        """Refresh cached data based on configured intervals.
        
        Args:
            force_refresh: List of cache keys to force refresh regardless of time/content
        """
        try:
            self.logger.debug("Refreshing caches...")
            
            # Check if caches need refreshing
            refreshed, content_changed = self.cache_manager.refresh_if_needed(force_refresh)
            
            if refreshed:
                self.logger.info(f"Refreshed caches: {', '.join(refreshed)}")
                
                if content_changed:
                    self.logger.info(f"Content changed in caches: {', '.join(content_changed)}")
                    self.logger.info("Anthropic prompt cache will be updated with new content")
                else:
                    self.logger.debug("Cache refreshed but no content changes detected")
                
        except Exception as e:
            self.logger.error(f"Error refreshing caches: {e}")
            self.handle_error(e, "Refreshing caches")
    
    def force_refresh_templates(self):
        """Force refresh of template cache."""
        try:
            self.logger.info("Force refreshing template cache...")
            success = self.cache_manager.force_refresh_templates()
            if success:
                self.logger.info("Template cache force refresh completed")
            else:
                self.logger.warning("Template cache force refresh failed")
            return success
        except Exception as e:
            self.logger.error(f"Error force refreshing templates: {e}")
            self.handle_error(e, "Force refreshing templates")
            return False
    
    def force_refresh_support_refs(self):
        """Force refresh of support references cache."""
        try:
            self.logger.info("Force refreshing support references cache...")
            success = self.cache_manager.force_refresh_support_refs()
            if success:
                self.logger.info("Support references cache force refresh completed")
            else:
                self.logger.warning("Support references cache force refresh failed")
            return success
        except Exception as e:
            self.logger.error(f"Error force refreshing support references: {e}")
            self.handle_error(e, "Force refreshing support references")
            return False
    
    def get_cache_status(self):
        """Get detailed cache status information."""
        try:
            stats = self.cache_manager.get_cache_stats()
            freshness = self.cache_manager.check_cache_freshness()
            
            self.logger.info("=== Cache Status ===")
            self.logger.info(f"Cache directory: {stats['cache_dir']}")
            self.logger.info(f"Total files: {stats['total_files']}")
            self.logger.info(f"Total size: {stats['total_size_mb']} MB")
            
            for cache_key, info in freshness.items():
                status = "EXPIRED" if info['is_expired'] else "FRESH"
                if info['last_updated']:
                    self.logger.info(f"{cache_key}: {status} (age: {info['age_minutes']:.1f}min, expires in: {info['expires_in_minutes']:.1f}min)")
                else:
                    self.logger.info(f"{cache_key}: NOT CACHED")
            
            return {'stats': stats, 'freshness': freshness}
            
        except Exception as e:
            self.logger.error(f"Error getting cache status: {e}")
            return None
    
    def handle_error(self, error: Exception, context: str):
        """Handle errors with optional email notification."""
        self.error_count += 1
        
        # Check if we should send an error notification
        now = datetime.now()
        cooldown_minutes = self.config.get('logging.email_cooldown_minutes', 10)
        
        should_notify = (
            self.config.get('logging.email_errors', False) and
            (self.last_error_notification is None or 
             now - self.last_error_notification > timedelta(minutes=cooldown_minutes))
        )
        
        if should_notify:
            try:
                self.error_notifier.send_error_notification(error, context, self.error_count)
                self.last_error_notification = now
                self.error_count = 0  # Reset count after notification
            except Exception as e:
                self.logger.error(f"Failed to send error notification: {e}")
    
    def _is_sheet_blocked(self, sheet_id: str, user: str) -> bool:
        """Check if a sheet should be skipped due to recent permission errors.
        
        Args:
            sheet_id: Sheet ID to check
            user: User name for logging
            
        Returns:
            True if sheet should be skipped, False otherwise
        """
        if sheet_id not in self.blocked_sheets:
            return False
        
        blocked_until = self.blocked_sheets[sheet_id]
        now = datetime.now()
        
        if now < blocked_until:
            # Still blocked
            remaining_minutes = (blocked_until - now).total_seconds() / 60
            friendly_name = self.config.get_editor_name_for_sheet(sheet_id)
            self.logger.debug(f"Skipping {friendly_name} sheet - blocked for {remaining_minutes:.1f} more minutes due to permission error")
            return True
        else:
            # Block period expired, remove from blocked list
            del self.blocked_sheets[sheet_id]
            friendly_name = self.config.get_editor_name_for_sheet(sheet_id)
            self.logger.info(f"Permission block expired for {friendly_name} - resuming sheet monitoring")
            return False
    
    def _block_sheet_for_permission_error(self, sheet_id: str, user: str):
        """Block a sheet for the configured time period due to permission error.
        
        Args:
            sheet_id: Sheet ID to block
            user: User name for logging
        """
        blocked_until = datetime.now() + timedelta(hours=self.permission_block_hours)
        self.blocked_sheets[sheet_id] = blocked_until
        
        friendly_name = self.config.get_editor_name_for_sheet(sheet_id)
        self.logger.warning(f"PERMISSION DENIED for {friendly_name} sheet - blocking for {self.permission_block_hours} hour(s)")
        self.logger.warning(f"Will retry {friendly_name} sheet at {blocked_until.strftime('%Y-%m-%d %H:%M:%S')}")
    
    def _is_permission_error(self, error: Exception) -> bool:
        """Check if an error is a permission denied error.
        
        Args:
            error: Exception to check
            
        Returns:
            True if this is a 403 permission error
        """
        error_str = str(error).lower()
        return (
            '403' in error_str and 
            ('permission' in error_str or 'forbidden' in error_str)
        )
    
    def run_once(self, dry_run: bool = False):
        """Run the application once."""
        try:
            self.logger.info("Starting manual processing")
            
            # Refresh cache if needed
            self.cache_manager.refresh_if_needed()
            
            total_processed = 0
            
            # Process each user's sheet separately
            sheet_ids = self.config.get_google_sheets_config()['sheet_ids']
            
            for editor_key, sheet_id in sheet_ids.items():
                try:
                    friendly_name = self.config.get_editor_name_for_sheet(sheet_id)
                    self.logger.info(f"Processing sheet for {friendly_name}")
                    
                    # Get pending work for this user
                    pending_items = self.sheet_manager.get_pending_work(sheet_id)
                    
                    if pending_items:
                        # Process items for this specific user
                        self.batch_processor.process_items_for_user(editor_key, pending_items, dry_run=dry_run)
                        total_processed += len(pending_items)
                    else:
                        self.logger.info(f"No pending items found for {friendly_name}")
                        
                except Exception as e:
                    friendly_name = self.config.get_editor_name_for_sheet(sheet_id)
                    self.logger.error(f"Error processing sheet for {friendly_name}: {e}")
                    continue
            
            self.logger.info(f"Total items processed this cycle: {total_processed}")
            self.logger.info("Manual processing complete")
            
        except Exception as e:
            self.logger.error(f"Error in run_once: {e}")
            self.error_notifier.notify_error("Application Error", str(e))
            raise
    
    def run_continuous(self):
        """Run the application continuously with the new continuous batch processing system."""
        self.logger.info("Starting continuous monitoring...")
        self.running = True
        
        # Setup signal handlers for graceful shutdown
        self.setup_signal_handlers()
        
        if self.use_continuous_processing:
            # Use the new continuous batch manager
            self.logger.info("Starting continuous batch processing system...")
            
            try:
                # Start the continuous batch manager
                self.continuous_batch_manager.start()
                
                # Schedule cache refresh checks
                schedule.every(5).minutes.do(self.refresh_caches)
                
                # Main monitoring loop
                last_status_log = datetime.now()
                status_log_interval = timedelta(minutes=5)  # Log status every 5 minutes
                
                while self.running and not getattr(self, '_shutdown_requested', False):
                    try:
                        # Run scheduled tasks (like cache refresh)
                        schedule.run_pending()
                        
                        # Log status periodically
                        now = datetime.now()
                        if now - last_status_log > status_log_interval:
                            status = self.continuous_batch_manager.get_status()
                            self.logger.info(f"Batch Manager Status: {status['running_batches']}/{status['max_concurrent']} batches running, "
                                           f"{status['work_queue_size']} items queued, "
                                           f"{status['available_slots']} slots available")
                            
                            if status['batches']:
                                for batch_id, info in status['batches'].items():
                                    elapsed = (now - datetime.fromisoformat(info['submitted_at'])).total_seconds() / 60
                                    self.logger.debug(f"  Batch {batch_id[:8]}: {info['user']} ({info['items_count']} items, "
                                                    f"{elapsed:.1f}m running)")
                            
                            last_status_log = now
                        
                        # Small sleep to prevent busy waiting
                        time.sleep(1)
                        
                    except KeyboardInterrupt:
                        self.logger.info("Received keyboard interrupt")
                        break
                    except Exception as e:
                        self.logger.error(f"Error in continuous monitoring loop: {e}")
                        time.sleep(5)  # Wait before retrying
                
            except Exception as e:
                self.logger.error(f"Error in continuous batch processing: {e}")
                self.handle_error(e, "Continuous batch processing")
            
            finally:
                # Stop the continuous batch manager
                self.logger.info("Stopping continuous batch manager...")
                self.continuous_batch_manager.stop()
        
        else:
            # Use the legacy synchronous processing
            self.logger.info("Using legacy synchronous processing...")
            
            # Run the first check immediately
            try:
                self.run_once()
            except Exception as e:
                self.logger.error(f"Error in initial check: {e}")
            
            # Schedule the work checking for subsequent runs
            poll_interval = self.config.get('processing.poll_interval', 60)
            schedule.every(poll_interval).seconds.do(self.check_for_work)
            
            # Schedule cache refresh checks
            schedule.every(5).minutes.do(self.refresh_caches)
            
            try:
                while self.running and not getattr(self, '_shutdown_requested', False):
                    schedule.run_pending()
                    time.sleep(1)  # Small sleep to prevent busy waiting
                    
            except KeyboardInterrupt:
                self.logger.info("Received keyboard interrupt")
        
        # Cleanup
        self._shutdown_requested = True
        self.running = False
        self.logger.info("Shutting down...")
        
        # Clear any remaining scheduled jobs
        schedule.clear()
        
        # Give a moment for any running operations to finish
        time.sleep(2)
        
        self.logger.info("Application shutdown complete")
    
    def run_manual(self):
        """Run the application once manually (for testing or one-off processing)."""
        self.logger.info("Running manual processing cycle...")
        self.run_once()
        self.logger.info("Manual processing complete")
    
    def convert_sref_values(self):
        """Convert short SRef values to full support reference names across all sheets."""
        try:
            self.logger.info("Starting SRef conversion across all sheets...")
            
            # First, ensure we have support references cached
            support_references = self.cache_manager.get_cached_data('support_references')
            if not support_references:
                self.logger.info("Support references not cached, fetching...")
                support_references = self.sheet_manager.fetch_support_references()
                if support_references:
                    self.cache_manager.set_cached_data('support_references', support_references)
                else:
                    self.logger.error("Failed to fetch support references")
                    return False
            
            # Get all sheet IDs to process
            sheet_ids = self.config.get('google_sheets.sheet_ids', {})
            total_conversions = 0
            
            for editor_key, sheet_id in sheet_ids.items():
                try:
                    # Get friendly name for logging
                    friendly_name = self.config.get_editor_name_for_sheet(sheet_id)
                    self.logger.info(f"Processing SRef conversion for {friendly_name}...")
                    
                    # Get all rows from this sheet
                    all_items = self.sheet_manager.get_all_rows_for_sref_conversion(sheet_id)
                    
                    if not all_items:
                        self.logger.info(f"No rows found for {friendly_name}")
                        continue
                    
                    # Convert SRef values
                    updates_needed = self.sheet_manager.convert_sref_values(all_items, support_references)
                    
                    if updates_needed:
                        self.logger.info(f"Found {len(updates_needed)} SRef conversions needed for {friendly_name}")
                        
                        # Check if dry run mode
                        if self.config.get('debug.dry_run', False):
                            self.logger.info("DRY RUN MODE: Would update the following SRef values:")
                            for update in updates_needed:
                                self.logger.info(f"  Row {update['row_number']}: '{update['original_sref']}' -> '{update['updated_sref']}'")
                        else:
                            # Apply the updates (no sound notification for SRef conversions)
                            self.sheet_manager.batch_update_rows(sheet_id, updates_needed)
                            self.logger.info(f"Successfully updated {len(updates_needed)} SRef values for {friendly_name}")
                        
                        total_conversions += len(updates_needed)
                    else:
                        self.logger.info(f"No SRef conversions needed for {friendly_name}")
                
                except Exception as e:
                    friendly_name = self.config.get_editor_name_for_sheet(sheet_id)
                    self.logger.error(f"Error processing SRef conversion for {friendly_name}: {e}")
                    self.handle_error(e, f"SRef conversion for {friendly_name}")
            
            if total_conversions > 0:
                self.logger.info(f"SRef conversion completed. Total conversions: {total_conversions}")
            else:
                self.logger.info("SRef conversion completed. No conversions were needed.")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error in SRef conversion: {e}")
            self.handle_error(e, "SRef conversion")
            return False

    def _check_and_process_suggestion_requests(self, sheet_id: str, editor_name: str):
        """Check for suggestion requests and process them if conditions are met.
        
        Args:
            sheet_id: Google Sheets ID
            editor_name: Name of the editor/user
        """
        try:
            # Check if suggestion request exists
            if not self._has_suggestion_request(sheet_id):
                return
            
            self.logger.info(f"Found suggestion request for {editor_name}")
            
            # Check if other work is in progress
            if self._is_other_work_in_progress(sheet_id):
                self.logger.info(f"Other work in progress for {editor_name}, skipping suggestions")
                return
            
            # Process the suggestion request
            self._process_suggestion_request(sheet_id, editor_name)
            
        except Exception as e:
            self.logger.error(f"Error checking suggestion requests for {editor_name}: {e}")
            self.handle_error(e, f"Suggestion requests for {editor_name}")

    def _has_suggestion_request(self, sheet_id: str) -> bool:
        """Check if there's a suggestion request (YES in suggested notes tab, column D, row 2).
        
        Args:
            sheet_id: Google Sheets ID
            
        Returns:
            True if suggestion request exists
        """
        try:
            # Read from suggested notes tab, column D, row 2
            range_name = "'suggested notes'!D2"
            
            result = self.sheet_manager.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            if values and len(values) > 0 and len(values[0]) > 0:
                value = values[0][0].strip().upper()
                return value == 'YES'
            
            return False
            
        except Exception as e:
            self.logger.debug(f"Error checking suggestion request: {e}")
            return False

    def _is_other_work_in_progress(self, sheet_id: str) -> bool:
        """Check if other work is in progress (Go? column has non-AI values).
        
        Args:
            sheet_id: Google Sheets ID
            
        Returns:
            True if other work is in progress
        """
        try:
            # Read from AI notes tab, column F (Go?)
            range_name = "'AI notes'!F:F"
            
            result = self.sheet_manager.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            # Skip header row (index 0) and check all other rows
            for i, row in enumerate(values[1:], start=2):
                if row and len(row) > 0:
                    go_value = row[0].strip()
                    if go_value and go_value.upper() != 'AI':
                        self.logger.debug(f"Found non-AI work in progress: row {i}, Go? = '{go_value}'")
                        return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking work in progress: {e}")
            return True  # Assume work in progress on error

    def _process_suggestion_request(self, sheet_id: str, editor_name: str):
        """Process a suggestion request by gathering data and calling AI.
        
        Args:
            sheet_id: Google Sheets ID
            editor_name: Name of the editor/user
        """
        try:
            self.logger.info(f"Processing suggestion request for {editor_name}")
            
            # Get existing notes data
            existing_notes = self._get_existing_notes(sheet_id)
            if not existing_notes:
                self.logger.warning(f"No existing notes found for {editor_name}")
                return
            
            # Get chapter information from first note
            if existing_notes:
                first_note = existing_notes[0]
                book = first_note.get('Book', '')
                ref = first_note.get('Ref', '')
                
                if not book or not ref:
                    self.logger.warning(f"Missing book or ref information for {editor_name}")
                    return
                
                # Extract chapter from ref (e.g., "1:2" -> 1)
                try:
                    chapter = int(ref.split(':')[0])
                except (ValueError, IndexError):
                    self.logger.warning(f"Invalid ref format for {editor_name}: {ref}")
                    return
            else:
                self.logger.warning(f"No notes to extract chapter information for {editor_name}")
                return
            
            # Get ULT and UST chapter data
            ult_chapter_data = self._get_chapter_text(book, chapter, 'ult')
            ust_chapter_data = self._get_chapter_text(book, chapter, 'ust')
            
            if not ult_chapter_data or not ust_chapter_data:
                self.logger.warning(f"Failed to get chapter text for {editor_name}")
                return
            
            # Get existing suggestions to avoid duplicates
            existing_suggestions = self._get_existing_suggestions(sheet_id)
            
            # Get translation issue descriptions
            translation_issues = self._get_translation_issue_descriptions()
            
            # Call AI to generate suggestions
            suggestions = self._generate_ai_suggestions(
                ult_chapter_data, ust_chapter_data, existing_notes, 
                existing_suggestions, translation_issues
            )
            
            self.logger.info(f"Received {len(suggestions) if suggestions else 0} suggestions from AI")
            if suggestions:
                self.logger.info(f"First suggestion: {suggestions[0]}")
            
            if suggestions:
                # Write suggestions to sheet
                self.logger.info(f"About to write {len(suggestions)} suggestions to sheet")
                self._write_suggestions_to_sheet(sheet_id, suggestions)
                self.logger.info(f"Wrote {len(suggestions)} suggestions for {editor_name}")
            else:
                self.logger.info(f"No new suggestions generated for {editor_name}")
            
            # Turn off the suggestion request (change YES to NO)
            self._turn_off_suggestion_request(sheet_id)
            
        except Exception as e:
            self.logger.error(f"Error processing suggestion request for {editor_name}: {e}")
            self.handle_error(e, f"Suggestion request for {editor_name}")

    def _get_existing_notes(self, sheet_id: str) -> List[Dict[str, Any]]:
        """Get existing notes from AI notes tab.
        
        Args:
            sheet_id: Google Sheets ID
            
        Returns:
            List of existing note dictionaries
        """
        try:
            # Read from AI notes tab, columns B, C, D, E, I
            range_name = "'AI notes'!B:I"
            
            result = self.sheet_manager.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            if not values:
                return []
            
            # Get headers
            headers = values[0] if values else []
            notes = []
            
            # Debug: show what headers we found
            self.logger.debug(f"Sheet headers found: {headers}")
            
            # Process each row
            for i, row in enumerate(values[1:], start=2):
                try:
                    # Create note dictionary
                    note = {}
                    for j, header in enumerate(headers):
                        if j < len(row):
                            note[header] = row[j]
                        else:
                            note[header] = ''
                    
                    # Debug: show first few rows of data
                    if i <= 3:
                        self.logger.debug(f"Row {i} data: {note}")
                    
                    # Only include rows with AI TN content
                    if note.get('AI TN', '').strip():
                        notes.append(note)
                
                except Exception as e:
                    self.logger.warning(f"Error processing note row {i}: {e}")
            
            return notes
            
        except Exception as e:
            self.logger.error(f"Error getting existing notes: {e}")
            return []

    def _get_chapter_text(self, book: str, chapter: int, text_type: str) -> Optional[str]:
        """Get chapter text for ULT or UST.
        
        Args:
            book: Book abbreviation
            chapter: Chapter number
            text_type: 'ult' or 'ust'
            
        Returns:
            Chapter text or None if not found
        """
        try:
            # Get biblical text from cache
            biblical_text = self.cache_manager.get_cached_data(f'{text_type}_chapters')
            
            if not biblical_text:
                self.logger.debug(f"{text_type.upper()} chapters not cached, fetching...")
                biblical_text = self.sheet_manager.fetch_biblical_text(text_type)
                if biblical_text:
                    self.cache_manager.set_cached_data(f'{text_type}_chapters', biblical_text)
                else:
                    self.logger.warning(f"Failed to fetch {text_type.upper()} biblical text")
                    return None
            
            # Check if this biblical text is for the requested book
            if biblical_text.get('book') != book:
                self.logger.warning(f"Biblical text cache is for book '{biblical_text.get('book')}', not '{book}'")
                return None
            
            # Find the chapter
            chapters = biblical_text.get('chapters', [])
            for chapter_data in chapters:
                if chapter_data.get('chapter') == chapter:
                    verses = chapter_data.get('verses', [])
                    # Format as chapter text
                    chapter_text = f"{book}\n"
                    for verse in verses:
                        verse_num = verse.get('number', 0)
                        content = verse.get('content', '')
                        chapter_text += f"{chapter}:{verse_num} {content}\n"
                    return chapter_text.strip()
            
            self.logger.warning(f"Chapter {chapter} not found in {text_type.upper()} for book {book}")
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting {text_type.upper()} chapter text: {e}")
            return None

    def _get_existing_suggestions(self, sheet_id: str) -> List[Dict[str, Any]]:
        """Get existing suggestions to avoid duplicates.
        
        Args:
            sheet_id: Google Sheets ID
            
        Returns:
            List of existing suggestion dictionaries
        """
        try:
            # Read from suggested notes tab
            range_name = "'suggested notes'!A:F"
            
            result = self.sheet_manager.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            if not values:
                return []
            
            # Skip header rows (first 2 rows)
            suggestions = []
            for i, row in enumerate(values[2:], start=3):
                if len(row) >= 6:  # Ensure we have all columns
                    suggestion = {
                        'reference': row[0] if len(row) > 0 else '',
                        'issuetype': row[1] if len(row) > 1 else '',
                        'quote': row[2] if len(row) > 2 else '',
                        'Go?': row[3] if len(row) > 3 else '',
                        'AT': row[4] if len(row) > 4 else '',
                        'explanation': row[5] if len(row) > 5 else ''
                    }
                    suggestions.append(suggestion)
            
            return suggestions
            
        except Exception as e:
            self.logger.error(f"Error getting existing suggestions: {e}")
            return []

    def _get_translation_issue_descriptions(self) -> List[Dict[str, Any]]:
        """Get translation issue descriptions from cache file.
        
        Returns:
            List of translation issue descriptions
        """
        try:
            import json
            import os
            
            cache_dir = os.path.join(os.path.dirname(__file__), 'cache')
            cache_file = os.path.join(cache_dir, 'translation_issue_descriptions.json')
            
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                self.logger.warning("Translation issue descriptions file not found")
                return []
                
        except Exception as e:
            self.logger.error(f"Error loading translation issue descriptions: {e}")
            return []

    def _generate_ai_suggestions(self, ult_text: str, ust_text: str, existing_notes: List[Dict[str, Any]], 
                               existing_suggestions: List[Dict[str, Any]], translation_issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate AI suggestions for missing translation notes.
        
        Args:
            ult_text: ULT chapter text
            ust_text: UST chapter text
            existing_notes: List of existing notes
            existing_suggestions: List of existing suggestions
            translation_issues: List of translation issue descriptions
            
        Returns:
            List of suggestion dictionaries
        """
        try:
            # Format existing notes for prompt
            notes_text = ""
            for note in existing_notes:
                ref = note.get('Ref', '')
                sref = note.get('SRef', '')
                quote = note.get('GLQuote', '')
                tn = note.get('AI TN', '')
                
                # Debug logging to see what we're getting
                self.logger.debug(f"Note data: Ref='{ref}', SRef='{sref}', GLQuote='{quote}', AI TN='{tn[:50]}...'")
                
                if ref and sref and tn:
                    # Include the note even if quote is empty, but show it
                    notes_text += f"{ref}\t{sref}\t{quote}\t{tn}\n"
            
            self.logger.info(f"Formatted {len(existing_notes)} notes for prompt. First few lines of notes_text:")
            for i, line in enumerate(notes_text.split('\n')[:3]):
                if line.strip():
                    self.logger.info(f"  Note {i+1}: {line}")
            
            # Format existing suggestions for prompt
            suggestions_text = ""
            for suggestion in existing_suggestions:
                ref = suggestion.get('reference', '')
                issuetype = suggestion.get('issuetype', '')
                quote = suggestion.get('quote', '')
                go = suggestion.get('Go?', '')
                at = suggestion.get('AT', '')
                explanation = suggestion.get('explanation', '')
                if ref and issuetype:
                    suggestions_text += f"{ref}\t{issuetype}\t{quote}\t{go}\t{at}\t{explanation}\n"
            
            # Build the prompt
            # Load the review prompt from configuration
            try:
                review_prompt_template = self.config.get_prompt('review_prompt')
                if not review_prompt_template:
                    self.logger.error("Review prompt not found in configuration")
                    return []
                
                # Format the prompt with variables
                prompt = review_prompt_template.format(
                    translation_issues=json.dumps(translation_issues, indent=2),
                    ult_text=ult_text,
                    ust_text=ust_text,
                    notes_text=notes_text,
                    suggestions_text=suggestions_text
                )
            except Exception as e:
                self.logger.error(f"Error loading/formatting review prompt: {e}")
                return []
            
            # Create batch requests
            requests = [
                {
                    "custom_id": "suggestion_request",
                    "params": {
                        "model": self.ai_service.model,
                        "max_tokens": 4096,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ]
                    }
                }
            ]
            
            # Add dummy prompt to make it a proper batch (saves money)
            requests.append({
                "custom_id": "dummy_request",
                "params": {
                    "model": self.ai_service.model,
                    "max_tokens": 50,
                    "messages": [
                        {"role": "user", "content": "What is the capital of Texas?"}
                    ]
                }
            })
            
            # Submit batch
            batch_id = self.ai_service.submit_batch(requests)
            self.logger.info(f"Submitted suggestion batch: {batch_id}")
            self.logger.info(f"Suggestion prompt (first 500 chars): {prompt[:500]}...")
            
            # Debug logging to show full prompt sections
            self.logger.info("=== FULL SUGGESTION PROMPT DEBUG ===")
            self.logger.info(f"Existing notes section:\n{notes_text}")
            self.logger.info(f"Existing suggestions section:\n{suggestions_text}")
            self.logger.info(f"ULT text (first 300 chars): {ult_text[:300]}...")
            self.logger.info(f"UST text (first 300 chars): {ust_text[:300]}...")
            self.logger.info(f"Translation issues count: {len(translation_issues)}")
            self.logger.info("=== FULL PROMPT ===")
            self.logger.info(prompt)
            self.logger.info("=== END FULL PROMPT ===")
            
            # Wait for batch to complete (polling)
            max_wait_time = 30 * 60  # 30 minutes
            poll_interval = 30  # 30 seconds
            elapsed = 0
            
            while elapsed < max_wait_time:
                time.sleep(poll_interval)
                elapsed += poll_interval
                
                try:
                    batch_status = self.ai_service.get_batch_status(batch_id)
                    
                    if batch_status.processing_status == 'ended':
                        # Get and process results
                        raw_results = self.ai_service.get_batch_results(batch_status)
                        self.logger.info(f"Got {len(raw_results)} batch results")
                        
                        # Find the suggestion result (ignore dummy)
                        for i, result in enumerate(raw_results):
                            self.logger.debug(f"Result {i}: type={type(result)}, custom_id={getattr(result, 'custom_id', 'unknown')}")
                            
                            if hasattr(result, 'custom_id') and result.custom_id == 'suggestion_request':
                                self.logger.info("Found suggestion request result")
                                
                                if hasattr(result, 'result') and result.result:
                                    # Log the response structure
                                    self.logger.info(f"Result structure: {type(result.result)}")
                                    
                                    try:
                                        if hasattr(result.result, 'message') and hasattr(result.result.message, 'content'):
                                            content = result.result.message.content
                                            if isinstance(content, list) and len(content) > 0:
                                                # Handle content array
                                                text_content = content[0].text if hasattr(content[0], 'text') else str(content[0])
                                            else:
                                                text_content = str(content)
                                            
                                            self.logger.info(f"AI Response content: {text_content[:500]}...")
                                            
                                            # Parse JSON response - handle cases where AI returns multiple JSON objects with text
                                            suggestions = []
                                            
                                            # Try to extract JSON objects from the response
                                            import re
                                            # Find all JSON-like objects in the response
                                            json_pattern = r'\{[^}]*"reference"[^}]*\}'
                                            json_matches = re.findall(json_pattern, text_content, re.DOTALL)
                                            
                                            self.logger.info(f"Found {len(json_matches)} potential JSON objects")
                                            
                                            for match in json_matches:
                                                try:
                                                    # Clean up the match and parse it
                                                    cleaned_match = match.strip()
                                                    suggestion = json.loads(cleaned_match)
                                                    suggestions.append(suggestion)
                                                    self.logger.debug(f"Parsed suggestion: {suggestion}")
                                                except json.JSONDecodeError as e:
                                                    self.logger.warning(f"Failed to parse JSON object: {match[:100]}... Error: {e}")
                                                    continue
                                            
                                            # If no JSON objects found, try parsing the whole thing as JSON
                                            if not suggestions:
                                                try:
                                                    # Remove descriptive text and try to parse
                                                    # Look for content between [ and ] or just parse as single object
                                                    if text_content.strip().startswith('['):
                                                        suggestions = json.loads(text_content)
                                                    elif text_content.strip().startswith('{'):
                                                        suggestions = [json.loads(text_content)]
                                                    else:
                                                        self.logger.warning("Could not identify JSON format in response")
                                                        return []
                                                except json.JSONDecodeError:
                                                    self.logger.warning("Response does not contain valid JSON")
                                                    return []
                                            
                                            self.logger.info(f"Generated {len(suggestions)} valid suggestions")
                                            return suggestions
                                        else:
                                            self.logger.error(f"Unexpected result structure: {result.result}")
                                            return []
                                            
                                    except Exception as e:
                                        self.logger.error(f"Error processing batch result: {e}")
                                        return []
                                else:
                                    self.logger.error("Result has no result attribute or result is None")
                                    return []
                        
                        # If we get here, didn't find the suggestion result
                        self.logger.warning("Suggestion result not found in batch results")
                        return []
                    
                    elif batch_status.processing_status in ['canceled', 'expired', 'failed']:
                        self.logger.error(f"Suggestion batch failed: {batch_status.processing_status}")
                        return []
                    
                    else:
                        self.logger.debug(f"Suggestion batch still processing: {batch_status.processing_status}")
                
                except Exception as e:
                    self.logger.error(f"Error checking suggestion batch status: {e}")
                    return []
            
            self.logger.error("Suggestion batch timed out")
            return []
            
        except Exception as e:
            self.logger.error(f"Error generating AI suggestions: {e}")
            return []

    def _write_suggestions_to_sheet(self, sheet_id: str, suggestions: List[Dict[str, Any]]):
        """Write suggestions to the suggested notes tab.
        
        Args:
            sheet_id: Google Sheets ID
            suggestions: List of suggestion dictionaries
        """
        try:
            if not suggestions:
                return
            
            # Get existing data to find next available row
            range_name = "'suggested notes'!A:F"
            
            result = self.sheet_manager.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            
            existing_values = result.get('values', [])
            next_row = max(3, len(existing_values) + 1)  # Start at row 3 minimum
            
            # Prepare data to write
            values_to_write = []
            suggestions_with_at = 0
            for suggestion in suggestions:
                alternate_translation = suggestion.get('alternate translation', '')
                if alternate_translation:
                    suggestions_with_at += 1
                
                # Apply post-processing to text fields
                row_data = [
                    _post_process_text(suggestion.get('reference', '')),
                    _post_process_text(suggestion.get('issuetype', '')),
                    _post_process_text(suggestion.get('quote', '')),
                    '',  # Go? column (column D) - leave empty
                    _post_process_text(alternate_translation),  # AT column (column E) - get from suggestion
                    _post_process_text(suggestion.get('explanation', ''))
                ]
                values_to_write.append(row_data)
            
            self.logger.info(f"Writing {len(suggestions)} suggestions, {suggestions_with_at} with alternate translations")
            
            # Write to sheet
            if values_to_write:
                range_to_write = f"'suggested notes'!A{next_row}:F{next_row + len(values_to_write) - 1}"
                
                body = {
                    'values': values_to_write
                }
                
                self.sheet_manager.service.spreadsheets().values().append(
                    spreadsheetId=sheet_id,
                    range=range_to_write,
                    valueInputOption='RAW',
                    body=body
                ).execute()
                
                self.logger.info(f"Successfully wrote {len(suggestions)} suggestions starting at row {next_row}")
                
                # Play sound notification for AI suggestions written to spreadsheet
                self.play_notification_sound(len(suggestions), "AI suggestions")
            
        except Exception as e:
            self.logger.error(f"Error writing suggestions to sheet: {e}")
            raise

    def _turn_off_suggestion_request(self, sheet_id: str):
        """Turn off the suggestion request by changing YES to NO.
        
        Args:
            sheet_id: Google Sheets ID
        """
        try:
            # Write 'NO' to suggested notes tab, column D, row 2
            range_name = "'suggested notes'!D2"
            
            body = {
                'values': [['NO']]
            }
            
            self.sheet_manager.service.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()
            
            self.logger.info("Successfully turned off suggestion request")
            
        except Exception as e:
            self.logger.error(f"Error turning off suggestion request: {e}")
            raise


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Translation Notes AI')
    parser.add_argument('--mode', choices=['continuous', 'once'], default='continuous',
                       help='Run mode: continuous monitoring or one-time processing')
    parser.add_argument('--config', help='Path to config file')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode (no actual updates)')
    parser.add_argument('--legacy-processing', action='store_true', 
                       help='Use legacy synchronous processing instead of continuous batch processing')
    parser.add_argument('--sound-notifications', action='store_true',
                       help='Play sound notifications when AI writes results to spreadsheet')
    
    # Cache management options
    parser.add_argument('--force-refresh-templates', action='store_true', 
                       help='Force refresh template cache and exit')
    parser.add_argument('--force-refresh-support-refs', action='store_true',
                       help='Force refresh support references cache and exit')
    parser.add_argument('--cache-status', action='store_true',
                       help='Show cache status and exit')
    parser.add_argument('--clear-cache', choices=['all', 'templates', 'ult_chapters', 'ust_chapters', 'support_references', 'system_prompts'],
                       help='Clear specified cache and exit')
    
    # SRef conversion option
    parser.add_argument('--convert-sref', action='store_true',
                       help='Convert short SRef values to full support reference names and exit')
    
    # Status monitoring
    parser.add_argument('--status', action='store_true',
                       help='Show current batch processing status and exit')
    
    args = parser.parse_args()
    
    # Override config if specified
    config_overrides = {}
    if args.debug:
        config_overrides['logging.level'] = 'DEBUG'
        config_overrides['debug.enabled'] = True
    if args.dry_run:
        config_overrides['debug.dry_run'] = True
    
    try:
        # Initialize application
        app = TranslationNotesAI()
        
        # Set processing mode based on command line flag
        if args.legacy_processing:
            app.use_continuous_processing = False
            app.logger.info("Using legacy synchronous processing (--legacy-processing flag)")
        
        # Enable sound notifications if requested
        if args.sound_notifications:
            app.enable_sound_notifications()
        
        # Apply any config overrides
        for key, value in config_overrides.items():
            app.config.set(key, value)
        
        # Handle cache management commands
        if args.force_refresh_templates:
            app.logger.info("Force refreshing template cache...")
            success = app.force_refresh_templates()
            sys.exit(0 if success else 1)
        
        if args.force_refresh_support_refs:
            app.logger.info("Force refreshing support references cache...")
            success = app.force_refresh_support_refs()
            sys.exit(0 if success else 1)
        
        if args.cache_status:
            app.logger.info("Getting cache status...")
            app.get_cache_status()
            sys.exit(0)
        
        if args.clear_cache:
            app.logger.info(f"Clearing cache: {args.clear_cache}")
            if args.clear_cache == 'all':
                app.cache_manager.clear_cache()
            else:
                app.cache_manager.clear_cache(args.clear_cache)
            app.logger.info("Cache cleared successfully")
            sys.exit(0)
        
        if args.convert_sref:
            app.logger.info("Converting SRef values...")
            success = app.convert_sref_values()
            sys.exit(0 if success else 1)
        
        if args.status:
            app.logger.info("Getting batch processing status...")
            status = app.continuous_batch_manager.get_status()
            
            print(f"\n=== Batch Processing Status ===")
            print(f"System Running: {status['running']}")
            print(f"Running Batches: {status['running_batches']}/{status['max_concurrent']}")
            print(f"Available Slots: {status['available_slots']}")
            print(f"Work Queue Size: {status['work_queue_size']}")
            
            if status['blocked_sheets']:
                print(f"\n=== Blocked Sheets (Permission Errors) ===")
                for sheet_id, info in status['blocked_sheets'].items():
                    user_name = app.config.get_editor_name_for_sheet(sheet_id)
                    remaining = info['remaining_minutes']
                    if remaining > 60:
                        time_str = f"{remaining/60:.1f} hours"
                    else:
                        time_str = f"{remaining:.1f} minutes"
                    print(f"  {user_name}: blocked for {time_str} more")
            
            if status['batches']:
                print(f"\n=== Active Batches ===")
                for batch_id, info in status['batches'].items():
                    submitted_time = datetime.fromisoformat(info['submitted_at'])
                    elapsed = (datetime.now() - submitted_time).total_seconds() / 60
                    print(f"  {batch_id[:8]}: {info['user']} ({info['items_count']} items, {elapsed:.1f}m running)")
            else:
                print("No active batches")
            
            print()
            sys.exit(0)
        
        # Setup signal handlers for graceful shutdown
        app.setup_signal_handlers()
        
        # Run based on mode
        if args.mode == 'continuous':
            app.run_continuous()
        elif args.mode == 'once':
            app.run_once(dry_run=args.dry_run)
            
    except Exception as e:
        logging.error(f"Application failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main() 