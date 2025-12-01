
import os
import re
import shutil
import zipfile
import threading
import logging
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Tuple, List

# ============================================================================
# CONFIGURATION & RUNTIME SETTINGS
# ============================================================================

# Paths (override via environment variables)
WORKSPACE_ROOT = os.environ.get("MUSIC_DL_ROOT", str(Path.home() / "music_downloads"))
BASE_DIR = WORKSPACE_ROOT
ARCHIVE_FILE = os.environ.get("MUSIC_DL_ARCHIVE", str(Path(WORKSPACE_ROOT) / "downloaded.archive"))

# Worker pool settings
MAX_WORKERS = int(os.environ.get("MUSIC_DL_WORKERS", "4"))
SOCKET_TIMEOUT = int(os.environ.get("MUSIC_DL_TIMEOUT", "30"))

# Ensure output dirs exist
os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(os.path.dirname(ARCHIVE_FILE), exist_ok=True)

# ============================================================================
# LOGGER SETUP (thread-safe)
# ============================================================================

logger = logging.getLogger("MusicDownloader")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# ============================================================================
# CORE DOWNLOADER ENGINE
# ============================================================================

class MusicDownloader:
    """Production-grade music downloader with concurrent processing."""

    def __init__(self):
        self.progress_log: List[str] = []
        self.is_running = False
        self._lock = threading.Lock()
        self.stats = {
            "total": 0,
            "completed": 0,
            "failed": 0,
            "skipped": 0
        }

    def reset_stats(self) -> None:
        """Reset download statistics."""
        with self._lock:
            self.stats = {"total": 0, "completed": 0, "failed": 0, "skipped": 0}
            self.progress_log = []

    def log(self, message: str, level: str = "INFO") -> str:
        """Thread-safe logging with emoji indicators."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        icons = {
            "INFO": "ℹ️",
            "SUCCESS": "✅",
            "ERROR": "❌",
            "WARNING": "⚠️",
            "DOWNLOAD": "⬇️"
        }
        icon = icons.get(level, "•")
        log_entry = f"[{timestamp}] {icon} {message}"

        with self._lock:
            self.progress_log.append(log_entry)

        log_method = getattr(logger, level.lower(), logger.info)
        log_method(message)

        return "\n".join(self.progress_log[-50:])
    
    def analyze_input_type(self, items: List[str]) -> str:
        """Analyze the type of input items and return a descriptive string."""
        if not items:
            return "Empty input"
        
        if len(items) == 1:
            item = items[0]
            if item.startswith(('http://', 'https://')):
                # Check for playlist indicators
                if any(playlist_indicator in item.lower() for playlist_indicator in [
                    '&list=', 'playlist', '/playlist', 'list='
                ]):
                    return "Single playlist URL"
                else:
                    return "Single video/audio URL"
            else:
                return "Single search query"
        else:
            # Multiple items - analyze composition
            urls = [item for item in items if item.startswith(('http://', 'https://'))]
            searches = [item for item in items if not item.startswith(('http://', 'https://'))]
            
            parts = []
            if urls:
                # Check if any URLs are playlists
                playlist_urls = [url for url in urls if any(
                    playlist_indicator in url.lower() for playlist_indicator in [
                        '&list=', 'playlist', '/playlist', 'list='
                    ]
                )]
                if playlist_urls:
                    parts.append(f"{len(playlist_urls)} playlist(s)")
                
                regular_urls = len(urls) - len(playlist_urls)
                if regular_urls > 0:
                    parts.append(f"{regular_urls} URL(s)")
            
            if searches:
                parts.append(f"{len(searches)} search query(ies)")
            
            return f"Batch: {', '.join(parts)}"
    
    def parse_input(self, text_input: str) -> List[str]:
        """Parse input text into list of URLs/queries."""
        lines = text_input.strip().split("\n")
        items = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                items.append(line)
        return items
    
    def sanitize_filename(self, name: str) -> str:
        """Remove invalid filename characters."""
        return re.sub(r'[<>:"/\\|?*]', '_', name)
    
    def download_single(
        self,
        url_or_query: str,
        output_dir: str,
        quality: str = "320",
        embed_thumbnail: bool = True
    ) -> Tuple[bool, str]:
        """Download a single URL or search query.
        
        Returns:
            (success: bool, message_or_title: str)
        """
        import yt_dlp

        # Determine if URL or search query
        is_url = url_or_query.startswith(('http://', 'https://', 'www.'))
        if not is_url:
            url_or_query = f"ytsearch:{url_or_query}"

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(output_dir, '%(artist)s/%(album)s/%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': quality,
            }],
            'download_archive': ARCHIVE_FILE,
            'ignoreerrors': True,
            'no_warnings': True,
            'quiet': True,
            'no_color': True,
            'retries': 10,
            'fragment_retries': 10,
            'socket_timeout': SOCKET_TIMEOUT,
            'extract_flat': False,
            'writethumbnail': embed_thumbnail,
            'embedthumbnail': embed_thumbnail,
            'postprocessor_args': ['-id3v2_version', '3'],
            'prefer_ffmpeg': True,
            'keepvideo': False,
        }

        if embed_thumbnail:
            ydl_opts['postprocessors'].extend([
                {'key': 'EmbedThumbnail'},
                {'key': 'FFmpegMetadata', 'add_metadata': True},
            ])

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url_or_query, download=True)
                if info:
                    title = info.get('title', 'Unknown')
                    return True, title
                return False, "No info extracted"
        except yt_dlp.utils.DownloadError as e:
            msg = str(e).lower()
            if any(x in msg for x in ["already in archive", "has already been recorded"]):
                return False, "SKIP_ALREADY_DOWNLOADED"
            return False, str(e)
        except Exception as e:
            return False, str(e)
    
    def download_batch(
        self,
        text_input: str,
        quality: str = "320",
        embed_thumbnail: bool = True,
        progress_callback=None
    ) -> Tuple[str, Optional[str]]:
        """Download multiple URLs/queries using a worker pool.
        
        Args:
            text_input: Multi-line string of URLs or search queries
            quality: Audio quality in kbps (128, 192, 256, 320)
            embed_thumbnail: Whether to embed album art
            progress_callback: Optional callback function for progress updates
            
        Returns:
            (progress_text: str, zip_file_path: Optional[str])
        """
        self.reset_stats()
        self.is_running = True

        # Create timestamped output directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(BASE_DIR, f"batch_{timestamp}")
        os.makedirs(output_dir, exist_ok=True)

        items = self.parse_input(text_input)
        self.stats["total"] = len(items)

        if not items:
            self.log("No valid URLs or search queries found!", "ERROR")
            self.is_running = False
            return self.get_progress_text(), None

        # Analyze and log input type
        input_type = self.analyze_input_type(items)
        self.log(f"📋 Input Type: {input_type}", "INFO")
        self.log(f"🎯 Total Items: {len(items)}", "INFO")
        self.log(f"⚙️ Workers: {MAX_WORKERS} concurrent downloads", "INFO")
        self.log(f"🎵 Quality: {quality}kbps | Thumbnails: {'Yes' if embed_thumbnail else 'No'}", "INFO")
        self.log(f"📁 Output: {output_dir}", "INFO")
        self.log("-" * 70, "INFO")

        # Submit all tasks to thread pool
        futures_to_item = {}
        with ThreadPoolExecutor(max_workers=max(1, MAX_WORKERS)) as executor:
            for idx, item in enumerate(items, 1):
                if not self.is_running:
                    break
                # Show item type in queue log
                item_type = "🔗 URL" if item.startswith(('http://', 'https://')) else "🔍 Search"
                self.log(f"[{idx:2d}/{len(items):2d}] Queued {item_type}: {item[:55]}...", "DOWNLOAD")
                future = executor.submit(
                    self.download_single,
                    item,
                    output_dir,
                    quality,
                    embed_thumbnail
                )
                futures_to_item[future] = (idx, len(items), item)

            # Process completed futures as they finish
            for future in as_completed(futures_to_item):
                if not self.is_running:
                    break

                idx, total, item = futures_to_item[future]
                try:
                    success, result = future.result()
                except Exception as e:
                    success, result = (False, str(e))

                # Update stats thread-safely
                with self._lock:
                    processed = self.stats['completed'] + self.stats['failed'] + self.stats['skipped'] + 1
                    if success:
                        self.stats["completed"] += 1
                        self.log(f"[{processed:2d}/{len(items):2d}] ✅ Downloaded: {result}", "SUCCESS")
                    else:
                        if result == "SKIP_ALREADY_DOWNLOADED" or "already" in result.lower():
                            self.stats["skipped"] += 1
                            self.log(f"[{processed:2d}/{len(items):2d}] ⏭️ Skipped (already downloaded): {item[:50]}", "WARNING")
                        else:
                            self.stats["failed"] += 1
                            self.log(f"[{processed:2d}/{len(items):2d}] ❌ Failed: {result[:80]}", "ERROR")

                if progress_callback:
                    progress_callback(self.get_progress_text())

        self.is_running = False

        # Final summary with detailed stats
        self.log("-" * 70, "INFO")
        self.log("🎉 BATCH COMPLETE!", "SUCCESS")
        self.log("-" * 70, "INFO")
        self.log(f"📊 Final Statistics:", "INFO")
        self.log(f"   🎯 Total Items:     {self.stats['total']}", "INFO")
        self.log(f"   ✅ Successful:      {self.stats['completed']}", "INFO")
        self.log(f"   ⏭️ Skipped:         {self.stats['skipped']}", "INFO")
        self.log(f"   ❌ Failed:          {self.stats['failed']}", "INFO")
        self.log(f"   📁 Output Directory: {os.path.basename(output_dir)}", "INFO")

        zip_path = None
        if self.stats["completed"] > 0:
            zip_path = self.create_zip(output_dir)
            if zip_path:
                self.log(f"📦 ZIP created: {zip_path}", "SUCCESS")

        return self.get_progress_text(), zip_path
    
    def create_zip(self, source_dir: str) -> Optional[str]:
        """Create ZIP file of downloaded music."""
        zip_filename = f"{source_dir}.zip"

        try:
            with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(source_dir):
                    for file in files:
                        if file.endswith(('.mp3', '.m4a', '.opus', '.webm', '.flac')):
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, source_dir)
                            zipf.write(file_path, arcname)
            return zip_filename
        except Exception as e:
            self.log(f"Failed to create ZIP: {e}", "ERROR")
            return None

    def get_progress_text(self) -> str:
        """Get formatted progress summary with detailed stats."""
        with self._lock:
            processed = self.stats['completed'] + self.stats['failed'] + self.stats['skipped']
            total = self.stats['total']
            
            # Calculate percentages
            success_rate = (self.stats['completed'] / total * 100) if total > 0 else 0
            skip_rate = (self.stats['skipped'] / total * 100) if total > 0 else 0
            fail_rate = (self.stats['failed'] / total * 100) if total > 0 else 0
            
            progress = f"📊 Progress: {processed}/{total} ({processed/total*100:.1f}%)" if total > 0 else "📊 Progress: 0/0"
            progress += "\n"
            progress += f"✅ Success: {self.stats['completed']} ({success_rate:.1f}%) | "
            progress += f"⏭️ Skipped: {self.stats['skipped']} ({skip_rate:.1f}%) | "
            progress += f"❌ Failed: {self.stats['failed']} ({fail_rate:.1f}%)"
            progress += "\n" + "-" * 70 + "\n"
            progress += "\n".join(self.progress_log[-25:])  # Show more recent logs

        return progress

    def stop(self) -> None:
        """Signal to stop current download."""
        self.is_running = False
        self.log("Download stop requested...", "WARNING")


# ============================================================================
# GRADIO WEB UI (lazy import)
# ============================================================================

def _import_gradio():
    """Lazy import of Gradio for testing purposes."""
    try:
        import gradio as gr
        return gr
    except ImportError:
        raise ImportError("Gradio not installed. Install with: pip install gradio")

def download_music(url_text, quality, embed_thumb):
    """Gradio interface function for downloading music."""
    if not url_text.strip():
        return "❌ Please enter at least one URL or search query!", None

    progress, zip_file = downloader.download_batch(
        url_text,
        quality=quality,
        embed_thumbnail=embed_thumb
    )

    return progress, zip_file


def stop_download():
    """Stop the current download."""
    downloader.stop()
    return "⏹️ Download stopped!"


def clear_archive():
    """Clear the download archive to allow re-downloading."""
    if os.path.exists(ARCHIVE_FILE):
        os.remove(ARCHIVE_FILE)
        return "🗑️ Archive cleared! You can now re-download previously downloaded files."
    return "ℹ️ Archive was already empty."


def get_file_list():
    """Get list of downloaded files."""
    if not os.path.exists(BASE_DIR):
        return "No downloads yet."

    files = []
    for root, dirs, filenames in os.walk(BASE_DIR):
        for f in filenames:
            if f.endswith(('.mp3', '.m4a', '.zip')):
                rel_path = os.path.relpath(os.path.join(root, f), BASE_DIR)
                files.append(rel_path)

    if not files:
        return "No music files found."

    return "\n".join(files[:100])


# Initialize downloader (global instance for Gradio)
downloader = MusicDownloader()


def create_ui():
    """Create and return the Gradio interface."""
    gr = _import_gradio()

    with gr.Blocks(
        title="🎵 Bulk Music Downloader"
    ) as app:

        gr.Markdown("""
        # 🎵 Bulk Music Downloader
        ### Download music from YouTube, SoundCloud, and 1000+ sites

        **How to use:**
        1. Paste URLs or search queries (one per line)
        2. Adjust settings if needed
        3. Click "Start Download"
        4. Download your ZIP file when complete!

        ---
        """)

        with gr.Row():
            with gr.Column(scale=2):
                url_input = gr.Textbox(
                    label="🔗 URLs or Search Queries",
                    placeholder="""Paste URLs or search queries here, one per line. Examples:

