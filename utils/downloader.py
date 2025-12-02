# =============================================================================
# BULK MUSIC DOWNLOADER - HIGH PERFORMANCE ENGINE v4.0
# =============================================================================
# Features: Proxy support | Genre categorization | Song catalog | File browser
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

# Import new modules
from utils.proxy import proxy_manager, ProxyConfig
from utils.catalog import music_catalog, SongEntry
from utils.filebrowser import file_browser
from utils.spotify import spotify_manager, is_spotify_url, parse_spotify_input

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

    def update_setting(self, key: str, value: Any) -> None:
        """Update a single setting."""
        self.settings[key] = value
        self.save_settings()

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
        self.custom_output_dir: Optional[str] = None  # Custom save location

    def set_output_directory(self, path: str) -> str:
        """Set custom output directory."""
        if os.path.isdir(path):
            self.custom_output_dir = path
            return f"Output directory set to: {path}"
        return f"Error: Invalid directory: {path}"

    def get_output_directory(self) -> str:
        """Get current output directory."""
        return self.custom_output_dir or BASE_DIR

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
                # Check for Spotify URLs
                if is_spotify_url(item):
                    if "playlist" in item or "album" in item:
                        return "Spotify Playlist/Album"
                    return "Spotify Track"
                if any(token in item.lower() for token in ["list=", "playlist", "/sets/"]):
                    return "Playlist URL"
                return "Single URL"
            return "Search query"
        # Check for mixed Spotify content
        spotify_count = sum(1 for i in items if is_spotify_url(i))
        if spotify_count > 0:
            return f"Batch: {len(items)} items ({spotify_count} Spotify)"
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
        # Apply proxy settings if configured
        proxy_opts = proxy_manager.get_yt_dlp_opts()
        opts.update(proxy_opts)
        
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
                    
                    # Add to catalog with genre detection
                    file_path = os.path.join(output_dir, f"{item.title}.mp3")
                    metadata = {
                        "source_url": url,
                        "uploader": info.get("uploader", ""),
                        "upload_date": info.get("upload_date", ""),
                        "description": info.get("description", "")[:200] if info.get("description") else "",
                        "tags": info.get("tags", []),
                        "categories": info.get("categories", []),
                    }
                    music_catalog.add_song(
                        title=item.title,
                        artist=item.artist,
                        file_path=file_path,
                        source_url=url,
                        info=metadata
                    )
                    
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
        base_output = self.custom_output_dir or BASE_DIR
        output_dir = os.path.join(base_output, f"batch_{timestamp}")
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


# =============================================================================
# NETWORK / PROXY FUNCTIONS
# =============================================================================

def get_network_info():
    """Get current network and IP information."""
    info = proxy_manager.get_network_info()
    lines = [
        "Network Information",
        "=" * 40,
        f"Current IP: {info.get('current_ip', 'Unknown')}",
        f"Location: {info.get('location', 'Unknown')}",
        f"ISP: {info.get('isp', 'Unknown')}",
        "",
        "Proxy Status",
        "-" * 40,
    ]
    if proxy_manager.config:
        lines.append(f"Type: {proxy_manager.config.proxy_type}")
        lines.append(f"Host: {proxy_manager.config.host}:{proxy_manager.config.port}")
        lines.append(f"Enabled: {'Yes' if proxy_manager.config.enabled else 'No'}")
    else:
        lines.append("No proxy configured")
    return "\n".join(lines)


def configure_proxy(proxy_type, host, port, username, password, enabled):
    """Configure proxy settings."""
    try:
        port_int = int(port) if port else 0
        if not host or port_int <= 0:
            # Leave a valid ProxyConfig with enabled=False so ProxyManager methods stay safe
            proxy_manager.config = ProxyConfig(enabled=False)
            proxy_manager.save_config()
            return "Proxy disabled (empty configuration)"
        
        config = ProxyConfig(
            proxy_type=proxy_type,
            host=host,
            port=port_int,
            username=username if username else None,
            password=password if password else None,
            enabled=enabled
        )
        proxy_manager.config = config
        proxy_manager.save_config()
        return f"Proxy configured: {proxy_type}://{host}:{port}"
    except Exception as e:
        return f"Error: {e}"


