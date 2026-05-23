# Civitai Data Extractor v2

Desktop GUI tool to download AI models and extract trigger words from [civitai.red](https://civitai.red).

## What it does

- **Paste & auto-download** — paste a URL (or copy to clipboard), and the download starts immediately
- **Progress tracking** — real-time progress bar with MB downloaded
- **Image preview** — shows the first gallery image from the model page
- **Trigger word extraction** — combines `trainedWords` with unique description keywords → `{filename}.txt`
- **Type detection** — identifies LORA, Checkpoint, etc., and the base model (Illustrious, Pony, SDXL…)
- **Organized saving** — right-click any download to move it into a structured folder tree

## Folder Structure

Create this tree under any root folder (configurable in the GUI):

```
{root}/data/
├── lora/
│   ├── illustrious/
│   │   ├── folder1/
│   │   ├── folder2/
│   │   └── folder3/
│   └── pony/
│       ├── folder4/
│       └── folder5/
├── checkpoint/
│   ├── sdxl/
│   │   └── models/
│   └── flux/
│       └── dev/
└── ...
```

Right-click a download → matching subfolders appear based on the file's type + base model.

## Dependencies

| Dependency | Version | Purpose | Install |
|------------|---------|---------|---------|
| Python | 3.11+ | Runtime | `sudo apt install python3` |
| Tkinter | — | GUI toolkit | `sudo apt install python3-tk` |
| Pillow | 9.0+ | Image preview thumbnails | `sudo apt install python3-pillow` |
| stdlib (`json`, `re`, `urllib`, `html`, `pathlib`, `tempfile`, `shutil`) | built-in | Core logic | None (bundled) |

Only `python3-tk` and `python3-pillow` need installing — everything else is standard library.

## Setup

```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt install python3 python3-tk python3-pillow

# Clone
git clone https://github.com/alexoutest2000-del/civitai-extractor.git
cd civitai-extractor
```

## API Key

Place your Civitai API key in `~/.api_key_civitai` (a single line of text). The GUI also lets you browse and select any location.

## Usage

### GUI (recommended)

```bash
./run.sh
```

1. Load your API key (Browse → Load, or auto-detected from `~/.api_key_civitai`)
2. Set the **Data Root** folder (where your `data/` tree lives)
3. Paste a civitai.red URL → auto-downloads to temp
4. Right-click the completed download → choose destination folder
5. Click **View Keywords** to see extracted trigger words

### CLI

```bash
python3 extractor.py "https://civitai.red/models/2641591/evelynn-league-of-legends"
```

## Output

Each download produces:
- `{filename}.safetensors` — the model file (temp until moved)
- `{filename}.txt` — one trigger word block per line

## Files

| File | Purpose |
|------|---------|
| `extractor.py` | Core — page parsing, keyword extraction, file download with progress |
| `gui.py` | Tkinter GUI — clipboard watch, progress bars, image preview, folder tree |
| `run.sh` | Launcher script |

## Security

- API key stored outside repo, loaded at runtime
- No hardcoded credentials in source
- Minimal dependencies (stdlib + tk + pillow)
