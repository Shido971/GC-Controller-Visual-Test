"""Mise à jour automatique de PhobGCC Tool depuis les Releases GitHub du projet.

Chaque build de la CI porte un numéro (``BUILD``, écrit dans ``_build.py``). La release « latest »
publie un ``version.json`` avec le numéro du dernier build : s'il est plus grand, une mise à jour existe.

Installation (version empaquetée seulement) : l'archive est téléchargée et extraite à côté, puis un petit
script attend la fermeture de l'appli, remplace les fichiers du dossier d'installation et la relance.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import __version__

REPO = "Shido971/GC-Controller-Visual-Test"
CHANNEL = "latest"
VERSION_URL = f"https://github.com/{REPO}/releases/download/{CHANNEL}/version.json"
RELEASE_PAGE = f"https://github.com/{REPO}/releases/tag/{CHANNEL}"
UA = f"PhobGCC-Tool/{__version__}"

try:  # généré par la CI
    from ._build import BUILD, SHA  # type: ignore
except Exception:  # exécution depuis les sources
    BUILD, SHA = 0, ""


@dataclass
class UpdateInfo:
    build: int
    sha: str
    date: str
    notes: str
    asset_url: Optional[str]
    asset_name: Optional[str]

    @property
    def label(self) -> str:
        return f"build {self.build}" + (f" ({self.sha[:7]}, {self.date})" if self.sha else "")


def current_label() -> str:
    if not BUILD:
        return f"{__version__} (sources)"
    return f"{__version__} · build {BUILD}" + (f" ({SHA[:7]})" if SHA else "")


def platform_key() -> Optional[str]:
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    return None


def is_packaged() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_dir() -> Path:
    """Dossier contenant l'exécutable (PyInstaller onedir)."""
    return Path(sys.executable).resolve().parent


def can_self_update() -> tuple[bool, str]:
    if not is_packaged():
        return False, "version lancée depuis les sources : fais un « git pull » pour mettre à jour"
    if platform_key() is None:
        return False, "mise à jour automatique non disponible sur ce système"
    d = install_dir()
    try:
        probe = d / ".phobtool-write-test"
        probe.write_text("ok")
        probe.unlink()
    except OSError:
        return False, f"pas le droit d'écrire dans {d} : télécharge la nouvelle version à la main"
    return True, ""


def _get(url: str, timeout: float = 10.0):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    return urllib.request.urlopen(req, timeout=timeout)


def parse_version_json(data: dict, platform: Optional[str]) -> UpdateInfo:
    assets = data.get("assets") or {}
    a = assets.get(platform or "") if isinstance(assets, dict) else None
    return UpdateInfo(
        build=int(data.get("build", 0)), sha=str(data.get("sha", "")), date=str(data.get("date", "")),
        notes=str(data.get("notes", "")),
        asset_url=(a or {}).get("url"), asset_name=(a or {}).get("name"))


def check(current: Optional[int] = None) -> Optional[UpdateInfo]:
    """Renvoie l'info de mise à jour si un build plus récent existe, sinon None. Lève en cas d'erreur réseau."""
    cur = BUILD if current is None else current
    with _get(VERSION_URL) as r:
        info = parse_version_json(json.loads(r.read().decode("utf-8")), platform_key())
    if cur and info.build > cur:
        return info
    if not cur and info.build:  # sources : on signale seulement, sans installer
        return info
    return None


def download(info: UpdateInfo, progress: Callable[[int, int], None], cancelled: Callable[[], bool]) -> Path:
    if not info.asset_url or not info.asset_name:
        raise RuntimeError("aucun fichier de mise à jour pour ce système")
    work = Path(tempfile.mkdtemp(prefix="phobtool-update-"))
    dest = work / info.asset_name
    with _get(info.asset_url, timeout=30) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if cancelled():
                raise InterruptedError("téléchargement annulé")
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            progress(done, total)
    return dest


def extract(archive: Path) -> Path:
    """Extrait l'archive et renvoie le dossier « PhobGCCTool » qu'elle contient."""
    out = archive.parent / "new"
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            for m in z.namelist():  # pas de chemin qui sort du dossier
                if m.startswith("/") or ".." in Path(m).parts:
                    raise RuntimeError(f"archive invalide : {m}")
            z.extractall(out)
    else:
        with tarfile.open(archive) as t:
            t.extractall(out, filter="data")
    root = out / "PhobGCCTool"
    exe = root / ("PhobGCCTool.exe" if sys.platform == "win32" else "PhobGCCTool")
    if not exe.is_file():
        raise RuntimeError("archive inattendue : PhobGCCTool introuvable")
    return root


def _windows_script(src: Path, dst: Path, exe: str, pid: int) -> str:
    return f"""@echo off
chcp 65001 >nul
title Mise a jour de PhobGCC Tool
echo Mise a jour de PhobGCC Tool, patiente quelques secondes...
:wait
tasklist /FI "PID eq {pid}" /NH 2>nul | find " {pid} " >nul
if not errorlevel 1 ( ping -n 2 127.0.0.1 >nul & goto wait )
robocopy "{src}\\_internal" "{dst}\\_internal" /MIR /R:5 /W:1 /NFL /NDL /NJH /NJS >nul
robocopy "{src}" "{dst}" /XD _internal /E /R:5 /W:1 /NFL /NDL /NJH /NJS >nul
start "" "{dst}\\{exe}"
rmdir /S /Q "{src.parent.parent}" >nul 2>&1
"""


def _posix_script(src: Path, dst: Path, exe: str, pid: int) -> str:
    return f"""#!/bin/sh
while kill -0 {pid} 2>/dev/null; do sleep 0.5; done
rm -rf "{dst}/_internal"
cp -a "{src}/." "{dst}/"
chmod +x "{dst}/{exe}" "{dst}/_internal/bin/"* 2>/dev/null
nohup "{dst}/{exe}" >/dev/null 2>&1 &
rm -rf "{src.parent.parent}"
"""


def launch_installer(new_root: Path) -> None:
    """Lance le script qui remplacera les fichiers dès que l'appli sera fermée. L'appelant doit quitter ensuite."""
    dst = install_dir()
    exe = Path(sys.executable).name
    pid = os.getpid()
    work = new_root.parent.parent
    if sys.platform == "win32":
        script = work / "update.bat"
        script.write_text(_windows_script(new_root, dst, exe, pid), encoding="utf-8")
        # console cachée (robocopy/tasklist en ont besoin) ; le script survit à la fermeture de l'appli
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(["cmd", "/c", str(script)], creationflags=flags, close_fds=True)
    else:
        script = work / "update.sh"
        script.write_text(_posix_script(new_root, dst, exe, pid))
        script.chmod(0o755)
        subprocess.Popen(["/bin/sh", str(script)], start_new_session=True, close_fds=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cleanup(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
