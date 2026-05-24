# Civitai Data Extractor v3

Desktop GUI tool to download AI models and extract trigger words from [civitai.red](https://civitai.red).

## What it does

- **Paste & download** — paste a URL and press Enter, download starts immediately
- **Progress tracking** — real-time progress bar with MB downloaded
- **Image preview** — left-click any download entry to see the model's first gallery image
- **Preview saved** — preview image auto-saved as `{filename}.preview.png` alongside the model file
- **Trigger word extraction** — combines `trainedWords` with unique description keywords → `{filename}.txt`
- **Type detection** — identifies LORA, Checkpoint, etc., and the base model (Illustrious, Pony, SDXL…)
- **Organized saving** — right-click a download → choose destination folder, or use the folder browser sidebar
- **Kill & purge** — ✕ button on any entry removes it and deletes all temp files

## Folder structure

```
{root}/
├── lora/
│   ├── illustrious/
│   │   ├── folder1/
│   │   └── folder2/
│   └── pony/
│       └── folder3/
├── checkpoint/    ← no base_model layer for checkpoints
│   ├── models/
│   └── dev/
└── ...
```

## Dependencies

| Dependency | Version | Purpose | Install |
|------------|---------|---------|---------|
| Python | 3.11+ | Runtime | `sudo apt install python3` |
| PySide6 | 6.11+ | Qt GUI toolkit | `pip install pyside6` |
| Pillow | 9.0+ | Image preview (fallback) | `sudo apt install python3-pillow` |
| libegl1 | any | Qt OpenGL support | `sudo apt install libegl1` |
| libxcb-cursor0 | any | Qt X11 cursor support | `sudo apt install libxcb-cursor0` |

All other deps are Python stdlib: `json`, `re`, `urllib`, `html`, `pathlib`, `tempfile`, `shutil`, `threading`.

## Setup

```bash
# System deps (Ubuntu/Debian)
sudo apt install python3 python3-pip libegl1 libxcb-cursor0

# Clone
git clone https://github.com/alexoutest2000-del/civitai-extractor.git
cd civitai-extractor

# Create venv + install PySide6
python3 -m venv .venv
.venv/bin/pip install pyside6
```

## API Key

Place your Civitai API key in `~/.api_key_civitai` (single line of text).  
The GUI auto-detects it and lets you browse for an alternative location.

## Usage

### GUI (recommended)

```bash
.venv/bin/python gui_qt.py
```

1. API key loads automatically from `~/.api_key_civitai`
2. Set the **Base Folder** (where your folder tree lives, default: `~/civitai-data`)
3. Paste a civitai.red URL in the **Model URL** field and press **Enter**
4. Download appears in the queue with live progress
5. **Left-click** the entry to preview the model image
6. **Right-click** the entry → save to folder, or **right-click a folder** in the sidebar → "Save here"
7. Click **✕** to kill any download and purge its temp files
8. Click **Keywords** to see extracted trigger words

### CLI

```bash
.venv/bin/python extractor.py "https://civitai.red/models/2641591"
```

## Architecture

- `extractor.py` — pure backend: page fetch, `__NEXT_DATA__` JSON parsing, deduplication, file download with progress
- `gui_qt.py` — PySide6/Qt6 frontend: QThread workers emit signals for thread-safe progress, QSS dark theme, QTreeView folder browser
- Temp downloads go to `~/.cache/civitai-temp/` (auto-purged on save or kill)
- API key read from `~/.api_key_civitai` at startup (never tracked in git)

## Security

- API key stored outside repo (`~/.api_key_civitai`), loaded at runtime
- `.gitignore` covers `.venv/`, `__pycache__/`, `.api_key_*`, `.env`
- No hardcoded credentials in source
- Network requests use explicit User-Agent header
