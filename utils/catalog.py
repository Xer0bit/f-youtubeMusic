# =============================================================================
# MUSIC CATALOG - Genre Organization & Metadata Management
# =============================================================================

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import threading

CATALOG_FILE = os.path.join(
    os.environ.get("MUSIC_DL_ROOT", str(Path.home() / "music_downloads")),
    "music_catalog.json"
)

# Genre mapping from common tags
GENRE_ALIASES = {
    "hip hop": "Hip-Hop",
    "hip-hop": "Hip-Hop",
    "hiphop": "Hip-Hop",
    "rap": "Hip-Hop",
    "r&b": "R&B",
    "rnb": "R&B",
    "rhythm and blues": "R&B",
    "electronic": "Electronic",
    "edm": "Electronic",
    "house": "Electronic",
    "techno": "Electronic",
    "dubstep": "Electronic",
    "trance": "Electronic",
    "drum and bass": "Electronic",
    "dnb": "Electronic",
    "pop": "Pop",
    "rock": "Rock",
    "alternative": "Rock",
    "indie": "Indie",
    "indie rock": "Indie",
    "metal": "Metal",
    "heavy metal": "Metal",
    "jazz": "Jazz",
    "blues": "Blues",
    "classical": "Classical",
    "country": "Country",
    "folk": "Folk",
    "reggae": "Reggae",
    "soul": "Soul",
    "funk": "Funk",
    "disco": "Disco",
    "latin": "Latin",
    "world": "World",
    "ambient": "Ambient",
    "chill": "Chill",
    "lofi": "Lo-Fi",
    "lo-fi": "Lo-Fi",
    "soundtrack": "Soundtrack",
    "ost": "Soundtrack",
    "k-pop": "K-Pop",
    "kpop": "K-Pop",
    "j-pop": "J-Pop",
    "jpop": "J-Pop",
    "anime": "Anime",
    "game": "Gaming",
    "gaming": "Gaming",
    "workout": "Workout",
    "party": "Party",
    "romantic": "Romantic",
    "sad": "Emotional",
    "emotional": "Emotional",
}

DEFAULT_GENRE = "Uncategorized"


@dataclass
class SongEntry:
    """Individual song entry in the catalog."""
    unique_id: str
    title: str
    artist: str
    album: str = ""
    genre: str = DEFAULT_GENRE
    duration: int = 0
    year: int = 0
    file_path: str = ""
    file_size: int = 0
    bitrate: str = ""
    source_url: str = ""
    download_date: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "unique_id": self.unique_id,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "genre": self.genre,
            "duration": self.duration,
            "year": self.year,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "bitrate": self.bitrate,
            "source_url": self.source_url,
            "download_date": self.download_date,
            "tags": self.tags,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SongEntry":
        return cls(
            unique_id=data.get("unique_id", ""),
            title=data.get("title", ""),
            artist=data.get("artist", ""),
            album=data.get("album", ""),
            genre=data.get("genre", DEFAULT_GENRE),
            duration=data.get("duration", 0),
            year=data.get("year", 0),
            file_path=data.get("file_path", ""),
            file_size=data.get("file_size", 0),
            bitrate=data.get("bitrate", ""),
            source_url=data.get("source_url", ""),
            download_date=data.get("download_date", ""),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )


