# =============================================================================
# BULK MUSIC DOWNLOADER - HIGH PERFORMANCE ENGINE v3.0
# =============================================================================
# This module powers the streaming downloader used by the Gradio UI.
# =============================================================================

import json
import logging
import os
import threading
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

# =============================================================================
# CONFIGURATION
# =============================================================================

WORKSPACE_ROOT = os.environ.get("MUSIC_DL_ROOT", str(Path.home() / "music_downloads"))
BASE_DIR = WORKSPACE_ROOT
ARCHIVE_FILE = os.environ.get("MUSIC_DL_ARCHIVE", str(Path(WORKSPACE_ROOT) / "downloaded.archive"))
HISTORY_FILE = os.path.join(WORKSPACE_ROOT, "download_history.json")
SETTINGS_FILE = os.path.join(WORKSPACE_ROOT, "user_settings.json")

MAX_WORKERS = int(os.environ.get("MUSIC_DL_WORKERS", "8"))
SOCKET_TIMEOUT = int(os.environ.get("MUSIC_DL_TIMEOUT", "15"))
CONCURRENT_FRAGMENTS = 8
BUFFER_SIZE = 1024 * 1024

for directory in [BASE_DIR, os.path.dirname(ARCHIVE_FILE)]:
    os.makedirs(directory, exist_ok=True)

# =============================================================================
# LOGGER
# =============================================================================

logger = logging.getLogger("MusicDownloader")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# =============================================================================
# DATA MODELS
# =============================================================================

class DownloadStatus(Enum):
    QUEUED = "queued"
    EXTRACTING = "extracting"
    DOWNLOADING = "downloading"
    CONVERTING = "converting"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class DownloadItem:
    id: str
    query: str
    url: str = ""
    status: DownloadStatus = DownloadStatus.QUEUED
    title: str = ""
    artist: str = ""
    duration: int = 0
    progress: float = 0.0
    speed: str = ""
    eta: str = ""
    error: str = ""
    file_path: str = ""

    def get_status_line(self) -> str:
        icons = {
            DownloadStatus.QUEUED: "[QUEUED]",
            DownloadStatus.EXTRACTING: "[EXTRACT]",
            DownloadStatus.DOWNLOADING: "[DOWNLOAD]",
            DownloadStatus.CONVERTING: "[CONVERT]",
            DownloadStatus.COMPLETED: "[COMPLETED]",
            DownloadStatus.FAILED: "[FAILED]",
            DownloadStatus.SKIPPED: "[SKIPPED]",
        }
        icon = icons.get(self.status, "[STATUS]")
        name = (self.title or self.query)[:40]
        speed = self.speed or "0B/s"

        if self.status == DownloadStatus.DOWNLOADING:
            return f"{icon} {name}... {self.progress:.0f}% | {speed}"
        if self.status == DownloadStatus.CONVERTING:
            return f"{icon} {name}... Converting to MP3"
        if self.status == DownloadStatus.COMPLETED:
            return f"{icon} {name} [Done]"
        if self.status == DownloadStatus.FAILED:
            return f"{icon} {name} - {self.error[:30]}"
        if self.status == DownloadStatus.SKIPPED:
            return f"{icon} {name} (already downloaded)"
        return f"{icon} {name}"


@dataclass
class DownloadSession:
    id: str
    started_at: str
    total: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    output_dir: str = ""
    zip_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "started_at": self.started_at,
            "total": self.total,
            "completed": self.completed,
            "failed": self.failed,
            "skipped": self.skipped,
            "output_dir": self.output_dir,
            "zip_path": self.zip_path,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DownloadSession":
        allowed = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**allowed)

# =============================================================================
# USER DATA
# =============================================================================

