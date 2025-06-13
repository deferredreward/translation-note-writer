"""
Command-line interface for Translation Notes AI
Handles argument parsing and command execution.
"""

import argparse
import sys
import os
from datetime import datetime
from typing import Dict, Any, Optional
import logging


class TranslationNotesAICLI:
    """Command-line interface for Translation Notes AI."""
    
    def __init__(self, app_class):
        """Initialize the CLI.
        
        Args:
            app_class: The main application class to instantiate
        """
        self.app_class = app_class
        self.parser = self._create_parser()
    
    def _create_parser(self) -> argparse.ArgumentParser:
        """Create the argument parser with all options."""
        parser = argparse.ArgumentParser(
            description='Translation Notes AI - Automated translation notes generation',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  %(prog)s --mode continuous                    # Run continuous monitoring
  %(prog)s --mode once --dry-run               # Test run without changes
  %(prog)s --mode once --noai                 # Run without making AI calls
  %(prog)s --cache-status                      # Show cache information
  %(prog)s --convert-sref                      # Convert SRef values
  %(prog)s --status                            # Show system status
  %(prog)s --clear-cache all                   # Clear all caches
            """
        )
        
        # Main operation modes
        mode_group = parser.add_argument_group('Operation Modes')
        mode_group.add_argument(
            '--mode', 
            choices=['continuous', 'once'], 
            default='continuous',
            help='Run mode: continuous monitoring or one-time processing (default: continuous)'
        )
        
        # Configuration options
        config_group = parser.add_argument_group('Configuration')
        config_group.add_argument(
            '--config', 
            help='Path to config file (default: config/config.yaml)'
        )
        config_group.add_argument(
            '--debug', 
            action='store_true', 
            help='Enable debug logging'
        )
        config_group.add_argument(
            '--dry-run',
            action='store_true',
            help='Dry run mode - no actual updates to sheets'
        )
        config_group.add_argument(
            '--noai',
            action='store_true',
            help='Disable all AI API calls for testing'
        )
        
        # Processing options
        processing_group = parser.add_argument_group('Processing Options')
        processing_group.add_argument(
            '--legacy-processing', 
            action='store_true',
            help='Use legacy synchronous processing instead of continuous batch processing'
        )
        processing_group.add_argument(
            '--sound-notifications', 
            action='store_true',
            help='Play sound notifications when AI writes results to spreadsheet'
        )
        
        # Cache management
        cache_group = parser.add_argument_group('Cache Management')
        cache_group.add_argument(
            '--force-refresh-templates', 
            action='store_true',
            help='Force refresh template cache and exit'
        )
        cache_group.add_argument(
            '--force-refresh-support-refs', 
            action='store_true',
            help='Force refresh support references cache and exit'
        )
        cache_group.add_argument(
            '--cache-status', 
            action='store_true',
            help='Show cache status and exit'
        )
        cache_group.add_argument(
            '--clear-cache', 
            choices=['all', 'templates', 'ult_chapters', 'ust_chapters', 'support_references', 'system_prompts'],
            help='Clear specified cache and exit'
        )
        
        # Utility commands
        utility_group = parser.add_argument_group('Utility Commands')
        utility_group.add_argument(
            '--convert-sref', 
            action='store_true',
            help='Convert short SRef values to full support reference names and exit'
        )
        utility_group.add_argument(
            '--status', 
            action='store_true',
            help='Show current batch processing status and exit'
        )
        
        return parser
    
    def parse_args(self, args: Optional[list] = None) -> argparse.Namespace:
        """Parse command-line arguments.
        
        Args:
            args: Arguments to parse (default: sys.argv)
            
        Returns:
            Parsed arguments namespace
        """
        return self.parser.parse_args(args)
    
    def run(self, args: Optional[list] = None) -> int:
        """Run the CLI with given arguments.
        
        Args:
            args: Arguments to parse (default: sys.argv)
            
        Returns:
            Exit code (0 for success, non-zero for error)
        """
        try:
            parsed_args = self.parse_args(args)
            return self._execute_command(parsed_args)
            
        except KeyboardInterrupt:
            print("\nInterrupted by user")
            return 130
        except Exception as e:
            print(f"Error: {e}")
            logging.error(f"CLI error: {e}")
            return 1
    
    def _execute_command(self, args: argparse.Namespace) -> int:
        """Execute the command based on parsed arguments.
        
        Args:
            args: Parsed command-line arguments
            
        Returns:
            Exit code
        """
        # Build configuration overrides
        config_overrides = self._build_config_overrides(args)

        if args.noai:
            os.environ['ANTHROPIC_DISABLED'] = '1'
        
        # Initialize application
        try:
            app = self.app_class()
            
            # Apply configuration overrides
            for key, value in config_overrides.items():
                app.config.set(key, value)
            
            # Configure processing mode
            if args.legacy_processing:
                app.use_continuous_processing = False
                app.logger.info("Using legacy synchronous processing (--legacy-processing flag)")
            
            # Configure notifications
            if args.sound_notifications:
                app.enable_sound_notifications()
            
        except Exception as e:
            print(f"Failed to initialize application: {e}")
            return 1
        
        # Handle utility commands that exit immediately
        if self._handle_utility_commands(app, args):
            return 0
        
        # Handle main operation modes
        return self._handle_main_operations(app, args)
    
    def _build_config_overrides(self, args: argparse.Namespace) -> Dict[str, Any]:
        """Build configuration overrides from command-line arguments.
        
        Args:
            args: Parsed arguments
            
        Returns:
            Dictionary of configuration overrides
        """
        overrides = {}
        
        if args.debug:
            overrides['logging.level'] = 'DEBUG'
            overrides['debug.enabled'] = True
        
        if args.dry_run:
            overrides['debug.dry_run'] = True

        if args.noai:
            overrides['anthropic.disabled'] = True

        return overrides
    
    def _handle_utility_commands(self, app, args: argparse.Namespace) -> bool:
        """Handle utility commands that exit immediately.
        
        Args:
            app: Application instance
            args: Parsed arguments
            
        Returns:
            True if a utility command was handled (caller should exit)
        """
        try:
            # Cache management commands
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
            
            # SRef conversion
            if args.convert_sref:
                app.logger.info("Converting SRef values...")
                success = app.convert_sref_values()
                sys.exit(0 if success else 1)
            
            # Status display
            if args.status:
                self._display_status(app)
                sys.exit(0)
            
            return False  # No utility command handled
            
        except SystemExit:
            raise  # Re-raise sys.exit calls
        except Exception as e:
            app.logger.error(f"Utility command failed: {e}")
            sys.exit(1)
    
    def _display_status(self, app):
        """Display current system status.
        
        Args:
            app: Application instance
        """
        app.logger.info("Getting batch processing status...")
        status = app.continuous_batch_manager.get_status()
        
        print(f"\n=== Translation Notes AI Status ===")
        print(f"System Running: {status['running']}")
        print(f"Running Batches: {status['running_batches']}/{status['max_concurrent']}")
        print(f"Available Slots: {status['available_slots']}")
        print(f"Work Queue Size: {status['work_queue_size']}")
        
        # Display blocked sheets
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
        
        # Display active batches
        if status['batches']:
            print(f"\n=== Active Batches ===")
            for batch_id, info in status['batches'].items():
                submitted_time = datetime.fromisoformat(info['submitted_at'])
                elapsed = (datetime.now() - submitted_time).total_seconds() / 60
                print(f"  {batch_id[:8]}: {info['user']} ({info['items_count']} items, {elapsed:.1f}m running)")
        else:
            print("No active batches")
        
        print()
    
    def _handle_main_operations(self, app, args: argparse.Namespace) -> int:
        """Handle main operation modes.
        
        Args:
            app: Application instance
            args: Parsed arguments
            
        Returns:
            Exit code
        """
        try:
            # Setup signal handlers for graceful shutdown
            app.setup_signal_handlers()
            
            # Run based on mode
            if args.mode == 'continuous':
                app.logger.info("Starting continuous monitoring mode...")
                app.run_continuous()
                return 0
                
            elif args.mode == 'once':
                app.logger.info("Running one-time processing...")
                app.run_once(dry_run=args.dry_run)
                return 0
            
            else:
                print(f"Unknown mode: {args.mode}")
                return 1
                
        except KeyboardInterrupt:
            app.logger.info("Interrupted by user")
            return 130
        except Exception as e:
            app.logger.error(f"Operation failed: {e}")
            return 1


def create_cli(app_class) -> TranslationNotesAICLI:
    """Create a CLI instance for the given application class.
    
    Args:
        app_class: Main application class
        
    Returns:
        CLI instance
    """
    return TranslationNotesAICLI(app_class)


def main_cli_entry_point(app_class, args: Optional[list] = None) -> int:
    """Main entry point for CLI applications.
    
    Args:
        app_class: Main application class
        args: Command-line arguments (default: sys.argv)
        
    Returns:
        Exit code
    """
    cli = create_cli(app_class)
    return cli.run(args) 