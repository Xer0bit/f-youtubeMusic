# =============================================================================
# PROXY MANAGER - Network Configuration & IP Detection
# =============================================================================

import json
import os
import socket
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional, Dict, Any
from pathlib import Path

PROXY_CONFIG_FILE = os.path.join(
    os.environ.get("MUSIC_DL_ROOT", str(Path.home() / "music_downloads")),
    "proxy_config.json"
)

@dataclass
class ProxyConfig:
    """Proxy configuration settings."""
    enabled: bool = False
    proxy_type: str = "http"  # http, https, socks4, socks5
    host: str = ""
    port: int = 0
    username: str = ""
    password: str = ""
    
    def get_proxy_url(self) -> str:
        """Build proxy URL string for yt-dlp."""
        if not self.enabled or not self.host or not self.port:
            return ""
        
        auth = ""
        if self.username:
            auth = f"{self.username}"
            if self.password:
                auth += f":{self.password}"
            auth += "@"
        
        if self.proxy_type in ("socks4", "socks5"):
            return f"{self.proxy_type}://{auth}{self.host}:{self.port}"
        return f"http://{auth}{self.host}:{self.port}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "proxy_type": self.proxy_type,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "password": self.password,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProxyConfig":
        return cls(
            enabled=data.get("enabled", False),
            proxy_type=data.get("proxy_type", "http"),
            host=data.get("host", ""),
            port=data.get("port", 0),
            username=data.get("username", ""),
            password=data.get("password", ""),
        )


class ProxyManager:
    """Manages proxy configuration and IP detection."""
    
    def __init__(self):
        self.config = self._load_config()
    
    def _load_config(self) -> ProxyConfig:
        """Load proxy configuration from file."""
        try:
            if os.path.exists(PROXY_CONFIG_FILE):
                with open(PROXY_CONFIG_FILE, "r", encoding="utf-8") as f:
                    return ProxyConfig.from_dict(json.load(f))
        except Exception:
            pass
        return ProxyConfig()
    
    def save_config(self) -> None:
        """Save proxy configuration to file."""
        os.makedirs(os.path.dirname(PROXY_CONFIG_FILE), exist_ok=True)
        with open(PROXY_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config.to_dict(), f, indent=2)
    
    def update_config(
        self,
        enabled: bool,
        proxy_type: str,
        host: str,
        port: int,
        username: str = "",
        password: str = ""
    ) -> str:
        """Update proxy configuration."""
        self.config = ProxyConfig(
            enabled=enabled,
            proxy_type=proxy_type,
            host=host.strip(),
            port=int(port) if port else 0,
            username=username.strip(),
            password=password,
        )
        self.save_config()
        return "Proxy configuration saved!"
    
    def get_current_ip(self, use_proxy: bool = False) -> str:
        """Get current external IP address."""
        ip_services = [
            "https://api.ipify.org",
            "https://icanhazip.com",
            "https://ifconfig.me/ip",
            "https://checkip.amazonaws.com",
        ]
        
        for service in ip_services:
            try:
                if use_proxy and self.config.enabled and self.config.get_proxy_url():
                    proxy_handler = urllib.request.ProxyHandler({
                        "http": self.config.get_proxy_url(),
                        "https": self.config.get_proxy_url(),
                    })
                    opener = urllib.request.build_opener(proxy_handler)
                else:
                    opener = urllib.request.build_opener()
                
                with opener.open(service, timeout=10) as response:
                    ip = response.read().decode("utf-8").strip()
                    if ip and len(ip) < 50:  # Basic validation
                        return ip
            except Exception:
                continue
        
        return "Unable to detect IP"
    
    def get_local_ip(self) -> str:
        """Get local network IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
    
    def test_proxy(self) -> tuple:
        """Test proxy connection and return status."""
        if not self.config.enabled:
            return False, "Proxy disabled"
        
        if not self.config.host or not self.config.port:
            return False, "Proxy not configured"
        
        try:
            # Test connection through proxy
            proxy_ip = self.get_current_ip(use_proxy=True)
            direct_ip = self.get_current_ip(use_proxy=False)

            if proxy_ip == "Unable to detect IP":
                return False, "Proxy test FAILED - Cannot connect through proxy"

            if proxy_ip == direct_ip:
                return True, f"WARNING: Proxy IP same as direct IP ({proxy_ip})"

            return True, f"Proxy working! IP: {proxy_ip} (Direct: {direct_ip})"
        except Exception as e:
            return False, f"Proxy test FAILED: {str(e)[:250]}"
    
    def get_network_info(self) -> Dict[str, Any]:
        """Return a structured dictionary with network information.

        Keys returned:
          - current_ip: the IP visible to external world (proxy IP when proxy is enabled)
          - direct_ip: IP when not using proxy
          - proxy_ip: IP when using proxy (or None)
          - local_ip: local LAN IP
          - location: human-friendly location string when available
          - isp: ISP name when available
          - proxy_config: proxy configuration dict
          - raw: raw JSON from ipinfo (if available)
        """
        result: Dict[str, Any] = {
            "current_ip": "Unknown",
            "direct_ip": "Unknown",
            "proxy_ip": None,
            "local_ip": self.get_local_ip(),
            "location": "Unknown",
            "isp": "Unknown",
            "proxy_config": self.config.to_dict() if self.config else None,
            "raw": None,
        }

        try:
            direct_ip = self.get_current_ip(use_proxy=False)
            result["direct_ip"] = direct_ip if isinstance(direct_ip, str) else str(direct_ip)
        except Exception:
            result["direct_ip"] = "Unknown"

        # If proxy enabled, attempt to get IP via proxy
        if self.config and self.config.enabled and self.config.get_proxy_url():
            try:
                proxy_ip = self.get_current_ip(use_proxy=True)
                result["proxy_ip"] = proxy_ip if isinstance(proxy_ip, str) else str(proxy_ip)
            except Exception:
                result["proxy_ip"] = None

        # current_ip prefers proxy_ip when present
        if result.get("proxy_ip"):
            result["current_ip"] = result["proxy_ip"]
        elif result.get("direct_ip"):
            result["current_ip"] = result["direct_ip"]

        # try to enrich with location/ISP via ipinfo.io
        try:
            # prefer fetching details for the current_ip (if available)
            ip_lookup = result.get("current_ip") or result.get("direct_ip")
            if ip_lookup and ip_lookup not in ("Unknown", "Unable to detect IP"):
                url = f"https://ipinfo.io/{ip_lookup}/json"
            else:
                url = "https://ipinfo.io/json"

            with urllib.request.urlopen(url, timeout=6) as resp:
                raw = json.load(resp)
                result["raw"] = raw
                city = raw.get("city") or ""
                region = raw.get("region") or ""
                country = raw.get("country") or ""
                org = raw.get("org") or ""
                location = ", ".join([p for p in (city, region, country) if p])
                result["location"] = location or "Unknown"
                # org often contains ISP/AS name; attempt to extract ISP
                result["isp"] = org
        except Exception:
            # Best-effort — do not fail hard
            pass

        return result
    
    def get_yt_dlp_opts(self) -> Dict[str, Any]:
        """Get yt-dlp options for proxy configuration."""
        if not self.config.enabled or not self.config.get_proxy_url():
            return {}
        
        return {
            "proxy": self.config.get_proxy_url(),
        }


# Global proxy manager instance
proxy_manager = ProxyManager()
