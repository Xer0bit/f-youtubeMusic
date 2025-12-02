# =============================================================================
# SPOTIFY DOWNLOADER MODULE
# =============================================================================
# Support for downloading Spotify tracks, albums, and playlists using spotdl
# =============================================================================

import json
import logging
import os
import re
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

logger = logging.getLogger("SpotifyDownloader")

# =============================================================================
# CONFIGURATION
# =============================================================================

SPOTIFY_CONFIG_FILE = os.path.join(
    os.environ.get("MUSIC_DL_ROOT", str(Path.home() / "music_downloads")),
    "spotify_config.json"
)

# Spotify URL patterns
SPOTIFY_PATTERNS = {
    "track": re.compile(r"https?://open\.spotify\.com/track/([a-zA-Z0-9]+)"),
    "album": re.compile(r"https?://open\.spotify\.com/album/([a-zA-Z0-9]+)"),
    "playlist": re.compile(r"https?://open\.spotify\.com/playlist/([a-zA-Z0-9]+)"),
    "artist": re.compile(r"https?://open\.spotify\.com/artist/([a-zA-Z0-9]+)"),
}

# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class SpotifyTrack:
    """Represents a Spotify track."""
    id: str
    name: str
    artist: str
    album: str = ""
    duration_ms: int = 0
    url: str = ""
    status: str = "pending"  # pending, downloading, completed, failed
    error: str = ""
    file_path: str = ""

    @property
    def duration_formatted(self) -> str:
        """Format duration as mm:ss."""
        if self.duration_ms <= 0:
            return "0:00"
        seconds = self.duration_ms // 1000
        return f"{seconds // 60}:{seconds % 60:02d}"


@dataclass 
class SpotifyPlaylist:
    """Represents a Spotify playlist or album."""
    id: str
    name: str
    owner: str = ""
    description: str = ""
    total_tracks: int = 0
    url: str = ""
    tracks: List[SpotifyTrack] = field(default_factory=list)
    type: str = "playlist"  # playlist, album, artist


@dataclass
class SpotifyConfig:
    """Spotify download configuration."""
    output_format: str = "mp3"
    audio_quality: str = "320k"
    output_template: str = "{artist} - {title}"
    threads: int = 4
    use_proxy: bool = False
    proxy_url: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "output_format": self.output_format,
            "audio_quality": self.audio_quality,
            "output_template": self.output_template,
            "threads": self.threads,
            "use_proxy": self.use_proxy,
            "proxy_url": self.proxy_url,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpotifyConfig":
        return cls(
            output_format=data.get("output_format", "mp3"),
            audio_quality=data.get("audio_quality", "320k"),
            output_template=data.get("output_template", "{artist} - {title}"),
            threads=data.get("threads", 4),
            use_proxy=data.get("use_proxy", False),
            proxy_url=data.get("proxy_url", ""),
        )

# =============================================================================
# SPOTIFY MANAGER
# =============================================================================

