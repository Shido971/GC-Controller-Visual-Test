"""Récupération des releases PhobGCC-SW sur GitHub."""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import __version__
from .paths import firmware_cache_dir

REPO = "PhobGCC/PhobGCC-SW"
API_URL = f"https://api.github.com/repos/{REPO}/releases"
USER_AGENT = f"PhobGCC-Tool/{__version__}"

# Cibles matérielles
BOARD_RP2040 = "rp2040"        # PhobGCC 2.x (Raspberry Pi RP2040) -> .uf2
BOARD_TEENSY40 = "teensy40"    # PhobGCC 1.1/1.2 sur Teensy 4.0 -> .hex
BOARD_TEENSY32 = "teensy32"    # PhobGCC 1.0/1.1 sur Teensy 3.2 -> .hex
BOARD_UNKNOWN = "unknown"

BOARD_LABELS = {
    BOARD_RP2040: "PhobGCC 2.x (RP2040, .uf2)",
    BOARD_TEENSY40: "PhobGCC 1.x – Teensy 4.0 (.hex)",
    BOARD_TEENSY32: "PhobGCC 1.x – Teensy 3.2 (.hex)",
    BOARD_UNKNOWN: "Autre fichier",
}


@dataclass
class Asset:
    name: str
    url: str
    size: int
    sha256: Optional[str] = None
    board: str = BOARD_UNKNOWN

    @property
    def is_firmware(self) -> bool:
        return self.name.lower().endswith((".uf2", ".hex"))


@dataclass
class Release:
    tag: str
    name: str
    published_at: str
    prerelease: bool
    body: str
    html_url: str
    assets: list[Asset] = field(default_factory=list)

    def firmware_for(self, board: str) -> Optional[Asset]:
        for a in self.assets:
            if a.board == board:
                return a
        return None

    @property
    def firmware_assets(self) -> list[Asset]:
        return [a for a in self.assets if a.is_firmware]


def classify_asset(name: str) -> str:
    n = name.lower()
    if n.endswith(".uf2"):
        return BOARD_RP2040
    if n.endswith(".hex"):
        m = re.search(r"teensy[^0-9]*([34])[^0-9]?([0-9])", n)
        if m and m.group(1) == "3":
            return BOARD_TEENSY32
        return BOARD_TEENSY40
    return BOARD_UNKNOWN


def parse_releases(data: list[dict]) -> list[Release]:
    out: list[Release] = []
    for r in data:
        if r.get("draft"):
            continue
        assets = []
        for a in r.get("assets", []):
            digest = a.get("digest") or ""
            sha = digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else None
            assets.append(Asset(
                name=a["name"],
                url=a["browser_download_url"],
                size=int(a.get("size", 0)),
                sha256=sha,
                board=classify_asset(a["name"]),
            ))
        out.append(Release(
            tag=r.get("tag_name", ""),
            name=r.get("name") or r.get("tag_name", ""),
            published_at=(r.get("published_at") or "")[:10],
            prerelease=bool(r.get("prerelease")),
            body=r.get("body") or "",
            html_url=r.get("html_url", ""),
            assets=assets,
        ))
    return out


def _request(url: str, accept: str = "application/vnd.github+json") -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})


def fetch_releases(per_page: int = 15, timeout: float = 15.0) -> list[Release]:
    """Interroge l'API GitHub. Met en cache la dernière réponse pour le mode hors-ligne."""
    cache = firmware_cache_dir() / "releases.json"
    try:
        with urllib.request.urlopen(_request(f"{API_URL}?per_page={per_page}"), timeout=timeout) as resp:
            raw = resp.read()
        data = json.loads(raw)
        if not isinstance(data, list):
            raise RuntimeError(data.get("message", "réponse inattendue de GitHub"))
        cache.write_bytes(raw)
    except Exception:
        if cache.exists():
            data = json.loads(cache.read_bytes())
        else:
            raise
    return parse_releases(data)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


class ChecksumError(RuntimeError):
    pass


def download_asset(asset: Asset, tag: str,
                   progress: Optional[Callable[[int, int], None]] = None,
                   cancelled: Optional[Callable[[], bool]] = None,
                   timeout: float = 30.0) -> Path:
    """Télécharge (ou réutilise depuis le cache) un fichier de release, vérifie le SHA-256."""
    dest_dir = firmware_cache_dir() / tag
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / asset.name

    if dest.exists() and dest.stat().st_size == asset.size and asset.size > 0:
        if not asset.sha256 or sha256_file(dest) == asset.sha256:
            if progress:
                progress(asset.size, asset.size)
            return dest

    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(_request(asset.url, "application/octet-stream"), timeout=timeout) as resp:
        total = int(resp.headers.get("Content-Length") or asset.size or 0)
        done = 0
        with open(tmp, "wb") as f:
            while True:
                if cancelled and cancelled():
                    raise InterruptedError("téléchargement annulé")
                chunk = resp.read(1 << 15)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)

    if asset.sha256:
        got = sha256_file(tmp)
        if got != asset.sha256:
            tmp.unlink(missing_ok=True)
            raise ChecksumError(f"SHA-256 incorrect pour {asset.name}\n attendu {asset.sha256}\n obtenu  {got}")
    tmp.replace(dest)
    return dest