https://www.youtube.com/watch?v=dQw4w9WgXcQ
https://soundcloud.com/artist/track
Bohemian Rhapsody Queen
Stairway to Heaven Led Zeppelin
# Lines starting with # are ignored""",
                    lines=12,
                    max_lines=50,
                )

                with gr.Row():
                    quality_dropdown = gr.Dropdown(
                        choices=["128", "192", "256", "320"],
                        value="320",
                        label="🎚️ Audio Quality (kbps)"
                    )
                    embed_thumb = gr.Checkbox(
                        value=True,
                        label="🖼️ Embed Album Art"
                    )

                with gr.Row():
                    download_btn = gr.Button("🚀 Start Download", variant="primary", size="lg")
                    stop_btn = gr.Button("⏹️ Stop", variant="stop")
                    clear_btn = gr.Button("🗑️ Clear Archive", variant="secondary")

            with gr.Column(scale=2):
                progress_output = gr.Textbox(
                    label="📋 Progress Log",
                    lines=20,
                    max_lines=30,
                    interactive=False,
                )

                zip_output = gr.File(
                    label="📦 Download ZIP",
                    file_count="single",
                )

        gr.Markdown("""
        ---
        ### 💡 Tips
        - **Search queries**: Just type artist and song name (e.g., "Imagine Dragons Believer")
        - **Playlists**: Paste a YouTube/Spotify playlist URL to download all tracks
        - **Resume**: If interrupted, just run again - already downloaded files are skipped
        - **Quality**: 320kbps is highest quality, 128kbps for smaller files

        ### ⚠️ Disclaimer
        This tool is for downloading music you have the right to download.
        Please respect copyright and support artists by purchasing their music.
        """)

        # Event handlers
        download_btn.click(
            fn=download_music,
            inputs=[url_input, quality_dropdown, embed_thumb],
            outputs=[progress_output, zip_output],
        )

        stop_btn.click(
            fn=stop_download,
            outputs=[progress_output],
        )

        clear_btn.click(
            fn=clear_archive,
            outputs=[progress_output],
        )

    return app


# ============================================================================
# ENTRY POINT (for standalone execution or import)
# ============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("🎵 BULK MUSIC DOWNLOADER")
    print("=" * 70)
    print("\nStarting web interface...")
    print(f"Workers: {MAX_WORKERS} | Timeout: {SOCKET_TIMEOUT}s | Root: {BASE_DIR}")
    print("\nOpen your browser to: http://0.0.0.0:7860\n")

    app = create_ui()
    app.launch(
        share=False,
        debug=False,
        show_error=True,
        server_name="0.0.0.0",
        server_port=7860,
    )
