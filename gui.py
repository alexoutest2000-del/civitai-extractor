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
import shutil
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extractor import CivitaiExtractor

# ─── COLOR THEMES ────────────────────────────────────────

THEMES = {
    "Dark": {
        "bg": "#1e1e1e", "frame_bg": "#252525", "entry_bg": "#333",
        "fg": "#d4d4d4", "dim": "#888", "accent": "#4a4", "error": "#e44",
        "button_bg": "#3a3a3a", "status_bg": "#333",
    },
    "Light": {
        "bg": "#f5f5f5", "frame_bg": "#ffffff", "entry_bg": "#ffffff",
        "fg": "#222", "dim": "#666", "accent": "#2a2", "error": "#c00",
        "button_bg": "#e0e0e0", "status_bg": "#ddd",
    },
    "Warm": {
        "bg": "#2b2420", "frame_bg": "#332e2a", "entry_bg": "#403832",
        "fg": "#e8d5b7", "dim": "#a09080", "accent": "#c9a96e", "error": "#d4785c",
        "button_bg": "#4a3f35", "status_bg": "#3a322c",
    },
    "Nord": {
        "bg": "#2e3440", "frame_bg": "#3b4252", "entry_bg": "#434c5e",
        "fg": "#d8dee9", "dim": "#81a1c1", "accent": "#a3be8c", "error": "#bf616a",
        "button_bg": "#4c566a", "status_bg": "#3b4252",
    },
    "Solarized Dark": {
        "bg": "#002b36", "frame_bg": "#073642", "entry_bg": "#073642",
        "fg": "#839496", "dim": "#586e75", "accent": "#859900", "error": "#dc322f",
        "button_bg": "#586e75", "status_bg": "#073642",
    },
}


