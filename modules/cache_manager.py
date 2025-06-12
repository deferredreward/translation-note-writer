"""
Cache Manager
Handles intelligent caching of biblical text, templates, and other data with content-based comparison.
"""

import json
import logging
import os
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from .config_manager import ConfigManager


class CacheManager:
    """Manages caching of biblical text, templates, and other frequently used data with smart content comparison."""
    
    def __init__(self, config: ConfigManager, sheet_manager):
        """Initialize the cache manager.
        
        Args:
            config: Configuration manager
            sheet_manager: Sheet manager for fetching fresh data
        """
        self.config = config
        self.sheet_manager = sheet_manager
        self.logger = logging.getLogger(__name__)
        
        # Get cache configuration
        self.cache_config = config.get_cache_config()
        self.cache_dir = Path(self.cache_config['cache_dir'])
        
        # Set default cache TTL
        self.cache_ttl = timedelta(hours=24)  # Default 24 hour cache
        
        # Ensure cache directory exists
        self.cache_dir.mkdir(exist_ok=True)
        
        # Initialize metadata and content hash tracking
        self.cache_metadata = self._load_cache_metadata()
        self.content_hashes = self._load_content_hashes()
        self._tw_headwords: Optional[List[str]] = None
        
        self.logger.info(f"Cache manager initialized with directory: {self.cache_dir}")
    
    def _load_cache_metadata(self) -> Dict[str, Any]:
        """Load cache metadata from file.
        
        Returns:
            Cache metadata dictionary
        """
        try:
            metadata_file = self.cache_dir / "cache_metadata.json"
            if metadata_file.exists():
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.debug(f"Could not load cache metadata: {e}")
        
        return {}
    
    def _load_content_hashes(self) -> Dict[str, str]:
        """Load content hashes from file.
        
        Returns:
            Content hashes dictionary
        """
        try:
            hashes_file = self.cache_dir / "content_hashes.json"
            if hashes_file.exists():
                with open(hashes_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.debug(f"Could not load content hashes: {e}")
        
        return {}
    
    def _save_cache_metadata(self):
        """Save cache metadata to file."""
        try:
            metadata_file = self.cache_dir / "cache_metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache_metadata, f, indent=2, default=str, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Error saving cache metadata: {e}")
    
    def _save_content_hashes(self):
        """Save content hashes to file."""
        try:
            hashes_file = self.cache_dir / "content_hashes.json"
            with open(hashes_file, 'w', encoding='utf-8') as f:
                json.dump(self.content_hashes, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Error saving content hashes: {e}")
    
    def _calculate_content_hash(self, data: Any) -> str:
        """Calculate hash of content for change detection.
        
        Args:
            data: Data to hash
            
        Returns:
            SHA256 hash of the content
        """
        try:
            # Convert data to JSON string for consistent hashing
            content_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
            return hashlib.sha256(content_str.encode('utf-8')).hexdigest()
        except Exception as e:
            self.logger.error(f"Error calculating content hash: {e}")
            return ""
    
    def _is_cache_expired(self, cache_key: str, refresh_minutes: int) -> bool:
        """Check if a cache entry is expired based on time.
        
        Args:
            cache_key: Cache key to check
            refresh_minutes: Refresh interval in minutes
            
        Returns:
            True if cache is expired
        """
        if cache_key not in self.cache_metadata:
            return True
        
        last_updated = datetime.fromisoformat(self.cache_metadata[cache_key]['last_updated'])
        expiry_time = last_updated + timedelta(minutes=refresh_minutes)
        
        return datetime.now() > expiry_time
    
    def _has_content_changed(self, cache_key: str, new_data: Any) -> bool:
        """Check if content has changed by comparing hashes.
        
        Args:
            cache_key: Cache key to check
            new_data: New data to compare
            
        Returns:
            True if content has changed
        """
        if cache_key not in self.content_hashes:
            return True
        
        old_hash = self.content_hashes[cache_key]
        new_hash = self._calculate_content_hash(new_data)
        
        return old_hash != new_hash
    
    def _update_cache_metadata(self, cache_key: str, file_path: str, content_hash: str = None):
        """Update cache metadata for a cache entry.
        
        Args:
            cache_key: Cache key
            file_path: Path to cached file
            content_hash: Content hash (optional)
        """
        self.cache_metadata[cache_key] = {
            'last_updated': datetime.now().isoformat(),
            'file_path': file_path,
            'size': os.path.getsize(file_path) if os.path.exists(file_path) else 0
        }
        
        if content_hash:
            self.content_hashes[cache_key] = content_hash
        
        self._save_cache_metadata()
        self._save_content_hashes()
    
    def get_cached_data(self, cache_type: str, user: str = None, book: str = None) -> Optional[Any]:
        """Get cached data with optional user and book specificity.
        
        Args:
            cache_type: Type of cache ('templates', 'support_references', 'system_prompts', 'ult_chapters', 'ust_chapters')
            user: Username for user-specific caches (optional)
            book: Book code for book-specific caches (optional)
            
        Returns:
            Cached data or None if not found/expired
        """
        try:
            # Build cache filename based on type and specificity
            if cache_type in ['ult_chapters', 'ust_chapters'] and user and book:
                # User and book-specific biblical text cache
                cache_file = f"{cache_type}_{user}_{book}.json"
            elif cache_type in ['ult_chapters', 'ust_chapters']:
                # Fallback to global biblical text cache
                cache_file = f"{cache_type}.json"
            else:
                # Global caches (templates, support_references, system_prompts)
                cache_file = f"{cache_type}.json"
            
            cache_path = os.path.join(self.cache_dir, cache_file)
            
            if not os.path.exists(cache_path):
                self.logger.debug(f"Cache file not found: {cache_file}")
                return None
            
            # Check if cache is expired
            file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cache_path))
            if file_age > self.cache_ttl:
                self.logger.debug(f"Cache expired for {cache_file}")
                return None
            
            # Load and return cached data
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.logger.debug(f"Loaded from cache: {cache_file}")
            return data
            
        except Exception as e:
            self.logger.error(f"Error loading cache {cache_type}: {e}")
            return None

    def set_cached_data(self, cache_type: str, data: Any, user: str = None, book: str = None):
        """Set cached data with optional user and book specificity.
        
        Args:
            cache_type: Type of cache
            data: Data to cache
            user: Username for user-specific caches (optional)
            book: Book code for book-specific caches (optional)
        """
        try:
            # Build cache filename based on type and specificity
            if cache_type in ['ult_chapters', 'ust_chapters'] and user and book:
                # User and book-specific biblical text cache
                cache_file = f"{cache_type}_{user}_{book}.json"
            elif cache_type in ['ult_chapters', 'ust_chapters']:
                # Fallback to global biblical text cache
                cache_file = f"{cache_type}.json"
            else:
                # Global caches (templates, support_references, system_prompts)
                cache_file = f"{cache_type}.json"
            
            cache_path = os.path.join(self.cache_dir, cache_file)
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            self.logger.debug(f"Saved to cache: {cache_file}")
            
        except Exception as e:
            self.logger.error(f"Error saving cache {cache_type}: {e}")

    def detect_user_book_from_items(self, items: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
        """Detect the current book and infer user from work items.
        
        Args:
            items: List of work items
            
        Returns:
            Tuple of (user, book) or (None, None) if cannot be determined
        """
        if not items:
            return None, None
        
        # Get the book from the first item (all items in a batch should be same book)
        book = items[0].get('Book', '').strip()
        if not book:
            self.logger.warning("No book found in work items")
            return None, None
        
        # For now, we don't have user info in items, so we'll need to pass it separately
        # This method can be extended later if user info is added to items
        return None, book

    def get_biblical_text_for_user(self, text_type: str, user: str, book: str) -> Optional[Dict[str, Any]]:
        """Get biblical text for a specific user and book.
        
        Args:
            text_type: 'ULT' or 'UST'
            user: Username
            book: Book code
            
        Returns:
            Biblical text data or None
        """
        # Try user-specific cache first
        data = self.get_cached_data(f"{text_type.lower()}_chapters", user=user, book=book)
        if data:
            self.logger.debug(f"Found {text_type} cache for user {user}, book {book}")
            return data
        
        # Fallback to global cache
        data = self.get_cached_data(f"{text_type.lower()}_chapters")
        if data and data.get('book') == book:
            self.logger.debug(f"Found {text_type} in global cache for book {book}")
            return data
        
        self.logger.debug(f"No {text_type} cache found for user {user}, book {book}")
        return None

    def set_biblical_text_for_user(self, text_type: str, user: str, book: str, data: Dict[str, Any]):
        """Set biblical text for a specific user and book.
        
        Args:
            text_type: 'ULT' or 'UST'
            user: Username
            book: Book code
            data: Biblical text data
        """
        self.set_cached_data(f"{text_type.lower()}_chapters", data, user=user, book=book)
        self.logger.info(f"Cached {text_type} for user {user}, book {book}")

    def clear_user_cache(self, user: str, book: str = None):
        """Clear cache for a specific user and optionally book.
        
        Args:
            user: Username
            book: Book code (optional, if None clears all books for user)
        """
        try:
            cache_files = os.listdir(self.cache_dir)
            cleared_count = 0
            
            for cache_file in cache_files:
                # Check if this is a user-specific cache file
                if book:
                    # Clear specific user+book combination
                    if cache_file.startswith(f"ult_chapters_{user}_{book}.") or \
                       cache_file.startswith(f"ust_chapters_{user}_{book}."):
                        cache_path = os.path.join(self.cache_dir, cache_file)
                        os.remove(cache_path)
                        cleared_count += 1
                        self.logger.info(f"Cleared user cache: {cache_file}")
                else:
                    # Clear all caches for user
                    if f"_{user}_" in cache_file:
                        cache_path = os.path.join(self.cache_dir, cache_file)
                        os.remove(cache_path)
                        cleared_count += 1
                        self.logger.info(f"Cleared user cache: {cache_file}")
            
            if cleared_count == 0:
                self.logger.info(f"No cache files found for user {user}" + (f", book {book}" if book else ""))
            else:
                self.logger.info(f"Cleared {cleared_count} cache files for user {user}" + (f", book {book}" if book else ""))
                
        except Exception as e:
            self.logger.error(f"Error clearing user cache: {e}")

    def refresh_if_needed(self, force_refresh: List[str] = None) -> Tuple[List[str], List[str]]:
        """Refresh caches that need updating.
        
        Args:
            force_refresh: List of cache keys to force refresh regardless of time/content
            
        Returns:
            Tuple of (refreshed_keys, content_changed_keys)
        """
        refreshed = []
        content_changed = []
        force_refresh = force_refresh or []
        
        # Check each cache type
        cache_checks = [
            ('ult_chapters', self.cache_config['biblical_text_refresh']),
            ('ust_chapters', self.cache_config['biblical_text_refresh']),
            ('templates', self.cache_config['templates_refresh']),
            ('support_references', self.cache_config['support_refs_refresh']),
            ('system_prompts', self.cache_config['templates_refresh'])
        ]
        
        for cache_key, refresh_minutes in cache_checks:
            should_refresh = (
                cache_key in force_refresh or 
                self._is_cache_expired(cache_key, refresh_minutes)
            )
            
            if should_refresh:
                try:
                    refresh_result = self._refresh_cache(cache_key, force=cache_key in force_refresh)
                    if refresh_result is not None:
                        refreshed.append(cache_key)
                        if refresh_result:  # Content actually changed
                            content_changed.append(cache_key)
                except Exception as e:
                    self.logger.error(f"Error refreshing cache {cache_key}: {e}")
        
        return refreshed, content_changed
    
    def _refresh_cache(self, cache_key: str, force: bool = False) -> Optional[bool]:
        """Refresh a specific cache.
        
        Args:
            cache_key: Cache key to refresh
            force: Force refresh even if content hasn't changed
            
        Returns:
            True if content changed, False if no change, None if failed
        """
        self.logger.info(f"Refreshing cache: {cache_key}")
        
        # Import here to avoid circular imports
        from .sheet_manager import SheetManager
        
        try:
            sheet_manager = SheetManager(self.config)
            
            # Skip global refresh for ult_chapters and ust_chapters
            # These should be handled by user-specific caching when a book is known.
            if cache_key == 'ult_chapters' or cache_key == 'ust_chapters':
                self.logger.info(f"Skipping global refresh for {cache_key}. Will be cached per user/book.")
                return None # Indicate no change or refresh happened here

            if cache_key == 'templates':
                data = sheet_manager.fetch_templates()
            elif cache_key == 'support_references':
                data = sheet_manager.fetch_support_references()
            elif cache_key == 'system_prompts':
                data = sheet_manager.fetch_system_prompts()
            else:
                self.logger.warning(f"Unknown cache key for refresh: {cache_key}")
                return None
            
            if data:
                # Check if content changed before updating
                content_changed = force or self._has_content_changed(cache_key, data)
                
                # Always update the cache with new data
                self.set_cached_data(cache_key, data)
                
                if content_changed:
                    self.logger.info(f"Successfully refreshed cache with new content: {cache_key}")
                else:
                    self.logger.info(f"Cache refreshed but content unchanged: {cache_key}")
                return content_changed
            else:
                self.logger.warning(f"No data returned for cache refresh: {cache_key}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error refreshing cache {cache_key}: {e}")
            return None
    
    def force_refresh_templates(self) -> bool:
        """Force refresh of template cache regardless of time or content.
        
        Returns:
            True if refresh was successful
        """
        self.logger.info("Force refreshing template cache")
        result = self._refresh_cache('templates', force=True)
        return result is not None
    
    def force_refresh_support_refs(self) -> bool:
        """Force refresh of support references cache regardless of time or content.
        
        Returns:
            True if refresh was successful
        """
        self.logger.info("Force refreshing support references cache")
        result = self._refresh_cache('support_references', force=True)
        return result is not None

    def load_tw_headwords(self) -> List[str]:
        """Load translationWords headwords from cache directory."""
        if self._tw_headwords is not None:
            return self._tw_headwords

        try:
            path = self.cache_dir / 'tw_headwords.json'
            if not path.exists():
                self.logger.warning(f"TW headwords file not found: {path}")
                self._tw_headwords = []
                return self._tw_headwords

            with open(path, 'r', encoding='utf-8') as f:
                self._tw_headwords = json.load(f) or []
            return self._tw_headwords
        except Exception as e:
            self.logger.error(f"Error loading TW headwords: {e}")
            self._tw_headwords = []
            return self._tw_headwords
    
    def clear_cache(self, cache_key: Optional[str] = None):
        """Clear cache data.
        
        Args:
            cache_key: Specific cache key to clear, or None to clear all
        """
        try:
            if cache_key:
                # Clear specific cache
                cache_mapping = {
                    'ult_chapters': self.cache_config['ult_cache_file'],
                    'ust_chapters': self.cache_config['ust_cache_file'],
                    'templates': self.cache_config['templates_cache_file'],
                    'support_references': self.cache_config['support_refs_cache_file'],
                    'system_prompts': self.cache_config['system_prompts_cache_file']
                }
                
                if cache_key in cache_mapping:
                    cache_file = self.cache_dir / cache_mapping[cache_key]
                    if cache_file.exists():
                        cache_file.unlink()
                    
                    if cache_key in self.cache_metadata:
                        del self.cache_metadata[cache_key]
                    
                    self.logger.info(f"Cleared cache: {cache_key}")
                else:
                    self.logger.warning(f"Unknown cache key: {cache_key}")
            else:
                # Clear all caches
                for cache_file in self.cache_dir.glob("*.json"):
                    if cache_file.name != "cache_metadata.json":
                        cache_file.unlink()
                
                self.cache_metadata.clear()
                self.logger.info("Cleared all caches")
            
            self._save_cache_metadata()
            
        except Exception as e:
            self.logger.error(f"Error clearing cache: {e}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        stats = {
            'cache_dir': str(self.cache_dir),
            'total_files': len(list(self.cache_dir.glob("*.json"))),
            'total_size_mb': 0,
            'entries': {}
        }
        
        # Calculate total size
        for cache_file in self.cache_dir.glob("*.json"):
            stats['total_size_mb'] += cache_file.stat().st_size
        
        stats['total_size_mb'] = round(stats['total_size_mb'] / (1024 * 1024), 2)
        
        # Add entry details
        for cache_key, metadata in self.cache_metadata.items():
            content_hash = self.content_hashes.get(cache_key, 'unknown')
            stats['entries'][cache_key] = {
                'last_updated': metadata.get('last_updated'),
                'size_kb': round(metadata.get('size', 0) / 1024, 2),
                'file_path': metadata.get('file_path'),
                'content_hash': content_hash[:8] + '...' if len(content_hash) > 8 else content_hash
            }
        
        return stats
    
    def check_cache_freshness(self) -> Dict[str, Dict[str, Any]]:
        """Check freshness of all caches.
        
        Returns:
            Dictionary with cache freshness information
        """
        cache_checks = [
            ('ult_chapters', self.cache_config['biblical_text_refresh']),
            ('ust_chapters', self.cache_config['biblical_text_refresh']),
            ('templates', self.cache_config['templates_refresh']),
            ('support_references', self.cache_config['support_refs_refresh']),
            ('system_prompts', self.cache_config['templates_refresh'])
        ]
        
        freshness = {}
        
        for cache_key, refresh_minutes in cache_checks:
            if cache_key in self.cache_metadata:
                last_updated = datetime.fromisoformat(self.cache_metadata[cache_key]['last_updated'])
                age_minutes = (datetime.now() - last_updated).total_seconds() / 60
                is_expired = age_minutes > refresh_minutes
                
                freshness[cache_key] = {
                    'last_updated': last_updated.isoformat(),
                    'age_minutes': round(age_minutes, 1),
                    'refresh_interval_minutes': refresh_minutes,
                    'is_expired': is_expired,
                    'expires_in_minutes': max(0, refresh_minutes - age_minutes) if not is_expired else 0
                }
            else:
                freshness[cache_key] = {
                    'last_updated': None,
                    'age_minutes': None,
                    'refresh_interval_minutes': refresh_minutes,
                    'is_expired': True,
                    'expires_in_minutes': 0
                }
        
        return freshness

    def get_cached_data_legacy(self, cache_key: str) -> Optional[Any]:
        """Legacy method for backward compatibility.
        
        Args:
            cache_key: Cache key (maps to cache_type)
            
        Returns:
            Cached data or None if not found/expired
        """
        return self.get_cached_data(cache_key)

    def set_cached_data_legacy(self, cache_key: str, data: Any) -> bool:
        """Legacy method for backward compatibility.
        
        Args:
            cache_key: Cache key (maps to cache_type)
            data: Data to cache
            
        Returns:
            True if data was updated
        """
        self.set_cached_data(cache_key, data)
        return True 
    def load_tw_headwords(self) -> list:
        """Load translation word headwords from cache directory."""
        path = self.cache_dir / "tw_headwords.json"
        if not path.exists():
            self.logger.warning(f"TW headwords cache not found: {path}")
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading TW headwords: {e}")
            return []

