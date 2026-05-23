#!/usr/bin/env python3
"""
Civitai Data Extractor — Tkinter GUI
Paste a civitai.red model URL, click Download, get the file + keywords.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import os
import sys

# Add project dir to path for import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extractor import CivitaiExtractor


class CivitaiGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Civitai Data Extractor")
        self.root.geometry("620x440")
        self.root.resizable(True, True)

        self.api_key = None
        self.download_dir = os.path.expanduser("~/civitai-download")
        self.extractor = None
        self.running = False

        self._build_ui()
        self._try_load_api_key()
        self._center_window()

    def _try_load_api_key(self):
        """Try default API key path, but don't block if missing."""
        default_path = os.path.expanduser("~/.api_key_civitai")
        if os.path.isfile(default_path):
            self.api_key_path_var.set(default_path)
            try:
                with open(default_path) as f:
                    self.api_key = f.read().strip()
                self._log("API key loaded from default path.")
            except Exception:
                pass

    def _build_ui(self):
        main = ttk.Frame(self.root, padding="15")
        main.pack(fill="both", expand=True)

        # Title
        title = ttk.Label(main, text="Civitai Data Extractor", font=("Sans", 16, "bold"))
        title.pack(anchor="w", pady=(0, 15))

        # --- API Key ---
        key_frame = ttk.LabelFrame(main, text="API Key", padding="8")
        key_frame.pack(fill="x", pady=(0, 10))

        key_row = ttk.Frame(key_frame)
        key_row.pack(fill="x")

        self.api_key_path_var = tk.StringVar(value="")
        self.key_entry = ttk.Entry(key_row, textvariable=self.api_key_path_var, font=("monospace", 9))
        self.key_entry.pack(side="left", fill="x", expand=True)

        browse_key_btn = ttk.Button(key_row, text="Browse", command=self._browse_key)
        browse_key_btn.pack(side="right", padx=(5, 0))

        load_key_btn = ttk.Button(key_row, text="Load", command=self._load_key, width=6)
        load_key_btn.pack(side="right", padx=(5, 0))

        self.key_status = ttk.Label(key_frame, text="No key loaded", foreground="red")
        self.key_status.pack(anchor="w", pady=(3, 0))

        # --- Model URL ---
        url_frame = ttk.Frame(main)
        url_frame.pack(fill="x", pady=(0, 5))

        ttk.Label(url_frame, text="Model URL:").pack(anchor="w")
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(url_frame, textvariable=self.url_var, font=("monospace", 10))
        self.url_entry.pack(fill="x", pady=(3, 0))
        self.url_entry.focus_set()

        self.url_entry.bind("<Control-v>", lambda e: self._paste_url())
        self.url_entry.bind("<Control-V>", lambda e: self._paste_url())

        # --- Save to ---
        dir_frame = ttk.Frame(main)
        dir_frame.pack(fill="x", pady=(10, 5))

        ttk.Label(dir_frame, text="Save to:").pack(anchor="w")
        dir_row = ttk.Frame(dir_frame)
        dir_row.pack(fill="x", pady=(3, 0))

        self.dir_var = tk.StringVar(value=self.download_dir)
        self.dir_entry = ttk.Entry(dir_row, textvariable=self.dir_var, font=("monospace", 9))
        self.dir_entry.pack(side="left", fill="x", expand=True)

        browse_dir_btn = ttk.Button(dir_row, text="Browse", command=self._browse_dir)
        browse_dir_btn.pack(side="right", padx=(5, 0))

        # --- Download button ---
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill="x", pady=(15, 10))

        self.dl_btn = ttk.Button(btn_frame, text="Download", command=self._start_download)
        self.dl_btn.pack(side="left", ipadx=20)

        # --- Status ---
        status_frame = ttk.LabelFrame(main, text="Status", padding="8")
        status_frame.pack(fill="both", expand=True)

        self.status_text = tk.Text(
            status_frame, height=8, font=("monospace", 9),
            bg="#1e1e1e", fg="#d4d4d4", insertbackground="#d4d4d4",
            relief="flat", borderwidth=0, wrap="word",
        )
        self.status_text.pack(fill="both", expand=True)

        self.progress = ttk.Progressbar(main, mode="indeterminate", length=200)

    def _center_window(self):
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"+{x}+{y}")

    def _paste_url(self):
        try:
            clip = self.root.clipboard_get()
            if clip:
                self.url_var.set(clip.strip())
        except tk.TclError:
            pass

    def _browse_key(self):
        path = filedialog.askopenfilename(
            title="Select API key file",
            initialdir=os.path.expanduser("~"),
        )
        if path:
            self.api_key_path_var.set(path)

    def _load_key(self):
        path = self.api_key_path_var.get().strip()
        if not path:
            messagebox.showwarning("No Path", "Select or enter an API key file path first.")
            return
        if not os.path.isfile(path):
            messagebox.showerror("Not Found", f"No file at:\n{path}")
            return
        try:
            with open(path) as f:
                key = f.read().strip()
            if not key:
                messagebox.showerror("Empty", "The file is empty.")
                return
            self.api_key = key
            self.key_status.configure(text=f"✓ Loaded: {os.path.basename(path)}", foreground="green")
            self._log(f"API key loaded: {path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read key file:\n{e}")

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.dir_var.get())
        if d:
            self.dir_var.set(d)

    def _log(self, text: str):
        self.status_text.insert("end", text + "\n")
        self.status_text.see("end")

    def _start_download(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Paste a civitai.red model URL first.")
            return
        if "civitai" not in url:
            messagebox.showwarning("Not Civitai", "URL doesn't look like a civitai model page.")
            return
        if not self.api_key:
            messagebox.showwarning("No API Key", "Load an API key file first (top section).")
            return
        self.download_dir = self.dir_var.get().strip()
        if not self.download_dir:
            messagebox.showwarning("Missing Path", "Set a download folder.")
            return
        if self.running:
            return

        self.running = True
        self.dl_btn.configure(state="disabled", text="Downloading...")
        self.progress.pack(fill="x", pady=(5, 0))
        self.progress.start(10)

        thread = threading.Thread(target=self._run_download, args=(url,), daemon=True)
        thread.start()

    def _run_download(self, url: str):
        try:
            self.extractor = CivitaiExtractor(
                api_key=self.api_key,
                download_dir=self.download_dir,
            )
            result = self.extractor.process(url)
            self.root.after(0, lambda: self._on_success(result))
        except Exception as e:
            self.root.after(0, lambda: self._on_error(str(e)))

    def _on_success(self, result: dict):
        self.running = False
        self.progress.stop()
        self.progress.pack_forget()
        self.dl_btn.configure(state="normal", text="Download")
        self._log(f"✓ {result['model_name']}")
        self._log(f"  File: {os.path.basename(result['file'])}")
        self._log(f"  Keywords: {result['keyword_count']} lines")
        self._log(f"  Saved to: {self.download_dir}")
        self._log("─" * 50)

    def _on_error(self, error: str):
        self.running = False
        self.progress.stop()
        self.progress.pack_forget()
        self.dl_btn.configure(state="normal", text="Download")
        self._log(f"✗ Error: {error}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = CivitaiGUI()
    app.run()