class MusicCatalog:
    """Manages the music catalog with genre organization."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self.songs: Dict[str, SongEntry] = {}
        self._load_catalog()
    
    def _load_catalog(self) -> None:
        """Load catalog from file."""
        try:
            if os.path.exists(CATALOG_FILE):
                with open(CATALOG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for song_data in data.get("songs", []):
                        song = SongEntry.from_dict(song_data)
                        self.songs[song.unique_id] = song
        except Exception:
            pass
    
    def save_catalog(self) -> None:
        """Save catalog to file."""
        with self._lock:
            os.makedirs(os.path.dirname(CATALOG_FILE), exist_ok=True)
            with open(CATALOG_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "version": "1.0",
                    "updated": datetime.now().isoformat(),
                    "total_songs": len(self.songs),
                    "songs": [s.to_dict() for s in self.songs.values()],
                }, f, indent=2)
    
    def generate_unique_id(self, title: str, artist: str, duration: int = 0) -> str:
        """Generate unique ID based on song metadata."""
        # Create a hash from title + artist + duration
        content = f"{title.lower().strip()}|{artist.lower().strip()}|{duration}"
        hash_obj = hashlib.sha256(content.encode("utf-8"))
        return hash_obj.hexdigest()[:16]
    
    def normalize_genre(self, genre_input: str) -> str:
        """Normalize genre name to standard format."""
        if not genre_input:
            return DEFAULT_GENRE
        
        genre_lower = genre_input.lower().strip()
        
        # Check aliases
        if genre_lower in GENRE_ALIASES:
            return GENRE_ALIASES[genre_lower]
        
        # Check if any alias is contained in the input
        for alias, normalized in GENRE_ALIASES.items():
            if alias in genre_lower:
                return normalized
        
        # Capitalize first letter of each word
        return genre_input.strip().title()
    
    def detect_genre_from_metadata(self, info: Dict[str, Any]) -> str:
        """Try to detect genre from video metadata."""
        # Check direct genre field
        genre = info.get("genre", "")
        if genre:
            return self.normalize_genre(genre)
        
        # Check categories
        categories = info.get("categories", [])
        for cat in categories:
            normalized = self.normalize_genre(cat)
            if normalized != DEFAULT_GENRE:
                return normalized
        
        # Check tags
        tags = info.get("tags", [])
        for tag in tags[:10]:  # Check first 10 tags
            normalized = self.normalize_genre(tag)
            if normalized != DEFAULT_GENRE:
                return normalized
        
        # Check title and description for genre hints
        title = info.get("title", "").lower()
        description = info.get("description", "").lower()[:500]
        combined = f"{title} {description}"
        
        for alias, normalized in GENRE_ALIASES.items():
            if alias in combined:
                return normalized
        
        return DEFAULT_GENRE
    
    def add_song(
        self,
        title: str,
        artist: str,
        file_path: str,
        source_url: str = "",
        info: Optional[Dict[str, Any]] = None
    ) -> SongEntry:
        """Add a song to the catalog."""
        info = info or {}
        
        duration = info.get("duration", 0)
        unique_id = self.generate_unique_id(title, artist, duration)
        
        # Check if already exists
        if unique_id in self.songs:
            return self.songs[unique_id]
        
        genre = self.detect_genre_from_metadata(info)
        
        # Extract additional metadata
        tags = []
        if info.get("tags"):
            tags = info["tags"][:20]  # Keep first 20 tags
        
        song = SongEntry(
            unique_id=unique_id,
            title=title,
            artist=artist,
            album=info.get("album", info.get("playlist_title", "")),
            genre=genre,
            duration=duration,
            year=info.get("release_year", info.get("upload_date", "")[:4] if info.get("upload_date") else 0),
            file_path=file_path,
            file_size=os.path.getsize(file_path) if os.path.exists(file_path) else 0,
            bitrate=info.get("abr", ""),
            source_url=source_url,
            download_date=datetime.now().isoformat(),
            tags=tags,
            metadata={
                "uploader": info.get("uploader", ""),
                "channel": info.get("channel", ""),
                "view_count": info.get("view_count", 0),
                "like_count": info.get("like_count", 0),
            }
        )
        
        with self._lock:
            self.songs[unique_id] = song
        
        self.save_catalog()
        return song
    
    def get_songs_by_genre(self, genre: Optional[str] = None) -> Union[List[SongEntry], Dict[str, List[SongEntry]]]:
        """Get songs organized by genre or return entries for a specific genre."""
        if genre:
            normalized = genre.strip().lower()
            return [song for song in self.songs.values() if song.genre.lower() == normalized]

        genres: Dict[str, List[SongEntry]] = {}
        for song in self.songs.values():
            if song.genre not in genres:
                genres[song.genre] = []
            genres[song.genre].append(song)
        return genres
    
    def get_genre_stats(self) -> Dict[str, int]:
        """Get count of songs per genre."""
        stats: Dict[str, int] = {}
        for song in self.songs.values():
            stats[song.genre] = stats.get(song.genre, 0) + 1
        return dict(sorted(stats.items(), key=lambda x: x[1], reverse=True))
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive catalog statistics."""
        total_songs = len(self.songs)
        total_artists = len(set(song.artist for song in self.songs.values() if song.artist))
        total_duration = sum(song.duration for song in self.songs.values())
        
        # Format duration
        hours = total_duration // 3600
        minutes = (total_duration % 3600) // 60
        seconds = total_duration % 60
        if hours > 0:
            total_duration_formatted = f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            total_duration_formatted = f"{minutes}m {seconds}s"
        else:
            total_duration_formatted = f"{seconds}s"
        
        # Genre stats
        genres = self.get_genre_stats()
        
        return {
            "total_songs": total_songs,
            "total_artists": total_artists,
            "total_duration": total_duration,
            "total_duration_formatted": total_duration_formatted,
            "genres": genres,
        }
    
    def search_songs(self, query: str) -> List[SongEntry]:
        """Search songs by title, artist, or tags."""
        query_lower = query.lower()
        results = []
        for song in self.songs.values():
            if (query_lower in song.title.lower() or
                query_lower in song.artist.lower() or
                any(query_lower in tag.lower() for tag in song.tags)):
                results.append(song)
        return results
    
    def get_song_by_id(self, unique_id: str) -> Optional[SongEntry]:
        """Get song by unique ID."""
        return self.songs.get(unique_id)
    
    def remove_song(self, unique_id: str) -> bool:
        """Remove song from catalog."""
        if unique_id in self.songs:
            with self._lock:
                del self.songs[unique_id]
            self.save_catalog()
            return True
        return False
    
    def get_catalog_display(self) -> str:
        """Get formatted catalog display."""
        if not self.songs:
            return "Music catalog is empty."
        
        lines = [
            "Music Catalog",
            "=" * 50,
            f"Total Songs: {len(self.songs)}",
            "",
            "Songs by Genre:",
            "-" * 50,
        ]
        
        genre_stats = self.get_genre_stats()
        for genre, count in genre_stats.items():
            lines.append(f"  {genre}: {count} songs")
        
        lines.extend(["", "Recent Additions:", "-" * 50])
        
        # Show last 10 songs
        recent = sorted(
            self.songs.values(),
            key=lambda s: s.download_date,
            reverse=True
        )[:10]
        
        for song in recent:
            lines.append(f"  [{song.unique_id[:8]}] {song.artist} - {song.title}")
        
        return "\n".join(lines)
    
    def export_catalog_json(self) -> str:
        """Export catalog as formatted JSON."""
        return json.dumps({
            "songs": [s.to_dict() for s in self.songs.values()]
        }, indent=2)


