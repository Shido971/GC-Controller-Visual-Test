"""Compilation et lancement des portages PC de Visual Controller Test et de GTS."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Optional

from .paths import (bundled_root, gts_build_dir, gts_exe_name, gts_source_dir, vct_build_dir,
                    vct_exe_name, vct_source_dir)

DEFAULT_UPSTREAM_REPO = "https://github.com/mardy/VisualControllerTest"
DEFAULT_UPSTREAM_REF = "e6482631b252b2a945965a036831036bf07ca5a5"
GTS_UPSTREAM_REPO = "https://github.com/greenwave-1/GTS"
GTS_UPSTREAM_REF = "9d72278e4114dc31a238f47a2e2d863ade7bf948"

# écrans de GTS accessibles directement (option --menu)
GTS_SCREENS = [
    ("Menu principal", ""),
    ("Controller Test", "controllertest"),
    ("Stick Oscilloscope (snapback…)", "oscilloscope"),
    ("Continuous Stick Oscilloscope", "continuous"),
    ("Trigger Oscilloscope", "trigger"),
    ("Coordinate Viewer", "coordview"),
    ("2D Plot", "2dplot"),
    ("Button Timing Viewer", "buttonplot"),
    ("Gate Visualizer", "gate"),
]


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


def find_gts_exe() -> Optional[Path]:
    name = gts_exe_name()
    b = gts_build_dir()
    root = bundled_root()
    for c in [b / name, b / "Release" / name, root / "bin" / name, root / name, root / "gts-pc" / "build" / name]:
        if c.is_file() and os.access(c, os.X_OK):
            return c
    return None


def _generator() -> list[str]:
    if sys.platform == "win32" and shutil.which("ninja"):
        return ["-G", "Ninja"]
    if sys.platform == "win32" and shutil.which("mingw32-make"):
        return ["-G", "MinGW Makefiles"]
    return []


def gts_configure_command() -> list[str]:
    return ["cmake", "-S", str(gts_source_dir()), "-B", str(gts_build_dir()), "-DCMAKE_BUILD_TYPE=Release",
            f"-DGTS_UPSTREAM_REPO={GTS_UPSTREAM_REPO}", f"-DGTS_UPSTREAM_REF={GTS_UPSTREAM_REF}"] + _generator()


def gts_build_command() -> list[str]:
    return ["cmake", "--build", str(gts_build_dir()), "--config", "Release", "--parallel"]


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
           f"-DVCT_UPSTREAM_DIR={local_upstream or ''}"] + _generator()
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