def test_proxy_connection():
    """Test proxy connection."""
    if not proxy_manager.config or not proxy_manager.config.enabled:
        return "No proxy configured"

    success, message = proxy_manager.test_proxy()
    return f"Test Result: {'SUCCESS' if success else 'FAILED'}\n{message}"


# =============================================================================
# CATALOG FUNCTIONS
# =============================================================================

def get_catalog_stats():
    """Get catalog statistics."""
    stats = music_catalog.get_statistics()
    lines = [
        "Music Catalog Statistics",
        "=" * 40,
        f"Total Songs: {stats['total_songs']}",
        f"Total Artists: {stats['total_artists']}",
        f"Total Duration: {stats['total_duration_formatted']}",
        "",
        "Genres",
        "-" * 40,
    ]
    for genre, count in sorted(stats['genres'].items(), key=lambda x: -x[1])[:15]:
        lines.append(f"  {genre}: {count}")
    return "\n".join(lines)


def search_catalog(query):
    """Search songs in catalog."""
    if not query.strip():
        return "Enter a search query"
    results = music_catalog.search_songs(query)
    if not results:
        return f"No songs found matching '{query}'"
    
    lines = [f"Found {len(results)} songs:"]
    for song in results[:30]:
        duration = f"{song.duration // 60}:{song.duration % 60:02d}" if song.duration else "?"
        lines.append(f"  [{song.unique_id[:8]}] {song.title} - {song.artist} ({duration}) [{song.genre}]")
    return "\n".join(lines)


def get_songs_by_genre(genre):
    """Get songs filtered by genre."""
    songs = music_catalog.get_songs_by_genre(genre)
    if not songs:
        return f"No songs in genre: {genre}"
    
    lines = [f"Genre: {genre} ({len(songs)} songs)"]
    for song in songs[:50]:
        duration = f"{song.duration // 60}:{song.duration % 60:02d}" if song.duration else "?"
        lines.append(f"  {song.title} - {song.artist} ({duration})")
    return "\n".join(lines)


def organize_catalog_by_genre(base_path):
    """Organize files by genre."""
    if not base_path.strip():
        base_path = os.path.join(BASE_DIR, "organized_by_genre")
    
    from utils.catalog import organize_by_genre
    result = organize_by_genre(base_path, music_catalog)
    return result


def get_genre_list():
    """Get list of available genres."""
    stats = music_catalog.get_statistics()
    genres = list(stats.get('genres', {}).keys())
    return genres if genres else ["Unknown"]


# =============================================================================
# FILE BROWSER FUNCTIONS  
# =============================================================================

def execute_terminal_command(command):
    """Execute command in file browser."""
    return file_browser.execute_command(command)


def get_current_directory():
    """Get current directory path."""
    return file_browser.pwd()


def browse_directory(path):
    """Browse to a directory and list contents."""
    if path:
        file_browser.cd(path)
    return file_browser.ls()


def set_download_location(path):
    """Set download location."""
    result = downloader.set_output_directory(path)
    file_browser.cd(path)
    return result


def get_directory_tree():
    """Get directory tree."""
    return file_browser.tree(max_depth=3)


def create_folder(name):
    """Create new folder."""
    return file_browser.mkdir(name)


# =============================================================================
# SPOTIFY FUNCTIONS
# =============================================================================

def get_spotify_status():
    """Get Spotify downloader status."""
    status = spotify_manager.get_status()
    lines = [
        "Spotify Downloader Status",
        "=" * 40,
        f"spotdl installed: {'Yes' if status['spotdl_installed'] else 'No - Install with: pip install spotdl'}",
        f"Currently downloading: {'Yes' if status['is_downloading'] else 'No'}",
        "",
        "Session Statistics",
        "-" * 40,
        f"Completed: {status['stats']['completed']}",
        f"Failed: {status['stats']['failed']}",
        f"Total: {status['stats']['total']}",
    ]
    return "\n".join(lines)


