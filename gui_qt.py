#!/usr/bin/env python3
"""
Civitai Data Extractor — PySide6 GUI.
Replaces the Tkinter version with a modern Qt6 interface.
"""
import sys
import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QDir
from PySide6.QtGui import QPixmap, QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter,
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QProgressBar, QListWidget, QListWidgetItem, QTreeView,
    QFileSystemModel, QFileDialog, QMenu, QStatusBar, QMessageBox,
    QSizePolicy, QStyleFactory,
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest

from extractor import CivitaiExtractor

# ─── QSS THEME ──────────────────────────────────────────

QSS_DARK = """
QMainWindow, QWidget {
    background: #1e1e1e;
    color: #d4d4d4;
    font-family: "Sans", "Noto Sans", sans-serif;
    font-size: 13px;
}
QLineEdit {
    background: #333;
    border: 1px solid #555;
    border-radius: 5px;
    padding: 6px 10px;
    color: #d4d4d4;
}
QLineEdit:focus {
    border-color: #4a4;
}
QPushButton {
    background: #3a3a3a;
    border: 1px solid #555;
    border-radius: 5px;
    padding: 6px 16px;
    color: #d4d4d4;
}
QPushButton:hover { background: #4a4a4a; }
QPushButton:pressed { background: #2a2a2a; }
QPushButton:disabled {
    color: #555;
    background: #2a2a2a;
    border-color: #3a3a3a;
}
QProgressBar {
    background: #333;
    border: none;
    border-radius: 4px;
    text-align: center;
    height: 22px;
    font-size: 10px;
}
QProgressBar::chunk {
    background: #4a4;
    border-radius: 4px;
}
QSplitter::handle {
    background: #444;
    width: 2px;
    margin: 0 2px;
}
QListWidget {
    background: #252525;
    border: 1px solid #444;
    border-radius: 6px;
    padding: 4px;
    outline: none;
}
QListWidget::item {
    background: transparent;
    border: none;
    margin: 3px 0;
    padding: 2px;
}
QListWidget::item:selected {
    background: transparent;
}
QTreeView {
    background: #252525;
    border: 1px solid #444;
    border-radius: 6px;
    alternate-background-color: #2a2a2a;
}
QTreeView::item:hover {
    background: #3a3a3a;
}
QStatusBar {
    background: #333;
    color: #888;
    border-top: 1px solid #444;
}
QMenu {
    background: #333;
    border: 1px solid #555;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px;
    border-radius: 3px;
}
QMenu::item:selected {
    background: #4a4;
    color: #fff;
}
QMenu::separator {
    height: 1px;
    background: #555;
    margin: 4px 8px;
}
QLabel#preview_label {
    background: #252525;
    border: 1px solid #444;
    border-radius: 6px;
    color: #666;
}
QLabel#section_header {
    color: #888;
    font-size: 11px;
    font-weight: bold;
    text-transform: uppercase;
    padding: 4px 0;
}
"""

# ─── URL LINE EDIT (paste detection) ─────────────────────

class UrlLineEdit(QLineEdit):
    """QLineEdit that auto-triggers download when a URL is pasted."""
    url_pasted = Signal()

    def paste(self):
        """Right-click → Paste / Shift+Insert."""
        super().paste()
        self.url_pasted.emit()

    def keyPressEvent(self, event):
        """Catch Ctrl+V which bypasses paste() in PySide6."""
        is_paste = (
            (event.key() == Qt.Key_V and event.modifiers() == Qt.ControlModifier) or
            (event.key() == Qt.Key_Insert and event.modifiers() == Qt.ShiftModifier)
        )
        super().keyPressEvent(event)
        if is_paste:
            self.url_pasted.emit()


# ─── DOWNLOAD WORKER ────────────────────────────────────