class UserDataManager:
    def __init__(self):
        self._lock = threading.Lock()
        self.settings = self._load_settings()
        self.history = self._load_history()

    def _load_settings(self) -> Dict[str, Any]:
        defaults = {"default_quality": "320", "embed_thumbnail": True, "auto_zip": True, "max_history": 50}
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    defaults.update(json.load(f))
        except Exception:
            pass
        return defaults

    def save_settings(self) -> None:
        with self._lock:
            try:
                with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.settings, f, indent=2)
            except Exception:
                pass

    def _load_history(self) -> List[DownloadSession]:
        if not os.path.exists(HISTORY_FILE):
            return []
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                sessions = data.get("sessions", [])
                return [DownloadSession.from_dict(s) for s in sessions]
        except Exception:
            return []

    def save_history(self) -> None:
        with self._lock:
            try:
                sessions = self.history[-self.settings.get("max_history", 50):]
                with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                    json.dump({"sessions": [s.to_dict() for s in sessions]}, f, indent=2)
            except Exception:
                pass

    def add_session(self, session: DownloadSession) -> None:
        self.history.append(session)
        self.save_history()

    def clear_history(self) -> None:
        self.history = []
        self.save_history()

    def get_recent_sessions(self, limit: int = 10) -> List[DownloadSession]:
        return list(reversed(self.history[-limit:]))

    def get_statistics(self) -> Dict[str, Any]:
        total = sum(s.completed for s in self.history)
        failed = sum(s.failed for s in self.history)
        skipped = sum(s.skipped for s in self.history)
        sessions = len(self.history)
        rate = f"{(total / max(total + failed, 1) * 100):.1f}%"
        return {
            "total_downloads": total,
            "total_failed": failed,
            "total_skipped": skipped,
            "total_sessions": sessions,
            "success_rate": rate,
        }

# =============================================================================
# MUSIC DOWNLOADER
# =============================================================================

