# Utils package for Music Downloader v4.0
from utils.proxy import proxy_manager, ProxyConfig
from utils.catalog import music_catalog, SongEntry
from utils.filebrowser import file_browser

__all__ = [
    'proxy_manager',
    'ProxyConfig',
    'music_catalog',
    'SongEntry',
    'file_browser',
]