def download_spotify_streaming(url_text: str, audio_format: str, audio_quality: str):
    """Download Spotify tracks/playlists with streaming progress."""
    if not url_text.strip():
        yield "Enter Spotify URLs or search queries!", "No items"
        return
    
    if not spotify_manager.is_spotdl_installed():
        yield "spotdl not installed!\n\nInstall it with:\npip install spotdl", "Install spotdl first"
        return
    
    # Parse input
    items = parse_spotify_input(url_text)
    if not items:
        yield "No valid items found", "No items"
        return
    
    # Set output directory
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(downloader.get_output_directory(), f"spotify_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)
    
    spotify_manager.log(f"Starting Spotify download: {len(items)} items")
    spotify_manager.log(f"Output: {output_dir}")
    spotify_manager.log(f"Format: {audio_format} @ {audio_quality}")
    
    progress_lines = [f"Downloading {len(items)} item(s) to {output_dir}"]
    status_lines = []
    
    # Check if batch or single
    if len(items) == 1 and is_spotify_url(items[0]):
        # Single URL download
        for update in spotify_manager.download_url(items[0], output_dir, audio_format, audio_quality):
            status = update.get("status", "")
            message = update.get("message", "")
            
            if status == "completed":
                progress_lines.append(f"\n{message}")
                status_lines.append("[COMPLETED] " + message)
            elif status == "error":
                progress_lines.append(f"\n[ERROR] {message}")
                status_lines.append("[FAILED] " + message)
            elif status == "downloading":
                current = update.get("current_track", "")
                status_lines.append(f"[DOWNLOADING] {current}")
            elif status == "info":
                progress_lines.append(message)
            
            logs = spotify_manager.get_logs(15)
            yield "\n".join(progress_lines) + "\n\n" + logs, "\n".join(status_lines[-20:])
    else:
        # Batch download (multiple URLs or search queries)
        for update in spotify_manager.download_batch(items, output_dir, audio_format, audio_quality):
            status = update.get("status", "")
            message = update.get("message", "")
            batch_progress = update.get("batch_progress", "")
            
            if status == "batch_completed":
                completed = update.get("completed", 0)
                failed = update.get("failed", 0)
                progress_lines.append(f"\nBatch complete! {completed} downloaded, {failed} failed")
            elif status == "completed":
                status_lines.append(f"[COMPLETED] [{batch_progress}] {message}")
            elif status == "error":
                status_lines.append(f"[FAILED] [{batch_progress}] {message}")
            elif status == "downloading":
                current = update.get("current_track", "")
                status_lines.append(f"[DOWNLOADING] [{batch_progress}] {current}")
            
            logs = spotify_manager.get_logs(15)
            yield "\n".join(progress_lines) + "\n\n" + logs, "\n".join(status_lines[-20:])
    
    yield "\n".join(progress_lines) + "\n\nDownload complete!", "\n".join(status_lines[-20:])


def stop_spotify_download():
    """Stop Spotify download."""
    spotify_manager.stop_download()
    return "Download stopped!", "Stopped by user"


def get_spotify_logs():
    """Get Spotify download logs."""
    return spotify_manager.get_logs(30)


def create_ui():
    gr = _import_gradio()
    with gr.Blocks(title="Music Downloader v5.0") as app:
        gr.Markdown(
            "# High-Performance Music Downloader v5.0\n"
            "**Features:** Spotify support | Proxy | Genre categorization | Song catalog | File browser"
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
            
            # =====================================================================
            # SPOTIFY TAB - Spotify Downloads
            # =====================================================================
            with gr.TabItem("Spotify"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown(
                            "### Spotify Downloader\n"
                            "Download tracks, albums, and playlists from Spotify.\n\n"
                            "**Supported URLs:**\n"
                            "- `https://open.spotify.com/track/...`\n"
                            "- `https://open.spotify.com/album/...`\n"
                            "- `https://open.spotify.com/playlist/...`\n"
                            "- Or search: `Artist - Song`"
                        )
                        spotify_input = gr.Textbox(
                            label="Spotify URLs / Search Queries",
                            placeholder=(
                                "Paste Spotify URLs or search queries (one per line)\n\n"
                                "Examples:\n"
                                "https://open.spotify.com/track/...\n"
                                "https://open.spotify.com/playlist/...\n"
                                "Drake - God's Plan\n"
                                "The Weeknd - Blinding Lights"
                            ),
                            lines=8,
                        )
                        with gr.Row():
                            spotify_format = gr.Dropdown(
                                choices=["mp3", "m4a", "flac", "opus", "ogg", "wav"],
                                value="mp3",
                                label="Audio Format"
                            )
                            spotify_quality = gr.Dropdown(
                                choices=["128k", "192k", "256k", "320k"],
                                value="320k",
                                label="Audio Quality"
                            )
                        with gr.Row():
                            spotify_download_btn = gr.Button("Download from Spotify", variant="primary", size="lg")
                            spotify_stop_btn = gr.Button("Stop", variant="stop")
                    with gr.Column(scale=1):
                        spotify_progress = gr.Textbox(
                            label="Progress",
                            lines=12,
                            interactive=False,
                        )
                        spotify_status = gr.Textbox(
                            label="Track Status",
                            lines=12,
                            interactive=False,
                        )
                with gr.Row():
                    spotify_info = gr.Textbox(
                        label="Spotify Status",
                        lines=6,
                        interactive=False,
                        value=get_spotify_status()
                    )
                    refresh_spotify_btn = gr.Button("Refresh Status")
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
            
            # =====================================================================
            # NETWORK TAB - Proxy Configuration
            # =====================================================================
            with gr.TabItem("Network"):
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Proxy Configuration")
                        proxy_type = gr.Dropdown(
                            choices=["http", "https", "socks4", "socks5"],
                            value="http",
                            label="Proxy Type"
                        )
                        proxy_host = gr.Textbox(label="Host", placeholder="proxy.example.com")
                        proxy_port = gr.Textbox(label="Port", placeholder="8080")
                        proxy_user = gr.Textbox(label="Username (optional)", placeholder="user")
                        proxy_pass = gr.Textbox(label="Password (optional)", type="password")
                        proxy_enabled = gr.Checkbox(value=True, label="Enable Proxy")
                        with gr.Row():
                            apply_proxy_btn = gr.Button("Apply Proxy", variant="primary")
                            test_proxy_btn = gr.Button("Test Connection")
                        proxy_status = gr.Textbox(label="Status", lines=2, interactive=False)
                    with gr.Column():
                        gr.Markdown("### Network Information")
                        network_info = gr.Textbox(
                            label="Current Network Status",
                            lines=15,
                            interactive=False,
                            value=get_network_info()
                        )
                        refresh_network_btn = gr.Button("Refresh IP Info")
            
            # =====================================================================
            # CATALOG TAB - Music Library
            # =====================================================================
            with gr.TabItem("Catalog"):
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Music Catalog")
                        catalog_stats = gr.Textbox(
                            label="Catalog Statistics",
                            lines=15,
                            interactive=False,
                            value=get_catalog_stats()
                        )
                        refresh_catalog_btn = gr.Button("Refresh Stats")
                    with gr.Column():
                        gr.Markdown("### Search Songs")
                        search_input = gr.Textbox(label="Search", placeholder="Artist, title, or genre...")
                        search_btn = gr.Button("Search")
                        search_results = gr.Textbox(label="Results", lines=12, interactive=False)
                        
                        gr.Markdown("### Filter by Genre")
                        genre_dropdown = gr.Dropdown(
                            choices=get_genre_list(),
                            label="Select Genre"
                        )
                        filter_genre_btn = gr.Button("Filter")
                        genre_results = gr.Textbox(label="Songs", lines=8, interactive=False)
                with gr.Row():
                    gr.Markdown("### Organize Files by Genre")
                    organize_path = gr.Textbox(
                        label="Output Path",
                        placeholder="Leave empty for default location",
                        value=""
                    )
                    organize_btn = gr.Button("Organize by Genre")
                    organize_status = gr.Textbox(label="Status", lines=2, interactive=False)
            
            # =====================================================================
            # FILE BROWSER TAB - Terminal Interface
            # =====================================================================
            with gr.TabItem("File Browser"):
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Terminal")
                        current_dir_display = gr.Textbox(
                            label="Current Directory",
                            value=get_current_directory(),
                            interactive=False
                        )
                        terminal_input = gr.Textbox(
                            label="Command",
                            placeholder="Type command (ls, cd, mkdir, pwd, tree, find, help...)"
                        )
                        execute_btn = gr.Button("Execute", variant="primary")
                        terminal_output = gr.Textbox(
                            label="Output",
                            lines=15,
                            interactive=False,
                            value=file_browser.ls()
                        )
                    with gr.Column():
                        gr.Markdown("### Quick Actions")
                        new_folder_name = gr.Textbox(label="New Folder Name", placeholder="my_folder")
                        create_folder_btn = gr.Button("Create Folder")
                        folder_status = gr.Textbox(label="Status", lines=1, interactive=False)
                        
                        gr.Markdown("### Set Download Location")
                        download_loc_input = gr.Textbox(
                            label="Download Path",
                            placeholder="/home/user/Music",
                            value=downloader.get_output_directory()
                        )
                        set_location_btn = gr.Button("Set as Download Location", variant="primary")
                        location_status = gr.Textbox(label="Status", lines=1, interactive=False)
                        
                        gr.Markdown("### Directory Tree")
                        tree_output = gr.Textbox(label="Tree View", lines=10, interactive=False)
                        show_tree_btn = gr.Button("Show Tree")
        download_btn.click(
            fn=download_music_streaming,
            inputs=[url_input, quality, embed_thumb],
            outputs=[progress_output, items_output, zip_output],
        )
        stop_btn.click(fn=stop_download, outputs=[progress_output, items_output])
        
        # Spotify tab events
        spotify_download_btn.click(
            fn=download_spotify_streaming,
            inputs=[spotify_input, spotify_format, spotify_quality],
            outputs=[spotify_progress, spotify_status]
        )
        spotify_stop_btn.click(fn=stop_spotify_download, outputs=[spotify_progress, spotify_status])
        refresh_spotify_btn.click(fn=get_spotify_status, outputs=[spotify_info])
        
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
        
        # Network tab events
        apply_proxy_btn.click(
            fn=configure_proxy,
            inputs=[proxy_type, proxy_host, proxy_port, proxy_user, proxy_pass, proxy_enabled],
            outputs=[proxy_status]
        )
        test_proxy_btn.click(fn=test_proxy_connection, outputs=[proxy_status])
        refresh_network_btn.click(fn=get_network_info, outputs=[network_info])
        
        # Catalog tab events
        refresh_catalog_btn.click(fn=get_catalog_stats, outputs=[catalog_stats])
        search_btn.click(fn=search_catalog, inputs=[search_input], outputs=[search_results])
        filter_genre_btn.click(fn=get_songs_by_genre, inputs=[genre_dropdown], outputs=[genre_results])
        organize_btn.click(fn=organize_catalog_by_genre, inputs=[organize_path], outputs=[organize_status])
        
        # File browser tab events
        def run_command_and_update(cmd):
            output = execute_terminal_command(cmd)
            current = get_current_directory()
            return output, current
        
        execute_btn.click(
            fn=run_command_and_update,
            inputs=[terminal_input],
            outputs=[terminal_output, current_dir_display]
        )
        create_folder_btn.click(fn=create_folder, inputs=[new_folder_name], outputs=[folder_status])
        set_location_btn.click(fn=set_download_location, inputs=[download_loc_input], outputs=[location_status])
        show_tree_btn.click(fn=get_directory_tree, outputs=[tree_output])
        
        app.load(fn=get_file_list, outputs=[file_output])
        app.load(fn=get_history, outputs=[history_output])
        app.load(fn=get_statistics, outputs=[stats_output])
    return app


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("HIGH-PERFORMANCE MUSIC DOWNLOADER v5.0")
    print("=" * 60)
    print(f"\nWorkers: {MAX_WORKERS} | Timeout: {SOCKET_TIMEOUT}s")
    print(f"Output: {BASE_DIR}")
    print("\nFeatures:")
    print("  - Spotify tracks, albums & playlists")
    print("  - YouTube videos & playlists")
    print("  - Proxy support with IP detection")
    print("  - Genre categorization")
    print("  - Song catalog with unique IDs")
    print("  - File browser / Terminal")
    print("\nOpen: http://0.0.0.0:7860\n")
    app = create_ui()
    app.launch(
        share=False,
        show_error=True,
        server_name="0.0.0.0",
        server_port=7860,
    )
