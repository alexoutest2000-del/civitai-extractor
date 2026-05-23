# Civitai Data Extractor

Desktop GUI tool to download AI models and extract trigger words from [civitai.red](https://civitai.red).

## What it does

1. **Paste a model URL** (e.g. `https://civitai.red/models/2641591/evelynn-league-of-legends`)
2. **Downloads** the `.safetensors` file to a configurable folder
3. **Extracts trigger words** — combines `trainedWords` from model metadata with unique keyword blocks found in the description, saved as `{filename}.txt`

## Dependencies

| Dependency | Version | Purpose | Install |
|------------|---------|---------|---------|
| Python | 3.11+ | Runtime | `sudo apt install python3` |
| Tkinter | — | GUI toolkit | `sudo apt install python3-tk` |
| stdlib (`json`, `re`, `urllib`, `html`, `pathlib`) | built-in | Page parsing, HTTP, dedup | None (bundled with Python) |

All dependencies are Python standard library except `python3-tk` (GUI only — not needed for CLI mode).

## Setup

```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt install python3 python3-tk

# Clone
git clone https://github.com/alexoutest2000-del/civitai-extractor.git
cd civitai-extractor
```

## API Key

Place your Civitai API key in `~/.api_key_civitai` (a single line of text). The GUI also lets you browse and select any location.

The key is loaded at runtime and never committed to git.

## Usage

### GUI (recommended)

```bash
./run.sh
```

- Paste a civitai.red model URL (Ctrl+V)
- Select download folder
- Click **Download**

### CLI

```bash
python3 extractor.py "https://civitai.red/models/2641591/evelynn-league-of-legends"
```

## Output

```
/home/bot/civitai-download/
├── Evelynn_LOL.safetensors    # 325MB model file
└── Evelynn_LOL.txt            # 16 trigger word lines
```

Each `.txt` contains one keyword block per line — trained words first, then unique description blocks.

## How it works

Civitai serves model metadata in a `<script id="__NEXT_DATA__">` JSON blob on each page. The extractor:

1. Fetches the page HTML
2. Parses `__NEXT_DATA__` → `trpcState` → model data
3. Extracts `trainedWords` from all model versions
4. Scans the description for unique comma-separated keyword blocks
5. Deduplicates (skips blocks that are subsets of trained words)
6. Downloads the `.safetensors` via `civitai.red/api/download/models/{id}?token={key}`

## Files

| File | Purpose |
|------|---------|
| `extractor.py` | Core — page parsing, keyword extraction, file download |
| `gui.py` | Tkinter GUI with paste shortcut and progress display |
| `run.sh` | Launcher script |

## Security

- API key stored outside repo (`/home/bot/projects/.api_key_civitai`, `chmod 600`)
- No hardcoded credentials in source
- Stdlib-only dependencies (no supply chain risk)
- Reviewed per `security-analyst` checklist — [PASS]
