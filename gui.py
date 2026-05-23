#!/usr/bin/env python3
"""
Civitai Data Extractor v2 — Tkinter GUI
Paste a URL → auto-download to temp → right-click to save into organized folder tree.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import os
import sys
import time
import shutil
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extractor import CivitaiExtractor


class DownloadEntry:
    """Tracks one download in the queue."""

    def __init__(self, url: str, parent_frame, extractor: CivitaiExtractor, gui):
        self.url = url
        self.parent = parent_frame
        self.extractor = extractor
        self.gui = gui
        self.result = None
        self.error = None
        self.status = "queued"  # queued, downloading, done, error
        self.progress_pct = 0
        self._widgets = {}
        self._build()

    def _build(self):
        # Container frame with border
        self.frame = tk.Frame(self.parent, bg="#2a2a2a", bd=1, relief="solid")
        self.frame.pack(fill="x", padx=5, pady=3)

        # Top row: name + type badge
        top = tk.Frame(self.frame, bg="#2a2a2a")
        top.pack(fill="x", padx=8, pady=(6, 0))

        self.name_label = tk.Label(top, text="Queued...", font=("Sans", 10, "bold"),
                                   fg="#d4d4d4", bg="#2a2a2a", anchor="w")
        self.name_label.pack(side="left")

        self.type_label = tk.Label(top, text="", font=("Sans", 8), fg="#888", bg="#2a2a2a")
        self.type_label.pack(side="right")

        # Progress bar
        self.progress = ttk.Progressbar(self.frame, mode="determinate", length=300)
        self.progress.pack(fill="x", padx=8, pady=(4, 0))

        # Bottom row: status + actions
        bottom = tk.Frame(self.frame, bg="#2a2a2a")
        bottom.pack(fill="x", padx=8, pady=(2, 6))

        self.status_label = tk.Label(bottom, text="Waiting...", font=("Sans", 8),
                                     fg="#888", bg="#2a2a2a", anchor="w")
        self.status_label.pack(side="left")

        # Right-click binding on the entire frame
        self.frame.bind("<Button-3>", self._on_right_click)
        self.name_label.bind("<Button-3>", self._on_right_click)
        self.type_label.bind("<Button-3>", self._on_right_click)
        self.status_label.bind("<Button-3>", self._on_right_click)
        self.progress.bind("<Button-3>", self._on_right_click)

    def update_name(self, name: str):
        self.name_label.configure(text=name)

    def update_type(self, file_type: str, base_model: str):
        self.type_label.configure(text=f"{file_type} | {base_model}")

    def update_progress(self, downloaded: int, total: int):
        if total:
            self.progress_pct = int(downloaded / total * 100)
            self.progress["value"] = self.progress_pct
            mb_done = downloaded / 1_048_576
            mb_total = total / 1_048_576
            self.status_label.configure(
                text=f"Downloading {mb_done:.0f}/{mb_total:.0f} MB ({self.progress_pct}%)"
            )

    def update_status(self, text: str, color: str = "#888"):
        self.status_label.configure(text=text, fg=color)

    def add_actions(self):
        """Add action buttons below the status."""
        actions = tk.Frame(self.frame, bg="#2a2a2a")
        actions.pack(fill="x", padx=8, pady=(0, 6))

        kw_btn = tk.Button(actions, text="View Keywords", font=("Sans", 8),
                           command=self._view_keywords,
                           bg="#3a3a3a", fg="#d4d4d4", relief="flat")
        kw_btn.pack(side="left", padx=(0, 8))

        save_btn = tk.Button(actions, text="Save To…", font=("Sans", 8),
                             command=self._on_right_click,
                             bg="#3a3a3a", fg="#d4d4d4", relief="flat")
        save_btn.pack(side="left")

        self.frame.bind("<Button-3>", self._on_right_click)
        for w in [kw_btn, save_btn, actions]:
            w.bind("<Button-3>", self._on_right_click)

    def _on_right_click(self, event=None):
        """Show folder tree context menu for destination selection."""
        if not self.result:
            return
        self.gui._show_dest_menu(self, event)

    def _view_keywords(self):
        """Show keywords in a popup window."""
        if not self.result:
            return
        win = tk.Toplevel(self.frame)
        win.title(f"Keywords — {self.result['model_name']}")
        win.geometry("500x400")
        win.configure(bg="#1e1e1e")

        text = tk.Text(win, font=("monospace", 9), bg="#1e1e1e", fg="#d4d4d4",
                       relief="flat", borderwidth=0, wrap="word")
        text.pack(fill="both", expand=True, padx=10, pady=10)

        for kw in self.result.get("keywords", []):
            text.insert("end", kw + "\n")
        text.configure(state="disabled")


class CivitaiGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Civitai Data Extractor v2")
        self.root.geometry("700x550")
        self.root.resizable(True, True)
        self.root.configure(bg="#1e1e1e")

        self.api_key = None
        self.extractor = None
        self.downloads: list[DownloadEntry] = []
        self.processing = False

        # Default paths
        self.temp_dir = Path.home() / ".cache" / "civitai-temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.data_root = Path.home() / "civitai-data"
        self.data_root.mkdir(parents=True, exist_ok=True)

        # Folder tree cache
        self._folder_tree = {}  # { (type, base_model): [subfolder_paths] }

        self._build_ui()
        self._try_load_api_key()
        self._scan_folders()

        # Start clipboard watcher
        self._last_clipboard = ""
        self._clipboard_watcher()

        self._center_window()

    # ─── UI BUILD ────────────────────────────────────────

    def _build_ui(self):
        main = tk.Frame(self.root, bg="#1e1e1e", padx=12, pady=12)
        main.pack(fill="both", expand=True)

        # Title
        title = tk.Label(main, text="Civitai Data Extractor", font=("Sans", 16, "bold"),
                         fg="#d4d4d4", bg="#1e1e1e")
        title.pack(anchor="w", pady=(0, 10))

        # ── API Key row
        self._build_key_row(main)

        # ── URL input
        self._build_url_row(main)

        # ── Data Root row
        self._build_root_row(main)

        # ── Content area: downloads list + image preview
        content = tk.Frame(main, bg="#1e1e1e")
        content.pack(fill="both", expand=True, pady=(10, 0))

        # Downloads panel
        dl_frame = tk.Frame(content, bg="#1e1e1e")
        dl_frame.pack(side="left", fill="both", expand=True)

        dl_label = tk.Label(dl_frame, text="Downloads", font=("Sans", 10, "bold"),
                            fg="#d4d4d4", bg="#1e1e1e")
        dl_label.pack(anchor="w")

        self.dl_canvas = tk.Canvas(dl_frame, bg="#252525", highlightthickness=0)
        scrollbar = ttk.Scrollbar(dl_frame, orient="vertical", command=self.dl_canvas.yview)
        self.dl_inner = tk.Frame(self.dl_canvas, bg="#252525")

        self.dl_inner.bind("<Configure>",
                           lambda e: self.dl_canvas.configure(scrollregion=self.dl_canvas.bbox("all")))
        self.dl_canvas.create_window((0, 0), window=self.dl_inner, anchor="nw")
        self.dl_canvas.configure(yscrollcommand=scrollbar.set)

        self.dl_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Image preview panel
        preview_frame = tk.Frame(content, bg="#252525", width=200)
        preview_frame.pack(side="right", fill="y", padx=(10, 0))
        preview_frame.pack_propagate(False)

        tk.Label(preview_frame, text="Preview", font=("Sans", 9, "bold"),
                 fg="#888", bg="#252525").pack(pady=(5, 5))

        self.preview_label = tk.Label(preview_frame, text="No image", font=("Sans", 8),
                                      fg="#555", bg="#252525", wraplength=180)
        self.preview_label.pack(expand=True)

        # ── Status bar
        self.status_bar = tk.Label(self.root, text="Ready", font=("Sans", 8),
                                   fg="#888", bg="#333", anchor="w", padx=10)
        self.status_bar.pack(side="bottom", fill="x")

    def _build_key_row(self, parent):
        frame = tk.Frame(parent, bg="#1e1e1e")
        frame.pack(fill="x", pady=(0, 8))

        tk.Label(frame, text="API Key:", font=("Sans", 9), fg="#888", bg="#1e1e1e").pack(side="left")

        self.key_path_var = tk.StringVar()
        key_entry = tk.Entry(frame, textvariable=self.key_path_var, font=("monospace", 9),
                             bg="#333", fg="#d4d4d4", insertbackground="#d4d4d4")
        key_entry.pack(side="left", fill="x", expand=True, padx=(5, 5))

        tk.Button(frame, text="Browse", font=("Sans", 8), command=self._browse_key,
                  bg="#3a3a3a", fg="#d4d4d4", relief="flat").pack(side="left", padx=(0, 5))
        tk.Button(frame, text="Load", font=("Sans", 8), command=self._load_key,
                  bg="#3a3a3a", fg="#d4d4d4", relief="flat").pack(side="left")

        self.key_status = tk.Label(frame, text="No key", font=("Sans", 8), fg="#e44", bg="#1e1e1e")
        self.key_status.pack(side="left", padx=(8, 0))

    def _build_url_row(self, parent):
        frame = tk.Frame(parent, bg="#1e1e1e")
        frame.pack(fill="x", pady=(0, 8))

        tk.Label(frame, text="Model URL:", font=("Sans", 9), fg="#888", bg="#1e1e1e").pack(side="left")

        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(frame, textvariable=self.url_var, font=("monospace", 10),
                                  bg="#333", fg="#d4d4d4", insertbackground="#d4d4d4")
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(5, 5))
        self.url_entry.bind("<Return>", lambda e: self._start_download(self.url_var.get().strip()))
        self.url_entry.focus_set()

        self.url_entry.bind("<Control-v>", lambda e: self.root.after(100, self._check_clipboard_paste))
        self.url_entry.bind("<Control-V>", lambda e: self.root.after(100, self._check_clipboard_paste))

    def _build_root_row(self, parent):
        frame = tk.Frame(parent, bg="#1e1e1e")
        frame.pack(fill="x", pady=(0, 5))

        tk.Label(frame, text="Data Root:", font=("Sans", 9), fg="#888", bg="#1e1e1e").pack(side="left")

        self.root_var = tk.StringVar(value=str(self.data_root))
        root_entry = tk.Entry(frame, textvariable=self.root_var, font=("monospace", 9),
                              bg="#333", fg="#d4d4d4", insertbackground="#d4d4d4")
        root_entry.pack(side="left", fill="x", expand=True, padx=(5, 5))

        tk.Button(frame, text="Browse", font=("Sans", 8), command=self._browse_root,
                  bg="#3a3a3a", fg="#d4d4d4", relief="flat").pack(side="left", padx=(0, 5))
        tk.Button(frame, text="↻ Refresh", font=("Sans", 8), command=self._scan_folders,
                  bg="#3a3a3a", fg="#d4d4d4", relief="flat").pack(side="left")

    # ─── API KEY ─────────────────────────────────────────

    def _try_load_api_key(self):
        for p in [Path.home() / ".api_key_civitai", Path("/home/bot/projects/.api_key_civitai")]:
            if p.is_file():
                self.key_path_var.set(str(p))
                with open(p) as f:
                    self.api_key = f.read().strip()
                self.key_status.configure(text="✓ Loaded", fg="#4a4")
                self._log("API key loaded.")
                return

    def _browse_key(self):
        p = filedialog.askopenfilename(title="Select API key file")
        if p:
            self.key_path_var.set(p)

    def _load_key(self):
        p = Path(self.key_path_var.get().strip())
        if not p.is_file():
            messagebox.showerror("Error", f"Not found: {p}")
            return
        with open(p) as f:
            self.api_key = f.read().strip()
        self.key_status.configure(text="✓ Loaded", fg="#4a4")
        self._log(f"API key loaded: {p.name}")

    # ─── CLIPBOARD WATCHER ───────────────────────────────

    def _clipboard_watcher(self):
        """Check clipboard every 500ms for new civitai URLs."""
        try:
            clip = self.root.clipboard_get()
            if clip and clip != self._last_clipboard and "civitai" in clip:
                self._last_clipboard = clip
                url = clip.strip()
                if url.startswith("http"):
                    self.url_var.set(url)
                    self._start_download(url)
        except Exception:
            pass
        self.root.after(500, self._clipboard_watcher)

    def _check_clipboard_paste(self):
        """Called after Ctrl+V — treat manual paste as trigger."""
        url = self.url_var.get().strip()
        if url and "civitai" in url and url != self._last_clipboard:
            self._last_clipboard = url
            self.root.after(200, lambda: self._start_download(url))

    # ─── DOWNLOAD FLOW ───────────────────────────────────

    def _start_download(self, url: str):
        if not url or "civitai" not in url:
            return
        if not self.api_key:
            messagebox.showwarning("No API Key", "Load an API key file first.")
            return

        # Clear URL field
        self.url_var.set("")

        # Create extractor with temp dir
        extractor = CivitaiExtractor(api_key=self.api_key, download_dir=str(self.temp_dir))

        # Create download entry
        entry = DownloadEntry(url, self.dl_inner, extractor, self)
        entry.update_name("Fetching page…")
        entry.update_status("Connecting…", "#888")

        self.downloads.insert(0, entry)
        self._log(f"Queued: {url[:60]}...")

        # Run in background
        thread = threading.Thread(target=self._run_download, args=(entry,), daemon=True)
        thread.start()

    def _run_download(self, entry: DownloadEntry):
        try:
            # Phase 1: fetch page + parse metadata (no progress yet)
            entry.gui.root.after(0, lambda: entry.update_name("Parsing page…"))
            entry.gui.root.after(0, lambda: entry.update_status("Fetching metadata…", "#888"))

            html = entry.extractor.fetch_page(entry.url)
            model_data = entry.extractor.parse_model_data(html)
            file_info = entry.extractor.get_file_info(model_data)
            first_image = entry.extractor.get_first_image(html)

            if not file_info:
                raise ValueError("No downloadable file found")

            # Update UI with metadata
            model_name = model_data.get("name", "Unknown")
            ft = file_info["type"]
            bm = file_info["base_model"]

            entry.gui.root.after(0, lambda: entry.update_name(file_info["name"]))
            entry.gui.root.after(0, lambda: entry.update_type(ft, bm))
            entry.gui.root.after(0, lambda: entry.update_status("Downloading…", "#ccc"))

            # Show first image preview
            if first_image:
                entry.gui.root.after(0, lambda: self._show_preview(first_image))

            # Progress callback
            def on_progress(downloaded: int, total: int):
                entry.gui.root.after(0, lambda: entry.update_progress(downloaded, total))

            # Phase 2: download
            dest = entry.extractor.download_file(model_data, file_info, on_progress)

            # Phase 3: save keywords
            txt_path = entry.extractor.save_keywords(model_data, file_info)
            keywords = entry.extractor.extract_keywords(model_data)

            result = {
                "model_name": model_name,
                "file": str(dest),
                "file_name": file_info["name"],
                "file_type": ft,
                "base_model": bm,
                "size_kb": file_info["size_kb"],
                "keywords_file": str(txt_path),
                "keyword_count": len(keywords),
                "keywords": keywords,
                "first_image": first_image,
            }

            entry.result = result
            entry.status = "done"
            entry.gui.root.after(0, lambda: entry.update_status(
                f"✓ {file_info['size_kb']:.0f} KB · {len(keywords)} keywords — right-click to save", "#4a4"
            ))
            entry.gui.root.after(0, entry.add_actions)
            entry.gui.root.after(0, lambda: self._log(f"✓ {model_name} ({ft} | {bm})"))

        except Exception as e:
            entry.status = "error"
            entry.error = str(e)
            entry.gui.root.after(0, lambda: entry.update_status(f"✗ {e}", "#e44"))
            entry.gui.root.after(0, lambda: self._log(f"✗ Error: {e}"))

    def _show_preview(self, url: str):
        """Download and display the first image as thumbnail."""
        try:
            import urllib.request as ur
            import io
            from PIL import Image, ImageTk

            req = ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = ur.urlopen(req, timeout=15).read()
            img = Image.open(io.BytesIO(data))
            img.thumbnail((180, 180), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)

            self.preview_label.configure(image=photo, text="")
            self.preview_label.image = photo
        except ImportError:
            self.preview_label.configure(text="(install Pillow for previews)\npip install Pillow", fg="#555")
        except Exception as e:
            self.preview_label.configure(text=f"(preview unavailable)\n{e}", fg="#555")

    # ─── FOLDER TREE ─────────────────────────────────────

    def _scan_folders(self):
        """Scan data root for folder structure: data/{type}/{base_model}/{subfolders}"""
        self.data_root = Path(self.root_var.get().strip())
        self._folder_tree = {}

        data_dir = self.data_root / "data"
        if not data_dir.is_dir():
            self._log("Data root has no 'data/' folder yet. Create: data/{type}/{base_model}/")
            return

        for type_dir in data_dir.iterdir():
            if not type_dir.is_dir():
                continue
            file_type = type_dir.name.lower()
            for model_dir in type_dir.iterdir():
                if not model_dir.is_dir():
                    continue
                base_model = model_dir.name.lower()
                key = (file_type, base_model)
                subfolders = [d.name for d in model_dir.iterdir() if d.is_dir()]
                if subfolders:
                    self._folder_tree[key] = subfolders

        count = sum(len(v) for v in self._folder_tree.values())
        self._log(f"Folder tree: {len(self._folder_tree)} type×model combos, {count} subfolders")

    def _show_dest_menu(self, entry: DownloadEntry, event=None):
        """Show right-click context menu with matching destination folders."""
        if not entry.result:
            return

        ft = entry.result["file_type"].lower()
        bm = entry.result["base_model"].lower()
        key = (ft, bm)

        menu = tk.Menu(self.root, tearoff=0, bg="#333", fg="#d4d4d4")

        if key in self._folder_tree and self._folder_tree[key]:
            base_path = self.data_root / "data" / ft / bm
            for folder in sorted(self._folder_tree[key]):
                dest = base_path / folder
                menu.add_command(
                    label=f"📁 {folder}",
                    command=lambda d=dest: self._move_to(entry, d),
                )
        else:
            menu.add_command(label=f"(no folders under data/{ft}/{bm}/)", state="disabled")

        menu.add_separator()
        menu.add_command(label="📂 Browse…", command=lambda: self._browse_dest(entry))
        menu.add_command(label="✕ Remove", command=lambda: self._remove_entry(entry))

        if event:
            menu.post(event.x_root, event.y_root)
        else:
            menu.post(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def _browse_dest(self, entry: DownloadEntry):
        d = filedialog.askdirectory(initialdir=str(self.data_root))
        if d:
            self._move_to(entry, Path(d))

    def _move_to(self, entry: DownloadEntry, dest: Path):
        """Move downloaded file and keywords from temp to destination folder."""
        if not entry.result:
            return

        dest.mkdir(parents=True, exist_ok=True)
        src_file = Path(entry.result["file"])
        src_kw = Path(entry.result["keywords_file"])

        if not src_file.exists():
            messagebox.showerror("Error", f"Source file missing: {src_file}")
            return

        shutil.move(str(src_file), str(dest / src_file.name))
        if src_kw.exists():
            shutil.move(str(src_kw), str(dest / src_kw.name))

        entry.update_status(f"✓ Saved → {dest}", "#4a4")
        self._log(f"Moved to: {dest}")

    def _remove_entry(self, entry: DownloadEntry):
        if entry in self.downloads:
            self.downloads.remove(entry)
        entry.frame.destroy()

    # ─── UTILITY ─────────────────────────────────────────

    def _log(self, text: str):
        self.status_bar.configure(text=text)
        print(text)

    def _center_window(self):
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"+{(sw-w)//2}+{(sh-h)//2}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = CivitaiGUI()
    app.run()
