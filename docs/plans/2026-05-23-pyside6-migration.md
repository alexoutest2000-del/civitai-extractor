# PySide6 Migration Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Replace Tkinter GUI with PySide6/Qt6 for a modern, native-looking interface. Extractor logic reused as-is.

**Architecture:** QMainWindow with QSplitter layout — download queue (left), preview + folder tree (right). QThread workers for downloads with signal-based progress. QSS stylesheets for theming.

**Tech Stack:** PySide6 6.11, Qt 6.11, Python 3.14, Pillow, urllib

**Files to create:** `gui_qt.py` (~400 lines estimate)
**Files to keep:** `extractor.py` (unchanged)
**Files to delete:** `gui.py` (after migration verified)

---

## Design Decisions

| Decision | Choice | Why |
|---|---|---|
| Window layout | QSplitter with 3 panels | Resizable queue list, image preview, folder browser |
| Download threading | QThread + signals | Qt-native, no threading module, proper progress emission |
| Progress updates | Qt signals (thread-safe) | `downloaded.connect(int)` emitted from worker thread |
| Folder navigation | QTreeView + QFileSystemModel | Native folder browser, replaces right-click menus |
| Image preview | QLabel + QPixmap | Native image rendering, scales automatically |
| Theming | QSS stylesheets (Dark/Light) | CSS-like, more powerful than Tkinter color dicts |
| Context menus | QMenu | Native OS menus |
| Status bar | QStatusBar | Built-in, auto-positioned |
| Temp dir | Same: `~/.cache/civitai-temp/` | No change |
| API key | Same: `~/.api_key_civitai` | No change |

---

## Tasks

### Task 1: Create gui_qt.py skeleton — window, layouts, placeholder panels

**Objective:** Window appears with 3-panel QSplitter layout.

**Files:** Create `gui_qt.py`

**Step 1:** Write skeleton

```python
#!/usr/bin/env python3
"""Civitai Data Extractor — PySide6 GUI."""
import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QSplitter, QWidget,
    QVBoxLayout, QLabel, QStatusBar
)
from PySide6.QtCore import Qt

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Civitai Data Extractor")
        self.resize(900, 600)
        self._setup_ui()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Horizontal)

        # Left: download queue
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Downloads"))
        splitter.addWidget(left)

        # Right: preview + folder tree
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Preview / Folders"))
        splitter.addWidget(right)

        splitter.setSizes([500, 400])
        root.addWidget(splitter)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
```

**Step 2:** Run to verify window appears
```bash
cd /home/bot/projects/civitai-extractor && .venv/bin/python gui_qt.py
```

**Step 3:** Commit
```bash
git add gui_qt.py && git commit -m "feat(qt): skeleton window with splitter layout"
```

---

### Task 2: Add top toolbar — URL input, API key, base folder

**Objective:** Add QLineEdit for URL, QPushButtons for key/folder, labels.

**Files:** Modify `gui_qt.py`

**Step 1:** Add toolbar widgets in `_setup_ui`

```python
# Above splitter:
# API Key row
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QFileDialog

key_layout = QHBoxLayout()
key_layout.addWidget(QLabel("API Key:"))
self.key_path = QLineEdit()
self.key_path.setPlaceholderText("~/.api_key_civitai")
key_layout.addWidget(self.key_path)
browse_key = QPushButton("Browse")
browse_key.clicked.connect(self._browse_key)
key_layout.addWidget(browse_key)
load_key = QPushButton("Load")
load_key.clicked.connect(self._load_key)
key_layout.addWidget(load_key)
self.key_status = QLabel("No key")
self.key_status.setStyleSheet("color: #e44;")
key_layout.addWidget(self.key_status)
root.insertLayout(0, key_layout)

# URL row
url_layout = QHBoxLayout()
url_layout.addWidget(QLabel("Model URL:"))
self.url_input = QLineEdit()
self.url_input.setPlaceholderText("Paste civitai URL and press Enter...")
self.url_input.returnPressed.connect(self._start_download)
url_layout.addWidget(self.url_input)
root.insertLayout(1, url_layout)

# Base folder row
folder_layout = QHBoxLayout()
folder_layout.addWidget(QLabel("Base Folder:"))
self.base_folder = QLineEdit(str(Path.home() / "civitai-data"))
folder_layout.addWidget(self.base_folder)
browse_root = QPushButton("Browse")
browse_root.clicked.connect(self._browse_root)
folder_layout.addWidget(browse_root)
refresh = QPushButton("↻ Refresh")
refresh.clicked.connect(self._scan_folders)
folder_layout.addWidget(refresh)
root.insertLayout(2, folder_layout)
```

