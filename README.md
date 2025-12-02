# 🎵 Music Downloader v5.0

<div align="center">

[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
![Status: Active](https://img.shields.io/badge/Status-Active-brightgreen)

### Download Music from Your Favorite Platforms 🎧

[![YouTube Music](https://img.shields.io/badge/YouTube%20Music-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://www.youtube.com/music)
[![Spotify](https://img.shields.io/badge/Spotify-1DB954?style=for-the-badge&logo=spotify&logoColor=white)](https://www.spotify.com/)
[![SoundCloud](https://img.shields.io/badge/SoundCloud-FF5500?style=for-the-badge&logo=soundcloud&logoColor=white)](https://soundcloud.com/)

**A powerful, multi-threaded music downloader with support for YouTube, Spotify, SoundCloud, and 1000+ sites**

[Features](#-features) • [Installation](#-installation) • [Quick Start](#-quick-start) • [Documentation](#-documentation)

</div>

## ✨ Features

### 🎼 Multi-Platform Support
- **Spotify**: Download tracks, albums, and playlists
- **YouTube Music**: Videos and entire playlists
- **SoundCloud**: Individual tracks and reposts
- **YouTube**: Full support with playlist extraction
- **1000+ Sites**: Reddit, Twitter, Instagram, and more via yt-dlp

### ⚡ Performance
- **Multi-threaded Downloads**: Configurable worker pool (up to 8 concurrent threads)
- **Smart Deduplication**: Never download the same track twice
- **Batch Operations**: Download hundreds of songs in one go
- **Concurrent Fragment Downloads**: Faster streaming optimization

### 🎯 Organization
- **Genre Categorization**: Automatic genre detection from metadata
- **Song Catalog**: Unique IDs and comprehensive metadata storage
- **Smart Organization**: Organize downloaded files by genre automatically
- **Search & Filter**: Find songs in your catalog by title, artist, or genre

### 🛡️ Advanced Features
- **Proxy Support**: Use HTTP/SOCKS proxies with authentication
- **IP Detection**: Monitor your current IP and network status
- **File Browser**: Terminal-like interface for managing downloads
- **Custom Save Locations**: Choose where to save your music
- **Audio Quality Control**: 128–320 kbps MP3 encoding
- **Album Art Embedding**: Automatic thumbnail embedding

### 🎨 User Experience
- **Modern Web UI**: Beautiful Gradio interface
- **Real-time Progress**: Watch downloads happen in real-time
- **Archive ZIP Creation**: Auto-package downloads
- **Download History**: Track all your download sessions
- **Detailed Statistics**: View success rates and session stats

## 📋 System Requirements

| Requirement | Version |
|------------|---------|
| **Python** | 3.8 or higher |
| **FFmpeg** | Latest version |
| **RAM** | 512 MB minimum |
| **Disk Space** | Depends on downloads |

## 🚀 Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/Xer0bit/f-youtubeMusic.git
cd f-youtubeMusic
```

### Step 2: Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate it
# On Linux/macOS:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Install FFmpeg

**Ubuntu/Debian:**
```bash
sudo apt-get update && sudo apt-get install -y ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
```bash
# Using Chocolatey:
choco install ffmpeg

# Or download from: https://ffmpeg.org/download.html
```

### Step 5: Verify Installation

```bash
ffmpeg -version
python -c "import yt_dlp, gradio, spotdl; print('✅ All dependencies installed!')"
```

---

## 🎯 Quick Start

### 1. Launch the Application

```bash
python app.py
```

### 2. Open Your Browser

Navigate to: **http://localhost:7860**

### 3. Choose Your Download Source

| Tab | Source | Example |
|-----|--------|---------|
| **Download** | YouTube & More | URLs or search queries |
| **Spotify** | Spotify | Track/Album/Playlist URLs |
| **File Browser** | Manage Files | Browse & organize |
| **Catalog** | Your Library | Search & organize by genre |

### 4. Start Downloading!

```
Paste these into the Download tab:
https://www.youtube.com/watch?v=dQw4w9WgXcQ
https://soundcloud.com/artist/track
The Weeknd - Blinding Lights
Queen - Bohemian Rhapsody
```

## 📖 Usage Guide

### YouTube & General Downloads

1. Paste URL or search query (one per line)
2. Select audio quality (128-320 kbps)
3. Enable album art if desired
4. Click **Download**
5. Monitor real-time progress
6. Download ZIP when complete

### Spotify Downloads

1. Go to **Spotify** tab
2. Paste Spotify URL or search query:
   - Track: `https://open.spotify.com/track/...`
   - Album: `https://open.spotify.com/album/...`
   - Playlist: `https://open.spotify.com/playlist/...`
   - Search: `The Weeknd - Blinding Lights`
3. Select audio format and quality
4. Click **Download from Spotify**

### Organize Your Music

1. Go to **Catalog** tab
2. View statistics and genre distribution
3. Search songs by title/artist
4. Filter by genre
5. Click **Organize by Genre** to auto-organize files

### Manage Downloads

1. Go to **File Browser** tab
2. Navigate directories with terminal-like commands
3. Create folders
4. Set custom download location
5. View directory tree

## ⚙️ Configuration

### Environment Variables

```bash
# Number of concurrent downloads (default: 8)
export MUSIC_DL_WORKERS=6

# Socket timeout in seconds (default: 15)
export MUSIC_DL_TIMEOUT=30

# Root download directory (default: ~/music_downloads)
export MUSIC_DL_ROOT="/mnt/external_drive/music"

python app.py
```

### Audio Quality Options

| Quality | Bitrate | File Size (3min) |
|---------|---------|------------------|
| Low | 128 kbps | 2.8 MB |
| Medium | 192 kbps | 4.2 MB |
| High | 256 kbps | 5.6 MB |
| **Best** | **320 kbps** | **7.0 MB** |

## 🎵 Supported Platforms

### Native Support
- ✅ YouTube & YouTube Music
- ✅ Spotify
- ✅ SoundCloud
- ✅ Apple Music (limited)

### Extended Support (via yt-dlp)
- ✅ Reddit
- ✅ Twitter/X
- ✅ TikTok
- ✅ Instagram
- ✅ Twitch
- ✅ Vimeo
- ✅ Dailymotion
- ✅ And 1000+ more sites

## 🔒 Proxy & Network Features

### Configure Proxy

1. Go to **Network** tab
2. Select proxy type (HTTP, HTTPS, SOCKS4, SOCKS5)
3. Enter proxy host and port
4. Add credentials if needed
5. Click **Apply Proxy** then **Test Connection**

### Monitor Network Status

- View current IP address
- Check ISP and location
- Monitor proxy status in real-time

---

## 🗂️ Download Structure

```
~/music_downloads/
├── batch_20250102_143022/
│   ├── Song One.mp3
│   ├── Song Two.mp3
│   └── Another Song.mp3
├── batch_20250102_143022.zip
│
├── spotify_20250102_150000/
│   └── Downloaded Spotify Tracks.mp3
│
└── by_genre/
    ├── Electronic/
    │   ├── track1.mp3
    │   └── track2.mp3
    ├── Hip-Hop/
    │   └── track3.mp3
    └── Pop/
        └── track4.mp3
```

## 🐛 Troubleshooting

### ❌ FFmpeg Not Found

```bash
# Verify FFmpeg is installed
ffmpeg -version

# If not installed, install it:
# Ubuntu: sudo apt install ffmpeg
# macOS: brew install ffmpeg
```

### ❌ Downloads Are Slow

```bash
# Increase concurrent workers
export MUSIC_DL_WORKERS=8
python app.py

# Or reduce timeout if you have good connectivity
export MUSIC_DL_TIMEOUT=10
```

### ❌ Port Already in Use

```bash
# Find process using port 7860
lsof -i :7860

# Kill it (replace PID with actual number)
kill -9 <PID>

# Or set a different port in app.py
```

### ❌ "Already Downloaded" Messages

This is normal! The app prevents duplicates using an archive.

```bash
# To re-download, clear the archive:
# Click "Clear Archive" in the Files tab
# Or manually delete:
rm ~/music_downloads/downloaded.archive
```

### ❌ Spotify Download Issues

```bash
# Ensure spotdl is installed
pip install spotdl

# Verify it works
spotdl --version
```

---

## 📊 Features by Tab

| Tab | Features |
|-----|----------|
| **Download** | YouTube, SoundCloud, 1000+ sites, search queries, batch downloads |
| **Spotify** | Tracks, albums, playlists, search, quality selection |
| **History** | Recent sessions, statistics, success rate tracking |
| **Files** | Browse, organize, set download location, view file list |
| **Settings** | Quality, album art, auto-ZIP, history size |
| **Network** | Proxy configuration, IP detection, network monitoring |
| **Catalog** | Genre stats, song search, genre filtering, organization |
| **File Browser** | Terminal interface, directory navigation, tree view |

---

## 🔐 Legal & Ethical Use

### ✅ Legal Uses
- Download music you own or have permission to download
- Personal use and archival
- Content you created or have rights to
- Licensed music and public domain content

### ❌ Illegal Uses
- Bypassing copyright protection
- Redistributing copyrighted content
- Commercial use without permission
- Violating platform terms of service

**Always support artists** by purchasing their music and attending concerts! 🎤

---

## 📈 Performance Tips

### For Faster Downloads
- Use `MUSIC_DL_WORKERS=8` on systems with good bandwidth
- Download during off-peak hours
- Use a wired connection instead of WiFi

### For Limited Bandwidth
- Use `MUSIC_DL_WORKERS=2` to reduce strain
- Lower quality (192 kbps) to reduce file sizes
- Download one playlist at a time

### For Large Collections
- Use the batch import feature
- Let it run overnight for massive playlists
- Monitor the History tab for completion

---

## 🔄 Keeping Updated

### Update yt-dlp (Important for compatibility)

```bash
pip install --upgrade yt-dlp
```

### Update spotdl

```bash
pip install --upgrade spotdl
```

### Update Gradio

```bash
pip install --upgrade gradio
```

### Update All Dependencies

```bash
pip install --upgrade -r requirements.txt
```

---

## 🤝 Contributing

Contributions are welcome! Here's how to contribute:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📝 Changelog

### v5.0 - Current
- ✅ Added Spotify support (tracks, albums, playlists)
- ✅ Enhanced genre categorization system
- ✅ Improved file browser with terminal interface
- ✅ Network monitoring and proxy support
- ✅ Music catalog with search and organization

### v4.0
- Added proxy support with IP detection
- Genre categorization for downloads
- Music catalog system
- File browser interface

### v3.0
- Batch download support
- Auto ZIP creation
- Archive-based deduplication

---

## ⚖️ License

This project is licensed under the **MIT License** - see the LICENSE file for details.

---

## 🙋 Support

- 📖 **Documentation**: Check the docs/ folder
- 🐛 **Issues**: Report bugs on GitHub Issues
- 💬 **Discussions**: Ask questions in GitHub Discussions
- 📧 **Email**: Contact the maintainers

---

## 🌟 Show Your Support

If this project helped you, please give it a ⭐ star on GitHub!

---

<div align="center">

### Built with ❤️ by the Community

**Python** • **Gradio** • **yt-dlp** • **spotdl**

[⬆ Back to Top](#-music-downloader-v50)

</div>
