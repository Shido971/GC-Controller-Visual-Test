"""Emplacements des fichiers (cache, config, sources VCT) selon l'OS."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "PhobGCCTool"


def _base_dir() -> Path:
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(root) / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    root = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(root) / APP_DIR_NAME.lower()


def data_dir() -> Path:
    d = _base_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def firmware_cache_dir() -> Path:
    d = data_dir() / "firmware"
    d.mkdir(parents=True, exist_ok=True)
    return d


def vct_build_dir() -> Path:
    d = data_dir() / "vct-build"
    d.mkdir(parents=True, exist_ok=True)
    return d


def bundled_root() -> Path:
    """Racine du projet (ou du bundle PyInstaller)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def vct_source_dir() -> Path:
    """Sources du portage PC (CMake) livrées avec l'outil."""
    return bundled_root() / "vct-pc"


def vct_exe_name() -> str:
    return "VisualControllerTest.exe" if sys.platform == "win32" else "VisualControllerTest"