def get_genre_folder_path(base_dir: str, genre: str) -> str:
    """Get folder path for a genre."""
    # Sanitize genre name for filesystem
    safe_genre = re.sub(r'[<>:"/\\|?*]', '_', genre)
    return os.path.join(base_dir, "by_genre", safe_genre)


def organize_by_genre(base_dir: str, catalog: MusicCatalog) -> str:
    """Organize existing files by genre (creates symlinks or copies)."""
    import shutil
    
    genre_base = os.path.join(base_dir, "by_genre")
    os.makedirs(genre_base, exist_ok=True)
    
    organized = 0
    for song in catalog.songs.values():
        if not os.path.exists(song.file_path):
            continue
        
        genre_folder = get_genre_folder_path(base_dir, song.genre)
        os.makedirs(genre_folder, exist_ok=True)
        
        dest_path = os.path.join(genre_folder, os.path.basename(song.file_path))
        
        if not os.path.exists(dest_path):
            try:
                # Try to create symlink first (saves space)
                os.symlink(song.file_path, dest_path)
                organized += 1
            except OSError:
                # Fall back to copy
                shutil.copy2(song.file_path, dest_path)
                organized += 1
    
    return f"Organized {organized} songs into genre folders"


# Global catalog instance
music_catalog = MusicCatalog()
