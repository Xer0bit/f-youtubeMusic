# 🎵 Bulk Music Downloader

A **production-ready**, **multi-threaded** music downloader with a modern web UI for batch downloading from YouTube, SoundCloud, and 1000+ sites.

## ✨ Key Features

- **🔄 Multi-Threaded Downloads**: Download multiple tracks simultaneously with configurable worker pool
- **📋 Batch Operations**: Paste URLs or search queries, one per line
- **🎯 Smart Deduplication**: Archive-based tracking prevents duplicate downloads
- **📦 Auto ZIP Creation**: Downloads are automatically packaged into a ZIP file
- **🛡️ Robust Error Handling**: Network timeouts, archive skips, and failures tracked separately
- **🌐 Web UI**: Easy-to-use Gradio interface
- **🔧 Configurable**: Control quality, workers, timeouts via environment variables
- **⚡ Fast & Efficient**: Uses `yt-dlp` for reliability and speed

## 📋 Requirements

- **Python 3.8+**
- **FFmpeg** (for audio encoding)

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Install Python packages
pip install -r requirements.txt

# Install FFmpeg
# On Ubuntu/Debian:
sudo apt-get update && sudo apt-get install -y ffmpeg

# On macOS:
brew install ffmpeg

# On Windows:
# Download from https://ffmpeg.org/download.html
```

### 2. Run the Application

```bash
python app.py
```

Then open your browser to: **http://0.0.0.0:7860**

## 📖 Usage

1. **Paste URLs or Search Queries** (one per line):
   ```
   https://www.youtube.com/watch?v=dQw4w9WgXcQ
   https://soundcloud.com/artist/track
   Bohemian Rhapsody Queen
   Stairway to Heaven Led Zeppelin
   ```

2. **Adjust Settings**:
   - Audio Quality: 128–320 kbps
   - Embed Album Art: Yes/No

3. **Click "Start Download"** and monitor progress

4. **Download ZIP** when complete

## 🔧 Configuration

Control behavior via environment variables:

```bash
# Number of concurrent workers (default: 4)
export MUSIC_DL_WORKERS=6

# Socket timeout in seconds (default: 30)
export MUSIC_DL_TIMEOUT=45

# Root directory for downloads (default: ~/music_downloads)
export MUSIC_DL_ROOT="$HOME/my_music"

python app.py
```

## 📊 Architecture

### Modular Design

- **`utils/downloader.py`**: Core engine with multi-threaded worker pool
- **`app.py`**: Clean entry point and Gradio UI launcher
- **`requirements.txt`**: Dependency manifest

### Thread-Safe Processing

- Lock-based synchronization for stats and logging
- `ThreadPoolExecutor` for bounded concurrency
- Per-worker error isolation (one failure doesn't break others)

### Error Categorization

- **Success**: Downloaded and converted to MP3
- **Skipped**: Already in archive (use "Clear Archive" to re-download)
- **Failed**: Network error, unavailable, or codec issue

## 🎯 Advanced Usage

### Custom Worker Count

For a fast machine or slow network:

```bash
MUSIC_DL_WORKERS=8 python app.py
```

For limited bandwidth:

```bash
MUSIC_DL_WORKERS=2 python app.py
```

### Access Downloaded Files

All downloads are saved to:

```
~/music_downloads/
├── batch_20250102_143022/
│   ├── artist1/
│   │   ├── album1/
│   │   │   └── song1.mp3
│   │   └── album2/
│   │       └── song2.mp3
│   └── artist2/
│       └── single.mp3
└── batch_20250102_143022.zip
```

### Reset/Resume

To re-download a file that's in the archive:

1. Click **"🗑️ Clear Archive"** in the UI
2. Start a new batch

## 🐛 Troubleshooting

### "FFmpeg not found"

Ensure FFmpeg is installed and in your PATH:

```bash
which ffmpeg  # macOS/Linux
# or
ffmpeg -version
```

### Downloads are slow

- ✅ Increase `MUSIC_DL_WORKERS` (more concurrent downloads)
- ✅ Reduce `MUSIC_DL_TIMEOUT` if you have a good network
- ❌ Decrease `MUSIC_DL_WORKERS` if you hit rate limits

### "Already in archive" messages

This is normal! The archive prevents duplicate downloads. Clear it with the button if you want to re-download.

### Port 7860 is already in use

Change the port in `app.py` (search for `server_port=7860`), or:

```bash
lsof -i :7860  # Find the process
kill -9 <PID>
```

## 📝 Log Output

Logs stream to terminal and UI with clear prefixes:

```
[14:30:22] ℹ️ Starting batch download of 5 items with 4 workers...
[14:30:23] ⬇️ [1/5] Queued: Bohemian Rhapsody Queen...
[14:30:28] ✅ Downloaded: Bohemian Rhapsody
[14:30:29] ⬇️ [2/5] Queued: Stairway to Heaven Led Zeppelin...
[14:30:35] ✅ Downloaded: Stairway to Heaven
...
[14:30:42] 🎉 BATCH COMPLETE!
[14:30:42]    ✅ Downloaded: 5
[14:30:42]    ⏭️ Skipped: 0
[14:30:42]    ❌ Failed: 0
```

## ⚠️ Legal Disclaimer

This tool is for downloading music **you have the right to download**. Please:

- ✅ Download music you own or have permission to download
- ✅ Support artists by purchasing their music
- ❌ Don't bypass copyright protection or DRM
- ❌ Don't redistribute downloaded content

## 🔄 Updates & Contributing

To update `yt-dlp` (which frequently improves compatibility):

```bash
pip install --upgrade yt-dlp
```

## 📄 License

This project is provided as-is for educational and personal use.

---

**Built with ❤️ using Python, Gradio, and yt-dlp**
