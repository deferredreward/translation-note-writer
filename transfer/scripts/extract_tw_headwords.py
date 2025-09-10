import os
import json
from pathlib import Path


def extract_headwords(repo_path: str) -> list:
    """Extract translation word headwords from the repo.

    Args:
        repo_path: Path to the en_tw repository.
    Returns:
        List of dictionaries with twarticle, file, headwords.
    """
    bible_path = Path(repo_path) / "bible"
    if not bible_path.is_dir():
        raise FileNotFoundError(f"bible directory not found in {repo_path}")

    tw_entries = []
    for subdir in ["kt", "names", "other"]:
        sub_path = bible_path / subdir
        if not sub_path.is_dir():
            continue
        for md_file in sorted(sub_path.glob("*.md")):
            with open(md_file, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
            if not first_line.startswith("#"):
                continue
            headwords_line = first_line.lstrip("#").strip()
            headwords = [w.strip() for w in headwords_line.split(",") if w.strip()]
            tw_entries.append({
                "twarticle": md_file.stem,
                "file": md_file.name,
                "headwords": headwords,
            })
    return tw_entries


def main():
    repo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "en_tw_repo")
    try:
        entries = extract_headwords(repo_path)
    except Exception as e:
        print(f"Error extracting headwords: {e}")
        return

    output_path = Path(os.path.dirname(os.path.dirname(__file__))) / "cache" / "tw_headwords.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(entries)} entries to {output_path}")


if __name__ == "__main__":
    main()
