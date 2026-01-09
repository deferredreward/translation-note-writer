#!/usr/bin/env python3
"""
TSV Quote Converter Python Wrapper with Caching

This wrapper provides caching for the tsv-quote-converters Node.js tool.
It checks the Git repository for updates to specific book files and only
re-downloads when the upstream has been updated.

Copy this file to your project and update CONVERTER_PATH to point to
the tsv-quote-converters directory.
"""

import subprocess
import json
import os
import hashlib
import time
from datetime import datetime
from typing import Optional, Dict, Any

# Configure this path for your setup
CONVERTER_PATH = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(os.path.dirname(__file__), '.cache', 'tsv_resources')


class TSVConverterCache:
    """Manages caching for TSV converter resources"""

    def __init__(self, cache_dir: str = CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _get_cache_key(self, bible_link: str, book_code: str, content_hash: Optional[str] = None) -> str:
        """Generate a unique cache key; include content hash when provided."""
        key_string = f"{bible_link}_{book_code}"
        if content_hash:
            key_string += f"_{content_hash}"
        return hashlib.md5(key_string.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> str:
        """Get the file path for a cache entry"""
        return os.path.join(self.cache_dir, f"{cache_key}.json")

    def _get_latest_commit_sha(self, dcs_url: str, org: str, repo: str,
                               ref: str, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest commit SHA for a specific file in the DCS repo.

        Returns dict with 'sha', 'date', 'message' or None if fails
        """
        try:
            commits_url = f"{dcs_url}/api/v1/repos/{org}/{repo}/commits"
            params = {
                'path': file_path,
                'sha': ref,
                'limit': 1
            }

            import requests
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
            print(f"Warning: Could not fetch commit info: {e}")
            return None

    def _get_usfm_filename(self, book_code: str) -> Optional[str]:
        """Get USFM filename for a book code (requires books.json or similar)"""
        # Book code to USFM mapping - simplified version
        # You might want to load this from the actual BibleBookData
        book_map = {
            'GEN': '01-GEN', 'EXO': '02-EXO', 'LEV': '03-LEV', 'NUM': '04-NUM',
            'DEU': '05-DEU', 'JOS': '06-JOS', 'JDG': '07-JDG', 'RUT': '08-RUT',
            '1SA': '09-1SA', '2SA': '10-2SA', '1KI': '11-1KI', '2KI': '12-2KI',
            '1CH': '13-1CH', '2CH': '14-2CH', 'EZR': '15-EZR', 'NEH': '16-NEH',
            'EST': '17-EST', 'JOB': '18-JOB', 'PSA': '19-PSA', 'PRO': '20-PRO',
            'ECC': '21-ECC', 'SNG': '22-SNG', 'ISA': '23-ISA', 'JER': '24-JER',
            'LAM': '25-LAM', 'EZK': '26-EZK', 'DAN': '27-DAN', 'HOS': '28-HOS',
            'JOL': '29-JOL', 'AMO': '30-AMO', 'OBA': '31-OBA', 'JON': '32-JON',
            'MIC': '33-MIC', 'NAM': '34-NAM', 'HAB': '35-HAB', 'ZEP': '36-ZEP',
            'HAG': '37-HAG', 'ZEC': '38-ZEC', 'MAL': '39-MAL',
            'MAT': '41-MAT', 'MRK': '42-MRK', 'LUK': '43-LUK', 'JHN': '44-JHN',
            'ACT': '45-ACT', 'ROM': '46-ROM', '1CO': '47-1CO', '2CO': '48-2CO',
            'GAL': '49-GAL', 'EPH': '50-EPH', 'PHP': '51-PHP', 'COL': '52-COL',
            '1TH': '53-1TH', '2TH': '54-2TH', '1TI': '55-1TI', '2TI': '56-2TI',
            'TIT': '57-TIT', 'PHM': '58-PHM', 'HEB': '59-HEB', 'JAS': '60-JAS',
            '1PE': '61-1PE', '2PE': '62-2PE', '1JN': '63-1JN', '2JN': '64-2JN',
            '3JN': '65-3JN', 'JUD': '66-JUD', 'REV': '67-REV'
        }
        return book_map.get(book_code.upper())

    def should_use_cache(self, bible_link: str, book_code: str,
                         dcs_url: str = 'https://git.door43.org',
                         verbose: bool = False,
                         content_hash: Optional[str] = None) -> tuple[bool, Optional[Dict]]:
        """
        Check if cached data is still valid.

        Returns: (use_cache: bool, cached_data: dict or None)
        """
        cache_key = self._get_cache_key(bible_link, book_code, content_hash)
        cache_path = self._get_cache_path(cache_key)

        # No cache file exists
        if not os.path.exists(cache_path):
            if verbose:
                print(f"  No cache for {bible_link}/{book_code}")
            return False, None

        # Load cache metadata
        try:
            with open(cache_path, 'r') as f:
                cache_data = json.load(f)
        except Exception as e:
            if verbose:
                print(f"  Error reading cache: {e}")
            return False, None

        # Parse bible link
        parts = bible_link.split('/')
        if len(parts) < 2:
            return False, None

        org, repo = parts[0], parts[1]
        ref = parts[2] if len(parts) > 2 else 'master'

        # Get USFM filename
        usfm_file = self._get_usfm_filename(book_code)
        if not usfm_file:
            return False, None

        file_path = f"{usfm_file}.usfm"

        # Check if upstream has been updated
        latest_commit = self._get_latest_commit_sha(dcs_url, org, repo, ref, file_path)

        if not latest_commit:
            # Could not verify, use cache if it exists
            if verbose:
                print(f"  Using cache (could not verify updates)")
            return True, cache_data

        # Compare commit SHAs and content hash if present
        cached_sha = cache_data.get('commit_sha')
        cached_content_hash = cache_data.get('content_hash')
        if cached_sha == latest_commit['sha'] and (content_hash is None or cached_content_hash == content_hash):
            if verbose:
                print(f"  ✓ Cache valid (commit: {cached_sha[:8]})")
            return True, cache_data

        # Cache is stale
        if verbose:
            print(f"  ✗ Cache outdated:")
            print(f"    Cached: {cached_sha[:8] if cached_sha else 'unknown'}")
            print(f"    Latest: {latest_commit['sha'][:8]}")
            print(f"    Update: {latest_commit['message'][:60]}")
            if content_hash is not None:
                print(f"    Content hash: {content_hash}")

        return False, None

    def save_to_cache(self, bible_link: str, book_code: str, result: Dict[str, Any],
                     dcs_url: str = 'https://git.door43.org',
                     verbose: bool = False,
                     content_hash: Optional[str] = None):
        """Save converter result to cache with metadata"""
        cache_key = self._get_cache_key(bible_link, book_code, content_hash)
        cache_path = self._get_cache_path(cache_key)

        # Parse bible link
        parts = bible_link.split('/')
        if len(parts) < 2:
            return

        org, repo = parts[0], parts[1]
        ref = parts[2] if len(parts) > 2 else 'master'

        # Get commit info
        usfm_file = self._get_usfm_filename(book_code)
        if not usfm_file:
            return

        file_path = f"{usfm_file}.usfm"
        latest_commit = self._get_latest_commit_sha(dcs_url, org, repo, ref, file_path)

        cache_data = {
            'bible_link': bible_link,
            'book_code': book_code,
            'dcs_url': dcs_url,
            'commit_sha': latest_commit['sha'] if latest_commit else 'unknown',
            'commit_date': latest_commit['date'] if latest_commit else None,
            'commit_message': latest_commit['message'] if latest_commit else None,
            'cached_at': datetime.now().isoformat(),
            'result': result,
            'content_hash': content_hash
        }

        try:
            with open(cache_path, 'w') as f:
                json.dump(cache_data, f, indent=2)
            if verbose:
                print(f"  Saved to cache: {cache_path}")
        except Exception as e:
            if verbose:
                print(f"  Error saving cache: {e}")

    def clear_cache(self):
        """Clear all cached resources"""
        if os.path.exists(self.cache_dir):
            files = os.listdir(self.cache_dir)
            for file in files:
                os.remove(os.path.join(self.cache_dir, file))
            print(f"Cleared {len(files)} cached resources")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        if not os.path.exists(self.cache_dir):
            return {'total_files': 0, 'total_size': 0, 'resources': []}

        files = os.listdir(self.cache_dir)
        total_size = 0
        resources = []

        for file in files:
            file_path = os.path.join(self.cache_dir, file)
            file_size = os.path.getsize(file_path)
            total_size += file_size

            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    resources.append({
                        'file': file,
                        'bible_link': data.get('bible_link'),
                        'book_code': data.get('book_code'),
                        'commit_sha': data.get('commit_sha', 'unknown')[:8],
                        'commit_date': data.get('commit_date'),
                        'cached_at': data.get('cached_at'),
                        'size': file_size
                    })
            except:
                pass

        return {
            'total_files': len(files),
            'total_size': total_size,
            'resources': resources
        }


class TSVConverter:
    """Python wrapper for TSV Quote Converters with intelligent caching"""

    def __init__(self, converter_path: str = CONVERTER_PATH, use_cache: bool = True):
        self.converter_path = converter_path
        self.cache = TSVConverterCache() if use_cache else None

    def _call_node_converter(self, command: str, bible_link: str,
                            book_code: str, tsv_content: str) -> Optional[Dict[str, Any]]:
        """Call the Node.js CLI wrapper"""
        # Pass TSV via stdin to avoid argument length and special character issues
        result = subprocess.run(
            ['node', 'cli_for_lang_conversion.js', command, bible_link, book_code, '-'],
            input=tsv_content,
            capture_output=True,
            text=True,
            cwd=self.converter_path
        )

        if result.returncode != 0:
            print(f"Error calling converter: {result.stderr}")
            return None

        return json.loads(result.stdout)

    def convert_gl_to_ol(self, bible_link: str, book_code: str,
                        tsv_content: str, use_cache: bool = True,
                        verbose: bool = False) -> Optional[Dict[str, Any]]:
        """
        Convert Gateway Language (English) quotes to Original Language (Hebrew/Greek).

        Args:
            bible_link: DCS link (e.g., 'unfoldingWord/en_ult/master')
            book_code: 3-letter book code (e.g., 'JON', 'GEN')
            tsv_content: TSV string with headers
            use_cache: Whether to use cached results
            verbose: Print cache status messages

        Returns:
            dict with 'output' (TSV string) and 'errors' (list) or None
        """
        # Hash the TSV content to avoid stale cache across different inputs
        content_hash = hashlib.md5(tsv_content.encode('utf-8')).hexdigest()

        # Check cache if enabled
        if use_cache and self.cache:
            should_use, cached_data = self.cache.should_use_cache(
                bible_link, book_code, verbose=verbose, content_hash=content_hash
            )
            if should_use and cached_data:
                return cached_data['result']

        # Call converter
        if verbose:
            print(f"  Calling converter: gl2ol {bible_link}/{book_code}")

        result = self._call_node_converter('gl2ol', bible_link, book_code, tsv_content)

        # Save to cache
        if result and self.cache:
            self.cache.save_to_cache(bible_link, book_code, result, verbose=verbose, content_hash=content_hash)

        return result

    def add_gl_columns(self, bible_link: str, book_code: str,
                      tsv_content: str, use_cache: bool = True,
                      verbose: bool = False) -> Optional[Dict[str, Any]]:
        """
        Add Gateway Language columns to TSV with Original Language quotes.

        Args:
            bible_link: DCS link (e.g., 'unfoldingWord/en_ult/master')
            book_code: 3-letter book code (e.g., 'JON', 'GEN')
            tsv_content: TSV string with OL quotes
            use_cache: Whether to use cached results
            verbose: Print cache status messages

        Returns:
            dict with 'output' (TSV string) and 'errors' (list) or None
        """
        # Note: We don't cache addgl results as they depend on the input TSV content
        if verbose:
            print(f"  Calling converter: addgl {bible_link}/{book_code}")

        return self._call_node_converter('addgl', bible_link, book_code, tsv_content)

    def roundtrip(self, bible_link: str, book_code: str, tsv_content: str,
                 use_cache: bool = True, verbose: bool = False) -> Optional[Dict[str, Any]]:
        """
        Perform round-trip conversion: GL → OL → GL (with GLQuote columns).

        Returns the final result with GLQuote and GLOccurrence columns added.
        """
        # Step 1: English to Hebrew/Greek
        if verbose:
            print("Step 1: Converting GL to OL...")
        result1 = self.convert_gl_to_ol(bible_link, book_code, tsv_content,
                                        use_cache=use_cache, verbose=verbose)

        if not result1:
            print("Failed at step 1")
            return None

        if result1.get('errors') and verbose:
            print(f"Step 1 errors: {result1['errors']}")

        # Step 2: Add GL columns
        if verbose:
            print("Step 2: Adding GL columns...")
        result2 = self.add_gl_columns(bible_link, book_code, result1['output'],
                                      use_cache=False, verbose=verbose)

        if not result2:
            print("Failed at step 2")
            return None

        if result2.get('errors') and verbose:
            print(f"Step 2 errors: {result2['errors']}")

        return result2


# Example usage
if __name__ == '__main__':
    # Initialize converter
    converter = TSVConverter()

    # Example TSV data
    tsv_data = """Reference\tID\tTags\tQuote\tOccurrence\tNote
1:3\tkrcb\trc://*/ta/man/translate/figs-metonymy\trun & face\t1\tThis is the note"""

    # Perform round-trip with caching
    print("=== Round-trip conversion with caching ===\n")
    result = converter.roundtrip(
        bible_link='unfoldingWord/en_ult/master',
        book_code='JON',
        tsv_content=tsv_data,
        use_cache=True,
        verbose=True
    )

    if result:
        print("\n=== Final Output ===")
        print(result['output'])

        if result.get('errors'):
            print("\n=== Errors ===")
            for error in result['errors']:
                print(f"  {error}")

    # Show cache stats
    print("\n=== Cache Statistics ===")
    stats = converter.cache.get_stats()
    print(f"Total cached files: {stats['total_files']}")
    print(f"Total cache size: {stats['total_size']:,} bytes")
    for resource in stats['resources']:
        print(f"  {resource['bible_link']}/{resource['book_code']} - "
              f"commit {resource['commit_sha']} - "
              f"{resource['size']:,} bytes")
