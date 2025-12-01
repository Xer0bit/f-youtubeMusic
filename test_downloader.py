#!/usr/bin/env python3
# =============================================================================
# TEST SCRIPT - Core Downloader Logic Validation
# =============================================================================
# Tests the downloader without external dependencies (no Gradio/yt-dlp needed)

import sys
import os
import threading
import tempfile
from pathlib import Path

# Mock minimal dependencies for testing
class DownloadError(Exception):
    pass

class MockUtils:
    DownloadError = DownloadError

class MockYTDLP:
    utils = MockUtils()

sys.modules['yt_dlp'] = MockYTDLP()
sys.modules['gradio'] = None

# Now we can import
sys.path.insert(0, str(Path(__file__).parent / "utils"))

from downloader import MusicDownloader

def test_parse_input():
    """Test URL/query parsing."""
    downloader = MusicDownloader()
    
    text = """
    https://youtube.com/watch?v=123
    # This is a comment
    Bohemian Rhapsody Queen
    
    Stairway to Heaven
    """
    
    items = downloader.parse_input(text)
    
    assert len(items) == 3, f"Expected 3 items, got {len(items)}"
    assert "https://youtube.com/watch?v=123" in items
    assert "Bohemian Rhapsody Queen" in items
    assert "# This is a comment" not in items
    print("✅ test_parse_input PASSED")

def test_stats_reset():
    """Test stats reset."""
    downloader = MusicDownloader()
    downloader.stats["completed"] = 10
    downloader.reset_stats()
    
    assert downloader.stats["completed"] == 0
    assert downloader.stats["total"] == 0
    print("✅ test_stats_reset PASSED")

def test_thread_safe_logging():
    """Test that logging is thread-safe."""
    downloader = MusicDownloader()
    results = []
    
    def log_in_thread(msg, idx):
        downloader.log(f"Thread {idx}: {msg}", "INFO")
        results.append(idx)
    
    threads = [threading.Thread(target=log_in_thread, args=(f"msg{i}", i)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    assert len(results) == 5, "Not all threads completed"
    assert len(downloader.progress_log) >= 5, "Not all logs recorded"
    print("✅ test_thread_safe_logging PASSED")

def test_sanitize_filename():
    """Test filename sanitization."""
    downloader = MusicDownloader()
    
    dirty = 'Song <Title> "With" Bad | Chars?'
    clean = downloader.sanitize_filename(dirty)
    
    assert all(c not in clean for c in '<>"\\|?*'), "Invalid chars not removed"
    print(f"   Input:  {dirty}")
    print(f"   Output: {clean}")
    print("✅ test_sanitize_filename PASSED")

def test_progress_text():
    """Test progress formatting."""
    downloader = MusicDownloader()
    downloader.stats = {"total": 10, "completed": 5, "failed": 2, "skipped": 1}
    downloader.progress_log = ["Test log entry"]
    
    progress = downloader.get_progress_text()
    
    assert "5" in progress, "Completed count missing"
    assert "2" in progress, "Failed count missing"
    assert "1" in progress, "Skipped count missing"
    print("✅ test_progress_text PASSED")

def test_stop_flag():
    """Test stop flag mechanism."""
    downloader = MusicDownloader()
    downloader.is_running = True
    
    assert downloader.is_running == True
    downloader.stop()
    assert downloader.is_running == False
    print("✅ test_stop_flag PASSED")

def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("🧪 DOWNLOADER UNIT TESTS")
    print("=" * 60 + "\n")
    
    tests = [
        test_parse_input,
        test_stats_reset,
        test_thread_safe_logging,
        test_sanitize_filename,
        test_progress_text,
        test_stop_flag,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} FAILED: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"📊 Results: {passed} passed, {failed} failed")
    print("=" * 60 + "\n")
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