class DownloadWorker(QThread):
    """Runs CivitaiExtractor pipeline in a background thread."""
    progress = Signal(float)     # percentage 0-100 (float to avoid 32-bit overflow)
    metadata = Signal(dict)
    done = Signal(dict)
    error = Signal(str)
    preview_url = Signal(str)

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
            first_image = ext.get_first_image(html, model_data)

            if not file_info:
                raise ValueError("No downloadable file found on this page")

            self.metadata.emit({
                "model_name": model_data.get("name", "Unknown"),
                "file_name": file_info["name"],
                "file_type": file_info["type"],
                "base_model": file_info["base_model"],
            })

            if first_image:
                self.preview_url.emit(first_image)

            def on_progress(downloaded, total):
                if total:
                    self.progress.emit(downloaded / total * 100.0)

            dest = ext.download_file(model_data, file_info, on_progress)
            txt_path = ext.save_keywords(model_data, file_info)
            keywords = ext.extract_keywords(model_data)

            # Save preview image
            preview_path = None
            if first_image:
                preview_path = ext.save_preview_image(first_image, file_info)

            self.done.emit({
                "model_name": model_data.get("name", "Unknown"),
                "url": self.url,
                "file": str(dest),
                "file_name": file_info["name"],
                "file_type": file_info["type"],
                "base_model": file_info["base_model"],
                "size_kb": file_info["size_kb"],
                "keywords_file": str(txt_path),
                "keyword_count": len(keywords),
                "keywords": keywords,
                "first_image": first_image,
                "preview_path": str(preview_path) if preview_path else None,
            })
        except Exception as e:
            self.error.emit(str(e))


# ─── DOWNLOAD ENTRY WIDGET ──────────────────────────────