class SpotifyManager:
    """Manager for Spotify downloads using spotdl."""
    
    def __init__(self):
        self.config = self._load_config()
        self._lock = threading.RLock()
        self.is_downloading = False
        self.current_tracks: List[SpotifyTrack] = []
        self.download_stats = {"completed": 0, "failed": 0, "total": 0}
        self.log_lines: List[str] = []
        self._spotdl_available: Optional[bool] = None
    
    def _load_config(self) -> SpotifyConfig:
        """Load Spotify configuration from file."""
        try:
            if os.path.exists(SPOTIFY_CONFIG_FILE):
                with open(SPOTIFY_CONFIG_FILE, "r", encoding="utf-8") as f:
                    return SpotifyConfig.from_dict(json.load(f))
        except Exception as e:
            logger.warning(f"Failed to load Spotify config: {e}")
        return SpotifyConfig()
    
    def save_config(self) -> None:
        """Save Spotify configuration to file."""
        try:
            os.makedirs(os.path.dirname(SPOTIFY_CONFIG_FILE), exist_ok=True)
            with open(SPOTIFY_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save Spotify config: {e}")
    
    def log(self, msg: str) -> None:
        """Add log entry."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {msg}"
        with self._lock:
            self.log_lines.append(entry)
            if len(self.log_lines) > 100:
                self.log_lines = self.log_lines[-50:]
        logger.info(msg)
    
    def get_logs(self, limit: int = 20) -> str:
        """Get recent log entries."""
        with self._lock:
            return "\n".join(self.log_lines[-limit:])
    
    def is_spotdl_installed(self) -> bool:
        """Check if spotdl is installed."""
        if self._spotdl_available is not None:
            return self._spotdl_available
        
        try:
            result = subprocess.run(
                ["spotdl", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            self._spotdl_available = result.returncode == 0
            if self._spotdl_available:
                version = result.stdout.strip()
                self.log(f"spotdl found: {version}")
        except (subprocess.SubprocessError, FileNotFoundError):
            self._spotdl_available = False
            self.log("spotdl not found - install with: pip install spotdl")
        
        return self._spotdl_available
    
    def is_spotify_url(self, url: str) -> bool:
        """Check if URL is a valid Spotify URL."""
        return any(pattern.match(url) for pattern in SPOTIFY_PATTERNS.values())
    
    def get_url_type(self, url: str) -> Optional[str]:
        """Get the type of Spotify URL (track, album, playlist, artist)."""
        for url_type, pattern in SPOTIFY_PATTERNS.items():
            if pattern.match(url):
                return url_type
        return None
    
    def extract_playlist_info(self, url: str) -> Optional[SpotifyPlaylist]:
        """Extract playlist/album info using spotdl."""
        if not self.is_spotdl_installed():
            return None
        
        url_type = self.get_url_type(url)
        if not url_type:
            return None
        
        try:
            # Use spotdl to get track list
            result = subprocess.run(
                ["spotdl", "--print-errors", "save", url, "--save-file", "/dev/stdout"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                self.log(f"Failed to extract info: {result.stderr[:100]}")
                return None
            
            # Parse the JSON output from spotdl
            try:
                data = json.loads(result.stdout)
                tracks = []
                for item in data:
                    track = SpotifyTrack(
                        id=item.get("song_id", ""),
                        name=item.get("name", "Unknown"),
                        artist=", ".join(item.get("artists", ["Unknown"])),
                        album=item.get("album_name", ""),
                        duration_ms=item.get("duration", 0) * 1000,
                        url=item.get("url", ""),
                    )
                    tracks.append(track)
                
                playlist = SpotifyPlaylist(
                    id=url.split("/")[-1].split("?")[0],
                    name=data[0].get("album_name", "Playlist") if data else "Unknown",
                    total_tracks=len(tracks),
                    url=url,
                    tracks=tracks,
                    type=url_type,
                )
                return playlist
            except json.JSONDecodeError:
                self.log("Failed to parse spotdl output")
                return None
                
        except subprocess.TimeoutExpired:
            self.log("Timeout while extracting playlist info")
            return None
        except Exception as e:
            self.log(f"Error extracting info: {e}")
            return None
    
    def download_url(
        self,
        url: str,
        output_dir: str,
        audio_format: str = "mp3",
        audio_quality: str = "320k"
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Download Spotify URL (track, album, or playlist).
        Yields progress updates.
        """
        if not self.is_spotdl_installed():
            yield {
                "status": "error",
                "message": "spotdl not installed. Run: pip install spotdl",
                "progress": 0,
            }
            return
        
        if not self.is_spotify_url(url):
            yield {
                "status": "error", 
                "message": "Invalid Spotify URL",
                "progress": 0,
            }
            return
        
        self.is_downloading = True
        self.download_stats = {"completed": 0, "failed": 0, "total": 0}
        os.makedirs(output_dir, exist_ok=True)
        
        url_type = self.get_url_type(url)
        self.log(f"Starting {url_type} download: {url[:60]}...")
        
        yield {
            "status": "starting",
            "message": f"Initializing {url_type} download...",
            "progress": 0,
        }
        
        # Build spotdl command
        cmd = [
            "spotdl",
            "--output", output_dir,
            "--format", audio_format,
            "--bitrate", audio_quality,
            "--threads", str(self.config.threads),
            "--print-errors",
        ]
        
        # Add proxy if configured
        if self.config.use_proxy and self.config.proxy_url:
            cmd.extend(["--proxy", self.config.proxy_url])
        
        cmd.append(url)
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            
            current_track = ""
            tracks_processed = 0
            
            for line in iter(process.stdout.readline, ""):
                if not self.is_downloading:
                    process.terminate()
                    yield {"status": "stopped", "message": "Download stopped by user", "progress": 0}
                    return
                
                line = line.strip()
                if not line:
                    continue
                
                self.log(line)
                
                # Parse spotdl output for progress
                if "Downloaded" in line or "Skipping" in line:
                    tracks_processed += 1
                    self.download_stats["completed"] += 1
                    
                    # Extract track name from output
                    if "Downloaded" in line:
                        parts = line.split("Downloaded")
                        if len(parts) > 1:
                            current_track = parts[1].strip()[:50]
                    
                    yield {
                        "status": "downloading",
                        "message": f"Downloaded: {current_track}",
                        "progress": tracks_processed,
                        "current_track": current_track,
                    }
                    
                elif "Error" in line or "Failed" in line:
                    self.download_stats["failed"] += 1
                    yield {
                        "status": "error",
                        "message": line[:100],
                        "progress": tracks_processed,
                    }
                    
                elif "Found" in line and "songs" in line:
                    # Extract total count
                    match = re.search(r"Found (\d+) songs?", line)
                    if match:
                        self.download_stats["total"] = int(match.group(1))
                        yield {
                            "status": "info",
                            "message": f"Found {self.download_stats['total']} tracks",
                            "progress": 0,
                            "total": self.download_stats["total"],
                        }
            
            process.wait()
            
            if process.returncode == 0:
                self.log(f"Download complete! {self.download_stats['completed']} tracks")
                yield {
                    "status": "completed",
                    "message": f"Download complete! {self.download_stats['completed']} tracks downloaded",
                    "progress": 100,
                    "stats": self.download_stats,
                }
            else:
                yield {
                    "status": "error",
                    "message": f"Download failed with code {process.returncode}",
                    "progress": 0,
                }
                
        except Exception as e:
            self.log(f"Download error: {e}")
            yield {
                "status": "error",
                "message": str(e)[:100],
                "progress": 0,
            }
        finally:
            self.is_downloading = False
    
    def download_search(
        self,
        query: str,
        output_dir: str,
        audio_format: str = "mp3",
        audio_quality: str = "320k"
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Download by search query (artist - song).
        Yields progress updates.
        """
        if not self.is_spotdl_installed():
            yield {
                "status": "error",
                "message": "spotdl not installed. Run: pip install spotdl",
                "progress": 0,
            }
            return
        
        self.is_downloading = True
        os.makedirs(output_dir, exist_ok=True)
        
        self.log(f"Searching and downloading: {query}")
        
        cmd = [
            "spotdl",
            "--output", output_dir,
            "--format", audio_format,
            "--bitrate", audio_quality,
            "--print-errors",
            query,
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            
            if result.returncode == 0:
                self.log(f"Downloaded: {query}")
                yield {
                    "status": "completed",
                    "message": f"Downloaded: {query}",
                    "progress": 100,
                }
            else:
                error_msg = result.stderr[:100] if result.stderr else "Unknown error"
                self.log(f"Failed: {error_msg}")
                yield {
                    "status": "error",
                    "message": error_msg,
                    "progress": 0,
                }
                
        except subprocess.TimeoutExpired:
            yield {"status": "error", "message": "Download timeout", "progress": 0}
        except Exception as e:
            yield {"status": "error", "message": str(e)[:100], "progress": 0}
        finally:
            self.is_downloading = False
    
    def download_batch(
        self,
        urls_or_queries: List[str],
        output_dir: str,
        audio_format: str = "mp3",
        audio_quality: str = "320k"
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Download multiple URLs or search queries.
        Yields progress updates.
        """
        total = len(urls_or_queries)
        completed = 0
        failed = 0
        
        for idx, item in enumerate(urls_or_queries, 1):
            if not self.is_downloading:
                yield {"status": "stopped", "message": "Batch download stopped", "progress": 0}
                return
            
            self.log(f"[{idx}/{total}] Processing: {item[:50]}...")
            
            if self.is_spotify_url(item):
                # It's a Spotify URL
                for update in self.download_url(item, output_dir, audio_format, audio_quality):
                    update["batch_progress"] = f"{idx}/{total}"
                    yield update
                    if update.get("status") == "completed":
                        completed += 1
                    elif update.get("status") == "error":
                        failed += 1
            else:
                # Treat as search query
                for update in self.download_search(item, output_dir, audio_format, audio_quality):
                    update["batch_progress"] = f"{idx}/{total}"
                    yield update
                    if update.get("status") == "completed":
                        completed += 1
                    elif update.get("status") == "error":
                        failed += 1
        
        yield {
            "status": "batch_completed",
            "message": f"Batch complete! {completed} downloaded, {failed} failed",
            "completed": completed,
            "failed": failed,
            "total": total,
            "progress": 100,
        }
    
    def stop_download(self) -> None:
        """Stop current download."""
        self.is_downloading = False
        self.log("Download stop requested")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current download status."""
        return {
            "is_downloading": self.is_downloading,
            "stats": self.download_stats.copy(),
            "spotdl_installed": self.is_spotdl_installed(),
        }


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

spotify_manager = SpotifyManager()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def is_spotify_url(url: str) -> bool:
    """Check if URL is a Spotify URL."""
    return spotify_manager.is_spotify_url(url)


def parse_spotify_input(text: str) -> List[str]:
    """Parse input text for Spotify URLs and search queries."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return [line for line in lines if not line.startswith("#")]


def get_spotify_install_instructions() -> str:
    """Get instructions for installing spotdl."""
    return """
## Installing spotdl (Spotify Downloader)

spotdl is required to download music from Spotify.

### Installation:
```bash
pip install spotdl
```

### After installation:
1. Restart this application
2. spotdl will automatically authenticate with Spotify's public API
3. No Spotify account required for downloading

### Supported URLs:
- Tracks: https://open.spotify.com/track/...
- Albums: https://open.spotify.com/album/...
- Playlists: https://open.spotify.com/playlist/...
- Artists: https://open.spotify.com/artist/...

### Notes:
- spotdl finds songs on YouTube and downloads them
- Quality depends on the YouTube source
- Large playlists may take some time
"""
