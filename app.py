from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from youtube_mp3 import download_mp3, validate_youtube_url


APP_TITLE = "YouTube → MP3（更新版）"
MAX_DOWNLOAD_RETRIES = 3
SETTINGS_FILE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "YouTubeMp3" / "settings.json"
BG = "#f5f3ef"
CARD = "#ffffff"
TEXT = "#202124"
MUTED = "#6b7280"
ACCENT = "#e11d48"
ACCENT_ACTIVE = "#be123c"


def load_last_output() -> str:
    default = str(Path.home() / "Downloads")
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        saved = data.get("last_output_dir")
        return saved if isinstance(saved, str) and saved.strip() else default
    except (OSError, ValueError, TypeError):
        return default


def save_last_output(output_dir: str) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps({"last_output_dir": output_dir}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class YouTubeMp3App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("720x590")
        self.minsize(620, 530)
        self.configure(bg=BG)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.downloading = False
        self.url_var = tk.StringVar()
        self.url_list: list[str] = []
        self.url_list_var = tk.StringVar(value="URLリスト未読込")
        self.url_list_folder_name = ""
        self.output_var = tk.StringVar(value=load_last_output())
        self.quality_var = tk.StringVar(value="320 kbps")
        self.playlist_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="URLを貼り付けてください")
        self.percent_var = tk.DoubleVar(value=0)

        self._configure_styles()
        self._build_ui()
        self.after(100, self._drain_events)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Yu Gothic UI", 10))
        style.configure("Card.TLabel", background=CARD, foreground=TEXT, font=("Yu Gothic UI", 10))
        style.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=("Yu Gothic UI", 9))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Yu Gothic UI", 24, "bold"))
        style.configure("Subtitle.TLabel", background=BG, foreground=MUTED, font=("Yu Gothic UI", 10))
        style.configure("Accent.TButton", background=ACCENT, foreground="white", font=("Yu Gothic UI", 11, "bold"), padding=(18, 10), borderwidth=0)
        style.map("Accent.TButton", background=[("active", ACCENT_ACTIVE), ("disabled", "#d1d5db")])
        style.configure("TButton", font=("Yu Gothic UI", 9), padding=(10, 7))
        style.configure("TEntry", padding=8, fieldbackground="#fafafa")
        style.configure("TCombobox", padding=6)
        style.configure("Horizontal.TProgressbar", troughcolor="#ebe7e1", background=ACCENT, thickness=10)
        style.configure("Card.TCheckbutton", background=CARD, foreground=TEXT, font=("Yu Gothic UI", 9))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=(34, 25))
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="YouTube → MP3", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="動画の音声を、かんたんにMP3として保存", style="Subtitle.TLabel").pack(anchor="w", pady=(2, 20))

        card = ttk.Frame(outer, style="Card.TFrame", padding=24)
        card.pack(fill="both", expand=True)

        ttk.Label(card, text="YouTube URL", style="Card.TLabel").pack(anchor="w")
        url_row = ttk.Frame(card, style="Card.TFrame")
        url_row.pack(fill="x", pady=(7, 17))
        self.url_entry = ttk.Entry(url_row, textvariable=self.url_var, font=("Yu Gothic UI", 10))
        self.url_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(url_row, text="貼り付け", command=self._paste).pack(side="left", padx=(8, 0))

        list_row = ttk.Frame(card, style="Card.TFrame")
        list_row.pack(fill="x", pady=(0, 17))
        ttk.Button(list_row, text="TXTからURLを読み込む…", command=self._load_url_list).pack(side="left")
        ttk.Label(list_row, textvariable=self.url_list_var, style="Muted.TLabel").pack(side="left", padx=(10, 0))
        self.clear_list_button = ttk.Button(list_row, text="解除", command=self._clear_url_list, state="disabled")
        self.clear_list_button.pack(side="right")

        ttk.Label(card, text="保存先", style="Card.TLabel").pack(anchor="w")
        folder_row = ttk.Frame(card, style="Card.TFrame")
        folder_row.pack(fill="x", pady=(7, 17))
        ttk.Entry(folder_row, textvariable=self.output_var).pack(side="left", fill="x", expand=True)
        ttk.Button(folder_row, text="選択…", command=self._choose_folder).pack(side="left", padx=(8, 0))

        options = ttk.Frame(card, style="Card.TFrame")
        options.pack(fill="x")
        quality_box = ttk.Frame(options, style="Card.TFrame")
        quality_box.pack(side="left", fill="x", expand=True)
        ttk.Label(quality_box, text="音質", style="Card.TLabel").pack(anchor="w")
        quality = ttk.Combobox(quality_box, textvariable=self.quality_var, state="readonly", values=("128 kbps", "192 kbps", "256 kbps", "320 kbps"), width=16)
        quality.pack(anchor="w", pady=(7, 0))
        ttk.Checkbutton(options, text="プレイリスト全体を保存", variable=self.playlist_var, style="Card.TCheckbutton").pack(side="right", anchor="s", pady=(0, 7))

        # Keep the primary action directly under the inputs. If the window is
        # short (or Windows display scaling is high), the expanding log area
        # can no longer push this button below the visible edge.
        actions = ttk.Frame(card, style="Card.TFrame")
        actions.pack(fill="x", pady=(18, 0))
        ttk.Button(actions, text="保存先を開く", command=self._open_output).pack(side="left")
        self.download_button = ttk.Button(actions, text="MP3をダウンロード", command=self._start_download, style="Accent.TButton")
        self.download_button.pack(side="right")

        ttk.Separator(card).pack(fill="x", pady=16)
        self.progress = ttk.Progressbar(card, variable=self.percent_var, maximum=100, mode="determinate")
        self.progress.pack(fill="x")
        ttk.Label(card, textvariable=self.status_var, style="Muted.TLabel").pack(anchor="w", pady=(8, 10))

        self.log = tk.Text(card, height=7, wrap="word", state="disabled", relief="flat", bg="#fafafa", fg=MUTED, font=("Yu Gothic UI", 9), padx=10, pady=8)
        self.log.pack(fill="both", expand=True)

        ttk.Label(outer, text="保存する権利のあるコンテンツにのみ使用してください。", style="Subtitle.TLabel").pack(anchor="center", pady=(14, 0))
        self.url_entry.focus_set()

    def _paste(self) -> None:
        try:
            self.url_var.set(self.clipboard_get().strip())
        except tk.TclError:
            pass

    def _load_url_list(self) -> None:
        selected = filedialog.askopenfilename(
            title="URLが書かれたテキストファイルを選択",
            filetypes=(("テキストファイル", "*.txt"), ("すべてのファイル", "*.*")),
        )
        if not selected:
            return

        try:
            raw = Path(selected).read_bytes()
            try:
                contents = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                contents = raw.decode("cp932")
        except (OSError, UnicodeDecodeError) as exc:
            messagebox.showerror(APP_TITLE, f"テキストファイルを読み込めませんでした。\n{exc}")
            return

        urls: list[str] = []
        for line_number, line in enumerate(contents.splitlines(), start=1):
            candidate = line.strip()
            if not candidate or candidate.startswith("#"):
                continue
            try:
                urls.append(validate_youtube_url(candidate))
            except ValueError as exc:
                messagebox.showerror(
                    APP_TITLE,
                    f"{line_number}行目のURLを確認してください。\n{exc}\n\n{candidate}",
                )
                return

        if not urls:
            messagebox.showwarning(APP_TITLE, "有効なURLが見つかりませんでした。")
            return

        folder_name = Path(selected).stem
        folder_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", folder_name).rstrip(" .")
        if not folder_name or folder_name.split(".", 1)[0].upper() in {
            "CON", "PRN", "AUX", "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }:
            folder_name = f"{folder_name or 'URLリスト'}_"

        self.url_list = urls
        self.url_list_folder_name = folder_name
        self.url_list_var.set(f"{len(urls)}件を読込済み → {folder_name} フォルダへ保存")
        self.clear_list_button.configure(state="normal")
        self._update_download_button_label()

    def _clear_url_list(self) -> None:
        self.url_list.clear()
        self.url_list_folder_name = ""
        self.url_list_var.set("URLリスト未読込")
        self.clear_list_button.configure(state="disabled")
        self._update_download_button_label()

    def _update_download_button_label(self) -> None:
        if self.url_list:
            self.download_button.configure(text=f"{len(self.url_list)}件を順番にダウンロード")
        else:
            self.download_button.configure(text="MP3をダウンロード")

    def _choose_folder(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_var.get() or str(Path.home()))
        if selected:
            self.output_var.set(selected)
            try:
                save_last_output(selected)
            except OSError:
                pass

    def _open_output(self, output_dir: str | None = None) -> None:
        folder = Path(output_dir or self.output_var.get()).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)  # type: ignore[attr-defined]

    def _append_log(self, message: str) -> None:
        clean = message.strip()
        if not clean:
            return
        self.log.configure(state="normal")
        self.log.insert("end", clean + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _start_download(self) -> None:
        if self.downloading:
            return
        if self.url_list:
            urls = list(self.url_list)
        else:
            try:
                urls = [validate_youtube_url(self.url_var.get())]
            except ValueError as exc:
                messagebox.showwarning(APP_TITLE, str(exc))
                self.url_entry.focus_set()
                return

        output = self.output_var.get().strip()
        if not output:
            messagebox.showwarning(APP_TITLE, "保存先を選択してください。")
            return

        try:
            save_last_output(output)
        except OSError:
            # A settings write failure should not block the download itself.
            pass

        if self.url_list:
            output = str(Path(output) / self.url_list_folder_name)

        self.downloading = True
        self.download_button.configure(state="disabled")
        self.percent_var.set(0)
        self.status_var.set(f"準備しています…（全{len(urls)}件）")
        self._append_log(f"ダウンロードを開始します。全{len(urls)}件を記載順に処理します。")
        self._append_log(f"保存先: {output}")

        thread = threading.Thread(
            target=self._worker,
            args=(urls, output, self.quality_var.get(), self.playlist_var.get()),
            daemon=True,
        )
        thread.start()

    def _worker(self, urls: list[str], output: str, quality: str, playlist: bool) -> None:
        errors: list[tuple[int, str, str]] = []
        succeeded = 0
        for index, url in enumerate(urls, start=1):
            self.events.put(("item", (index, len(urls), url)))
            for attempt in range(MAX_DOWNLOAD_RETRIES + 1):
                try:
                    download_mp3(
                        url,
                        output,
                        quality,
                        playlist,
                        progress_callback=lambda data: self.events.put(("progress", data)),
                        log_callback=lambda message: self.events.put(("log", message)),
                    )
                except Exception as exc:
                    if attempt < MAX_DOWNLOAD_RETRIES:
                        retry_number = attempt + 1
                        wait_seconds = retry_number
                        self.events.put(("retry", (index, len(urls), retry_number, wait_seconds)))
                        self.events.put(("log", f"{index}/{len(urls)}件目に失敗。{wait_seconds}秒後に再試行します（{retry_number}/{MAX_DOWNLOAD_RETRIES}回目）"))
                        time.sleep(wait_seconds)
                        continue
                    errors.append((index, url, str(exc)))
                    self.events.put(("log", f"{index}/{len(urls)}件目は{MAX_DOWNLOAD_RETRIES}回再試行後も失敗: {exc}"))
                else:
                    succeeded += 1
                    break
        self.events.put(("done", {"output": output, "total": len(urls), "succeeded": succeeded, "errors": errors}))

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "item":
                    index, total, _url = payload  # type: ignore[misc]
                    self.percent_var.set(0)
                    self.status_var.set(f"{index}/{total}件目を処理中…")
                elif kind == "retry":
                    index, total, retry_number, wait_seconds = payload  # type: ignore[misc]
                    self.percent_var.set(0)
                    self.status_var.set(f"{index}/{total}件目: {retry_number}/{MAX_DOWNLOAD_RETRIES}回目の再試行まで{wait_seconds}秒待機")
                elif kind == "progress":
                    self._update_progress(payload)  # type: ignore[arg-type]
                elif kind == "error":
                    self._finish()
                    self.status_var.set("エラーが発生しました")
                    self._append_log(str(payload))
                    messagebox.showerror(APP_TITLE, str(payload))
                elif kind == "done":
                    result = payload  # type: ignore[assignment]
                    self.percent_var.set(100 if result["succeeded"] == result["total"] else 0)
                    self.status_var.set(f"完了: {result['succeeded']}/{result['total']}件成功")
                    self._append_log(f"処理が完了しました。成功 {result['succeeded']}件 / 全{result['total']}件")
                    for index, url, error in result["errors"]:
                        self._append_log(f"失敗 ({index}件目): {url} — {error}")
                    self._finish()
                    if result["errors"]:
                        messagebox.showwarning(APP_TITLE, f"{result['total']}件中{result['succeeded']}件を保存しました。\n失敗したURLはログ欄をご確認ください。")
                    elif messagebox.askyesno(APP_TITLE, f"{result['succeeded']}件の保存が完了しました。\n保存先を開きますか？"):
                        self._open_output(result["output"])
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _update_progress(self, data: dict) -> None:
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = data.get("downloaded_bytes", 0)
            if total:
                percent = min(100.0, downloaded / total * 100)
                self.percent_var.set(percent)
                speed = data.get("_speed_str", "").strip()
                eta = data.get("_eta_str", "").strip()
                detail = f"{percent:.1f}%"
                if speed:
                    detail += f"  •  {speed}"
                if eta:
                    detail += f"  •  残り {eta}"
                self.status_var.set(detail)
            else:
                self.status_var.set("ダウンロード中…")
        elif status == "finished":
            self.percent_var.set(100)
            self.status_var.set("MP3に変換しています…")

    def _finish(self) -> None:
        self.downloading = False
        self.download_button.configure(state="normal")
        self._update_download_button_label()


if __name__ == "__main__":
    YouTubeMp3App().mainloop()