class MusicDownloader:
    def __init__(self):
        self.is_running = False
        self._lock = threading.RLock()
        self.items: Dict[str, DownloadItem] = {}
        self.log_lines: List[str] = []
        self.stats = {"total": 0, "completed": 0, "failed": 0, "skipped": 0}
        self.current_session: Optional[DownloadSession] = None
        self.user_data = UserDataManager()
        self._yt_dlp: Any = None

    def _get_yt_dlp(self):
        if self._yt_dlp is None:
            import yt_dlp
            self._yt_dlp = yt_dlp
        return self._yt_dlp

    def reset(self) -> None:
        with self._lock:
            self.items.clear()
            self.log_lines.clear()
            self.stats = {"total": 0, "completed": 0, "failed": 0, "skipped": 0}

    def log(self, msg: str, level: str = "INFO") -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        prefixes = {
            "INFO": "[INFO]",
            "SUCCESS": "[OK]",
            "ERROR": "[ERR]",
            "WARNING": "[WARN]",
            "DOWNLOAD": "[DL]",
        }
        prefix = prefixes.get(level, "[INFO]")
        entry = f"[{timestamp}] {prefix} {msg}"
        with self._lock:
            self.log_lines.append(entry)
            if len(self.log_lines) > 200:
                self.log_lines = self.log_lines[-100:]
        getattr(logger, level.lower(), logger.info)(msg)

    def get_logs(self, limit: int = 30) -> str:
        with self._lock:
            return "\n".join(self.log_lines[-limit:])

    def parse_input(self, text: str) -> List[str]:
        return [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]

    def analyze_input_type(self, items: List[str]) -> str:
        if not items:
            return "Empty"
        if len(items) == 1:
            item = items[0]
            if item.startswith(("http://", "https://")):
                if any(token in item.lower() for token in ["list=", "playlist", "/sets/"]):
                    return "Playlist URL"
                return "Single URL"
            return "Search query"
        return f"Batch: {len(items)} items"

    def _extract_playlist_urls(self, url: str) -> List[Dict[str, Any]]:
        yt_dlp = self._get_yt_dlp()
        try:
            opts = {
                "extract_flat": "in_playlist",
                "quiet": True,
                "no_warnings": True,
                "ignoreerrors": True,
                "socket_timeout": SOCKET_TIMEOUT,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info and "entries" in info:
                    tracks = []
                    for entry in info.get("entries", []):
                        if not entry:
                            continue
                        url_value = entry.get("url") or entry.get("webpage_url")
                        tracks.append({
                            "url": url_value or f"https://youtube.com/watch?v={entry.get('id', '')}",
                            "title": entry.get("title", "Unknown"),
                            "duration": entry.get("duration", 0),
                        })
                    return tracks
                if info:
                    return [{
                        "url": info.get("webpage_url", url),
                        "title": info.get("title", "Unknown"),
                        "duration": info.get("duration", 0),
                    }]
        except Exception as error:
            self.log(f"Extraction error: {str(error)[:60]}", "ERROR")
        return [{"url": url, "title": url[:50], "duration": 0}]

    def _create_progress_hook(self, item: DownloadItem):
        def hook(data: Dict[str, Any]) -> None:
            status = data.get("status")
            if status == "downloading":
                pct = data.get("_percent_str", "0%").replace("%", "").strip()
                try:
                    item.progress = float(pct)
                except Exception:
                    item.progress = 0.0
                item.speed = data.get("_speed_str", "0B/s")
                item.eta = data.get("_eta_str", "")
                item.status = DownloadStatus.DOWNLOADING
            elif status == "finished":
                item.status = DownloadStatus.CONVERTING
                item.progress = 100.0
            elif status == "error":
                item.status = DownloadStatus.FAILED
        return hook

    def _download_single(self, item: DownloadItem, output_dir: str, quality: str, embed_thumb: bool) -> Tuple[bool, str]:
        yt_dlp = self._get_yt_dlp()
        url = item.url or item.query
        item.status = DownloadStatus.DOWNLOADING
        if not url.startswith(("http://", "https://")):
            url = f"ytsearch:{url}"
        opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": quality,
            }],
            "download_archive": ARCHIVE_FILE,
            "ignoreerrors": True,
            "quiet": True,
            "no_warnings": True,
            "no_color": True,
            "socket_timeout": SOCKET_TIMEOUT,
            "retries": 3,
            "fragment_retries": 3,
            "concurrent_fragment_downloads": CONCURRENT_FRAGMENTS,
            "buffersize": BUFFER_SIZE,
            "http_chunk_size": 10 * 1024 * 1024,
            "progress_hooks": [self._create_progress_hook(item)],
            "prefer_ffmpeg": True,
            "keepvideo": False,
            "writethumbnail": embed_thumb,
            "postprocessor_args": {"ffmpeg": ["-threads", "4"]},
        }
        if embed_thumb:
            opts["postprocessors"].extend([
                {"key": "EmbedThumbnail"},
                {"key": "FFmpegMetadata"},
            ])
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info:
                    item.title = info.get("title", item.title or "Unknown")
                    item.artist = info.get("artist", info.get("uploader", ""))
                    item.duration = info.get("duration", 0)
                    item.status = DownloadStatus.COMPLETED
                    return True, item.title
                return False, "No info extracted"
        except yt_dlp.utils.DownloadError as error:
            message = str(error)
            if "already" in message.lower():
                item.status = DownloadStatus.SKIPPED
                return False, "SKIPPED"
            item.status = DownloadStatus.FAILED
            item.error = message[:100]
            return False, message
        except Exception as error:
            item.status = DownloadStatus.FAILED
            item.error = str(error)[:100]
            return False, str(error)

    def download_batch_streaming(
        self,
        text_input: str,
        quality: str = "320",
        embed_thumbnail: bool = True,
    ) -> Generator[Tuple[str, str, Optional[str]], None, None]:
        self.reset()
        self.is_running = True
        raw_items = self.parse_input(text_input)
        if not raw_items:
            self.log("No valid inputs provided", "ERROR")
            self.is_running = False
            yield self._format_progress(), "No items", None
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(BASE_DIR, f"batch_{timestamp}")
        os.makedirs(output_dir, exist_ok=True)
        self.log(f"Analyzing {len(raw_items)} inputs", "INFO")
        yield self._format_progress(), "Extracting playlist information...", None
        all_tracks: List[Dict[str, Any]] = []
        for raw_item in raw_items:
            if not self.is_running:
                break
            if raw_item.startswith(("http://", "https://")) and any(token in raw_item.lower() for token in ["list=", "playlist", "/sets/"]):
                self.log(f"Extracting playlist: {raw_item[:50]}", "INFO")
                yield self._format_progress(), "Extracting playlist...", None
                all_tracks.extend(self._extract_playlist_urls(raw_item))
            else:
                all_tracks.append({"url": raw_item if raw_item.startswith(("http://", "https://")) else "", "title": raw_item, "duration": 0})
        if not all_tracks:
            self.log("No tracks discovered", "ERROR")
            self.is_running = False
            yield self._format_progress(), "No tracks found", None
            return
        for idx, track in enumerate(all_tracks):
            item = DownloadItem(
                id=f"{idx:04d}",
                query=track.get("title") or track.get("url", ""),
                url=track.get("url", ""),
                title=track.get("title", ""),
                duration=track.get("duration", 0),
            )
            self.items[item.id] = item
        self.stats["total"] = len(self.items)
        self.current_session = DownloadSession(
            id=str(uuid.uuid4())[:8],
            started_at=datetime.now().isoformat(),
            total=len(self.items),
            output_dir=output_dir,
        )
        self.log(f"Total tracks: {len(self.items)}", "INFO")
        self.log(f"Workers: {MAX_WORKERS} | Quality: {quality}kbps", "INFO")
        self.log(f"Output: {output_dir}", "INFO")
        self.log("-" * 60, "INFO")
        yield self._format_progress(), self._format_items_status(), None
        futures: Dict[Future, DownloadItem] = {}
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for item in self.items.values():
                if not self.is_running:
                    break
                futures[executor.submit(self._download_single, item, output_dir, quality, embed_thumbnail)] = item
            completed = 0
            for future in as_completed(futures):
                if not self.is_running:
                    break
                item = futures[future]
                completed += 1
                try:
                    success, result = future.result()
                except Exception as error:
                    success, result = False, str(error)
                    item.status = DownloadStatus.FAILED
                    item.error = str(error)[:100]
                if success:
                    self.stats["completed"] += 1
                    self.log(f"[{completed}/{len(self.items)}] Downloaded {item.title[:40]}", "SUCCESS")
                elif result == "SKIPPED":
                    self.stats["skipped"] += 1
                    self.log(f"[{completed}/{len(self.items)}] Skipped {item.title[:40]}", "WARNING")
                else:
                    self.stats["failed"] += 1
                    self.log(f"[{completed}/{len(self.items)}] Failed {item.title[:40]}", "ERROR")
                yield self._format_progress(), self._format_items_status(), None
        self.is_running = False
        self.log("-" * 60, "INFO")
        self.log("DOWNLOAD COMPLETE!", "SUCCESS")
        self.log(f"Downloaded: {self.stats['completed']}", "INFO")
        self.log(f"Skipped: {self.stats['skipped']}", "INFO")
        self.log(f"Failed: {self.stats['failed']}", "INFO")
        zip_path = None
        if self.stats["completed"] > 0 and self.user_data.settings.get("auto_zip", True):
            zip_path = self._create_zip(output_dir)
            if zip_path:
                self.log(f"ZIP created: {os.path.basename(zip_path)}", "SUCCESS")
                self.current_session.zip_path = zip_path
        self.current_session.completed = self.stats["completed"]
        self.current_session.failed = self.stats["failed"]
        self.current_session.skipped = self.stats["skipped"]
        self.user_data.add_session(self.current_session)
        yield self._format_progress(), self._format_items_status(), zip_path

    def _format_progress(self) -> str:
        total = self.stats["total"]
        if total == 0:
            return "Ready to download\n" + self.get_logs()
        processed = self.stats["completed"] + self.stats["failed"] + self.stats["skipped"]
        pct = processed / total * 100 if total else 0
        lines = [
            f"Progress: {processed}/{total} ({pct:.0f}%)",
            f"Completed: {self.stats['completed']} | Skipped: {self.stats['skipped']} | Failed: {self.stats['failed']}",
            "-" * 60,
        ]
        lines.append(self.get_logs(20))
        return "\n".join(lines)

    def _format_items_status(self) -> str:
        if not self.items:
            return "No items"
        lines = []
        for item in list(self.items.values())[:50]:
            lines.append(item.get_status_line())
        if len(self.items) > 50:
            lines.append(f"... and {len(self.items) - 50} more items")
        return "\n".join(lines)

    def _create_zip(self, source_dir: str) -> Optional[str]:
        zip_path = f"{source_dir}.zip"
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
                for root, _, files in os.walk(source_dir):
                    for file in files:
                        if file.lower().endswith((".mp3", ".m4a", ".opus", ".flac")):
                            file_path = os.path.join(root, file)
                            archive.write(file_path, os.path.relpath(file_path, source_dir))
            return zip_path
        except Exception as error:
            self.log(f"ZIP error: {error}", "ERROR")
            return None

    def stop(self) -> None:
        self.is_running = False
        self.log("Stop requested", "WARNING")

    def get_history_display(self) -> str:
        sessions = self.user_data.get_recent_sessions(10)
        if not sessions:
            return "No download history yet."
        lines = ["Recent Downloads:", "-" * 40]
        for session in sessions:
            date = session.started_at[:10] if session.started_at else "?"
            lines.append(
                f"[{date}] Total: {session.total} | Completed: {session.completed} | Skipped: {session.skipped} | Failed: {session.failed}"
            )
        return "\n".join(lines)

    def get_statistics_display(self) -> str:
        stats = self.user_data.get_statistics()
        lines = [
            "Statistics",
            "=" * 40,
            f"Downloads: {stats['total_downloads']}",
            f"Failed: {stats['total_failed']}",
            f"Skipped: {stats['total_skipped']}",
            f"Sessions: {stats['total_sessions']}",
            f"Success: {stats['success_rate']}",
        ]
        return "\n".join(lines)