class DownloadEntry:
    """Tracks one download in the queue."""

    def __init__(self, url: str, parent_frame, extractor: CivitaiExtractor, gui):
        self.url = url
        self.parent = parent_frame
        self.extractor = extractor
        self.gui = gui
        self.result = None
        self.error = None
        self.status = "queued"
        self.progress_pct = 0
        self._build()

    @property
    def t(self):
        return self.gui.theme

    def _build(self):
        t = self.t
        self.frame = tk.Frame(self.parent, bg=t["frame_bg"], bd=1, relief="solid")
        self.frame.pack(fill="x", padx=5, pady=3)

        top = tk.Frame(self.frame, bg=t["frame_bg"])
        top.pack(fill="x", padx=8, pady=(6, 0))

        self.name_label = tk.Label(top, text="Queued...", font=("Sans", 10, "bold"),
                                   fg=t["fg"], bg=t["frame_bg"], anchor="w")
        self.name_label.pack(side="left")

        self.type_label = tk.Label(top, text="", font=("Sans", 8), fg=t["dim"], bg=t["frame_bg"])
        self.type_label.pack(side="right")

        self.progress = ttk.Progressbar(self.frame, mode="determinate", length=300)
        self.progress.pack(fill="x", padx=8, pady=(4, 0))

        bottom = tk.Frame(self.frame, bg=t["frame_bg"])
        bottom.pack(fill="x", padx=8, pady=(2, 6))

        self.status_label = tk.Label(bottom, text="Waiting...", font=("Sans", 8),
                                     fg=t["dim"], bg=t["frame_bg"], anchor="w")
        self.status_label.pack(side="left")

        for w in [self.frame, self.name_label, self.type_label, self.status_label, self.progress]:
            w.bind("<Button-3>", self._on_right_click)

    def update_name(self, name: str):
        self.name_label.configure(text=name[:60])

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

    def update_status(self, text: str, color: str = None):
        self.status_label.configure(text=text, fg=color or self.t["dim"])

    def add_actions(self):
        t = self.t
        actions = tk.Frame(self.frame, bg=t["frame_bg"])
        actions.pack(fill="x", padx=8, pady=(0, 6))

        kw_btn = tk.Button(actions, text="View Keywords", font=("Sans", 8),
                           command=self._view_keywords,
                           bg=t["button_bg"], fg=t["fg"], relief="flat",
                           activebackground=t["entry_bg"], activeforeground=t["fg"])
        kw_btn.pack(side="left", padx=(0, 8))

        save_btn = tk.Button(actions, text="Save To…", font=("Sans", 8),
                             command=self._on_right_click,
                             bg=t["button_bg"], fg=t["fg"], relief="flat",
                             activebackground=t["entry_bg"], activeforeground=t["fg"])
        save_btn.pack(side="left")

        for w in [kw_btn, save_btn, actions]:
            w.bind("<Button-3>", self._on_right_click)

    def _on_right_click(self, event=None):
        if not self.result:
            return
        self.gui._show_dest_menu(self, event)

    def _view_keywords(self):
        if not self.result:
            return
        win = tk.Toplevel(self.frame)
        win.title(f"Keywords — {self.result['model_name']}")
        win.geometry("500x400")
        win.configure(bg=self.t["bg"])

        text = tk.Text(win, font=("monospace", 9), bg=self.t["bg"], fg=self.t["fg"],
                       relief="flat", borderwidth=0, wrap="word",
                       insertbackground=self.t["fg"])
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

        # Theme
        self.theme_name = tk.StringVar(value="Dark")
        self.theme = THEMES["Dark"]
        self.root.configure(bg=self.theme["bg"])

        self.api_key = None
        self.downloads: list[DownloadEntry] = []
        self._active_menu = None  # track right-click menu for dismissal

        # Paths
        self.temp_dir = Path.home() / ".cache" / "civitai-temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.data_root = Path.home() / "civitai-data"
        self.data_root.mkdir(parents=True, exist_ok=True)
        self._folder_tree = {}

        self._build_ui()
        self._try_load_api_key()
        self._scan_folders()

        # Dismiss right-click menu on left-click anywhere
        self.root.bind("<Button-1>", self._dismiss_menu, add="+")

        self._last_clipboard = ""
        self._clipboard_watcher()
        self._center_window()

    # ─── THEME APPLICATION ────────────────────────────────

    def _apply_theme(self):
        self.theme = THEMES[self.theme_name.get()]
        t = self.theme
        self.root.configure(bg=t["bg"])
        self.status_bar.configure(bg=t["status_bg"], fg=t["dim"])
        self.preview_label.configure(bg=t["frame_bg"], fg=t["dim"])
        # Re-apply to main and all children
        for child in self.root.winfo_children():
            self._retheme_widget(child)

    def _retheme_widget(self, w):
        t = self.theme
        try:
            if isinstance(w, (tk.Label, tk.Button, tk.Frame)):
                if isinstance(w, tk.Button):
                    w.configure(bg=t["button_bg"], fg=t["fg"],
                                activebackground=t["entry_bg"], activeforeground=t["fg"])
                elif isinstance(w, tk.Frame):
                    w.configure(bg=t["bg"])
                elif isinstance(w, tk.Label):
                    w.configure(bg=t["bg"], fg=t["fg"])
        except tk.TclError:
            pass
        for child in w.winfo_children():
            self._retheme_widget(child)

    # ─── UI BUILD ────────────────────────────────────────

    def _build_ui(self):
        t = self.theme
        main = tk.Frame(self.root, bg=t["bg"], padx=12, pady=12)
        main.pack(fill="both", expand=True)

        # Title row with theme selector
        title_row = tk.Frame(main, bg=t["bg"])
        title_row.pack(fill="x", pady=(0, 10))

        tk.Label(title_row, text="Civitai Data Extractor", font=("Sans", 16, "bold"),
                 fg=t["fg"], bg=t["bg"]).pack(side="left")

        theme_frame = tk.Frame(title_row, bg=t["bg"])
        theme_frame.pack(side="right")
        tk.Label(theme_frame, text="Theme:", font=("Sans", 8), fg=t["dim"], bg=t["bg"]).pack(side="left")
        theme_menu = ttk.Combobox(theme_frame, textvariable=self.theme_name,
                                  values=list(THEMES.keys()), state="readonly", width=16)
        theme_menu.pack(side="left", padx=(4, 0))
        theme_menu.bind("<<ComboboxSelected>>", lambda e: self._apply_theme())

        self._build_key_row(main)
        self._build_url_row(main)
        self._build_root_row(main)

        # Content: downloads + preview
        content = tk.Frame(main, bg=t["bg"])
        content.pack(fill="both", expand=True, pady=(10, 0))

        # Downloads
        dl_frame = tk.Frame(content, bg=t["bg"])
        dl_frame.pack(side="left", fill="both", expand=True)

        tk.Label(dl_frame, text="Downloads", font=("Sans", 10, "bold"),
                 fg=t["fg"], bg=t["bg"]).pack(anchor="w")

        self.dl_canvas = tk.Canvas(dl_frame, bg=t["frame_bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(dl_frame, orient="vertical", command=self.dl_canvas.yview)
        self.dl_inner = tk.Frame(self.dl_canvas, bg=t["frame_bg"])
        self.dl_inner.bind("<Configure>",
                           lambda e: self.dl_canvas.configure(scrollregion=self.dl_canvas.bbox("all")))
        self.dl_canvas.create_window((0, 0), window=self.dl_inner, anchor="nw")
        self.dl_canvas.configure(yscrollcommand=scrollbar.set)
        self.dl_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Preview
        self.preview_frame = tk.Frame(content, bg=t["frame_bg"], width=200, height=250)
        self.preview_frame.pack(side="right", fill="y", padx=(10, 0))
        self.preview_frame.pack_propagate(False)

        tk.Label(self.preview_frame, text="Preview", font=("Sans", 9, "bold"),
                 fg=t["dim"], bg=t["frame_bg"]).pack(pady=(5, 5))

        self.preview_label = tk.Label(self.preview_frame, text="No image", font=("Sans", 8),
                                      fg=t["dim"], bg=t["frame_bg"], wraplength=180,
                                      compound="center")
        self.preview_label.pack(expand=True, fill="both", padx=5, pady=5)

        # Status bar
        self.status_bar = tk.Label(self.root, text="Ready", font=("Sans", 8),
                                   fg=t["dim"], bg=t["status_bg"], anchor="w", padx=10)
        self.status_bar.pack(side="bottom", fill="x")

    def _build_key_row(self, parent):
        t = self.theme
        frame = tk.Frame(parent, bg=t["bg"])
        frame.pack(fill="x", pady=(0, 8))
        tk.Label(frame, text="API Key:", font=("Sans", 9), fg=t["dim"], bg=t["bg"]).pack(side="left")

        self.key_path_var = tk.StringVar()
        tk.Entry(frame, textvariable=self.key_path_var, font=("monospace", 9),
                 bg=t["entry_bg"], fg=t["fg"], insertbackground=t["fg"]).pack(
            side="left", fill="x", expand=True, padx=(5, 5))

        tk.Button(frame, text="Browse", font=("Sans", 8), command=self._browse_key,
                  bg=t["button_bg"], fg=t["fg"], relief="flat",
                  activebackground=t["entry_bg"], activeforeground=t["fg"]).pack(
            side="left", padx=(0, 5))
        tk.Button(frame, text="Load", font=("Sans", 8), command=self._load_key,
                  bg=t["button_bg"], fg=t["fg"], relief="flat",
                  activebackground=t["entry_bg"], activeforeground=t["fg"]).pack(side="left")

        self.key_status = tk.Label(frame, text="No key", font=("Sans", 8), fg=t["error"], bg=t["bg"])
        self.key_status.pack(side="left", padx=(8, 0))

    def _build_url_row(self, parent):
        t = self.theme
        frame = tk.Frame(parent, bg=t["bg"])
        frame.pack(fill="x", pady=(0, 8))

        tk.Label(frame, text="Model URL:", font=("Sans", 9), fg=t["dim"], bg=t["bg"]).pack(side="left")

        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(frame, textvariable=self.url_var, font=("monospace", 10),
                                  bg=t["entry_bg"], fg=t["fg"], insertbackground=t["fg"])
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(5, 5))
        self.url_entry.bind("<Return>", lambda e: self._start_download(self.url_var.get().strip()))
        self.url_entry.focus_set()
        self.url_entry.bind("<Control-v>", lambda e: self.root.after(100, self._check_clipboard_paste))
        self.url_entry.bind("<Control-V>", lambda e: self.root.after(100, self._check_clipboard_paste))

    def _build_root_row(self, parent):
        t = self.theme
        frame = tk.Frame(parent, bg=t["bg"])
        frame.pack(fill="x", pady=(0, 5))

        tk.Label(frame, text="Base Folder:", font=("Sans", 9), fg=t["dim"], bg=t["bg"]).pack(side="left")

        self.root_var = tk.StringVar(value=str(self.data_root))
        tk.Entry(frame, textvariable=self.root_var, font=("monospace", 9),
                 bg=t["entry_bg"], fg=t["fg"], insertbackground=t["fg"]).pack(
            side="left", fill="x", expand=True, padx=(5, 5))

        tk.Button(frame, text="Browse", font=("Sans", 8), command=self._browse_root,
                  bg=t["button_bg"], fg=t["fg"], relief="flat",
                  activebackground=t["entry_bg"], activeforeground=t["fg"]).pack(
            side="left", padx=(0, 5))
        tk.Button(frame, text="↻ Refresh", font=("Sans", 8), command=self._scan_folders,
                  bg=t["button_bg"], fg=t["fg"], relief="flat",
                  activebackground=t["entry_bg"], activeforeground=t["fg"]).pack(side="left")

    # ─── API KEY ────────────────────────────────────────

    def _browse_root(self):
        d = filedialog.askdirectory(initialdir=self.root_var.get())
        if d:
            self.root_var.set(d)
            self._scan_folders()

    def _try_load_api_key(self):
        for p in [Path.home() / ".api_key_civitai", Path("/home/bot/projects/.api_key_civitai")]:
            if p.is_file():
                self.key_path_var.set(str(p))
                with open(p) as f:
                    self.api_key = f.read().strip()
                self.key_status.configure(text="✓ Loaded", fg=self.theme["accent"])
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
        self.key_status.configure(text="✓ Loaded", fg=self.theme["accent"])
        self._log(f"API key loaded: {p.name}")

    # ─── CLIPBOARD ──────────────────────────────────────

    def _clipboard_watcher(self):
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
        url = self.url_var.get().strip()
        if url and "civitai" in url and url != self._last_clipboard:
            self._last_clipboard = url
            self.root.after(200, lambda: self._start_download(url))

    # ─── DOWNLOAD ───────────────────────────────────────

    def _start_download(self, url: str):
        if not url or "civitai" not in url:
            return
        if not self.api_key:
            messagebox.showwarning("No API Key", "Load an API key file first.")
            return

        self.url_var.set("")
        extractor = CivitaiExtractor(api_key=self.api_key, download_dir=str(self.temp_dir))

        entry = DownloadEntry(url, self.dl_inner, extractor, self)
        entry.update_name("Fetching page…")
        entry.update_status("Connecting…")

        self.downloads.insert(0, entry)
        self._log(f"Queued: {url[:60]}...")

        thread = threading.Thread(target=self._run_download, args=(entry,), daemon=True)
        thread.start()

    def _run_download(self, entry: DownloadEntry):
        try:
            entry.gui.root.after(0, lambda: entry.update_name("Parsing page…"))
            entry.gui.root.after(0, lambda: entry.update_status("Fetching metadata…"))

            html = entry.extractor.fetch_page(entry.url)
            model_data = entry.extractor.parse_model_data(html)
            file_info = entry.extractor.get_file_info(model_data)
            first_image = entry.extractor.get_first_image(html)

            if not file_info:
                raise ValueError("No downloadable file found")

            model_name = model_data.get("name", "Unknown")
            ft = file_info["type"]
            bm = file_info["base_model"]

            entry.gui.root.after(0, lambda: entry.update_name(file_info["name"]))
            entry.gui.root.after(0, lambda: entry.update_type(ft, bm))
            entry.gui.root.after(0, lambda: entry.update_status("Downloading…", entry.t["fg"]))

            if first_image:
                entry.gui.root.after(0, lambda img=first_image: self._show_preview(img))

            def on_progress(downloaded: int, total: int):
                entry.gui.root.after(0, lambda: entry.update_progress(downloaded, total))

            dest = entry.extractor.download_file(model_data, file_info, on_progress)
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
                f"✓ {file_info['size_kb']:.0f} KB · {len(keywords)} keywords — right-click to save",
                entry.t["accent"]))
            entry.gui.root.after(0, entry.add_actions)
            entry.gui.root.after(0, lambda: self._log(f"✓ {model_name} ({ft} | {bm})"))

        except Exception as e:
            entry.status = "error"
            entry.error = str(e)
            entry.gui.root.after(0, lambda: entry.update_status(f"✗ {e}", entry.t["error"]))
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

            self.preview_label.configure(image=photo, text="", bg=self.theme["frame_bg"])
            self.preview_label.image = photo
        except ImportError:
            self.preview_label.configure(
                text="(pillow not installed)\npip install Pillow",
                image="", fg=self.theme["dim"], bg=self.theme["frame_bg"])
        except Exception as e:
            self.preview_label.configure(
                text=f"(preview error)\n{type(e).__name__}",
                image="", fg=self.theme["dim"], bg=self.theme["frame_bg"])

    # ─── FOLDER TREE ────────────────────────────────────

    def _scan_folders(self):
        """Scan root for folder structure: {root}/{type}/{base_model}/subfolders"""
        self.data_root = Path(self.root_var.get().strip())
        self._folder_tree = {}

        if not self.data_root.is_dir():
            self._log(f"Base folder not found: {self.data_root}")
            return

        for type_dir in sorted(self.data_root.iterdir()):
            if not type_dir.is_dir():
                continue
            file_type = type_dir.name.lower()
            for model_dir in sorted(type_dir.iterdir()):
                if not model_dir.is_dir():
                    continue
                base_model = model_dir.name.lower()
                subfolders = sorted(d.name for d in model_dir.iterdir() if d.is_dir())
                if subfolders:
                    self._folder_tree[(file_type, base_model)] = subfolders

        count = sum(len(v) for v in self._folder_tree.values())
        self._log(f"Folder tree: {len(self._folder_tree)} type×model combos, {count} subfolders")

    def _dismiss_menu(self, event=None):
        """Dismiss the active right-click menu on left-click."""
        if self._active_menu:
            try:
                self._active_menu.unpost()
            except tk.TclError:
                pass
            self._active_menu = None

    def _show_dest_menu(self, entry: DownloadEntry, event=None):
        """Show right-click context menu — only one at a time, left-click dismisses."""
        if not entry.result:
            return

        self._dismiss_menu()  # dismiss any existing menu first
        t = self.theme

        ft = entry.result["file_type"].lower()
        bm = entry.result["base_model"].lower()
        key = (ft, bm)

        menu = tk.Menu(self.root, tearoff=0, bg=t["entry_bg"], fg=t["fg"],
                       activebackground=t["button_bg"], activeforeground=t["fg"])

        base_path = self.data_root / ft / bm
        if key in self._folder_tree and self._folder_tree[key]:
            for folder in self._folder_tree[key]:
                dest = base_path / folder
                menu.add_command(
                    label=f"📁 {folder}",
                    command=lambda d=dest: (self._move_to(entry, d), self._dismiss_menu()),
                )
        else:
            menu.add_command(
                label=f"(no folders under {ft}/{bm}/)",
                state="disabled")

        menu.add_separator()
        menu.add_command(label="📂 Browse…",
                         command=lambda: (self._browse_dest(entry), self._dismiss_menu()))
        menu.add_command(label="✕ Remove",
                         command=lambda: (self._remove_entry(entry), self._dismiss_menu()))

        self._active_menu = menu
        if event:
            menu.post(event.x_root, event.y_root)
        else:
            menu.post(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def _browse_dest(self, entry: DownloadEntry):
        d = filedialog.askdirectory(initialdir=str(self.data_root))
        if d:
            self._move_to(entry, Path(d))

    def _move_to(self, entry: DownloadEntry, dest: Path):
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

        entry.update_status(f"✓ Saved → {dest}", entry.t["accent"])
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
