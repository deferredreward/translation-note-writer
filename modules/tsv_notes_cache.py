"""
TSV Notes Cache Manager
Manages caching of upstream Translation Notes TSV files and generates unique IDs.
"""

import os
import json
import hashlib
import logging
import random
import string
from datetime import datetime
from typing import Dict, List, Optional, Set, Any

try:
    import requests
except ImportError:
    requests = None


class TSVNotesCache:
    """Manages caching for upstream Translation Notes TSV files and ID generation."""

    def __init__(self, cache_dir: Optional[str] = None):
        """Initialize the TSV notes cache.

        Args:
            cache_dir: Directory for caching TSV files (default: .cache/tsv_notes)
        """
        if cache_dir is None:
            cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.cache', 'tsv_notes')

        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.logger = logging.getLogger(__name__)

        # Check if requests is available
        if requests is None:
            self.logger.warning("requests library not available. Upstream TSV fetching will be disabled.")

    def _get_cache_path(self, book_code: str) -> str:
        """Get the cache file path for a book.

        Args:
            book_code: 3-letter book code (e.g., 'GEN', 'JON')

        Returns:
            Path to cache file
        """
        return os.path.join(self.cache_dir, f"tn_{book_code.upper()}.json")

    def _get_latest_commit_sha(self, book_code: str) -> Optional[Dict[str, Any]]:
        """Get the latest commit SHA for a specific TSV file in the DCS repo.

        Args:
            book_code: 3-letter book code

        Returns:
            dict with 'sha', 'date', 'message' or None if fails
        """
        if requests is None:
            return None

        try:
            commits_url = "https://git.door43.org/api/v1/repos/unfoldingWord/en_tn/commits"
            file_path = f"tn_{book_code.upper()}.tsv"
            params = {
                'path': file_path,
                'sha': 'master',
                'limit': 1
            }

            response = requests.get(commits_url, params=params, timeout=10)
            response.raise_for_status()

            commits = response.json()
            if commits and len(commits) > 0:
                commit = commits[0]
                return {
                    'sha': commit['sha'],
                    'date': commit['commit']['committer']['date'],
                    'message': commit['commit']['message']
                }
            return None
        except Exception as e:
            self.logger.warning(f"Could not fetch commit info for {book_code}: {e}")
            return None

    def fetch_upstream_tsv(self, book_code: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """Fetch upstream TSV file from door43.org, using cache if valid.

        Args:
            book_code: 3-letter book code (e.g., 'GEN', 'JON')
            force_refresh: Force re-download even if cache is valid

        Returns:
            Dict with 'content' (TSV text), 'rows' (parsed list), 'ids' (set of IDs),
            'commit_sha', 'cached_at', or None if failed
        """
        book_code = book_code.upper()
        cache_path = self._get_cache_path(book_code)

        # Check cache validity
        if not force_refresh and os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)

                # Check if upstream has been updated
                latest_commit = self._get_latest_commit_sha(book_code)

                if latest_commit and cached_data.get('commit_sha') == latest_commit['sha']:
                    self.logger.debug(f"Using cached TSV for {book_code} (commit: {latest_commit['sha'][:8]})")
                    return cached_data
                elif not latest_commit:
                    # Could not verify, use cache
                    self.logger.debug(f"Using cached TSV for {book_code} (could not verify updates)")
                    return cached_data
                else:
                    self.logger.info(f"Cache outdated for {book_code}, fetching new version")
            except Exception as e:
                self.logger.warning(f"Error reading cache for {book_code}: {e}")

        # Fetch from upstream
        if requests is None:
            self.logger.error("Cannot fetch upstream TSV: requests library not available")
            return None

        try:
            url = f"https://git.door43.org/unfoldingWord/en_tn/raw/branch/master/tn_{book_code}.tsv"
            self.logger.info(f"Fetching upstream TSV from {url}")

            response = requests.get(url, timeout=30)
            response.raise_for_status()

            tsv_content = response.text

            # Parse TSV content
            rows = self._parse_tsv(tsv_content)
            ids = self._extract_ids(rows)

            # Get commit info
            latest_commit = self._get_latest_commit_sha(book_code)

            # Prepare cache data
            cache_data = {
                'book_code': book_code,
                'content': tsv_content,
                'rows': rows,
                'ids': list(ids),  # Convert set to list for JSON serialization
                'commit_sha': latest_commit['sha'] if latest_commit else 'unknown',
                'commit_date': latest_commit['date'] if latest_commit else None,
                'commit_message': latest_commit['message'] if latest_commit else None,
                'cached_at': datetime.now().isoformat(),
                'url': url
            }

            # Save to cache
            try:
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump(cache_data, f, indent=2)
                self.logger.debug(f"Cached TSV for {book_code} at {cache_path}")
            except Exception as e:
                self.logger.warning(f"Could not save cache for {book_code}: {e}")

            return cache_data

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                self.logger.warning(f"TSV file not found for {book_code} (404)")
            else:
                self.logger.error(f"HTTP error fetching TSV for {book_code}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error fetching upstream TSV for {book_code}: {e}")
            return None

    def _parse_tsv(self, tsv_content: str) -> List[Dict[str, str]]:
        """Parse TSV content into list of row dictionaries.

        Args:
            tsv_content: TSV file content as string

        Returns:
            List of dictionaries, one per row (excluding header)
        """
        lines = tsv_content.strip().split('\n')
        if len(lines) < 2:
            return []

        # First line is headers
        headers = lines[0].split('\t')

        # Parse remaining lines
        rows = []
        for line in lines[1:]:
            if not line.strip():
                continue

            values = line.split('\t')
            row = {}
            for i, header in enumerate(headers):
                if i < len(values):
                    row[header] = values[i]
                else:
                    row[header] = ''
            rows.append(row)

        return rows

    def _extract_ids(self, rows: List[Dict[str, str]]) -> Set[str]:
        """Extract all IDs from parsed TSV rows.

        Args:
            rows: List of row dictionaries

        Returns:
            Set of ID strings found in the TSV
        """
        ids = set()
        for row in rows:
            row_id = row.get('ID', '').strip()
            if row_id:
                ids.add(row_id)
        return ids

    def get_existing_ids(self, book_code: str, additional_ids: Optional[Set[str]] = None) -> Set[str]:
        """Get all existing IDs for a book from upstream TSV and additional sources.

        Args:
            book_code: 3-letter book code
            additional_ids: Additional IDs to include (e.g., from current spreadsheet)

        Returns:
            Set of all existing IDs
        """
        existing_ids = set()

        # Get IDs from upstream TSV
        tsv_data = self.fetch_upstream_tsv(book_code)
        if tsv_data and 'ids' in tsv_data:
            existing_ids.update(tsv_data['ids'])

        # Add additional IDs
        if additional_ids:
            existing_ids.update(additional_ids)

        return existing_ids

    def generate_unique_id(self, existing_ids: Set[str], max_attempts: int = 100) -> Optional[str]:
        """Generate a unique 4-character ID.

        Format: First char [a-z], remaining 3 chars [a-z0-9]

        Args:
            existing_ids: Set of existing IDs to avoid
            max_attempts: Maximum number of generation attempts

        Returns:
            Unique 4-character ID or None if failed after max_attempts
        """
        # Characters for first position (lowercase letters only)
        first_chars = string.ascii_lowercase

        # Characters for remaining positions (lowercase letters + digits)
        other_chars = string.ascii_lowercase + string.digits

        for attempt in range(max_attempts):
            # Generate ID: first char is letter, rest can be letter or digit
            new_id = random.choice(first_chars) + ''.join(random.choices(other_chars, k=3))

            if new_id not in existing_ids:
                return new_id

        # If we couldn't generate unique ID after max_attempts, log error
        self.logger.error(f"Failed to generate unique ID after {max_attempts} attempts")
        return None

    def generate_fallback_id(self) -> str:
        """Generate a fallback ID based on timestamp.

        This is used when random generation fails. Format: x + 3 chars from timestamp hash

        Returns:
            4-character fallback ID
        """
        timestamp = str(int(datetime.now().timestamp() * 1000))
        hash_obj = hashlib.md5(timestamp.encode())
        hash_hex = hash_obj.hexdigest()

        # Use 'x' as prefix for fallback IDs and take 3 chars from hash (lowercase letters only)
        fallback_chars = ''.join(c for c in hash_hex if c in string.ascii_lowercase)[:3]

        # Pad with 'z' if not enough letters
        while len(fallback_chars) < 3:
            fallback_chars += 'z'

        return 'x' + fallback_chars[:3]

    def clear_cache(self, book_code: Optional[str] = None):
        """Clear cached TSV files.

        Args:
            book_code: Clear cache for specific book, or None to clear all
        """
        if book_code:
            cache_path = self._get_cache_path(book_code)
            if os.path.exists(cache_path):
                os.remove(cache_path)
                self.logger.info(f"Cleared cache for {book_code}")
        else:
            # Clear all caches
            if os.path.exists(self.cache_dir):
                files = os.listdir(self.cache_dir)
                for file in files:
                    os.remove(os.path.join(self.cache_dir, file))
                self.logger.info(f"Cleared {len(files)} cached TSV files")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about cached TSV files.

        Returns:
            Dict with cache statistics
        """
        if not os.path.exists(self.cache_dir):
            return {'total_files': 0, 'total_size': 0, 'books': []}

        files = os.listdir(self.cache_dir)
        total_size = 0
        books = []

        for file in files:
            if not file.endswith('.json'):
                continue

            file_path = os.path.join(self.cache_dir, file)
            file_size = os.path.getsize(file_path)
            total_size += file_size

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    books.append({
                        'file': file,
                        'book_code': data.get('book_code'),
                        'commit_sha': data.get('commit_sha', 'unknown')[:8],
                        'commit_date': data.get('commit_date'),
                        'cached_at': data.get('cached_at'),
                        'id_count': len(data.get('ids', [])),
                        'row_count': len(data.get('rows', [])),
                        'size': file_size
                    })
            except Exception as e:
                self.logger.warning(f"Could not read cache stats for {file}: {e}")

        return {
            'total_files': len(files),
            'total_size': total_size,
            'books': books
        }
