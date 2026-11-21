"""Config (ordem das cores) em ~/.config/cobra-rgb e backup das cores em ~/.local/share/cobra-rgb."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from .protocol import ORDERS, PROFILES, LedState


def _xdg(var: str, fallback: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / fallback) / "cobra-rgb"


def config_file() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config") / "config"


def backup_file() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share") / "backup-original.txt"


def load_order() -> str:
    try:
        for line in config_file().read_text(encoding="utf-8").splitlines():
            if line.startswith("ordem=") and line[6:].strip() in ORDERS:
                return line[6:].strip()
    except OSError:
        pass
    return "RGB"


def save_order(order: str) -> None:
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"ordem={order}\n", encoding="utf-8")


def save_backup_if_missing(leds: list[LedState]) -> bool:
    """Guarda as cores que estavam no mouse antes da primeira mudanca. Devolve True se criou agora."""
    path = backup_file()
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# cores originais do mouse, lidas pelo Cobra RGB em {datetime.now():%Y-%m-%d %H:%M}"]
    lines += [f"perfil{p + 1}=" + leds[p].to_bytes().hex(" ") for p in range(len(leds))]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def load_backup() -> dict[int, LedState]:
    """Le o backup (mesmo formato da versao Windows). Linhas invalidas sao ignoradas."""
    leds = {}
    for line in backup_file().read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if not sep or not key.startswith("perfil") or not key[6:].isdigit():
            continue
        profile = int(key[6:]) - 1
        try:
            data = bytes.fromhex(value)
        except ValueError:
            continue
        if 0 <= profile < PROFILES and len(data) == 7:
            leds[profile] = LedState.from_bytes(data)
    return leds
