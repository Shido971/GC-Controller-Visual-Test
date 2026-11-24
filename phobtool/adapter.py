"""Lecture de l'adaptateur GameCube officiel (WUP-028) via libusb/pyusb.

Même protocole que Dolphin : on envoie 0x13 sur l'endpoint OUT 0x02, puis
on lit des rapports de 37 octets sur l'endpoint IN 0x81.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

VID, PID = 0x057E, 0x0337
EP_IN, EP_OUT = 0x81, 0x02

BUTTONS1 = {0x01: "A", 0x02: "B", 0x04: "X", 0x08: "Y",
            0x10: "Dl", 0x20: "Dr", 0x40: "Dd", 0x80: "Du"}
BUTTONS2 = {0x01: "S", 0x02: "Z", 0x04: "R", 0x08: "L"}


@dataclass
class PadState:
    connected: bool = False
    wireless: bool = False
    buttons: frozenset = field(default_factory=frozenset)
    ax: int = 128
    ay: int = 128
    cx: int = 128
    cy: int = 128
    l: int = 0
    r: int = 0
    t: float = 0.0      # horodatage de réception (time.perf_counter, secondes)

    def pressed(self, *names: str) -> bool:
        return all(n in self.buttons for n in names)

    # Coordonnées centrées (-128..127), axe Y vers le haut comme sur GameCube
    @property
    def a_xy(self) -> tuple[int, int]:
        return self.ax - 128, self.ay - 128

    @property
    def c_xy(self) -> tuple[int, int]:
        return self.cx - 128, self.cy - 128

    def melee(self, stick: str = "A") -> tuple[float, float]:
        """Coordonnées Melee approximatives (-1..1, pas de 0.0125)."""
        x, y = self.a_xy if stick == "A" else self.c_xy
        def conv(v: int) -> float:
            v = max(-80, min(80, v))
            return round(v * 0.0125, 4)
        return conv(x), conv(y)


def parse_report(data: bytes) -> Optional[list[PadState]]:
    if len(data) < 37 or data[0] != 0x21:
        return None
    pads = []
    for i in range(4):
        p = data[1 + 9 * i: 10 + 9 * i]
        kind = (p[0] >> 4) & 0x3
        if kind == 0:
            pads.append(PadState())
            continue
        btn = {n for m, n in BUTTONS1.items() if p[1] & m} | {n for m, n in BUTTONS2.items() if p[2] & m}
        pads.append(PadState(True, kind == 2, frozenset(btn), p[3], p[4], p[5], p[6], p[7], p[8]))
    return pads


def angle_deg(x: float, y: float) -> float:
    return math.degrees(math.atan2(y, x)) % 360.0


class AdapterError(RuntimeError):
    pass


def _backend():
    """Backend libusb : celui de libusb-package (DLL embarquée sous Windows) si dispo."""
    try:
        import libusb_package  # type: ignore
        return libusb_package.get_libusb1_backend()
    except Exception:
        return None


class AdapterReader:
    """Thread de lecture. `on_state(list[PadState] | None, status_text)` est appelé à ~60 Hz."""

    def __init__(self, on_state: Callable[[Optional[list[PadState]], str], None]):
        self._on_state = on_state
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._dev = None
        self._rumble = [0, 0, 0, 0]
        self._rumble_sent: Optional[list[int]] = None
        self._lock = threading.Lock()

    # -- API ---------------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="gc-adapter", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Libère complètement l'adaptateur (indispensable avant de lancer VCT ou Dolphin)."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._thread = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def set_rumble(self, port: int, on: bool) -> None:
        with self._lock:
            self._rumble[port] = 1 if on else 0

    # -- interne ----------------------------------------------------------
    def _open(self):
        import usb.core  # type: ignore
        import usb.util  # type: ignore
        dev = usb.core.find(idVendor=VID, idProduct=PID, backend=_backend())
        if dev is None:
            return None
        try:
            try:
                if dev.is_kernel_driver_active(0):
                    dev.detach_kernel_driver(0)
            except (NotImplementedError, usb.core.USBError):
                pass
            try:
                dev.set_configuration()
            except usb.core.USBError:
                pass  # déjà configuré
            usb.util.claim_interface(dev, 0)
            try:
                dev.ctrl_transfer(0x21, 11, 0x0001, 0, None, 1000)
            except usb.core.USBError:
                pass
            dev.write(EP_OUT, b"\x13", 1000)
        except usb.core.USBError as e:
            usb.util.dispose_resources(dev)
            raise AdapterError(_explain_usb_error(e)) from e
        return dev

    def _close(self):
        if self._dev is None:
            return
        import usb.util  # type: ignore
        try:
            self._dev.write(EP_OUT, b"\x11\x00\x00\x00\x00", 100)
        except Exception:
            pass
        try:
            usb.util.release_interface(self._dev, 0)
        except Exception:
            pass
        usb.util.dispose_resources(self._dev)
        self._dev = None

    def _run(self) -> None:
        try:
            import usb.core  # type: ignore
        except ImportError:
            self._on_state(None, "pyusb n'est pas installé (pip install pyusb libusb-package)")
            return
        last_err = ""
        while not self._stop.is_set():
            if self._dev is None:
                try:
                    self._dev = self._open()
                    self._rumble_sent = None
                except AdapterError as e:
                    msg = str(e)
                    if msg != last_err:
                        self._on_state(None, msg)
                        last_err = msg
                    self._stop.wait(2.0)
                    continue
                except Exception as e:  # backend absent, etc.
                    msg = f"libusb indisponible : {e}"
                    if msg != last_err:
                        self._on_state(None, msg)
                        last_err = msg
                    self._stop.wait(2.0)
                    continue
                if self._dev is None:
                    if last_err != "absent":
                        self._on_state(None, "Adaptateur GameCube non détecté")
                        last_err = "absent"
                    self._stop.wait(1.0)
                    continue
                last_err = ""
            try:
                data = bytes(self._dev.read(EP_IN, 37, 100))
                now = time.perf_counter()
                pads = parse_report(data)
                if pads is not None:
                    for p in pads:
                        p.t = now
                    self._on_state(pads, "Adaptateur connecté")
                with self._lock:
                    want = list(self._rumble)
                if want != self._rumble_sent:
                    self._dev.write(EP_OUT, bytes([0x11] + want), 100)
                    self._rumble_sent = want
            except usb.core.USBTimeoutError:
                continue
            except usb.core.USBError as e:
                self._close()
                self._on_state(None, f"Adaptateur déconnecté ({e})")
                self._stop.wait(1.0)
        self._close()


def _explain_usb_error(e: Exception) -> str:
    import sys
    s = str(e)
    if "Access denied" in s or "Errno 13" in s or "insufficient permissions" in s.lower():
        if sys.platform.startswith("linux"):
            return ("Accès refusé à l'adaptateur : installe la règle udev fournie "
                    "(packaging/51-gcadapter.rules) puis débranche/rebranche.")
        return "Accès refusé à l'adaptateur."
    if "Entity not found" in s or "not supported" in s.lower() or "Errno 2" in s:
        return ("L'adaptateur n'a pas le pilote WinUSB : lance Zadig, sélectionne "
                "« WUP-028 » et installe WinUSB (comme pour Dolphin).")
    if "Resource busy" in s or "Errno 16" in s:
        return "Adaptateur déjà utilisé par un autre programme (Dolphin, VCT…)."
    return f"Erreur USB : {s}"