**Step 2:** Add stub methods, then verify the UI compiles
```bash
.venv/bin/python -c "import py_compile; py_compile.compile('gui_qt.py', doraise=True)"
```

**Step 3:** Commit
```bash
git add gui_qt.py && git commit -m "feat(qt): toolbar with URL, API key, base folder inputs"
```

---

### Task 3: Download worker thread — QThread with progress signals

**Objective:** Create `DownloadWorker(QThread)` that wraps CivitaiExtractor and emits progress signals.

**Files:** Modify `gui_qt.py`

**Step 1:** Add worker class

```python
from PySide6.QtCore import QThread, Signal
from extractor import CivitaiExtractor

class DownloadWorker(QThread):
    """Runs extractor pipeline in a background thread."""
    progress = Signal(int, int)               # downloaded, total
    metadata = Signal(dict)                    # model_name, file_type, base_model
    finished_ok = Signal(dict)                 # full result dict
    finished_err = Signal(str)                 # error message
    preview_url = Signal(str)                  # first_image URL

    def __init__(self, url: str, api_key: str, temp_dir: str):
        super().__init__()
        self.url = url
        self.api_key = api_key
        self.temp_dir = temp_dir

    def run(self):
        try:
            ext = CivitaiExtractor(api_key=self.api_key, download_dir=self.temp_dir)
            html = ext.fetch_page(self.url)
            model_data = ext.parse_model_data(html)
            file_info = ext.get_file_info(model_data)
            first_image = ext.get_first_image(html)

            if not file_info:
                raise ValueError("No downloadable file found")

            self.metadata.emit({
                "model_name": model_data.get("name", "Unknown"),
                "file_name": file_info["name"],
                "file_type": file_info["type"],
                "base_model": file_info["base_model"],
            })

            if first_image:
                self.preview_url.emit(first_image)

            def on_progress(dl, total):
                self.progress.emit(dl, total)

            dest = ext.download_file(model_data, file_info, on_progress)
            txt_path = ext.save_keywords(model_data, file_info)
            keywords = ext.extract_keywords(model_data)

            self.finished_ok.emit({
                "model_name": model_data.get("name", "Unknown"),
                "file": str(dest),
                "file_name": file_info["name"],
                "file_type": file_info["type"],
                "base_model": file_info["base_model"],
                "size_kb": file_info["size_kb"],
                "keywords_file": str(txt_path),
                "keyword_count": len(keywords),
                "keywords": keywords,
                "first_image": first_image,
            })
        except Exception as e:
            self.finished_err.emit(str(e))
```

**Step 2:** Verify compiles
```bash
.venv/bin/python -c "from gui_qt import DownloadWorker; print('OK')"
```

**Step 3:** Commit

---

### Task 4: Download queue widget — QListWidget with progress bars

**Objective:** Each download appears as a custom widget row in a scrollable list, with progress bar, name, type, status, and actions (preview click, keywords, save, kill).

**Files:** Modify `gui_qt.py`

**Step 1:** Add `DownloadEntryWidget(QWidget)` class

