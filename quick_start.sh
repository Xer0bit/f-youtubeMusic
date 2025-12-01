#!/bin/bash
# =============================================================================
# QUICK START SCRIPT - Installation & Setup
# =============================================================================
# Run this script to set up the YouTube Music Downloader in seconds
# 
# Usage:
#   bash quick_start.sh
#

set -e

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "🎵 YouTube Music Downloader - Quick Start Setup"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Check Python version
echo "🔍 Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.8 or later."
    exit 1
fi

python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✅ Found Python $python_version"
echo ""

# Check FFmpeg
echo "🔍 Checking FFmpeg..."
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  FFmpeg not found. Installing..."
    if command -v apt-get &> /dev/null; then
        echo "   → Installing via apt-get..."
        sudo apt-get update -qq
        sudo apt-get install -y -qq ffmpeg
    elif command -v brew &> /dev/null; then
        echo "   → Installing via Homebrew..."
        brew install ffmpeg
    else
        echo "❌ Could not install FFmpeg automatically."
        echo "   Please install FFmpeg manually from: https://ffmpeg.org/download.html"
        exit 1
    fi
    echo "✅ FFmpeg installed"
else
    echo "✅ FFmpeg found: $(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')"
fi
echo ""

# Install Python dependencies
echo "📦 Installing Python dependencies..."
echo "   → pip install -r requirements.txt"
pip install -q -r requirements.txt
echo "✅ Dependencies installed"
echo ""

# Summary
echo "════════════════════════════════════════════════════════════════"
echo "✅ SETUP COMPLETE!"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "🚀 To start the downloader, run:"
echo "   python app.py"
echo ""
echo "🌐 Then open in your browser:"
echo "   http://0.0.0.0:7860"
echo ""
echo "💡 Advanced: Control behavior with environment variables"
echo "   export MUSIC_DL_WORKERS=6      # More concurrent downloads"
echo "   export MUSIC_DL_TIMEOUT=45     # Socket timeout (seconds)"
echo "   export MUSIC_DL_ROOT=/path/to/downloads"
echo "   python app.py"
echo ""
echo "📖 For more info, see:"
echo "   - README.md (usage guide)"
echo "   - ARCHITECTURE.md (technical details)"
echo ""