# =============================================================================
# GRADIO UI
# =============================================================================

def _import_gradio():
    try:
        import gradio as gr
        return gr
    except ImportError:
        raise ImportError("Gradio not installed. Install it with: pip install gradio")


downloader = MusicDownloader()


def download_music_streaming(url_text: str, quality: str, embed_thumb: bool):
    if not url_text.strip():
        yield "Enter URLs or search queries!", "No items", None
        return
    for progress, items, zip_file in downloader.download_batch_streaming(
        url_text, quality=quality, embed_thumbnail=embed_thumb
    ):
        yield progress, items, zip_file


def stop_download():
    downloader.stop()
    return "Stopped!", downloader._format_items_status()


def clear_archive():
    if os.path.exists(ARCHIVE_FILE):
        os.remove(ARCHIVE_FILE)
        return "Archive cleared!"
    return "Archive was empty."


def get_file_list():
    if not os.path.exists(BASE_DIR):
        return "No downloads yet."
    files = []
    for root, _, filenames in os.walk(BASE_DIR):
        for file in filenames:
            if file.lower().endswith((".mp3", ".m4a", ".zip")):
                files.append(os.path.relpath(os.path.join(root, file), BASE_DIR))
    return "\n".join(files[:100]) if files else "No music files."


def get_history():
    return downloader.get_history_display()


