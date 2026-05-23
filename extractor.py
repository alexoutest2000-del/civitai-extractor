"""
Civitai Extractor — core extraction and download logic.
Handles: page parsing, keyword extraction, deduplication, file download with progress.
"""

import json
import re
import os
import tempfile
import urllib.request
from html import unescape
from pathlib import Path
from typing import Callable


# Per-user bucket cache for image URL construction
_bucket_cache: dict[str, str] = {}


def _get_bucket(username: str) -> str | None:
    """Fetch the image bucket for a user from their profile page."""
    if username in _bucket_cache:
        return _bucket_cache[username]
    try:
        req = urllib.request.Request(
            f"https://civitai.red/user/{username}",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")
        buckets = re.findall(r'https?://image\.civitai\.com/([^/]+)/', html)
        if buckets:
            _bucket_cache[username] = buckets[0]
            return buckets[0]
    except Exception:
        pass
    return None



class CivitaiExtractor:
    """Extract model metadata and download files from civitai.red."""

    def __init__(self, api_key: str, download_dir: str | None = None):
        self.api_key = api_key
        self.download_dir = Path(download_dir) if download_dir else Path(tempfile.mkdtemp(prefix="civitai_"))
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

    def get_first_image(self, html: str, model_data: dict = None) -> str | None:
        """Extract the first model example image URL.

        1. Model data images array (civitai.com main site)
        2. Showcase image from __NEXT_DATA__ queries (civitai.red)
        3. HTML regex fallback
        """
        # 1. Model data images array
        if model_data:
            for v in model_data.get("modelVersions", []):
                images = v.get("images")
                if images:
                    url = images[0].get("url")
                    if url:
                        return url

        # 2. Showcase image from __NEXT_DATA__ (civitai.red)
        try:
            nd_match = re.search(
                r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                html, re.DOTALL
            )
            if nd_match:
                data = json.loads(nd_match.group(1))
                queries = data["props"]["pageProps"]["trpcState"]["json"]["queries"]
                showcase_uuid = None
                username = None
                for q in queries:
                    d = q["state"]["data"]
                    if isinstance(d, dict):
                        if "image" in d and isinstance(d["image"], dict):
                            showcase_uuid = d["image"].get("url")
                        if "user" in d and isinstance(d["user"], dict):
                            username = d["user"].get("username")
                if showcase_uuid and username:
                    bucket = _get_bucket(username)
                    if bucket:
                        return f"https://image.civitai.com/{bucket}/{showcase_uuid}/width=450/{showcase_uuid}.jpeg"
        except Exception:
            pass

        # 3. Fallback: HTML regex
        imgs = re.findall(r'src=\\"(https://image\.civitai\.com[^"]+)\\"', html)
        if not imgs:
            imgs = re.findall(r'src="(https://image\.civitai\.com[^"]+)"', html)
        return imgs[0] if imgs else None

    def extract_keywords(self, model_data: dict) -> list[str]:
        """Extract trigger words. Returns deduplicated list."""
        trained_words: list[str] = []
        for v in model_data.get("modelVersions", []):
            for word in v.get("trainedWords", []):
                word = word.strip()
                if word.lower().startswith("see model info"):
                    continue
                trained_words.append(word)

        desc_html = model_data.get("description", "")
        desc_html = re.sub(r'<(?:br|/p|/div)\s*/?>', '\n', desc_html)
        desc_text = re.sub(r'<[^>]+>', '', desc_html)
        desc_text = unescape(desc_text)
        desc_text = re.sub(r'[ \t]+', ' ', desc_text).strip()

        desc_blocks = []
        for line in desc_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            blocks = re.findall(r'(?:[\w\s#.-]+(?:,\s*[\w\s#.-]+){2,})', line)
            desc_blocks.extend(b.strip().rstrip(",") for b in blocks)

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
                    "size_bytes": int(f.get("sizeKB", 0) * 1024),
                    "version_id": v["id"],
                    "type": model_data.get("type", "Unknown"),
                    "base_model": v.get("baseModel", "Unknown"),
                    "base_model_type": v.get("baseModelType", ""),
                }
        return None

    def download_file(
        self,
        model_data: dict,
        file_info: dict,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Path:
        """Download the model file with progress tracking. Returns local path."""
        version_id = file_info["version_id"]
        filename = file_info["name"]
        dest = self.download_dir / filename
        total_bytes = file_info.get("size_bytes", 0)

        api_url = f"https://civitai.red/api/download/models/{version_id}?token={self.api_key}"

        req = urllib.request.Request(api_url, method="GET")
        req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")

        downloaded = 0
        with urllib.request.urlopen(req, timeout=600) as resp:
            # Try to get actual content-length from response headers
            cl = resp.headers.get("Content-Length")
            if cl:
                total_bytes = int(cl)

            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_bytes:
                        progress_callback(downloaded, total_bytes)

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

    def process(
        self,
        url: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict:
        """Full pipeline: fetch → parse → download → save keywords."""
        html = self.fetch_page(url)
        model_data = self.parse_model_data(html)

        file_info = self.get_file_info(model_data)
        if not file_info:
            raise ValueError("No downloadable file found on this page")

        first_image = self.get_first_image(html)
        model_name = model_data.get("name", "Unknown")
        keywords = self.extract_keywords(model_data)

        # Download
        dest = self.download_file(model_data, file_info, progress_callback)

        # Save keywords
        txt_path = self.save_keywords(model_data, file_info)

        return {
            "model_name": model_name,
            "file": str(dest),
            "file_name": file_info["name"],
            "file_type": file_info["type"],
            "base_model": file_info["base_model"],
            "size_kb": file_info["size_kb"],
            "keywords_file": str(txt_path),
            "keyword_count": len(keywords),
            "keywords": keywords,
            "first_image": first_image,
        }


if __name__ == "__main__":
    import sys

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
    print(f"\nDone! {result['model_name']} ({result['file_type']} | {result['base_model']})")
    print(f"  File: {result['file_name']} ({result['size_kb']:.0f} KB)")
    print(f"  Keywords: {result['keyword_count']} lines")
    if result.get("first_image"):
        print(f"  Preview: {result['first_image']}")
