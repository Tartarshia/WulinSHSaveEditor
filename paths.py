"""Portable discovery and local preference storage for WulinSH."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path


APP_ID = "1948980"
GAME_FOLDER = "WulinSH"
TEAM_FILE = "SaveObjectPlayerTeam.save"


def is_game_root(path: Path) -> bool:
    return (path / "Wulin.exe").is_file() and (path / "Wulin_Data").is_dir()


def is_save_root(path: Path) -> bool:
    return path.is_dir() and any((slot / TEAM_FILE).is_file() for slot in path.iterdir() if slot.is_dir() and (slot.name.startswith("Save") or slot.name.startswith("QuickSave")))


def _steam_roots() -> list[Path]:
    roots: list[Path] = []
    for value in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES")):
        if value:
            roots.append(Path(value) / "Steam")
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            roots.append(Path(winreg.QueryValueEx(key, "SteamPath")[0]))
    except (ImportError, OSError):
        pass
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique


def discover_game_roots() -> list[Path]:
    candidates: list[Path] = []
    for steam_root in _steam_roots():
        libraries = [steam_root]
        library_file = steam_root / "steamapps/libraryfolders.vdf"
        if library_file.is_file():
            text = library_file.read_text(encoding="utf-8", errors="ignore")
            libraries.extend(Path(value.replace("\\\\", "\\")) for value in re.findall(r'"path"\s+"([^"]+)"', text))
        for library in libraries:
            candidate = library / "steamapps/common" / GAME_FOLDER
            manifest = library / "steamapps" / f"appmanifest_{APP_ID}.acf"
            if is_game_root(candidate) and manifest.is_file():
                candidates.append(candidate)
    return list(dict.fromkeys(candidates))


def discover_save_roots() -> list[Path]:
    local_low = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "AppData/LocalLow/DefaultCompany/Wulin"
    if not local_low.is_dir():
        return []
    return sorted((path for path in local_low.iterdir() if is_save_root(path)), key=lambda path: path.stat().st_mtime, reverse=True)


def config_path() -> Path:
    base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))) / "WulinSHSaveEditor"
    return base / "config.json"


def load_preferences() -> dict[str, str]:
    path = config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {key: value for key, value in data.items() if key in {"game_root", "save_root"} and isinstance(value, str)}
    except (OSError, json.JSONDecodeError):
        return {}


def save_preferences(game_root: Path | None, save_root: Path | None) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"game_root": str(game_root) if game_root else "", "save_root": str(save_root) if save_root else ""}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
