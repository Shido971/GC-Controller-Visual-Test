"""Compilation et lancement du portage PC de Visual Controller Test."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Optional

from .paths import bundled_root, vct_build_dir, vct_exe_name, vct_source_dir

DEFAULT_UPSTREAM_REPO = "https://github.com/mardy/VisualControllerTest"
DEFAULT_UPSTREAM_REF = "e6482631b252b2a945965a036831036bf07ca5a5"


def find_vct_exe(extra: Optional[str] = None) -> Optional[Path]:
    """Cherche un exécutable déjà compilé : chemin choisi, build local, binaire livré."""
    name = vct_exe_name()
    cands = []
    if extra:
        cands.append(Path(extra))
    b = vct_build_dir()
    cands += [b / name, b / "Release" / name, b / "RelWithDebInfo" / name]
    root = bundled_root()
    cands += [root / "bin" / name, root / name, root / "vct-pc" / "build" / name]
    for c in cands:
        if c.is_file() and os.access(c, os.X_OK):
            return c
    return None


def toolchain_status() -> tuple[bool, str]:
    cmake = shutil.which("cmake")
    git = shutil.which("git")
    if not cmake:
        return False, ("CMake introuvable. Installe CMake, un compilateur C, SDL2 et libusb "
                       "(Windows : MSYS2 UCRT64 → voir README).")
    msg = f"CMake : {cmake}"
    msg += f"\nGit : {git}" if git else "\nGit absent : les sources seront téléchargées en archive."
    return True, msg


def configure_command(repo: str = DEFAULT_UPSTREAM_REPO, ref: str = DEFAULT_UPSTREAM_REF,
                      local_upstream: Optional[str] = None) -> list[str]:
    cmd = ["cmake", "-S", str(vct_source_dir()), "-B", str(vct_build_dir()),
           "-DCMAKE_BUILD_TYPE=Release",
           f"-DVCT_UPSTREAM_REPO={repo}", f"-DVCT_UPSTREAM_REF={ref}",
           f"-DVCT_UPSTREAM_DIR={local_upstream or ''}"]
    if sys.platform == "win32" and shutil.which("ninja"):
        cmd += ["-G", "Ninja"]
    elif sys.platform == "win32" and shutil.which("mingw32-make"):
        cmd += ["-G", "MinGW Makefiles"]
    return cmd


def build_command() -> list[str]:
    return ["cmake", "--build", str(vct_build_dir()), "--config", "Release", "--parallel"]


def launch_args(fullscreen: bool = False, scale: float = 1.5, sdl_fallback: bool = True) -> list[str]:
    args = ["--scale", f"{scale:g}"]
    if fullscreen:
        args.append("--fullscreen")
    if not sdl_fallback:
        args.append("--no-sdl-pads")
    return args