```python
from PySide6.QtWidgets import QProgressBar, QListWidget, QListWidgetItem, QMenu

class DownloadEntryWidget(QWidget):
    """One row in the download queue."""
    kill_requested = Signal(object)   # self
    menu_requested = Signal(object)   # self

    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self.result = None
        self.first_image = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Top row: name + type + kill button
        top = QHBoxLayout()
        self.name_label = QLabel("Queued...")
        self.name_label.setStyleSheet("font-weight: bold;")
        top.addWidget(self.name_label)
        top.addStretch()
        self.type_label = QLabel("")
        self.type_label.setStyleSheet("color: #888; font-size: 11px;")
        top.addWidget(self.type_label)
        kill_btn = QPushButton("✕")
        kill_btn.setFixedSize(22, 22)
        kill_btn.setStyleSheet("border: none; color: #888;")
        kill_btn.clicked.connect(lambda: self.kill_requested.emit(self))
        top.addWidget(kill_btn)
        layout.addLayout(top)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        layout.addWidget(self.progress)

        # Status label
        self.status_label = QLabel("Waiting...")
        self.status_label.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(self.status_label)
```

This goes inside the queue list. Each item is added as:
```python
item = QListWidgetItem()
widget = DownloadEntryWidget(url)
self.queue_list.addItem(item)
self.queue_list.setItemWidget(item, widget)
item.setSizeHint(widget.sizeHint())
```

**Step 2:** Compile check + commit

---

### Task 5: Wire download flow — URL paste → worker → queue entry → progress

**Objective:** Hooking `_start_download` to create worker, create queue entry, connect signals.

**Files:** Modify `gui_qt.py`

**Step 1:** Add `_start_download`, `_on_metadata`, `_on_progress`, `_on_finished`, `_on_error` methods to `MainWindow`.

Key wiring:
```python
def _start_download(self):
    url = self.url_input.text().strip()
    if not url or "civitai" not in url:
        return
    self.url_input.clear()

    entry = DownloadEntryWidget(url)
    item = QListWidgetItem()
    self.queue_list.insertItem(0, item)
    self.queue_list.setItemWidget(item, entry)
    item.setSizeHint(entry.sizeHint())
    entry.kill_requested.connect(self._kill_entry)
    entry.menu_requested.connect(self._show_context_menu)
    # Also connect left-click for preview
    entry.mousePressEvent = lambda e, w=entry: self._show_preview(w) if e.button() == Qt.LeftButton else QWidget.mousePressEvent(w, e)

    worker = DownloadWorker(url, self.api_key, str(self.temp_dir))
    worker.metadata.connect(lambda d: self._on_metadata(entry, d))
    worker.progress.connect(lambda dl, tot: self._on_progress(entry, dl, tot))
    worker.preview_url.connect(lambda u: self._on_preview_url(entry, u))
    worker.finished_ok.connect(lambda r: self._on_finished(entry, r))
    worker.finished_err.connect(lambda e: self._on_error(entry, e))
    worker.start()
```

**Step 2:** Compile + commit

---

### Task 6: Image preview panel — QLabel with pixmap scaling

**Objective:** Right panel shows image preview. Click on entry triggers download and display.

**Files:** Modify `gui_qt.py`

**Step 1:** Replace the right placeholder with:

```python
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtCore import QUrl, QByteArray

# In _setup_ui, right panel becomes:
right_panel = QVBoxLayout(right_widget)

# Preview
preview_label = QLabel("Preview")
preview_label.setAlignment(Qt.AlignCenter)
preview_label.setStyleSheet("background: #252525; border-radius: 6px;")
preview_label.setMinimumHeight(200)
right_panel.addWidget(preview_label)
self.preview_label = preview_label

# Folder tree
right_panel.addWidget(QLabel("Folders"))
self.folder_tree = QTreeView()
self.folder_model = QFileSystemModel()
self.folder_model.setRootPath(str(self.data_root))
self.folder_tree.setModel(self.folder_model)
self.folder_tree.setRootIndex(self.folder_model.index(str(self.data_root)))
# Hide size/type columns, show only name
self.folder_tree.setColumnHidden(1, True)
self.folder_tree.setColumnHidden(2, True)
self.folder_tree.setColumnHidden(3, True)
right_panel.addWidget(self.folder_tree)
```

