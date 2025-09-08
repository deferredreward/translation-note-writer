"""
Notification system for Translation Notes AI
Handles audio and visual notifications across different platforms.
"""

import logging
import platform
import time
from typing import Optional, Callable


class NotificationSystem:
    """Handles various types of notifications including audio alerts."""
    
    def __init__(self, logger: Optional[logging.Logger] = None, enabled: bool = False):
        """Initialize the notification system.
        
        Args:
            logger: Logger instance for notification events
            enabled: Whether notifications are enabled
        """
        self.logger = logger or logging.getLogger(__name__)
        self.enabled = enabled
        self.system = platform.system().lower()
        
        # Cache available notification methods
        self._audio_methods = self._detect_audio_methods()
        
        if self.enabled:
            self.logger.info(f"Notification system initialized for {self.system}")
            if not self._audio_methods:
                self.logger.warning("No audio notification methods available")
    
    def enable(self):
        """Enable notifications."""
        self.enabled = True
        self.logger.info("Notifications enabled")
    
    def disable(self):
        """Disable notifications."""
        self.enabled = False
        self.logger.info("Notifications disabled")
    
    def notify_completion(self, count: int = 1, context: str = "", item_type: str = "item"):
        """Notify completion of AI processing.
        
        Args:
            count: Number of items processed
            context: Context description for logging
            item_type: Type of items processed (e.g., "note", "suggestion")
        """
        if not self.enabled:
            return
        
        try:
            self._play_completion_sound(count)
            context_msg = f" ({context})" if context else ""
            self.logger.info(f"🔊 Played notification sound for {count} AI {item_type}(s) written to spreadsheet{context_msg}")
            
        except Exception as e:
            self.logger.debug(f"Error playing notification sound: {e}")
            # Don't let sound errors interrupt the main workflow
    
    def notify_error(self, error_message: str):
        """Notify about an error condition.
        
        Args:
            error_message: Error message to log
        """
        if not self.enabled:
            return
        
        try:
            self._play_error_sound()
            self.logger.warning(f"🚨 Error notification: {error_message}")
            
        except Exception as e:
            self.logger.debug(f"Error playing error notification: {e}")
    
    def notify_status(self, message: str):
        """Notify about a status change.
        
        Args:
            message: Status message
        """
        if not self.enabled:
            return
        
        self.logger.info(f"📢 Status: {message}")
    
    def _detect_audio_methods(self) -> list[str]:
        """Detect available audio notification methods.
        
        Returns:
            List of available audio methods
        """
        methods = []
        
        if self.system == "windows":
            try:
                import winsound
                methods.append("winsound")
            except ImportError:
                pass
        
        elif self.system == "darwin":  # macOS
            import subprocess
            try:
                # Check if afplay is available
                result = subprocess.run(["which", "afplay"], capture_output=True, timeout=1)
                if result.returncode == 0:
                    methods.append("afplay")
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
        
        elif self.system == "linux":
            import subprocess
            # Check for common Linux audio tools
            for tool in ["paplay", "aplay", "espeak"]:
                try:
                    result = subprocess.run(["which", tool], capture_output=True, timeout=1)
                    if result.returncode == 0:
                        methods.append(tool)
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass
        
        # Check for pygame (cross-platform)
        try:
            import pygame
            methods.append("pygame")
        except ImportError:
            pass
        
        return methods
    
    def _play_completion_sound(self, count: int):
        """Play completion notification sound.
        
        Args:
            count: Number of items completed (affects sound pattern)
        """
        if self.system == "windows" and "winsound" in self._audio_methods:
            self._play_windows_sound(count)
        elif self.system == "darwin" and "afplay" in self._audio_methods:
            self._play_macos_sound(count)
        elif self.system == "linux" and any(method in self._audio_methods for method in ["paplay", "aplay", "espeak"]):
            self._play_linux_sound(count)
        elif "pygame" in self._audio_methods:
            self._play_pygame_sound(count, frequency=800, duration=0.3)
        else:
            self._play_fallback_notification()
    
    def _play_error_sound(self):
        """Play error notification sound."""
        if self.system == "windows" and "winsound" in self._audio_methods:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONHAND)  # Error sound
        elif "pygame" in self._audio_methods:
            # Lower frequency for error
            self._play_pygame_sound(1, frequency=400, duration=0.5)
        else:
            self._play_fallback_notification()
    
    def _play_windows_sound(self, count: int):
        """Play notification sound on Windows.
        
        Args:
            count: Number of items (affects repetition)
        """
        import winsound
        
        # Use a pleasant notification sound
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
        
        if count > 1:
            # For multiple items, play an additional beep
            time.sleep(0.2)
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
    
    def _play_macos_sound(self, count: int):
        """Play notification sound on macOS.
        
        Args:
            count: Number of items (affects repetition)
        """
        import subprocess
        
        try:
            # Use macOS system sound
            subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], 
                         check=False, capture_output=True, timeout=3)
            
            if count > 1:
                time.sleep(0.3)
                subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], 
                             check=False, capture_output=True, timeout=3)
                
        except subprocess.TimeoutExpired:
            self._play_fallback_notification()
    
    def _play_linux_sound(self, count: int):
        """Play notification sound on Linux.
        
        Args:
            count: Number of items (affects repetition)
        """
        import subprocess
        
        # Try different Linux sound methods in order of preference
        sound_commands = []
        
        if "paplay" in self._audio_methods:
            sound_commands.append(["paplay", "/usr/share/sounds/alsa/Front_Right.wav"])
        if "aplay" in self._audio_methods:
            sound_commands.append(["aplay", "/usr/share/sounds/alsa/Front_Right.wav"])
        if "espeak" in self._audio_methods:
            sound_commands.append(["espeak", "AI results ready"])
        
        for cmd in sound_commands:
            try:
                subprocess.run(cmd, check=False, capture_output=True, timeout=3)
                break  # Success, don't try other methods
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
        else:
            # No command worked
            self._play_fallback_notification()
    
    def _play_pygame_sound(self, count: int, frequency: int = 800, duration: float = 0.3):
        """Play notification sound using pygame.
        
        Args:
            count: Number of items (affects repetition)
            frequency: Sound frequency in Hz
            duration: Sound duration in seconds
        """
        try:
            import pygame
            import numpy as np
            
            pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
            
            # Generate a simple beep sound
            sample_rate = 22050
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
            
            if count > 1:
                time.sleep(0.2)
                sound.play()
                time.sleep(duration)
            
            pygame.mixer.quit()
            
        except ImportError:
            self._play_fallback_notification()
        except Exception as e:
            self.logger.debug(f"Pygame sound failed: {e}")
            self._play_fallback_notification()
    
    def _play_fallback_notification(self):
        """Fallback method to create an audible notification."""
        try:
            # Terminal bell character (may work on some systems)
            print("\a", end="", flush=True)
            
            # Visual notification in logs
            self.logger.info("🔊 *** NOTIFICATION *** 🔊")
            
        except Exception as e:
            self.logger.debug(f"Fallback notification failed: {e}")


