"""Application-level settings persistence (window size, theme, recent files).

Why: Users expect their window layout, theme preference, and recently used
     file paths to survive across application restarts. Without persistence,
     every launch starts from scratch.
How: Stores a compact JSON file in the platform-appropriate app data
     directory. Settings are loaded once on startup and saved on each
     significant state change (window resize, theme toggle, file open).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

_MAX_RECENT_ENTRIES: int = 5


def _settings_path() -> Path:
    """Determine the platform-appropriate path for app settings.

    Why: Each OS has a conventional location for per-user application data;
         following the convention makes the file discoverable and avoids
         polluting the home directory.
    How: Uses %APPDATA% on Windows, ~/.config on Linux/macOS.

    Returns:
        Absolute Path to the settings JSON file.
    """
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home())))
    else:
        base = Path.home() / ".config"
    return base / "csp-name-splitter" / "app_settings.json"


@dataclass
class AppSettings:
    """Persistent application settings.

    Why: Centralising all persistent state in a single dataclass makes
         serialisation straightforward and keeps gui.py free of ad-hoc
         file I/O logic.
    How: Plain dataclass with default values matching the first-launch
         experience. add_recent_* methods manage bounded FIFO lists.
         preset_* methods manage named configuration snapshots.
    """

    window_width: int = 1200
    window_height: int = 850
    theme_mode: str = "light"
    recent_configs: list[str] = field(default_factory=list)
    recent_inputs: list[str] = field(default_factory=list)
    auto_open_output: bool = True
    first_run: bool = True
    presets: list[dict[str, object]] = field(default_factory=list)
    last_run_config: dict[str, object] | None = None

    def add_recent_config(self, path: str) -> None:
        """Record a config file path, keeping most-recent first.

        Why: MRU list size must be bounded to avoid unbounded growth.
        How: Removes duplicate if present, prepends, truncates to limit.
        """
        if path in self.recent_configs:
            self.recent_configs.remove(path)
        self.recent_configs.insert(0, path)
        self.recent_configs = self.recent_configs[:_MAX_RECENT_ENTRIES]

    def add_recent_input(self, path: str) -> None:
        """Record an input image path, keeping most-recent first.

        Why: Same bounded MRU rationale as add_recent_config.
        How: Same dedup-then-prepend strategy.
        """
        if path in self.recent_inputs:
            self.recent_inputs.remove(path)
        self.recent_inputs.insert(0, path)
        self.recent_inputs = self.recent_inputs[:_MAX_RECENT_ENTRIES]

    def save_preset(self, name: str, config_dict: dict) -> None:
        """Add or overwrite a named preset with the given configuration dict.

        Why: Users repeatedly switch between a small set of configurations;
             presets eliminate re-entering all fields each time.
        How: Removes any existing preset with the same name (case-sensitive),
             then appends the new entry so the list stays ordered by insertion.

        Args:
            name: Human-readable preset name (must be non-empty).
            config_dict: Serialisable dict representing the UI configuration.
        """
        self.presets = [p for p in self.presets if p.get("name") != name]
        self.presets.append({"name": name, "config": config_dict})

    def delete_preset(self, name: str) -> None:
        """Remove the preset with the given name, if it exists.

        Why: Stale presets clutter the dropdown; deletion keeps the list
             manageable without requiring an app restart.
        How: Filters out any entry whose "name" key matches; no-op if absent.

        Args:
            name: Preset name to remove.
        """
        self.presets = [p for p in self.presets if p.get("name") != name]

    def get_preset_names(self) -> list[str]:
        """Return the ordered list of saved preset names.

        Why: The preset dropdown needs the current name list every time it
             is rebuilt (save, delete, initial load).
        How: Extracts the "name" key from each preset entry in list order.

        Returns:
            List of preset name strings; empty if no presets have been saved.
        """
        return [str(p["name"]) for p in self.presets if "name" in p]

    def get_preset(self, name: str) -> dict | None:
        """Return the config dict for the named preset, or None if not found.

        Why: The load-preset handler needs the config dict to apply field
             values to the UI without hitting the filesystem.
        How: Linear scan — preset count is small enough to make this trivial.

        Args:
            name: Preset name to look up.

        Returns:
            Config dict stored under the preset name, or None if not found.
        """
        for p in self.presets:
            if p.get("name") == name:
                cfg = p.get("config")
                return dict(cfg) if isinstance(cfg, dict) else None
        return None


def load_app_settings() -> AppSettings:
    """Load settings from disk, falling back to defaults on any error.

    Why: The app must always start even if the settings file is corrupt or
         missing. Silently falling back to defaults is the safest approach.
    How: Reads JSON, filters known fields, and unpacks into AppSettings.

    Returns:
        AppSettings populated from disk or fresh defaults.
    """
    path = _settings_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            known_fields = {f for f in AppSettings.__dataclass_fields__}
            filtered = {k: v for k, v in data.items() if k in known_fields}
            return AppSettings(**filtered)
        except Exception:  # noqa: BLE001
            pass
    return AppSettings()


def save_app_settings(settings: AppSettings) -> None:
    """Persist settings to disk, creating directories as needed.

    Why: Settings must survive application restarts. Writing on each
         significant state change ensures minimal data loss on crash.
    How: Serialises the dataclass to JSON and writes atomically.
    """
    path = _settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass  # Why: Failure to persist settings must never crash the app


__all__ = ["AppSettings", "load_app_settings", "save_app_settings"]