**Step 2:** Add `_show_preview(url)` method — downloads image with QNetworkAccessManager (async, non-blocking):

```python
def _show_preview(self, url: str):
    self._nam = QNetworkAccessManager()
    req = QNetworkRequest(QUrl(url))
    req.setRawHeader(b"User-Agent", b"Mozilla/5.0")
    reply = self._nam.get(req)
    reply.finished.connect(lambda: self._on_preview_loaded(reply))

def _on_preview_loaded(self, reply):
    data = reply.readAll()
    pix = QPixmap()
    pix.loadFromData(data)
    pix = pix.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    self.preview_label.setPixmap(pix)
```

**Step 3:** Compile + commit

---

### Task 7: Folder browser + save-to action

**Objective:** Replace right-click menu with sidebar folder tree. Drag-drop or right-click save from queue into a folder.

**Files:** Modify `gui_qt.py`

**Step 1:** Add `_save_to(entry, dest_path)` method (mirrors `_move_to` from old gui.py)

**Step 2:** Add context menu on folder tree:
```python
self.folder_tree.setContextMenuPolicy(Qt.CustomContextMenu)
self.folder_tree.customContextMenuRequested.connect(self._folder_context_menu)
```

When right-clicking a folder, show "Save selected here" action.

**Step 3:** Also keep right-click context menu on queue entries for "Save To…", "View Keywords", "Remove & Purge".

**Step 4:** Commit

---

### Task 8: Dark theme QSS stylesheet

**Objective:** Apply a polished dark theme.

**Files:** Create `theme.qss`, load in `MainWindow`

**Step 1:** Create dark theme stylesheet:

```css
QMainWindow, QWidget { background: #1e1e1e; color: #d4d4d4; font-family: "Sans"; }
QLineEdit { background: #333; border: 1px solid #555; border-radius: 4px; padding: 6px; }
QPushButton { background: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 6px 14px; }
QPushButton:hover { background: #4a4a4a; }
QPushButton:pressed { background: #2a2a2a; }
QProgressBar { background: #333; border: none; border-radius: 4px; text-align: center; }
QProgressBar::chunk { background: #4a4; border-radius: 4px; }
QSplitter::handle { background: #444; width: 2px; }
QListWidget { background: #252525; border: 1px solid #444; border-radius: 4px; }
QTreeView { background: #252525; border: 1px solid #444; }
QStatusBar { background: #333; color: #888; }
QMenu { background: #333; border: 1px solid #555; }
QMenu::item:selected { background: #4a4; }
```

**Step 2:** Load it:
```python
style_sheet = (Path(__file__).parent / "theme.qss").read_text()
app.setStyleSheet(style_sheet)
```

**Step 3:** Commit

---

### Task 9: Final integration — add __main__ entry point, test end-to-end

**Objective:** Full download flow works: paste URL → download appears in queue → progress updates → preview shows → save to folder.

**Files:** Modify `gui_qt.py`

**Step 1:** Make `gui_qt.py` the canonical entry point.
**Step 2:** Test end-to-end with a real civitai URL.
**Step 3:** Commit

---

### Task 10: Update README, remove old gui.py

**Objective:** Documentation updated, old Tkinter file archived.

**Step 1:** Update README.md to reflect PySide6 stack.
**Step 2:** Archive old `gui.py` → `gui_tk.py.bak` or delete.
**Step 3:** Final commit + push.

---

## Verification Checklist

- [ ] Window opens with splitter layout
- [ ] API key loads from `~/.api_key_civitai`
- [ ] Paste URL + Enter starts download
- [ ] Progress bar updates in real time
- [ ] Preview image appears on left-click of entry
- [ ] Folder tree shows `~/civitai-data/` structure
- [ ] Right-click on folder saves file
- [ ] "✕" button kills download + purges temp files
- [ ] Error handling shows message in status bar
- [ ] Dark theme applies consistently
