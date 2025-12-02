# =============================================================================
# FILE BROWSER - Terminal-like Directory Navigation
# =============================================================================

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional

BASE_DOWNLOAD_DIR = os.environ.get("MUSIC_DL_ROOT", str(Path.home() / "music_downloads"))


class FileBrowser:
    """Terminal-like file browser for managing download locations."""
    
    def __init__(self):
        self.current_dir = BASE_DOWNLOAD_DIR
        self.command_history: List[str] = []
    
    def _ensure_safe_path(self, path: str) -> str:
        """Ensure path is absolute and exists."""
        if not os.path.isabs(path):
            path = os.path.join(self.current_dir, path)
        return os.path.normpath(path)
    
    def pwd(self) -> str:
        """Print working directory."""
        return self.current_dir
    
    def cd(self, path: str = "") -> str:
        """Change directory."""
        if not path or path == "~":
            self.current_dir = str(Path.home())
            return f"Changed to: {self.current_dir}"
        
        if path == "-":
            # Go to previous directory
            if len(self.command_history) > 1:
                prev = self.command_history[-2] if self.command_history else self.current_dir
                self.current_dir = prev
            return f"Changed to: {self.current_dir}"
        
        new_path = self._ensure_safe_path(path)
        
        if os.path.isdir(new_path):
            self.current_dir = new_path
            return f"Changed to: {self.current_dir}"
        else:
            return f"Error: Directory not found: {path}"
    
    def ls(self, path: str = "", show_hidden: bool = False, long_format: bool = True) -> str:
        """List directory contents."""
        target = self._ensure_safe_path(path) if path else self.current_dir
        
        if not os.path.isdir(target):
            return f"Error: Not a directory: {target}"
        
        try:
            entries = os.listdir(target)
            if not show_hidden:
                entries = [e for e in entries if not e.startswith('.')]
            entries.sort(key=lambda x: (not os.path.isdir(os.path.join(target, x)), x.lower()))
            
            if not entries:
                return "(empty directory)"
            
            if long_format:
                lines = [f"Directory: {target}", "-" * 60]
                for entry in entries:
                    full_path = os.path.join(target, entry)
                    try:
                        stat = os.stat(full_path)
                        is_dir = os.path.isdir(full_path)
                        size = stat.st_size
                        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                        
                        if is_dir:
                            size_str = "<DIR>"
                            entry_str = f"{entry}/"
                        else:
                            size_str = self._format_size(size)
                            entry_str = entry
                        
                        lines.append(f"{mtime}  {size_str:>10}  {entry_str}")
                    except OSError:
                        lines.append(f"                          {entry}")
                
                return "\n".join(lines)
            else:
                return "  ".join(entries)
        except PermissionError:
            return f"Error: Permission denied: {target}"
    
    def _format_size(self, size: float) -> str:
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"
    
    def mkdir(self, path: str) -> str:
        """Create directory."""
        target = self._ensure_safe_path(path)
        try:
            os.makedirs(target, exist_ok=True)
            return f"Created directory: {target}"
        except Exception as e:
            return f"Error creating directory: {e}"
    
    def rm(self, path: str, recursive: bool = False) -> str:
        """Remove file or directory."""
        target = self._ensure_safe_path(path)
        
        if not os.path.exists(target):
            return f"Error: Path not found: {path}"
        
        try:
            if os.path.isdir(target):
                if recursive:
                    shutil.rmtree(target)
                    return f"Removed directory: {target}"
                else:
                    os.rmdir(target)
                    return f"Removed empty directory: {target}"
            else:
                os.remove(target)
                return f"Removed file: {target}"
        except Exception as e:
            return f"Error removing: {e}"
    
    def mv(self, source: str, dest: str) -> str:
        """Move file or directory."""
        src = self._ensure_safe_path(source)
        dst = self._ensure_safe_path(dest)
        
        if not os.path.exists(src):
            return f"Error: Source not found: {source}"
        
        try:
            shutil.move(src, dst)
            return f"Moved: {source} -> {dest}"
        except Exception as e:
            return f"Error moving: {e}"
    
    def cp(self, source: str, dest: str) -> str:
        """Copy file or directory."""
        src = self._ensure_safe_path(source)
        dst = self._ensure_safe_path(dest)
        
        if not os.path.exists(src):
            return f"Error: Source not found: {source}"
        
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            return f"Copied: {source} -> {dest}"
        except Exception as e:
            return f"Error copying: {e}"
    
    def tree(self, path: str = "", max_depth: int = 2) -> str:
        """Show directory tree."""
        target = self._ensure_safe_path(path) if path else self.current_dir
        
        if not os.path.isdir(target):
            return f"Error: Not a directory: {target}"
        
        lines = [target]
        self._tree_recurse(target, "", lines, 0, max_depth)
        return "\n".join(lines[:100])  # Limit output
    
    def _tree_recurse(self, path: str, prefix: str, lines: List[str], depth: int, max_depth: int):
        if depth >= max_depth:
            return
        
        try:
            entries = sorted(os.listdir(path))
            entries = [e for e in entries if not e.startswith('.')]
            
            for i, entry in enumerate(entries):
                is_last = i == len(entries) - 1
                connector = "└── " if is_last else "├── "
                full_path = os.path.join(path, entry)
                
                if os.path.isdir(full_path):
                    lines.append(f"{prefix}{connector}{entry}/")
                    new_prefix = prefix + ("    " if is_last else "│   ")
                    self._tree_recurse(full_path, new_prefix, lines, depth + 1, max_depth)
                else:
                    lines.append(f"{prefix}{connector}{entry}")
        except PermissionError:
            pass
    
    def du(self, path: str = "") -> str:
        """Show disk usage."""
        target = self._ensure_safe_path(path) if path else self.current_dir
        
        if not os.path.exists(target):
            return f"Error: Path not found: {path}"
        
        total_size = 0
        file_count = 0
        dir_count = 0
        
        if os.path.isfile(target):
            return f"{self._format_size(os.path.getsize(target))}  {target}"
        
        for root, dirs, files in os.walk(target):
            dir_count += len(dirs)
            for f in files:
                file_count += 1
                try:
                    total_size += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        
        return "\n".join([
            f"Path: {target}",
            f"Total Size: {self._format_size(total_size)}",
            f"Files: {file_count}",
            f"Directories: {dir_count}",
        ])
    
    def find(self, pattern: str, path: str = "") -> str:
        """Find files matching pattern."""
        target = self._ensure_safe_path(path) if path else self.current_dir
        pattern_lower = pattern.lower()
        
        matches = []
        for root, dirs, files in os.walk(target):
            for f in files:
                if pattern_lower in f.lower():
                    rel_path = os.path.relpath(os.path.join(root, f), target)
                    matches.append(rel_path)
        
        if not matches:
            return f"No files matching '{pattern}' found"
        
        return "\n".join(matches[:50])  # Limit results
    
    def execute_command(self, command_str: str) -> str:
        """Execute a terminal command."""
        command_str = command_str.strip()
        if not command_str:
            return ""
        
        self.command_history.append(self.current_dir)
        
        parts = command_str.split()
        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        # Built-in commands
        if cmd == "pwd":
            return self.pwd()
        elif cmd == "cd":
            return self.cd(args[0] if args else "")
        elif cmd == "ls":
            show_hidden = "-a" in args
            long_format = "-l" in args or not any(a.startswith("-") for a in args)
            path = next((a for a in args if not a.startswith("-")), "")
            return self.ls(path, show_hidden, long_format)
        elif cmd == "mkdir":
            if args:
                return self.mkdir(args[0])
            return "Usage: mkdir <directory>"
        elif cmd == "rm":
            if args:
                recursive = "-r" in args or "-rf" in args
                path = next((a for a in args if not a.startswith("-")), "")
                return self.rm(path, recursive)
            return "Usage: rm [-r] <path>"
        elif cmd == "mv":
            if len(args) >= 2:
                return self.mv(args[0], args[1])
            return "Usage: mv <source> <destination>"
        elif cmd == "cp":
            if len(args) >= 2:
                return self.cp(args[0], args[1])
            return "Usage: cp <source> <destination>"
        elif cmd == "tree":
            depth = 2
            if args and args[0].isdigit():
                depth = int(args[0])
            return self.tree(max_depth=depth)
        elif cmd == "du":
            return self.du(args[0] if args else "")
        elif cmd == "find":
            if args:
                return self.find(args[0])
            return "Usage: find <pattern>"
        elif cmd == "help":
            return self._get_help()
        elif cmd == "clear":
            return "\n" * 20  # Clear screen effect
        else:
            return f"Unknown command: {cmd}. Type 'help' for available commands."
    
    def _get_help(self) -> str:
        return """Available Commands:
====================
pwd                    - Print working directory
cd <path>              - Change directory (cd ~ for home, cd - for previous)
ls [-a] [-l] [path]    - List directory contents
mkdir <dir>            - Create directory
rm [-r] <path>         - Remove file/directory (-r for recursive)
mv <src> <dest>        - Move file/directory
cp <src> <dest>        - Copy file/directory
tree [depth]           - Show directory tree
du [path]              - Show disk usage
find <pattern>         - Find files matching pattern
clear                  - Clear screen
help                   - Show this help"""
    
    def get_directory_choices(self, base_path: str = "") -> List[str]:
        """Get list of subdirectories for dropdown."""
        target = base_path or str(Path.home())
        choices = [target]
        
        try:
            for entry in os.listdir(target):
                full_path = os.path.join(target, entry)
                if os.path.isdir(full_path) and not entry.startswith('.'):
                    choices.append(full_path)
        except Exception:
            pass
        
        return sorted(choices)


# Global file browser instance
file_browser = FileBrowser()
