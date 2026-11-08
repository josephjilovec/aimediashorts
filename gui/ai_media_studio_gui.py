"""
AI Media & Shorts Studio — Modern Desktop Control Center GUI
Author: Joseph Jilovec (JJ)
"""

import sys
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from core import config
from core import auto_shorts_pipeline as asp
from core import universal_media_inbox as umi

BOT_QUEUES = [
    ("Twitter / X", "Twitter_Main_JosephJilovec"),
    ("Facebook", "Facebook"),
    ("Bluesky", "Bluesky"),
    ("Tumblr", "Tumblr"),
    ("Mastodon", "Mastodon"),
    ("LinkedIn", "LinkedIn"),
    ("Twitter (Alt)", "Twitter_AltAccount_SpaceMothership"),
    ("Twitter (CannaLog)", "Twitter_CannaLog"),
]


class AIMediaStudioGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("AI Media & Shorts Studio — Control Center")
        self.root.geometry("960x690")
        self.root.configure(bg="#0f172a")
        self.is_running_job = False
        self.last_log_size = 0

        self._build_ui()
        self._refresh_stats()
        self._poll_log()

    def _build_ui(self):
        header = tk.Frame(self.root, bg="#1e293b", padx=20, pady=14)
        header.pack(fill=tk.X)

        title_lbl = tk.Label(
            header,
            text="🎬 AI Media & Auto-Shorts Studio",
            font=("Segoe UI", 16, "bold"),
            fg="#f8fafc",
            bg="#1e293b"
        )
        title_lbl.pack(side=tk.LEFT)

        self.status_badge = tk.Label(
            header,
            text="● AI Curator: ACTIVE  |  Privacy Shield: ON  |  Auto-Cleanup: ON",
            font=("Segoe UI", 9, "bold"),
            fg="#34d399",
            bg="#1e293b"
        )
        self.status_badge.pack(side=tk.RIGHT)

        sub_bar = tk.Frame(self.root, bg="#0f172a", padx=20, pady=8)
        sub_bar.pack(fill=tk.X)
        tk.Label(
            sub_bar,
            text=(
                "How it works: Videos & photos dropped into Drive or imported here are curated automatically.\n"
                "The AI filters screenshots/blurry photos, picks the #1 sharpest photo per burst, slices videos into 9:16 Shorts, and routes to bot queues."
            ),
            font=("Segoe UI", 9),
            fg="#94a3b8",
            bg="#0f172a",
            justify=tk.LEFT
        ).pack(anchor="w")

        btn_frame = tk.Frame(self.root, bg="#0f172a", padx=20, pady=8)
        btn_frame.pack(fill=tk.X)

        btn_style = {
            "font": ("Segoe UI", 10, "bold"),
            "bd": 0,
            "padx": 14,
            "pady": 10,
            "cursor": "hand2"
        }

        self.btn_scan_now = tk.Button(
            btn_frame,
            text="⚡ Scan & Auto-Clip Media Now",
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#1d4ed8",
            activeforeground="#ffffff",
            command=self.run_scan_now,
            **btn_style
        )
        self.btn_scan_now.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_folder = tk.Button(
            btn_frame,
            text="📂 Import Folder (AI Pick Best & Clip)",
            bg="#059669",
            fg="#ffffff",
            activebackground="#047857",
            activeforeground="#ffffff",
            command=self.import_local_folder,
            **btn_style
        )
        self.btn_folder.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_auth = tk.Button(
            btn_frame,
            text="🔑 Authorize Google OAuth",
            bg="#475569",
            fg="#ffffff",
            activebackground="#334155",
            activeforeground="#ffffff",
            command=self.run_google_auth,
            **btn_style
        )
        self.btn_auth.pack(side=tk.LEFT, padx=(0, 10))

        q_outer = tk.Frame(self.root, bg="#0f172a", padx=20, pady=8)
        q_outer.pack(fill=tk.X)

        tk.Label(
            q_outer,
            text="LIVE BOT MEDIA QUEUES (FIFO — Auto-Deleted After Live Post):",
            font=("Segoe UI", 9, "bold"),
            fg="#cbd5e1",
            bg="#0f172a"
        ).pack(anchor="w", pady=(0, 6))

        cards_row = tk.Frame(q_outer, bg="#0f172a")
        cards_row.pack(fill=tk.X)

        self.queue_labels = {}
        for idx, (label_text, folder_name) in enumerate(BOT_QUEUES):
            card = tk.Frame(cards_row, bg="#1e293b", padx=10, pady=8, highlightbackground="#334155", highlightthickness=1)
            card.grid(row=0, column=idx, padx=4, sticky="nsew")
            cards_row.grid_columnconfigure(idx, weight=1)

            tk.Label(card, text=label_text, font=("Segoe UI", 8, "bold"), fg="#94a3b8", bg="#1e293b").pack()
            cnt_lbl = tk.Label(card, text="0", font=("Segoe UI", 14, "bold"), fg="#38bdf8", bg="#1e293b")
            cnt_lbl.pack(pady=(2, 0))
            self.queue_labels[folder_name] = cnt_lbl

        log_frame = tk.Frame(self.root, bg="#0f172a", padx=20, pady=10)
        log_frame.pack(fill=tk.BOTH, expand=True)

        log_header = tk.Frame(log_frame, bg="#0f172a")
        log_header.pack(fill=tk.X, pady=(0, 4))

        tk.Label(
            log_header,
            text="LIVE PIPELINE & AI CURATOR LOG:",
            font=("Segoe UI", 9, "bold"),
            fg="#cbd5e1",
            bg="#0f172a"
        ).pack(side=tk.LEFT)

        self.job_indicator = tk.Label(
            log_header,
            text="Idle — Ready",
            font=("Segoe UI", 9, "bold"),
            fg="#94a3b8",
            bg="#0f172a"
        )
        self.job_indicator.pack(side=tk.RIGHT)

        self.log_text = tk.Text(
            log_frame,
            bg="#020617",
            fg="#e2e8f0",
            font=("Consolas", 9),
            bd=0,
            padx=12,
            pady=10,
            wrap=tk.WORD
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _refresh_stats(self):
        try:
            for _, folder_name in BOT_QUEUES:
                q_dir = config.ALL_BOTS_INBOX / folder_name
                count = 0
                if q_dir.exists():
                    count = sum(
                        1 for f in q_dir.iterdir()
                        if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in umi.ALL_MEDIA_EXTS
                    )
                lbl = self.queue_labels.get(folder_name)
                if lbl:
                    lbl.configure(text=str(count), fg="#34d399" if count > 0 else "#64748b")
        except Exception:
            pass
        self.root.after(4000, self._refresh_stats)

    def _poll_log(self):
        try:
            if config.LOG_FILE.exists():
                sz = config.LOG_FILE.stat().st_size
                if sz != self.last_log_size:
                    lines = config.LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
                    self.log_text.delete("1.0", tk.END)
                    self.log_text.insert(tk.END, "\n".join(lines) + "\n")
                    self.log_text.see(tk.END)
                    self.last_log_size = sz
        except Exception:
            pass
        self.root.after(2500, self._poll_log)

    def _set_busy(self, busy: bool, label: str = ""):
        self.is_running_job = busy
        if busy:
            self.job_indicator.configure(text=f"⏳ {label}...", fg="#fbbf24")
        else:
            self.job_indicator.configure(text="✓ Ready", fg="#34d399")

    def run_scan_now(self):
        if self.is_running_job:
            return
        self._set_busy(True, "Scanning Media & Auto-Clipping Shorts")

        def _worker():
            try:
                asp.run_pipeline()
            except Exception as e:
                asp.logger.error(f"Scan error: {e}")
            finally:
                self.root.after(0, lambda: self._set_busy(False))

        threading.Thread(target=_worker, daemon=True).start()

    def import_local_folder(self):
        if self.is_running_job:
            return
        folder = filedialog.askdirectory(title="Select Folder of Photos/Videos for AI Curation & Clipping")
        if not folder:
            return

        self._set_busy(True, f"Curating from {Path(folder).name}")

        def _worker():
            try:
                config.ensure_workspace()
                src_dir = Path(folder)
                count = 0
                for entry in src_dir.iterdir():
                    if entry.is_file() and not entry.name.startswith(".") and entry.suffix.lower() in umi.ALL_MEDIA_EXTS:
                        shutil.copy2(entry, config.RAW_INBOX_DIR / entry.name)
                        count += 1
                asp.logger.info(f"[Import] Loaded {count} files from '{src_dir}'. Running AI Curator...")
                asp.run_pipeline()
            except Exception as e:
                asp.logger.error(f"Import error: {e}")
            finally:
                self.root.after(0, lambda: self._set_busy(False))

        threading.Thread(target=_worker, daemon=True).start()

    def run_google_auth(self):
        if self.is_running_job:
            return
        self._set_busy(True, "Launching Google OAuth in Browser")

        def _worker():
            try:
                from core import authorize_google
                authorize_google.main()
            except Exception as e:
                asp.logger.error(f"OAuth error: {e}")
            finally:
                self.root.after(0, lambda: self._set_busy(False))

        threading.Thread(target=_worker, daemon=True).start()


def launch():
    root = tk.Tk()
    AIMediaStudioGUI(root)
    root.mainloop()


if __name__ == "__main__":
    launch()
