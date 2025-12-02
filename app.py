#!/usr/bin/env python3
# =============================================================================
# BULK MUSIC DOWNLOADER v4.0 - APP ENTRY POINT
# =============================================================================
# Main application launcher for the Gradio web UI.
#
# Usage:
#   python app.py
#
# Environment Variables:
#   MUSIC_DL_ROOT     - Root directory for downloads (default: ~/music_downloads)
#   MUSIC_DL_WORKERS  - Number of concurrent workers (default: 8)
#   MUSIC_DL_TIMEOUT  - Socket timeout in seconds (default: 15)
#
# =============================================================================

import sys
from pathlib import Path

# Add project root to path for proper imports
project_root = str(Path(__file__).parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils.downloader import create_ui, logger, MAX_WORKERS, SOCKET_TIMEOUT, BASE_DIR


def main():
    """Main entry point."""
    print("\n" + "=" * 70)
    print("BULK MUSIC DOWNLOADER v4.0 - PRODUCTION BUILD")
    print("=" * 70)
    print("\nConfiguration:")
    print(f"   Workers:        {MAX_WORKERS}")
    print(f"   Timeout:        {SOCKET_TIMEOUT}s")
    print(f"   Download Root:  {BASE_DIR}")
    print("\nWeb Interface:")
    print("   Open http://0.0.0.0:7860 in your browser")
    print("\nFeatures:")
    print("   - Proxy support with IP detection")
    print("   - Genre categorization")
    print("   - Song catalog with unique IDs")
    print("   - Embedded file browser / terminal")
    print("   - Multi-threaded concurrent downloads")
    print("   - Archive-based duplicate prevention")
    print("\n" + "=" * 70 + "\n")

    try:
        app = create_ui()
        app.launch(
            share=False,
            debug=False,
            show_error=True,
            server_name="0.0.0.0",
            server_port=7860,
            allowed_paths=[BASE_DIR],
        )
    except KeyboardInterrupt:
        print("\n\nShutting down gracefully...")
        logger.info("Application terminated by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
