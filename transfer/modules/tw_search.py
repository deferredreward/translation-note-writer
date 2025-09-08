import json
import os
from pathlib import Path
from typing import List


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


def find_matches(quote: str, tw_entries: List[dict]) -> List[str]:
    """Find matching TW articles for phrases in quote."""
    tokens = quote.lower().split()
    matches = set()
    for start in range(len(tokens)):
        for end in range(start + 1, len(tokens) + 1):
            phrase_tokens = tokens[start:end]
            if len(phrase_tokens) == 1 and phrase_tokens[0] in STOPWORDS:
                continue
            phrase = " ".join(phrase_tokens)
            for entry in tw_entries:
                for hw in entry.get("headwords", []):
                    if phrase == hw.lower():
                        matches.add(entry["file"])
                        break
    return sorted(matches)
