"""Flash du firmware PhobGCC.

* PhobGCC 2.x (RP2040) : la carte en mode BOOTSEL apparaît comme une clé USB
  « RPI-RP2 ». Copier le .uf2 dessus suffit ; la manette redémarre seule.
* PhobGCC 1.x (Teensy) : via teensy_loader_cli s'il est installé.
"""
from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

UF2_MAGIC_START0 = 0x0A324655
UF2_MAGIC_START1 = 0x9E5D5157
UF2_MAGIC_END = 0x0AB16F30
UF2_FLAG_FAMILY_ID = 0x00002000
RP2040_FAMILY_ID = 0xE48BFF56


class FirmwareError(RuntimeError):
    pass


@dataclass
class Uf2Info:
    blocks: int
    family_id: Optional[int]
    payload_bytes: int
    start_addr: int


def validate_uf2(path: Path, require_rp2040: bool = True) -> Uf2Info:
    """Vérifie la structure du fichier UF2 (magic, numérotation, famille RP2040)."""
    data = Path(path).read_bytes()
    if len(data) == 0 or len(data) % 512:
        raise FirmwareError("taille de fichier UF2 invalide (doit être un multiple de 512 octets)")
    n = len(data) // 512
    family = None
    payload = 0
    start = None
    for i in range(n):
        blk = data[i * 512:(i + 1) * 512]
        m0, m1, flags, addr, size, blockno, numblocks, fam = struct.unpack_from("<8I", blk, 0)
        (mend,) = struct.unpack_from("<I", blk, 508)
        if m0 != UF2_MAGIC_START0 or m1 != UF2_MAGIC_START1 or mend != UF2_MAGIC_END:
            raise FirmwareError(f"bloc UF2 {i} corrompu (magic incorrect)")
        if blockno != i or numblocks != n:
            raise FirmwareError(f"numérotation UF2 incohérente au bloc {i}")
        if size > 476:
            raise FirmwareError(f"bloc UF2 {i}: taille de données invalide")
        if flags & UF2_FLAG_FAMILY_ID:
            if family is None:
                family = fam
            elif fam != family:
                raise FirmwareError("plusieurs familles de MCU dans le même UF2")
        if start is None:
            start = addr
        payload += size
    if require_rp2040 and family != RP2040_FAMILY_ID:
        raise FirmwareError(f"ce UF2 ne cible pas un RP2040 (famille 0x{(family or 0):08X})")
    return Uf2Info(blocks=n, family_id=family, payload_bytes=payload, start_addr=start or 0)


# ---------------------------------------------------------------------------
# Détection du lecteur BOOTSEL RPI-RP2
# ---------------------------------------------------------------------------
def _candidate_mounts() -> list[Path]:
    cands: list[Path] = []
    if sys.platform == "win32":
        import string
        try:
            import ctypes
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()  # type: ignore[attr-defined]
        except Exception:
            bitmask = (1 << 26) - 1
        for i, letter in enumerate(string.ascii_uppercase):
            if bitmask & (1 << i) and letter not in "AB":
                cands.append(Path(f"{letter}:\\"))
    elif sys.platform == "darwin":
        vol = Path("/Volumes")
        if vol.is_dir():
            cands += [p for p in vol.iterdir() if p.is_dir()]
    else:
        user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
        roots = [Path("/media") / user, Path("/run/media") / user, Path("/media"), Path("/mnt")]
        for r in roots:
            try:
                if r.is_dir():
                    cands += [p for p in r.iterdir() if p.is_dir()]
            except PermissionError:
                pass
    return cands


def is_rp2_bootloader(mount: Path) -> bool:
    info = mount / "INFO_UF2.TXT"
    try:
        if not info.is_file():
            return False
        txt = info.read_text(errors="ignore")
    except OSError:
        return False
    return "RP2040" in txt or "RPI-RP2" in txt


def find_rp2_drives() -> list[Path]:
    return [m for m in _candidate_mounts() if is_rp2_bootloader(m)]


def wait_for_rp2_drive(timeout: float = 120.0, poll: float = 0.5,
                       cancelled: Optional[Callable[[], bool]] = None) -> Optional[Path]:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cancelled and cancelled():
            return None
        drives = find_rp2_drives()
        if drives:
            return drives[0]
        time.sleep(poll)
    return None


def flash_uf2(uf2: Path, drive: Path,
              progress: Optional[Callable[[int, int], None]] = None) -> None:
    """Copie le .uf2 sur le lecteur BOOTSEL. Le RP2040 redémarre dès le dernier bloc reçu,
    il est donc normal que le lecteur disparaisse à la fin de la copie."""
    validate_uf2(uf2)
    data = Path(uf2).read_bytes()
    target = Path(drive) / Path(uf2).name
    total = len(data)
    written = 0
    try:
        with open(target, "wb", buffering=0) as f:
            step = 64 * 512
            while written < total:
                chunk = data[written:written + step]
                f.write(chunk)
                written += len(chunk)
                if progress:
                    progress(written, total)
            try:
                f.flush()
                os.fsync(f.fileno())
            except OSError:
                pass  # lecteur déjà démonté par le reboot : normal
    except OSError as e:
        if written < total:
            raise FirmwareError(f"copie interrompue après {written}/{total} octets : {e}") from e


def wait_for_drive_gone(drive: Path, timeout: float = 15.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not is_rp2_bootloader(Path(drive)):
            return True
        time.sleep(0.3)
    return False


# ---------------------------------------------------------------------------
# Teensy (PhobGCC 1.x)
# ---------------------------------------------------------------------------
TEENSY_MCU = {"teensy40": "TEENSY40", "teensy32": "TEENSY32"}


def find_teensy_loader() -> Optional[str]:
    return shutil.which("teensy_loader_cli") or shutil.which("teensy_loader_cli.exe")


def flash_teensy(hex_file: Path, board: str, log: Callable[[str], None]) -> None:
    exe = find_teensy_loader()
    if not exe:
        raise FirmwareError(
            "teensy_loader_cli introuvable. Installe-le (ou utilise Teensy Loader de PJRC) "
            "puis ouvre le fichier .hex téléchargé et appuie sur le bouton du Teensy.")
    mcu = TEENSY_MCU.get(board, "TEENSY40")
    cmd = [exe, f"--mcu={mcu}", "-w", "-v", str(hex_file)]
    log("$ " + " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    for line in (proc.stdout + proc.stderr).splitlines():
        log(line)
    if proc.returncode != 0:
        raise FirmwareError(f"teensy_loader_cli a échoué (code {proc.returncode})")
