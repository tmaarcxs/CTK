"""Configuration management for CTK."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = {
    "version": 1,
    "enabled": True,
    "commands": {
        "docker": {
            "enabled": True,
            "compose": True,
            "ps": True,
            "images": True,
            "logs": True,
        },
        "git": {"enabled": True, "status": True, "diff": True, "log": True},
        "system": {
            "enabled": True,
            "ps": True,
            "free": True,
            "date": True,
            "whoami": True,
        },
        "files": {
            "enabled": True,
            "ls": True,
            "tree": True,
            "grep": True,
            "find": True,
        },
        "python": {"enabled": True, "pytest": True, "ruff": True, "pip": True},
        "nodejs": {
            "enabled": True,
            "npm": True,
            "pnpm": True,
            "vitest": True,
            "tsc": True,
        },
    },
    "display": {
        "color": True,
        "compact": True,
        "max_lines": 100,
    },
    "metrics": {
        "enabled": True,
        "database": None,  # Will be set to default path
    },
}


class Config:
    """Configuration manager for CTK."""

    def __init__(self, config_path: Path | None = None):
        self.config_dir = Path.home() / ".config" / "ctk"
        self.config_path = config_path or (self.config_dir / "config.yaml")
        self._config: dict[str, Any] = {}
        self.load()

    @property
    def data_dir(self) -> Path:
        """Get the data directory path."""
        return Path.home() / ".local" / "share" / "ctk"

    @property
    def database_path(self) -> Path:
        """Get the metrics database path."""
        db_path = self._config.get("metrics", {}).get("database")
        if db_path:
            return Path(db_path)
        return self.data_dir / "metrics.db"

    def load(self) -> dict[str, Any]:
        """Load configuration from file."""
        if self.config_path.exists():
            with open(self.config_path) as f:
                self._config = yaml.safe_load(f) or {}
        else:
            self._config = {}

        # Merge with defaults
        self._config = self._merge(DEFAULT_CONFIG, self._config)
        return self._config

    def save(self) -> None:
        """Save configuration to file."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            yaml.dump(self._config, f, default_flow_style=False)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by dot-notation key."""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value by dot-notation key."""
        keys = key.split(".")
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    def is_command_enabled(self, category: str, command: str) -> bool:
        """Check if a specific command is enabled."""
        return bool(
            self.get(f"commands.{category}.enabled", True)
            and self.get(f"commands.{category}.{command}", True)
        )

    def _merge(self, base: dict, override: dict) -> dict:
        """Recursively merge two dictionaries."""
        result = base.copy()
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._merge(result[key], value)
            else:
                result[key] = value
        return result


# Global config instance
_config: Config | None = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config