class CallbackNotificationSystem(NotificationSystem):
    """Notification system that supports custom callbacks."""
    
    def __init__(self, logger: Optional[logging.Logger] = None, enabled: bool = False):
        """Initialize the callback notification system."""
        super().__init__(logger, enabled)
        self.completion_callbacks: list[Callable] = []
        self.error_callbacks: list[Callable] = []
    
    def add_completion_callback(self, callback: Callable):
        """Add a callback for completion notifications.
        
        Args:
            callback: Function to call on completion (signature: callback(count, context))
        """
        self.completion_callbacks.append(callback)
    
    def add_error_callback(self, callback: Callable):
        """Add a callback for error notifications.
        
        Args:
            callback: Function to call on error (signature: callback(error_message))
        """
        self.error_callbacks.append(callback)
    
    def notify_completion(self, count: int = 1, context: str = "", item_type: str = "item"):
        """Notify completion and call registered callbacks."""
        super().notify_completion(count, context, item_type)
        
        for callback in self.completion_callbacks:
            try:
                callback(count, context)
            except Exception as e:
                self.logger.warning(f"Completion callback failed: {e}")
    
    def notify_error(self, error_message: str):
        """Notify error and call registered callbacks."""
        super().notify_error(error_message)
        
        for callback in self.error_callbacks:
            try:
                callback(error_message)
            except Exception as e:
                self.logger.warning(f"Error callback failed: {e}")


# Create a default global notification instance
_default_notification_system = NotificationSystem()


def get_notification_system() -> NotificationSystem:
    """Get the default notification system instance."""
    return _default_notification_system


def enable_notifications():
    """Enable the default notification system."""
    _default_notification_system.enable()


def disable_notifications():
    """Disable the default notification system."""
    _default_notification_system.disable()


def notify_completion(count: int = 1, context: str = "", item_type: str = "item"):
    """Convenience function for completion notifications."""
    _default_notification_system.notify_completion(count, context, item_type)


def notify_error(error_message: str):
    """Convenience function for error notifications."""
    _default_notification_system.notify_error(error_message) 