"""
Civitai Extractor — core extraction and download logic.
Handles: page parsing, keyword extraction, deduplication, file download.
"""

import json
import re
import os
import urllib.request
from html import unescape
from pathlib import Path


class CivitaiExtractor:
    """Extract model metadata and download files from civitai.red."""

    def __init__(self, api_key: str, download_dir: str = "/home/bot/civitai-download"):
        self.api_key = api_key
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def fetch_page(self, url: str) -> str:
        """Fetch a civitai page and return its HTML."""
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")

    def parse_model_data(self, html: str) -> dict:
        """Extract model data from __NEXT_DATA__ JSON in the page."""
        match = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html, re.DOTALL
        )
        if not match:
            raise ValueError("Could not find __NEXT_DATA__ in page — not a civitai model page?")

        data = json.loads(match.group(1))
        queries = data["props"]["pageProps"]["trpcState"]["json"]["queries"]

        for q in queries:
            d = q["state"]["data"]
            if isinstance(d, dict) and "modelVersions" in d:
                return d
        raise ValueError("No model data found in page")

    def extract_keywords(self, model_data: dict) -> list[str]:
        """
        Extract trigger words from model data.
        Returns deduplicated list: trainedWords + unique description blocks.
        """
        # 1. Collect trainedWords from all versions
        trained_words: list[str] = []
        for v in model_data.get("modelVersions", []):
            for word in v.get("trainedWords", []):
                word = word.strip()
                # Skip placeholder entries
                if word.lower().startswith("see model info"):
                    continue
                trained_words.append(word)

        # 2. Parse description for keyword blocks
        desc_html = model_data.get("description", "")
        desc_html = re.sub(r'<(?:br|/p|/div)\s*/?>', '\n', desc_html)
        desc_text = re.sub(r'<[^>]+>', '', desc_html)
        desc_text = unescape(desc_text)
        desc_text = re.sub(r'[ \t]+', ' ', desc_text).strip()

        # Extract comma-separated blocks (3+ items) from each line separately
        desc_blocks = []
        for line in desc_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            blocks = re.findall(
                r'(?:[\w\s#.-]+(?:,\s*[\w\s#.-]+){2,})',
                line
            )
            desc_blocks.extend(b.strip().rstrip(",") for b in blocks)

        # 3. Deduplicate: skip description blocks that are subsets of trainedWords
        trained_kw_sets = [
            set(k.strip().lower() for k in tw.split(",") if k.strip())
            for tw in trained_words
        ]

        new_blocks = []
        for block in desc_blocks:
            block_kw = set(k.strip().lower() for k in block.split(",") if k.strip())
            is_dup = any(
                block_kw.issubset(ts) or ts.issubset(block_kw)
                for ts in trained_kw_sets
            )
            if not is_dup:
                new_blocks.append(block)

        return trained_words + new_blocks

    def get_file_info(self, model_data: dict) -> dict | None:
        """Get the first downloadable file's metadata."""
        for v in model_data.get("modelVersions", []):
            for f in v.get("files", []):
                return {
                    "name": f["name"],
                    "url": f["url"],
                    "size_kb": f.get("sizeKB", 0),
                    "version_id": v["id"],
                }
        return None

    def download_file(self, model_data: dict, file_info: dict) -> Path:
        """Download the model file and return the local path."""
        version_id = file_info["version_id"]
        filename = file_info["name"]
        dest = self.download_dir / filename

        if dest.exists():
            return dest  # Already downloaded

        api_url = f"https://civitai.red/api/download/models/{version_id}?token={self.api_key}"

        req = urllib.request.Request(api_url, method="GET")
        req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")

        with urllib.request.urlopen(req, timeout=300) as resp:
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)

        return dest

    def save_keywords(self, model_data: dict, file_info: dict) -> Path:
        """Save keywords as .txt next to the downloaded file."""
        keywords = self.extract_keywords(model_data)
        model_name = file_info["name"]
        base = os.path.splitext(model_name)[0]
        txt_path = self.download_dir / f"{base}.txt"

        with open(txt_path, "w") as f:
            for kw in keywords:
                f.write(kw + "\n")

        return txt_path

    def process(self, url: str) -> dict:
        """Full pipeline: fetch → parse → download → save keywords."""
        html = self.fetch_page(url)
        model_data = self.parse_model_data(html)

        file_info = self.get_file_info(model_data)
        if not file_info:
            raise ValueError("No downloadable file found on this page")

        model_name = model_data.get("name", "Unknown")
        print(f"Model: {model_name}")
        print(f"File: {file_info['name']} ({file_info['size_kb']:.0f} KB)")

        # Download
        print("Downloading...")
        dest = self.download_file(model_data, file_info)
        print(f"Saved: {dest}")

        # Keywords
        txt_path = self.save_keywords(model_data, file_info)
        keywords = self.extract_keywords(model_data)
        print(f"Keywords: {len(keywords)} lines → {txt_path}")

        return {
            "model_name": model_name,
            "file": str(dest),
            "keywords_file": str(txt_path),
            "keyword_count": len(keywords),
        }


if __name__ == "__main__":
    import sys

    # Try common paths
    key_paths = [
        os.path.expanduser("~/.api_key_civitai"),
        "/home/bot/projects/.api_key_civitai",
    ]
    api_key = None
    for p in key_paths:
        if os.path.isfile(p):
            with open(p) as f:
                api_key = f.read().strip()
            break

    if not api_key:
        print("API key not found. Tried:", key_paths)
        print("Create ~/.api_key_civitai with your Civitai API token.")
        sys.exit(1)

    extractor = CivitaiExtractor(api_key)
    url = sys.argv[1] if len(sys.argv) > 1 else input("URL: ")
    result = extractor.process(url)
    print(f"\nDone! {result}")
