"""Test de snapback, sur le modèle de l'oscilloscope de GTS (greenwave-1/GTS).

Déroulé (identique à GTS) :
* le stick doit d'abord dépasser ±64 sur un axe ;
* on suit la position la plus extrême atteinte ; dès que le stick revient d'au moins
  15 unités vers le centre, l'enregistrement démarre (avec ~25 ms de données avant) ;
* il s'arrête quand le stick est resté 25 ms près du centre (|x|,|y| < 15).
  S'il s'immobilise ailleurs, la mesure est annulée et on attend un nouveau lâcher.

Interprétation : Melee ne prend pas en compte une direction tant que la valeur reste
entre -22 et +22. Un rebond qui dépasse cette zone du côté opposé au lâcher
peut être lu comme un input parasite (dashback, tilt involontaire…).
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Optional

MOVEMENT_THRESHOLD = 15
ORIGIN_TIME_S = 0.025
PREPEND_S = 0.025
TRIGGER_RANGE = 64
MELEE_DEADZONE = 22          # |v| <= 22 : neutre pour Melee
MAX_SAMPLES = 3000
MAX_DURATION_S = 1.5
STILL_CANCEL_S = 0.25        # stick immobile hors du centre : on annule


@dataclass
class Sample:
    t: float      # secondes
    x: int        # -128..127, centre 0
    y: int


@dataclass
class SnapbackResult:
    samples: list[Sample]
    axis: str                 # "x" ou "y" : axe du lâcher (plus grande amplitude, X en cas d'égalité)
    start_value: int          # valeur extrême tenue avant le lâcher, sur cet axe
    min_x: int
    max_x: int
    min_y: int
    max_y: int
    overshoot: int            # rebond le plus fort du côté opposé (valeur signée, 0 si aucun)
    settle_ms: float          # temps entre le début du retour et l'entrée définitive dans ±22
    crossings: int            # nombre de sorties de la zone ±22 du côté opposé
    sample_period_ms: float   # période moyenne entre deux mesures
    t0: float = 0.0           # instant du début du retour (pour l'affichage)

    @property
    def direction(self) -> str:
        if self.axis == "x":
            return "droite" if self.start_value > 0 else "gauche"
        return "haut" if self.start_value > 0 else "bas"

    @property
    def passed(self) -> bool:
        return abs(self.overshoot) <= MELEE_DEADZONE

    def values(self, axis: Optional[str] = None) -> list[int]:
        a = axis or self.axis
        return [s.x if a == "x" else s.y for s in self.samples]


class SnapbackDetector:
    def __init__(self):
        self.history: deque[Sample] = deque(maxlen=400)
        self.reset()

    def reset(self) -> None:
        self.crossed = False
        self.start_x = 0
        self.start_y = 0
        self.recording: Optional[list[Sample]] = None
        self.in_origin_s = 0.0
        self.still_s = 0.0
        self.release_t = 0.0
        self.history.clear()

    @property
    def state(self) -> str:
        if self.recording is not None:
            return "recording"
        return "armed" if self.crossed else "waiting"

    def feed(self, t: float, x: int, y: int) -> Optional[SnapbackResult]:
        s = Sample(t, x, y)
        prev = self.history[-1] if self.history else None
        self.history.append(s)
        dt = (t - prev.t) if prev else 0.0

        if self.recording is not None:
            self.recording.append(s)
            near = abs(x) < MOVEMENT_THRESHOLD and abs(y) < MOVEMENT_THRESHOLD
            self.in_origin_s = self.in_origin_s + dt if near else 0.0
            still = prev is not None and abs(x - prev.x) <= 2 and abs(y - prev.y) <= 2
            self.still_s = self.still_s + dt if (still and not near) else 0.0
            too_long = (len(self.recording) >= MAX_SAMPLES or self.still_s >= STILL_CANCEL_S or
                        t - self.recording[0].t > MAX_DURATION_S)
            if self.in_origin_s >= ORIGIN_TIME_S or too_long:
                if near:
                    res = self._finish()
                    self._rearm()
                    return res
                # le stick est tenu ailleurs : on annule, et on repart de cette position
                self.recording = None
                self.crossed = False
                self.start_x, self.start_y = x, y
            return None

        if not self.crossed:
            if abs(x) > TRIGGER_RANGE or abs(y) > TRIGGER_RANGE:
                self.crossed = True
                self.start_x, self.start_y = x, y
            return None

        grew = False
        if abs(x) > abs(self.start_x):
            self.start_x = x
            grew = True
        if abs(y) > abs(self.start_y):
            self.start_y = y
            grew = True
        if not grew and (abs(x) + MOVEMENT_THRESHOLD <= abs(self.start_x) or
                         abs(y) + MOVEMENT_THRESHOLD <= abs(self.start_y)):
            self.release_t = t
            pre = [h for h in list(self.history)[:-1] if t - h.t <= PREPEND_S]
            self.recording = pre + [s]
            self.in_origin_s = 0.0
            self.still_s = 0.0
        return None

    def _rearm(self) -> None:
        self.recording = None
        self.crossed = False
        self.start_x = self.start_y = 0
        self.in_origin_s = 0.0

    def _finish(self) -> SnapbackResult:
        rec = self.recording or []
        return analyse(rec, self.start_x, self.start_y, self.release_t)


def analyse(rec: list[Sample], start_x: int, start_y: int, release_t: float) -> SnapbackResult:
    xs = [s.x for s in rec]
    ys = [s.y for s in rec]
    max_ax = max((abs(v) for v in xs), default=0)
    max_ay = max((abs(v) for v in ys), default=0)
    axis = "x" if max_ax >= max_ay else "y"
    start = start_x if axis == "x" else start_y
    if start == 0:
        vals = xs if axis == "x" else ys
        start = max(vals, key=abs) if vals else 0
    sign = 1 if start >= 0 else -1
    vals = xs if axis == "x" else ys

    # rebond = valeur la plus extrême du côté opposé au lâcher
    opposite = [v for v in vals if v * sign < 0]
    overshoot = max(opposite, key=abs) if opposite else 0

    # sorties de la zone morte côté opposé
    crossings = 0
    outside = False
    for v in vals:
        o = v * sign < 0 and abs(v) > MELEE_DEADZONE
        if o and not outside:
            crossings += 1
        outside = o

    # stabilisation : dernier échantillon hors ±22 après le début du retour
    last_out_t = release_t
    for s in rec:
        v = s.x if axis == "x" else s.y
        if s.t >= release_t and abs(v) > MELEE_DEADZONE:
            last_out_t = s.t
    settle_ms = max(0.0, (last_out_t - release_t) * 1000)

    periods = [b.t - a.t for a, b in zip(rec, rec[1:]) if b.t > a.t]
    period_ms = (sum(periods) / len(periods) * 1000) if periods else 0.0

    return SnapbackResult(
        samples=rec, axis=axis, start_value=start,
        min_x=min(xs, default=0), max_x=max(xs, default=0),
        min_y=min(ys, default=0), max_y=max(ys, default=0),
        overshoot=overshoot, settle_ms=settle_ms, crossings=crossings,
        sample_period_ms=period_ms, t0=release_t,
    )


class RateMeter:
    """Mesure la fréquence réelle des rapports de l'adaptateur."""

    def __init__(self, window: int = 250):
        self.ts: deque[float] = deque(maxlen=window)

    def tick(self, t: float) -> None:
        if not self.ts or t > self.ts[-1]:
            self.ts.append(t)

    @property
    def hz(self) -> float:
        if len(self.ts) < 10:
            return 0.0
        span = self.ts[-1] - self.ts[0]
        return (len(self.ts) - 1) / span if span > 0 else 0.0


def simulate_release(start: float = 100.0, axis: str = "x", overshoot: float = 0.35,
                     freq_hz: float = 70.0, decay_ms: float = 12.0, rate_hz: float = 1000.0,
                     hold_ms: float = 60.0, after_ms: float = 120.0, t0: float = 0.0) -> list[Sample]:
    """Lâcher de stick synthétique (oscillation amortie) – pour tests et démo."""
    out = []
    dt = 1.0 / rate_hz
    n_hold = int(hold_ms / 1000 * rate_hz)
    n_after = int(after_ms / 1000 * rate_hz)
    t = t0
    for _ in range(n_hold):
        v = int(round(start))
        out.append(Sample(t, v if axis == "x" else 0, v if axis == "y" else 0))
        t += dt
    # descente rapide (~3 ms) puis oscillation amortie autour de 0
    for i in range(n_after):
        tau = i * dt * 1000
        fall = max(0.0, 1 - tau / 3.0)
        osc = -overshoot * start * math.exp(-tau / decay_ms) * math.sin(2 * math.pi * freq_hz * (tau / 1000))
        v = int(round(start * fall + (0 if fall > 0 else osc)))
        out.append(Sample(t, v if axis == "x" else 0, v if axis == "y" else 0))
        t += dt
    return out
