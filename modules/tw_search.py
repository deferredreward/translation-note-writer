import json
import os
from pathlib import Path
from typing import List, Optional, Union


STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'if', 'in', 'on', 'to', 'for',
    'with', 'at', 'by', 'from', 'up', 'about', 'into', 'over', 'after',
    'under', 'again', 'further', 'then', 'once', 'of', 'off', 'out', 'so',
    'than', 'too', 'very', 'he', 'she', 'it', 'they', 'them', 'him', 'her',
    'you', 'i', 'we', 'us', 'my', 'your', 'his', 'their', 'our'
}


def load_tw_headwords(cache_dir: str) -> List[dict]:
    """Load TW headwords JSON from cache directory."""
    path = Path(cache_dir) / "tw_headwords.json"
    if not path.exists():
        raise FileNotFoundError(f"tw_headwords.json not found in {cache_dir}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_matches(quote: str, tw_entries: List[dict],
                 category_filter: Optional[Union[str, List[str]]] = None) -> List[str]:
    """Find matching TW articles for phrases in quote.

    Args:
        quote: The text to search for matches (e.g., GLQuote)
        tw_entries: List of TW entry dictionaries with headwords
        category_filter: Optional category or list of categories to filter by
                        ("kt", "names", "other")

    Returns:
        Sorted list of matching TW file names
    """
    tokens = quote.lower().split()
    matches = set()

    # Normalize category_filter to a set for efficient lookup
    if category_filter is None:
        allowed_categories = None
    elif isinstance(category_filter, str):
        allowed_categories = {category_filter}
    else:
        allowed_categories = set(category_filter)

    for start in range(len(tokens)):
        for end in range(start + 1, len(tokens) + 1):
            phrase_tokens = tokens[start:end]
            if len(phrase_tokens) == 1 and phrase_tokens[0] in STOPWORDS:
                continue
            phrase = " ".join(phrase_tokens)
            for entry in tw_entries:
                # Filter by category if specified
                if allowed_categories and entry.get("category") not in allowed_categories:
                    continue
                for hw in entry.get("headwords", []):
                    if phrase == hw.lower():
                        matches.add(entry["file"])
                        break
    return sorted(matches)