class DownloadEntryWidget(QWidget):
    """One download row in the queue list."""
    killed = Signal(object)
    preview_clicked = Signal(object)
    menu_requested = Signal(object)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url
        self.result = None
        self.first_image_url = None
        self.setCursor(Qt.PointingHandCursor)
        self._build()

    def _build(self):
        # Outer frame for visible border
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._card = QWidget()
        self._card.setStyleSheet("""
            QWidget {
                background: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 5px;
            }
        """)
        self._card_normal_ss = self._card.styleSheet()
        outer.addWidget(self._card)

        layout = QVBoxLayout(self._card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # Top row: name + type + kill
        top = QHBoxLayout()
        top.setSpacing(8)

        self.name_label = QLabel("Queued...")
        self.name_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.name_label.setMinimumWidth(120)
        top.addWidget(self.name_label)

        top.addStretch()

        self.type_label = QLabel("")
        self.type_label.setStyleSheet("color: #888; font-size: 11px;")
        top.addWidget(self.type_label)

        kill_btn = QPushButton("✕")
        kill_btn.setFixedSize(24, 24)
        kill_btn.setStyleSheet(
            "QPushButton { border: none; color: #888; font-size: 14px; padding: 0; }"
            "QPushButton:hover { color: #e44; background: #3a2020; border-radius: 3px; }"
        )
        kill_btn.clicked.connect(lambda: self.killed.emit(self))
        kill_btn.setCursor(Qt.ArrowCursor)
        top.addWidget(kill_btn)

        layout.addLayout(top)

        # Spacer before progress bar
        spacer = QWidget()
        spacer.setFixedHeight(2)
        layout.addWidget(spacer)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("Waiting...")
        layout.addWidget(self.progress)

        # Actions row (always visible — buttons enabled only when done)
        self.actions_row = QHBoxLayout()
        self.actions_row.setSpacing(8)

        self.kw_btn = QPushButton("Keywords")
        self.kw_btn.setMinimumHeight(30)
        self.kw_btn.setStyleSheet("font-size: 12px; padding: 5px 16px;")
        self.kw_btn.clicked.connect(self._view_keywords)
        self.kw_btn.setCursor(Qt.ArrowCursor)
        self.kw_btn.setEnabled(False)
        self.actions_row.addWidget(self.kw_btn)

        self.save_btn = QPushButton("Save To…")
        self.save_btn.setMinimumHeight(30)
        self.save_btn.setStyleSheet("font-size: 12px; padding: 5px 16px;")
        self.save_btn.clicked.connect(lambda: self.menu_requested.emit(self))
        self.save_btn.setCursor(Qt.ArrowCursor)
        self.save_btn.setEnabled(False)
        self.actions_row.addWidget(self.save_btn)

        self.actions_row.addStretch()
        self.actions_widget = QWidget()
        self.actions_widget.setLayout(self.actions_row)
        layout.addWidget(self.actions_widget)

    def set_highlighted(self, on: bool):
        """Toggle light-yellow left-edge accent on the card."""
        if on:
            self._card.setStyleSheet("""
                QWidget {
                    background: #2a2a2a;
                    border: 1px solid #3a3a3a;
                    border-left: 3px solid #e8d44d;
                    border-radius: 5px;
                }
            """)
        else:
            self._card.setStyleSheet(self._card_normal_ss)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.preview_clicked.emit(self)
        elif event.button() == Qt.RightButton:
            self.menu_requested.emit(self)
        super().mousePressEvent(event)

    def _view_keywords(self):
        if not self.result:
            return
        from PySide6.QtWidgets import QDialog, QTextEdit
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Keywords — {self.result['model_name']}")
        dlg.resize(500, 400)
        dlg.setStyleSheet("background: #1e1e1e;")
        txt = QTextEdit(dlg)
        txt.setReadOnly(True)
        txt.setStyleSheet("font-family: monospace; font-size: 11px; color: #d4d4d4; background: #252525; border: none;")
        txt.setPlainText("\n".join(self.result.get("keywords", [])))
        layout = QVBoxLayout(dlg)
        layout.addWidget(txt)
        dlg.exec()


# ─── MAIN WINDOW ────────────────────────────────────────


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Civitai Data Extractor")
        self.resize(950, 650)

        # State
        self.api_key = None
        self._workers: list[DownloadWorker] = []
        self._entries: list[DownloadEntryWidget] = []
        self._active_entry: DownloadEntryWidget | None = None
        self._nam = QNetworkAccessManager()
        self._preview_replies: list = []  # prevent GC

        # Config persistence
        self._config_path = Path.home() / ".config" / "civitai-extractor"
        self._config_path.mkdir(parents=True, exist_ok=True)
        self._config_file = self._config_path / "settings.json"
        self._config = self._load_config()

        # Paths
        self.temp_dir = Path.home() / ".cache" / "civitai-temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.data_root = Path(self._config.get("data_root", Path.home() / "civitai-data"))
        self.data_root.mkdir(parents=True, exist_ok=True)
        self._saved_key_path = self._config.get("key_path", "")

        self._setup_ui()
        self._try_load_api_key()
        self._scan_folders()

    # ─── CONFIG PERSISTENCE ────────────────────────────

    def _load_config(self) -> dict:
        """Load saved preferences from settings.json."""
        if self._config_file.is_file():
            try:
                import json
                return json.loads(self._config_file.read_text())
            except Exception:
                pass
        return {}

    def _save_config(self):
        """Persist current preferences."""
        import json
        cfg = {
            "data_root": str(self.data_root),
            "key_path": self.key_path_input.text().strip(),
        }
        self._config_file.write_text(json.dumps(cfg, indent=2))

    # ─── UI SETUP ──────────────────────────────────────

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self._build_toolbar(root)
        self._build_splitter(root)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def _build_toolbar(self, root):
        # API Key row
        key_row = QHBoxLayout()
        key_row.setSpacing(6)
        key_row.addWidget(QLabel("API Key:"))
        self.key_path_input = QLineEdit()
        self.key_path_input.setPlaceholderText("~/.api_key_civitai")
        self.key_path_input.setMaximumWidth(300)
        key_row.addWidget(self.key_path_input)
        btn = QPushButton("Browse")
        btn.clicked.connect(self._browse_key)
        key_row.addWidget(btn)
        btn = QPushButton("Load")
        btn.clicked.connect(self._load_key)
        key_row.addWidget(btn)
        self.key_status = QLabel("No key")
        self.key_status.setStyleSheet("color: #e44; padding-left: 6px;")
        key_row.addWidget(self.key_status)
        key_row.addStretch()
        root.addLayout(key_row)

        # URL row
        url_row = QHBoxLayout()
        url_row.setSpacing(6)
        url_row.addWidget(QLabel("Model URL:"))
        self.url_input = UrlLineEdit()
        self.url_input.setPlaceholderText("Paste civitai URL…")
        self.url_input.returnPressed.connect(self._start_download)
        self.url_input.url_pasted.connect(self._on_url_pasted)
        url_row.addWidget(self.url_input)
        root.addLayout(url_row)

        # Base folder row
        folder_row = QHBoxLayout()
        folder_row.setSpacing(6)
        folder_row.addWidget(QLabel("Base Folder:"))
        self.base_folder_input = QLineEdit(str(self.data_root))
        folder_row.addWidget(self.base_folder_input)
        btn = QPushButton("Browse")
        btn.clicked.connect(self._browse_root)
        folder_row.addWidget(btn)
        btn = QPushButton("↻ Refresh")
        btn.clicked.connect(self._scan_folders)
        folder_row.addWidget(btn)
        folder_row.addStretch()
        root.addLayout(folder_row)

    def _build_splitter(self, root):
        splitter = QSplitter(Qt.Horizontal)

        # ── Left: download queue ──
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        hdr = QLabel("DOWNLOADS")
        hdr.setObjectName("section_header")
        left_layout.addWidget(hdr)

        self.queue_list = QListWidget()
        self.queue_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.queue_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.queue_list.customContextMenuRequested.connect(self._queue_context_menu)
        left_layout.addWidget(self.queue_list)
        splitter.addWidget(left)

        # ── Right: preview + folder tree ──
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        hdr = QLabel("PREVIEW")
        hdr.setObjectName("section_header")
        right_layout.addWidget(hdr)

        self.preview_title = QLabel("")
        self.preview_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #d4d4d4; padding: 2px 0;")
        self.preview_title.setWordWrap(True)
        self.preview_title.hide()
        right_layout.addWidget(self.preview_title)

        self.preview_label = QLabel()
        self.preview_label.setObjectName("preview_label")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(200)
        self.preview_label.setText("No preview")
        right_layout.addWidget(self.preview_label)

        hdr = QLabel("FOLDERS")
        hdr.setObjectName("section_header")
        right_layout.addWidget(hdr)

        self.folder_tree = QTreeView()
        self.folder_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.folder_tree.customContextMenuRequested.connect(self._folder_context_menu)
        self.folder_model = QFileSystemModel()
        self.folder_model.setRootPath(str(self.data_root))
        self.folder_model.setFilter(QDir.Filter.Dirs | QDir.Filter.NoDotAndDotDot)
        self.folder_tree.setModel(self.folder_model)
        root_idx = self.folder_model.index(str(self.data_root))
        self.folder_tree.setRootIndex(root_idx)
        for col in (1, 2, 3):
            self.folder_tree.setColumnHidden(col, True)
        right_layout.addWidget(self.folder_tree)

        splitter.addWidget(right)
        splitter.setSizes([550, 400])
        root.addWidget(splitter)

    # ─── API KEY ───────────────────────────────────────

    def _browse_key(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select API Key File")
        if path:
            self.key_path_input.setText(path)
            self._save_config()

    def _load_key(self):
        p = Path(self.key_path_input.text().strip())
        if not p.is_file():
            QMessageBox.critical(self, "Error", f"Not found: {p}")
            return
        self.api_key = p.read_text().strip()
        self.key_status.setText("✓ Loaded")
        self.key_status.setStyleSheet("color: #4a4; padding-left: 6px;")
        self._save_config()
        self.status_bar.showMessage(f"API key loaded from {p.name}")

    def _try_load_api_key(self):
        for p in [Path(self._saved_key_path) if self._saved_key_path else None,
                  Path.home() / ".api_key_civitai",
                  Path("/home/bot/projects/.api_key_civitai")]:
            if p and p.is_file():
                self.key_path_input.setText(str(p))
                self.api_key = p.read_text().strip()
                self.key_status.setText("✓ Loaded")
                self.key_status.setStyleSheet("color: #4a4; padding-left: 6px;")
                return

    # ─── BASE FOLDER ───────────────────────────────────

    def _browse_root(self):
        d = QFileDialog.getExistingDirectory(self, "Select Base Folder", self.base_folder_input.text())
        if d:
            self.base_folder_input.setText(d)
            self._scan_folders()
            self._save_config()

    def _scan_folders(self):
        self.data_root = Path(self.base_folder_input.text().strip())
        if not self.data_root.is_dir():
            self.status_bar.showMessage(f"Folder not found: {self.data_root}")
            return
        self.folder_model.setRootPath(str(self.data_root))
        self.folder_tree.setRootIndex(self.folder_model.index(str(self.data_root)))
        self.status_bar.showMessage(f"Folder tree: {self.data_root}")

    # ─── DOWNLOAD FLOW ─────────────────────────────────

    def _on_url_pasted(self):
        """Auto-start download after paste (short delay to let text settle)."""
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, self._check_pasted_url)

    def _check_pasted_url(self):
        url = self.url_input.text().strip()
        if url and "civitai" in url:
            self._start_download()

    def _start_download(self):
        url = self.url_input.text().strip()
        if not url or "civitai" not in url:
            return
        if not self.api_key:
            QMessageBox.warning(self, "No API Key", "Load an API key file first.")
            return
        self.url_input.clear()

        entry = DownloadEntryWidget(url)
        entry.preview_clicked.connect(self._on_preview_clicked)
        entry.menu_requested.connect(lambda e: self._show_context_menu(e))
        entry.killed.connect(self._kill_entry)

        item = QListWidgetItem()
        self.queue_list.insertItem(0, item)
        self.queue_list.setItemWidget(item, entry)
        item.setSizeHint(entry.sizeHint())
        self._entries.append(entry)

        worker = DownloadWorker(url, self.api_key, str(self.temp_dir))
        worker.metadata.connect(lambda d: self._on_metadata(entry, d))
        worker.progress.connect(lambda pct: self._on_progress(entry, pct))
        worker.preview_url.connect(lambda u: self._on_preview_url(entry, u))
        worker.done.connect(lambda r: self._on_done(entry, r))
        worker.error.connect(lambda e: self._on_error(entry, e))
        worker.finished.connect(lambda w=worker: self._workers.remove(w) if w in self._workers else None)
        self._workers.append(worker)
        worker.start()

        self.status_bar.showMessage(f"Downloading: {url[:60]}...")

    def _on_metadata(self, entry: DownloadEntryWidget, data: dict):
        entry.name_label.setText(data["model_name"][:80])
        entry.type_label.setText(f"{data['file_name']} · {data['file_type']} · {data['base_model']}")

    def _on_progress(self, entry: DownloadEntryWidget, pct: float):
        entry.progress.setValue(int(pct))
        entry.progress.setFormat(f"{pct:.0f}%")
        entry.progress.repaint()

    def _on_preview_url(self, entry: DownloadEntryWidget, url: str):
        entry.first_image_url = url

    def _on_done(self, entry: DownloadEntryWidget, result: dict):
        entry.result = result
        entry.progress.setValue(100)
        entry.progress.setFormat(f"✓ {result['size_kb']:.0f} KB · {result['keyword_count']} keywords")
        entry.progress.setStyleSheet(
            "QProgressBar { background: #333; } QProgressBar::chunk { background: #4a4; }"
        )
        entry.kw_btn.setEnabled(True)
        entry.save_btn.setEnabled(True)
        self.status_bar.showMessage(
            f"✓ {result['model_name']} ({result['file_type']} | {result['base_model']})"
        )

    def _on_error(self, entry: DownloadEntryWidget, msg: str):
        entry.progress.setFormat(f"✗ {msg}")
        entry.progress.setStyleSheet(
            "QProgressBar { background: #333; } QProgressBar::chunk { background: #e44; }"
        )
        self.status_bar.showMessage(f"✗ Error: {msg}")

    def _on_preview_clicked(self, entry: DownloadEntryWidget):
        if self._active_entry and self._active_entry is not entry:
            self._active_entry.set_highlighted(False)
        self._active_entry = entry
        entry.set_highlighted(True)
        # Set title above preview
        title = (entry.result or {}).get("model_name") or entry.name_label.text()
        if title and title != "Queued...":
            self.preview_title.setText(title)
            self.preview_title.show()
        else:
            self.preview_title.hide()
        img = entry.first_image_url or (entry.result or {}).get("first_image")
        if img:
            self._show_preview(img)

    # ─── PREVIEW ───────────────────────────────────────

    def _show_preview(self, url: str):
        self.preview_label.setText("Loading…")
        # Try Qt's network stack first
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", b"Mozilla/5.0")
        reply = self._nam.get(req)
        reply.finished.connect(self._on_preview_reply)
        self._preview_replies.append(reply)

    def _on_preview_reply(self):
        reply = self.sender()
        err = reply.error()
        if err != reply.NetworkError.NoError:
            # Qt SSL may be missing — fall back to urllib
            url = reply.url().toString()
            self._show_preview_urllib(url)
        else:
            data = reply.readAll()
            self._display_preview_data(data)
        self._preview_replies = [r for r in self._preview_replies if not r.isFinished()]
        reply.deleteLater()

    def _show_preview_urllib(self, url: str):
        """Fallback: download image via urllib (always has SSL)."""
        import urllib.request as ur
        import threading
        def _fetch():
            try:
                req = ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                data = ur.urlopen(req, timeout=15).read()
                self._display_preview_data(data)
            except Exception as e:
                self.preview_label.setText(f"Preview error: {e}")
        threading.Thread(target=_fetch, daemon=True).start()

    def _display_preview_data(self, data):
        from PySide6.QtCore import QByteArray
        pix = QPixmap()
        if isinstance(data, bytes):
            pix.loadFromData(QByteArray(data))
        else:
            pix.loadFromData(data)
        if not pix.isNull():
            pix = pix.scaled(350, 350, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.preview_label.setPixmap(pix)
            self.preview_label.setText("")
        else:
            self.preview_label.setText("Preview failed — bad image data")

    # ─── CONTEXT MENUS ─────────────────────────────────

    def _queue_context_menu(self, pos):
        item = self.queue_list.itemAt(pos)
        if not item:
            return
        entry = self.queue_list.itemWidget(item)
        if not entry:
            return
        self._active_entry = entry
        self._show_context_menu(entry, self.queue_list.viewport().mapToGlobal(pos))

    def _folder_context_menu(self, pos):
        idx = self.folder_tree.indexAt(pos)
        if not idx.isValid():
            return
        dest = Path(self.folder_model.filePath(idx))
        if not dest.is_dir():
            return
        entry = self._active_entry
        if not entry or not entry.result:
            return

        menu = QMenu(self)
        save_action = menu.addAction(f"Save here → {dest.name}")
        save_action.triggered.connect(lambda: self._save_to(entry, dest))
        menu.exec(self.folder_tree.viewport().mapToGlobal(pos))

    def _show_context_menu(self, entry: DownloadEntryWidget, global_pos=None):
        menu = QMenu(self)

        # Copy URL (always available)
        a = menu.addAction("📋 Copy civitai URL")
        a.triggered.connect(lambda: QApplication.clipboard().setText(entry.url))

        if not entry.result:
            menu.addSeparator()
            a = menu.addAction("✕ Remove & Purge")
            a.triggered.connect(lambda: self._kill_entry(entry))
            if global_pos:
                menu.exec(global_pos)
            else:
                menu.exec(menu.pos() if hasattr(menu, 'pos') else self.cursor().pos())
            return

        menu.addSeparator()

        # Destination folders
        ft = entry.result["file_type"].lower()
        bm = entry.result["base_model"].lower()

        if ft in ("checkpoint", "checkpoints"):
            base_path = self.data_root / ft
        else:
            base_path = self.data_root / ft / bm

        if base_path.is_dir():
            action_added = False
            for sub in sorted(base_path.iterdir()):
                if sub.is_dir():
                    a = menu.addAction(f"📁 {sub.name}")
                    a.triggered.connect(lambda checked, d=sub: self._save_to(entry, d))
                    action_added = True
            if not action_added:
                label = f"(no folders under {ft}/)" if ft in ("checkpoint", "checkpoints") else f"(no folders under {ft}/{bm}/)"
                a = menu.addAction(label)
                a.setEnabled(False)

        menu.addSeparator()
        a = menu.addAction("📂 Browse…")
        a.triggered.connect(lambda: self._browse_save(entry))
        a = menu.addAction("View Keywords")
        a.triggered.connect(entry._view_keywords)
        a = menu.addAction("✕ Remove & Purge")
        a.triggered.connect(lambda: self._kill_entry(entry))

        if global_pos:
            menu.exec(global_pos)
        else:
            menu.exec(self.cursor().pos())

    def _browse_save(self, entry: DownloadEntryWidget):
        d = QFileDialog.getExistingDirectory(self, "Save To", str(self.data_root))
        if d:
            self._save_to(entry, Path(d))

    # ─── FILE OPERATIONS ───────────────────────────────

    def _save_to(self, entry: DownloadEntryWidget, dest: Path):
        if not entry.result:
            return
        dest.mkdir(parents=True, exist_ok=True)
        src_file = Path(entry.result["file"])
        src_kw = Path(entry.result["keywords_file"])

        if not src_file.exists():
            QMessageBox.critical(self, "Error", f"Source file missing: {src_file}")
            return

        # Check for existing files in destination
        existing = []
        for src, label in [
            (src_file, "model"),
            (src_kw, "keywords"),
        ]:
            if src.exists() and (dest / src.name).exists():
                existing.append(f"  • {src.name} ({label})")

        preview_path = entry.result.get("preview_path")
        if preview_path:
            pp = Path(preview_path)
            if pp.exists() and (dest / pp.name).exists():
                existing.append(f"  • {pp.name} (preview)")

        if existing:
            msg = "These files already exist:\n" + "\n".join(existing) + "\n\nOverwrite them?"
            reply = QMessageBox.question(
                self, "Overwrite?", msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        shutil.move(str(src_file), str(dest / src_file.name))
        if src_kw.exists():
            shutil.move(str(src_kw), str(dest / src_kw.name))

        # Also move preview image if present
        if preview_path:
            pp = Path(preview_path)
            if pp.exists():
                shutil.move(str(pp), str(dest / pp.name))

        base = src_file.stem
        for leftover in list(self.temp_dir.iterdir()):
            if leftover.is_file() and leftover.stem == base:
                try:
                    leftover.unlink()
                except OSError:
                    pass

        self.status_bar.showMessage(f"✓ Saved → {dest}")
        self._kill_entry(entry)

    def _kill_entry(self, entry: DownloadEntryWidget):
        """Remove entry from UI and purge its temp files."""
        if self._active_entry is entry:
            self._active_entry = None
        if entry.result:
            for key in ("file", "keywords_file", "preview_path"):
                fp = entry.result.get(key)
                if fp and Path(fp).exists():
                    try:
                        Path(fp).unlink()
                    except OSError:
                        pass
            src_file = Path(entry.result["file"])
            base = src_file.stem
            for leftover in list(self.temp_dir.iterdir()):
                if leftover.is_file() and leftover.stem in (base, f"{base}.preview"):
                    try:
                        leftover.unlink()
                    except OSError:
                        pass

        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            w = self.queue_list.itemWidget(item)
            if w is entry:
                self.queue_list.takeItem(i)
                break

        if entry in self._entries:
            self._entries.remove(entry)
        entry.deleteLater()


# ─── ENTRY POINT ───────────────────────────────────────


def main():
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setStyleSheet(QSS_DARK)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