def get_statistics():
    return downloader.get_statistics_display()


def clear_history():
    downloader.user_data.clear_history()
    return "History cleared!"


def update_settings(quality, embed_thumb, auto_zip, max_history):
    downloader.user_data.update_setting("default_quality", quality)
    downloader.user_data.update_setting("embed_thumbnail", embed_thumb)
    downloader.user_data.update_setting("auto_zip", auto_zip)
    downloader.user_data.update_setting("max_history", int(max_history))
    return "Settings saved!"


def create_ui():
    gr = _import_gradio()
    with gr.Blocks(title="Music Downloader v3.0") as app:
        gr.Markdown(
            "# High-Performance Music Downloader v3.0\n"
            "**Features:** 8x concurrent downloads | Playlist extraction | Real-time progress | Auto ZIP"
        )
        with gr.Tabs():
            with gr.TabItem("Download"):
                with gr.Row():
                    with gr.Column(scale=1):
                        url_input = gr.Textbox(
                            label="URLs / Search Queries",
                            placeholder=(
                                "Paste URLs or search queries (one per line)\n\n"
                                "Supports:\n"
                                "- YouTube videos & playlists\n"
                                "- SoundCloud tracks\n"
                                "- Search queries like 'Artist - Song'"
                            ),
                            lines=8,
                        )
                        with gr.Row():
                            quality = gr.Dropdown(
                                choices=["128", "192", "256", "320"],
                                value=downloader.user_data.settings.get("default_quality", "320"),
                                label="Quality (kbps)"
                            )
                            embed_thumb = gr.Checkbox(
                                value=downloader.user_data.settings.get("embed_thumbnail", True),
                                label="Album Art"
                            )
                        with gr.Row():
                            download_btn = gr.Button("Download", variant="primary", size="lg")
                            stop_btn = gr.Button("Stop", variant="stop")
                        zip_output = gr.File(label="Download ZIP")
                    with gr.Column(scale=1):
                        progress_output = gr.Textbox(
                            label="Progress",
                            lines=12,
                            interactive=False,
                        )
                        items_output = gr.Textbox(
                            label="Items Status",
                            lines=12,
                            interactive=False,
                        )
            with gr.TabItem("History"):
                with gr.Row():
                    with gr.Column():
                        history_output = gr.Textbox(
                            label="Recent Sessions",
                            lines=12,
                            interactive=False,
                            value=downloader.get_history_display(),
                        )
                        with gr.Row():
                            refresh_history = gr.Button("Refresh")
                            clear_history_btn = gr.Button("Clear")
                    with gr.Column():
                        stats_output = gr.Textbox(
                            label="Statistics",
                            lines=8,
                            interactive=False,
                            value=downloader.get_statistics_display(),
                        )
                        refresh_stats = gr.Button("Refresh")
            with gr.TabItem("Files"):
                file_output = gr.Textbox(label="Downloaded Files", lines=15, interactive=False)
                with gr.Row():
                    refresh_files = gr.Button("Refresh")
                    clear_archive_btn = gr.Button("Clear Archive")
                    archive_status = gr.Textbox(label="Status", lines=1, interactive=False)
            with gr.TabItem("Settings"):
                with gr.Row():
                    with gr.Column():
                        s_quality = gr.Dropdown(
                            choices=["128", "192", "256", "320"],
                            value=downloader.user_data.settings.get("default_quality", "320"),
                            label="Default Quality",
                        )
                        s_thumb = gr.Checkbox(
                            value=downloader.user_data.settings.get("embed_thumbnail", True),
                            label="Embed Album Art",
                        )
                        s_zip = gr.Checkbox(
                            value=downloader.user_data.settings.get("auto_zip", True),
                            label="Auto ZIP",
                        )
                        s_history = gr.Slider(10, 200, value=50, step=10, label="Max History")
                        save_btn = gr.Button("Save", variant="primary")
                        save_status = gr.Textbox(label="Status", lines=1, interactive=False)
                    with gr.Column():
                        gr.Markdown(
                            "### Performance Settings\n"
                            "\n"
                            "This downloader uses:\n"
                            "- **8 concurrent workers** for parallel downloads\n"
                            "- **Fast playlist extraction** to show all tracks upfront\n"
                            "- **Optimized FFmpeg** settings for quick conversion\n"
                            "- **Connection pooling** for faster requests\n"
                            "\n"
                            "**Tips:**\n"
                            "- Large playlists are extracted first, then downloaded in parallel\n"
                            "- Each track shows real-time download progress\n"
                            "- Already downloaded tracks are automatically skipped"
                        )
        download_btn.click(
            fn=download_music_streaming,
            inputs=[url_input, quality, embed_thumb],
            outputs=[progress_output, items_output, zip_output],
        )
        stop_btn.click(fn=stop_download, outputs=[progress_output, items_output])
        refresh_history.click(fn=get_history, outputs=[history_output])
        clear_history_btn.click(fn=clear_history, outputs=[history_output])
        refresh_stats.click(fn=get_statistics, outputs=[stats_output])
        refresh_files.click(fn=get_file_list, outputs=[file_output])
        clear_archive_btn.click(fn=clear_archive, outputs=[archive_status])
        save_btn.click(
            fn=update_settings,
            inputs=[s_quality, s_thumb, s_zip, s_history],
            outputs=[save_status],
        )
        app.load(fn=get_file_list, outputs=[file_output])
        app.load(fn=get_history, outputs=[history_output])
        app.load(fn=get_statistics, outputs=[stats_output])
    return app


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("HIGH-PERFORMANCE MUSIC DOWNLOADER v3.0")
    print("=" * 60)
    print(f"\nWorkers: {MAX_WORKERS} | Timeout: {SOCKET_TIMEOUT}s")
    print(f"Output: {BASE_DIR}")
    print("\nOpen: http://0.0.0.0:7860\n")
    app = create_ui()
    app.launch(
        share=False,
        show_error=True,
        server_name="0.0.0.0",
        server_port=7860,
    )
