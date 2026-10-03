"""YouTube audio downloader core.

Only download media that you own or have permission to save.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse


ProgressCallback = Callable[[dict], None]
LogCallback = Callable[[str], None]

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}


def validate_youtube_url(url: str) -> str:
    """Return a normalized YouTube URL or raise ValueError."""
    url = url.strip()
    if not url:
        raise ValueError("YouTubeのURLを入力してください。")

    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise ValueError("URLの形式が正しくありません。") from exc

    if parsed.scheme not in {"http", "https"} or parsed.hostname not in YOUTUBE_HOSTS:
        raise ValueError("youtube.com または youtu.be のURLを入力してください。")
    return url


def quality_to_yt_dlp(value: str) -> str:
    """Convert a UI quality value such as ``320 kbps`` to yt-dlp syntax."""
    match = re.search(r"(128|192|256|320)", value)
    if not match:
        raise ValueError("対応していない音質です。")
    # The Python postprocessor API expects a numeric kbps value (unlike the
    # CLI, where values such as ``320K`` are accepted).
    return match.group(1)


def prepare_ffmpeg() -> str | None:
    """Make bundled ffmpeg/ffprobe available and return their directory."""
    try:
        import static_ffmpeg

        static_ffmpeg.add_paths(weak=True)
    except ImportError:
        return None
    except Exception as exc:
        raise RuntimeError(
            "FFmpegの準備に失敗しました。setup.batをもう一度実行してください。"
        ) from exc

    executable = _find_executable("ffmpeg")
    return str(Path(executable).parent) if executable else None


def _find_executable(name: str) -> str | None:
    import shutil

    return shutil.which(name)


class YtDlpLogger:
    """Small logger adapter that keeps the UI output readable."""

    def __init__(self, callback: LogCallback | None = None):
        self.callback = callback or (lambda _message: None)

    def debug(self, message: str) -> None:
        # yt-dlp sends normal status messages through debug too.
        if not message.startswith("[debug]"):
            self.callback(message)

    def info(self, message: str) -> None:
        self.callback(message)

    def warning(self, message: str) -> None:
        self.callback(f"警告: {message}")

    def error(self, message: str) -> None:
        self.callback(f"エラー: {message}")


def download_mp3(
    url: str,
    output_dir: str | os.PathLike[str],
    quality: str = "320 kbps",
    allow_playlist: bool = False,
    progress_callback: ProgressCallback | None = None,
    log_callback: LogCallback | None = None,
) -> None:
    """Download a YouTube video's audio and convert it to MP3."""
    url = validate_youtube_url(url)
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)

    ffmpeg_dir = prepare_ffmpeg()
    if not ffmpeg_dir:
        raise RuntimeError("FFmpegが見つかりません。setup.batをもう一度実行してください。")

    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("yt-dlpが未インストールです。setup.batを実行してください。") from exc

    hooks = [progress_callback] if progress_callback else []
    options = {
        "format": "bestaudio/best",
        "outtmpl": str(destination / "%(title).180B [%(id)s].%(ext)s"),
        "windowsfilenames": True,
        "noplaylist": not allow_playlist,
        "ignoreerrors": False,
        "continuedl": True,
        "overwrites": False,
        "restrictfilenames": False,
        "ffmpeg_location": ffmpeg_dir,
        "logger": YtDlpLogger(log_callback),
        "progress_hooks": hooks,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": quality_to_yt_dlp(quality),
            },
            {"key": "FFmpegMetadata", "add_metadata": True},
        ],
    }

    with yt_dlp.YoutubeDL(options) as downloader:
        result = downloader.download([url])
        if result:
            raise RuntimeError("ダウンロードを完了できませんでした。")
